document.querySelectorAll('[data-order]').forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{
    const response=await fetch('/admin/ventes/'+button.dataset.order,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:button.dataset.state})});
    if(!response.ok)throw Error();location.reload();
  }catch{document.querySelector('#status').textContent='Modification impossible. Rechargez la liste.';button.disabled=false;}
});
