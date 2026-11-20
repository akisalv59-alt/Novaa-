from pathlib import Path

import json
from uuid import UUID
import checkout
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent

app = FastAPI(title='NOVA STORE API', version='4.0.0')
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
templates = Jinja2Templates(directory=BASE / 'templates')
PRODUCTS = [p for p in json.loads((BASE / 'catalog.json').read_text(encoding='utf-8')) if p.get('visible', True)]
BY_ID = {p['id']:p for p in PRODUCTS}
BY_SLUG = {p['slug']:p for p in PRODUCTS}

app.include_router(checkout.router)
app.router.add_event_handler('startup', checkout.initialize)

class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=10)

class CartRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=20)

def calculate(items):
    totals = {}
    for item in items:
        if item.product_id not in BY_ID:
            raise HTTPException(400, 'Produit inconnu')
        totals[item.product_id] = totals.get(item.product_id, 0) + item.quantity
    if sum(totals.values()) > 20 or any(q > 10 for q in totals.values()):
        raise HTTPException(400, 'Limite : 10 unités par produit et 20 au total')
    lines = [{'product_id':pid,'name':BY_ID[pid]['name'],'quantity':qty,'unit_price_cents':BY_ID[pid]['price_cents'],'line_total_cents':qty*BY_ID[pid]['price_cents']} for pid,qty in totals.items()]
    return {'currency':'EUR','items':lines,'subtotal_cents':sum(x['line_total_cents'] for x in lines),'shipping_cents':checkout.SHIPPING,'total_cents':sum(x['line_total_cents'] for x in lines)+checkout.SHIPPING,'checkout_enabled':checkout.configured(),'message':'Simulation France uniquement. Aucun débit réel.'}

@app.get('/', response_class=HTMLResponse)
def home(request:Request):
    return templates.TemplateResponse(request=request,name='index.html',context={'products':PRODUCTS})

@app.get('/products/{slug}',response_class=HTMLResponse)
def product_page(request:Request,slug:str):
    p = BY_SLUG.get(slug)
    if not p: raise HTTPException(404,'Produit introuvable')
    return templates.TemplateResponse(request=request,name='product.html',context={'product':p})

@app.get('/api/products')
def list_products(category:str|None=None,q:str|None=None,sort:str='featured'):
    result = [p for p in PRODUCTS if (not category or category.lower()=='tous' or p['category'].lower()==category.lower()) and (not q or q.lower() in (p['name']+' '+p['description']).lower())]
    if sort=='price_asc': result.sort(key=lambda p:p['price_cents'])
    elif sort=='price_desc': result.sort(key=lambda p:p['price_cents'],reverse=True)
    elif sort!='featured': raise HTTPException(400,'Tri invalide')
    return result

@app.get('/api/products/{product_id}')
def get_product(product_id:int):
    if product_id not in BY_ID: raise HTTPException(404,'Produit introuvable')
    return BY_ID[product_id]

@app.post('/api/cart/quote')
def quote(cart:CartRequest):
    return calculate(cart.items)

class CheckoutRequest(CartRequest):
    attempt:UUID

@app.post('/api/checkout')
def start_checkout(cart:CheckoutRequest,request:Request):
    return checkout.session_for(cart.attempt,calculate(cart.items),request.client.host if request.client else 'unknown')

@app.get('/commande/{result}',response_class=HTMLResponse)
def receipt(request:Request,result:str,session_id:str=''):
    if result not in ('confirmation','annulation'):raise HTTPException(404)
    confirmed=False
    if result=='confirmation' and session_id.startswith('cs_test_') and len(session_id)<256 and checkout.configured():
        with checkout.database() as con:
            row=con.execute('SELECT state FROM checkout_orders WHERE session_id=%s',(session_id,)).fetchone()
            confirmed=bool(row and row['state'] in ('paid','shipped','delivered'))
    return templates.TemplateResponse(request=request,name='receipt.html',context={'cancelled':result=='annulation','confirmed':confirmed},headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

@app.get('/api/status')
def status():
    return {'version':'4.0.0','mode':'test','test_checkout_configured':checkout.configured(),'payment_enabled':False,'fulfillment_enabled':False,'products':len(PRODUCTS)}

@app.get('/admin', response_class=HTMLResponse)
def admin(request: Request):
    response = templates.TemplateResponse(request=request, name='admin.html', context={})
    response.headers.update({
        'Cache-Control': 'no-store',
        'Referrer-Policy': 'no-referrer',
        'X-Frame-Options': 'DENY',
        'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src https://api.github.com; img-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
    })
    return response
