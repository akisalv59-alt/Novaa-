'use strict';
const el=id=>document.getElementById(id);
const repo='https://api.github.com/repos/akisalv59-alt/Novaa-';
const catalog=repo+'/contents/catalog.json';
let token='',sha='',items=[];
const headers=()=>({Authorization:'Bearer '+token,Accept:'application/vnd.github+json'});
function choose(){
  const item=items.find(p=>p.id===+el('pick').value);
  el('edit').reset();
  for(const field of ['name','category','description','image'])el(field).value=item?.[field]||'';
  el('price').value=item?(item.price_cents/100).toFixed(2):'';
  el('details').value=(item?.details||[]).join('\n');el('visible').checked=item?.visible!==false;
}
function populate(selected){
  el('pick').replaceChildren(...items.map(p=>new Option(p.name,p.id)),new Option('Ajouter un produit','new'));
  if(selected)el('pick').value=selected;choose();
}
el('login').onsubmit=async e=>{
  e.preventDefault();token=el('token').value.trim();el('token').value='';el('status').textContent='Vérification…';
  try{
    const account=await fetch(repo,{headers:headers(),cache:'no-store'});if(!account.ok||!(await account.json()).permissions?.push)throw Error();
    const r=await fetch(catalog+'?ref=main',{headers:headers(),cache:'no-store'});if(!r.ok)throw Error();
    const f=await r.json();sha=f.sha;items=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(f.content),c=>c.charCodeAt(0))));
    populate();el('login').hidden=true;el('editor').hidden=false;el('status').textContent='';
  }catch{token='';el('status').textContent='Connexion refusée. Vérifiez le dépôt et les droits du jeton.';}
};
el('pick').onchange=choose;el('logout').onclick=()=>location.reload();
el('edit').onsubmit=async e=>{
  e.preventDefault();const submit=e.submitter;if(submit.disabled)return;submit.disabled=true;
  try{
    const name=el('name').value.trim(),category=el('category').value.trim(),description=el('description').value.trim();
    if(!name||!category||!description)throw Error('Renseignez le nom, la catégorie et la description.');
    const old=items.find(p=>p.id===+el('pick').value);
    if(!old&&!el('image').value)throw Error('Ajoutez une photo autorisée pour le nouveau produit.');
    const id=old?.id??Math.max(0,...items.map(p=>p.id))+1;
    const updated={...old,id,slug:old?.slug||'objet-'+id,name,category,description,price_cents:Math.round(Number(el('price').value)*100),details:el('details').value.split('\n').map(x=>x.trim()).filter(Boolean),image:el('image').value.trim(),visible:el('visible').checked};
    const next=old?items.map(p=>p.id===id?updated:p):[...items,updated];
    const bytes=new TextEncoder().encode(JSON.stringify(next,null,2)+'\n');
    const r=await fetch(catalog,{method:'PUT',headers:{...headers(),'Content-Type':'application/json'},body:JSON.stringify({branch:'main',message:'Mettre à jour le catalogue NOVA',sha,content:btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''))})});
    if(!r.ok)throw Error(r.status===409?'Le catalogue a changé. Reconnectez-vous pour charger la dernière version.':'Publication refusée par GitHub. Vérifiez le droit Contents en écriture.');
    sha=(await r.json()).content.sha;items=next;populate(id);el('status').textContent='Fiche enregistrée sur GitHub. Render déploie le catalogue.';
  }catch(err){el('status').textContent=err.message;}finally{submit.disabled=false;}
};
