"""Test-mode Stripe checkout. All amounts are in euro cents."""
import hashlib
import hmac
import json
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

router = APIRouter()
BASE_URL = "https://novaa-9d3w.onrender.com"
SHIPPING = 490  # Simulation France, never used to take live payments.
SCHEMA = """
CREATE TABLE IF NOT EXISTS checkout_orders (
    id uuid PRIMARY KEY, fingerprint text NOT NULL, items jsonb NOT NULL,
    subtotal integer NOT NULL, shipping integer NOT NULL,
    state text NOT NULL DEFAULT 'pending', created timestamptz NOT NULL DEFAULT now(),
    session_id text UNIQUE, intent text UNIQUE, checkout_url text,
    refunded integer NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checkout_events (id text PRIMARY KEY, created timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS checkout_limits (bucket text PRIMARY KEY, hits integer NOT NULL, expires timestamptz NOT NULL);
"""
LABELS = {'pending':'En attente', 'paid':'Payée', 'shipped':'Expédiée', 'delivered':'Livrée', 'refunded':'Remboursée'}

def configured():
    return bool(os.getenv('STRIPE_SECRET_KEY','').startswith(('sk_test_', 'rk_test_'))
                and os.getenv('STRIPE_WEBHOOK_SECRET','').startswith('whsec_') and os.getenv('DATABASE_URL'))

def api_key():
    if not configured():
        raise HTTPException(503, 'Le paiement de test est en cours de configuration.')
    return os.environ['STRIPE_SECRET_KEY']

@contextmanager
def database():
    url = os.getenv('DATABASE_URL')
    if not url:
        raise HTTPException(503, 'Base de commandes indisponible.')
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=6) as con:
        yield con

def initialize():
    if os.getenv('DATABASE_URL'):
        with database() as con:
            con.execute(SCHEMA)

def session_for(order_id, quote, client):
    key = api_key()
    lines = sorted(quote['items'], key=lambda p:p['product_id'])
    fingerprint = hashlib.sha256(json.dumps(lines,sort_keys=True).encode()).hexdigest()
    with database() as con:
        created = con.execute('INSERT INTO checkout_orders(id,fingerprint,items,subtotal,shipping) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id',
            (order_id,fingerprint,json.dumps(lines),quote['subtotal_cents'],SHIPPING)).fetchone()
        row = con.execute('SELECT * FROM checkout_orders WHERE id=%s FOR UPDATE',(order_id,)).fetchone()
        if row['fingerprint'] != fingerprint:
            raise HTTPException(409,'Le panier a changé.')
        if row['state'] != 'pending' or row['created'] < datetime.now(timezone.utc)-timedelta(hours=1):
            raise HTTPException(409,'Cette tentative est terminée. Ouvrez une nouvelle session.')
        if not row['checkout_url'] and row['created'] < datetime.now(timezone.utc)-timedelta(minutes=25):
            raise HTTPException(409,'Tentative expirée.')
        if row['checkout_url']:
            return {'url':row['checkout_url']}
        if created:
            bucket = hmac.new(key.encode(),client.encode(),'sha256').hexdigest()
            con.execute('DELETE FROM checkout_limits WHERE expires < now()')
            hits = con.execute("INSERT INTO checkout_limits VALUES(%s,1,now()+interval '10 minutes') ON CONFLICT(bucket) DO UPDATE SET hits=checkout_limits.hits+1 RETURNING hits",(bucket,)).fetchone()['hits']
            if hits>25: raise HTTPException(429,'Trop de tentatives. Réessayez plus tard.')
    # Commit the reservation before contacting Stripe. Concurrent retries use the same key.
    try:
        session = stripe.checkout.Session.create(
            expires_at=int(row['created'].timestamp())+3600,
            api_key=key, idempotency_key='nova-test-'+str(order_id), mode='payment',
            payment_method_types=['card'], client_reference_id=str(order_id),
            metadata={'nova_order':str(order_id)},payment_intent_data={'metadata':{'nova_order':str(order_id)}},
            line_items=[{'price_data':{'currency':'eur','unit_amount':x['unit_price_cents'],'product_data':{'name':x['name']}},'quantity':x['quantity']} for x in lines],
            shipping_address_collection={'allowed_countries':['FR']},
            shipping_options=[{'shipping_rate_data':{'type':'fixed_amount','display_name':'Livraison France · simulation','fixed_amount':{'amount':SHIPPING,'currency':'eur'}}}],
            success_url=BASE_URL+'/commande/confirmation?session_id={CHECKOUT_SESSION_ID}',cancel_url=BASE_URL+'/commande/annulation')
    except stripe.StripeError:
        raise HTTPException(503,'Stripe est temporairement indisponible.')
    if session.livemode or not session.id.startswith('cs_test_'):
        raise HTTPException(502,'Session de test attendue.')
    with database() as con:
        con.execute('UPDATE checkout_orders SET session_id=%s,checkout_url=%s WHERE id=%s',(session.id,session.url,order_id))
    return {'url':session.url}

def reconcile(event):
    obj=event['data']['object']
    typ=event['type']
    if typ not in {'checkout.session.completed','checkout.session.async_payment_succeeded','charge.refunded'}:return
    if obj.get('livemode') is not False:return
    ref=(obj.get('metadata') or {}).get('nova_order')
    if not ref:return
    try: order_id=UUID(ref)
    except (TypeError,ValueError):return
    with database() as con:
        if not con.execute('INSERT INTO checkout_events(id) VALUES(%s) ON CONFLICT DO NOTHING RETURNING id',(event['id'],)).fetchone():return
        row=con.execute('SELECT * FROM checkout_orders WHERE id=%s FOR UPDATE',(order_id,)).fetchone()
        if not row:return
        if obj.get('currency')!='eur':return
        total=row['subtotal']+row['shipping']
        if typ=='charge.refunded':
            if row['intent'] is None: raise HTTPException(503,'Confirmation de paiement attendue.')
            if obj.get('payment_intent')!=row['intent'] or obj.get('amount')!=total:return
            refunded=min(total,max(row['refunded'],int(obj['amount_refunded'])))
            con.execute('UPDATE checkout_orders SET refunded=%s,state=%s WHERE id=%s',(refunded,'refunded' if refunded==total else row['state'],order_id))
        elif obj.get('payment_status')=='paid' and obj.get('mode')=='payment' and obj.get('amount_total')==total and obj.get('client_reference_id')==str(order_id):
            if not row['session_id']:raise HTTPException(503,'Session en cours de sauvegarde.')
            if obj['id']==row['session_id'] and obj.get('payment_intent') and row['state']=='pending':
                con.execute("UPDATE checkout_orders SET state='paid',intent=%s WHERE id=%s",(obj['payment_intent'],order_id))

@router.post('/api/stripe/webhook',include_in_schema=False)
async def webhook(request:Request):
    api_key()
    payload=bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload)>512000:raise HTTPException(413)
    try:
        event=stripe.Webhook.construct_event(bytes(payload),request.headers.get('stripe-signature',''),os.environ['STRIPE_WEBHOOK_SECRET'],tolerance=300)
    except (ValueError,stripe.SignatureVerificationError):
        raise HTTPException(400,'Signature Stripe invalide.')
    if event['livemode'] is False:await run_in_threadpool(reconcile,event)
    return {'received':True}

def admin(credentials:HTTPBasicCredentials=Depends(HTTPBasic())):
    expected=os.getenv('SALES_ADMIN_PASSWORD','')
    if len(expected)<20 or not(secrets.compare_digest(credentials.username.encode(),b'nova') and secrets.compare_digest(credentials.password.encode(),expected.encode())):
        raise HTTPException(401,'Connexion requise.',headers={'WWW-Authenticate':'Basic realm="Ventes NOVA"'})

class Transition(BaseModel):
    state:str

@router.patch('/admin/ventes/{order_id}',dependencies=[Depends(admin)])
def advance(order_id:UUID, data:Transition, request:Request):
    if request.headers.get('origin')!=BASE_URL:raise HTTPException(403)
    previous={'shipped':'paid','delivered':'shipped'}.get(data.state)
    if not previous:raise HTTPException(400,'Transition invalide.')
    with database() as con:
        if not con.execute('UPDATE checkout_orders SET state=%s WHERE id=%s AND state=%s RETURNING id',(data.state,order_id,previous)).fetchone():
            raise HTTPException(409,'Le statut a changé.')
    return {'state':data.state}

@router.get('/admin/ventes',dependencies=[Depends(admin)],response_class=HTMLResponse)
def sales(request:Request,page:int=1):
    from main import templates
    page=max(1,page)
    with database() as con:
        rows=con.execute('SELECT * FROM checkout_orders ORDER BY created DESC,id LIMIT 31 OFFSET %s',(30*(page-1),)).fetchall()
    return templates.TemplateResponse(request=request,name='sales.html',context={'orders':rows[:30],'labels':LABELS,'page':page,'more':len(rows)>30},headers={'Cache-Control':'no-store','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer'})
