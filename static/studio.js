'use strict';
const byId = id => document.getElementById(id);
const money = cents => (cents / 100).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});
const norm = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const bag = byId('bag'), key = 'nova_cart_v3';
let products = [], cart = {}, ready = false, saving = false;
function node(tag, value, cls) {
  const el = document.createElement(tag);
  if (value !== undefined) el.textContent = value;
  if (cls) el.className = cls;
  return el;
}
function readCart() {
  cart = {};
  try {
    let total = 0;
    for (const [id,n] of Object.entries(JSON.parse(localStorage.getItem(key) || '{}'))) {
      if (products.some(p => p.id === +id) && Number.isInteger(n) && n > 0 && n <= 10 && total+n <= 20) {cart[id]=n;total+=n;}
    }
  } catch {}
}
function change(id, delta) {
  if (!ready || saving) return;
  const next = (cart[id] || 0) + delta;
  if (next > 10 || Object.values(cart).reduce((a,b)=>a+b,0)+delta > 20) {
    byId('feedback').textContent='Limite de 10 unités par objet et de 20 au total.';return;
  }
  if (next>0) cart[id]=next; else delete cart[id];
  try {localStorage.setItem(key,JSON.stringify(cart));} catch {}
  byId('feedback').textContent='';render();
}
function render() {
  const lines=byId('lines');lines.replaceChildren();let total=0,count=0;
  for (const p of products) {
    const n=cart[p.id];if(!n)continue;
    const row=node('div',undefined,'cart-line'),img=node('img'),info=node('div'),step=node('div',undefined,'stepper');
    img.alt='';img.src=p.image||'/static/'+p.slug+'.jpg';
    const minus=node('button','−'),plus=node('button','+');
    minus.ariaLabel='Retirer un '+p.name;plus.ariaLabel='Ajouter un '+p.name;
    minus.onclick=()=>change(p.id,-1);plus.onclick=()=>change(p.id,1);
    step.append(minus,node('span',n),plus);info.append(node('strong',p.name),step);
    row.append(img,info,node('span',money(n*p.price_cents)));lines.append(row);total+=n*p.price_cents;count+=n;
  }
  if(!count)lines.append(node('p',ready?'Votre panier est vide.':'Chargement du catalogue…'));
  byId('qty').textContent=count;byId('total').textContent=money(total);byId('draft').disabled=!count||saving;
}
function openBag(){if(!bag.open)bag.showModal();}
byId('bag-open').onclick=openBag;byId('bag-close').onclick=()=>bag.close();
document.querySelectorAll('[data-add]').forEach(btn=>{btn.disabled=true;btn.onclick=()=>{openBag();change(+btn.dataset.add,1);};});
byId('menu-toggle').onclick=e=>{const open=byId('nav').classList.toggle('open');e.currentTarget.setAttribute('aria-expanded',open);};
byId('nav').onclick=()=>{byId('nav').classList.remove('open');byId('menu-toggle').setAttribute('aria-expanded','false');};
async function init(){
  try {const r=await fetch('/api/products');if(!r.ok)throw Error();products=await r.json();ready=true;readCart();render();document.querySelectorAll('[data-add]').forEach(b=>b.disabled=false);}
  catch {byId('lines').textContent='Catalogue indisponible. Rechargez la page.';}
}
window.addEventListener('storage',e=>{if(e.key===key&&ready){readCart();render();}});
byId('draft').onclick=async()=>{
  if(saving)return;saving=true;render();byId('feedback').textContent='Enregistrement…';
  try {const r=await fetch('/api/orders/demo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:Object.entries(cart).map(([id,quantity])=>({product_id:+id,quantity}))})});
    if(!r.ok)throw Error();const data=await r.json();byId('feedback').textContent='Brouillon enregistré · '+data.order_id;
  }catch{byId('feedback').textContent='Enregistrement impossible. Réessayez.';}finally{saving=false;render();}
};
if(byId('grid')){
  const cards=Array.from(byId('grid').children);let category='';
  function filter(){
    const q=norm(byId('search').value.trim()),sort=byId('sort').value;let shown=0;
    const ordered=cards.slice();if(sort!=='featured')ordered.sort((a,b)=>(+a.dataset.price-+b.dataset.price)*(sort==='asc'?1:-1));
    ordered.forEach(c=>{c.hidden=!!((category&&c.dataset.category!==category)||!norm(c.dataset.name).includes(q));if(!c.hidden)shown++;byId('grid').append(c);});
    byId('count').textContent=shown+' objet'+(shown>1?'s':'');byId('empty').hidden=shown!==0;
  }
  document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{category=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',x===b));filter();});
  byId('search').oninput=filter;byId('sort').onchange=filter;
}
init();
