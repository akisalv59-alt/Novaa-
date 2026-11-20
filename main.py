from pathlib import Path
from contextlib import contextmanager
import sqlite3, json, secrets
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
DB = BASE / 'store.db'
app = FastAPI(title='NOVA STORE API', version='4.0.0')
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
templates = Jinja2Templates(directory=BASE / 'templates')
PRODUCTS = [p for p in json.loads((BASE / 'catalog.json').read_text(encoding='utf-8')) if p.get('visible', True)]
BY_ID = {p['id']:p for p in PRODUCTS}
BY_SLUG = {p['slug']:p for p in PRODUCTS}

@contextmanager
def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.execute('CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, status TEXT NOT NULL, total_cents INTEGER NOT NULL, items_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')

init_db()

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
    return {'currency':'EUR','items':lines,'subtotal_cents':sum(x['line_total_cents'] for x in lines),'shipping_cents':None,'total_cents':None,'checkout_enabled':False,'message':'Frais de livraison et fiscalité à déterminer. Aucun paiement réel disponible.'}

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

@app.post('/api/orders/demo',status_code=201)
def create_demo_order(cart:CartRequest):
    result = calculate(cart.items)
    oid = 'DEMO-'+secrets.token_hex(6).upper()
    with connect() as con:
        con.execute('INSERT INTO orders (id,status,total_cents,items_json) VALUES (?,?,?,?)',(oid,'draft_demo',result['subtotal_cents'],json.dumps(result['items'])))
    return {'order_id':oid,'status':'draft_demo','subtotal_cents':result['subtotal_cents'],'message':'Brouillon enregistré localement. Aucune vente, aucun paiement ni livraison.'}

@app.get('/api/status')
def status():
    return {'version':'4.0.0','mode':'demo','payment_enabled':False,'fulfillment_enabled':False,'products':len(PRODUCTS)}

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
