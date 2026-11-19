(() => {
 'use strict';
 const form=document.getElementById('expense-form');if(!form)return;
 const photo=document.getElementById('expense-photo'),status=document.getElementById('expense-status'),reply=document.getElementById('expense-reply'),button=form.querySelector('button'),history=document.getElementById('expense-history');
 let csrf='',busy=false,preview=null;
 async function api(data){
  const response=await fetch('/__expenses',{credentials:'same-origin',cache:'no-store',...(data?{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)}:{})});
  const value=await response.json();if(!response.ok)throw new Error(value.error||'No se pudo completar la solicitud.');return value;
 }
 function drawHistory(rows){
  history.replaceChildren();if(!rows.length){history.textContent='Aún no has preparado gastos con fotos.';return;}
  for(const row of rows){const div=document.createElement('div');div.className='expense-entry';const text=document.createElement('span');text.textContent=row.comprobante+' · '+row.moneda+' '+Number(row.total).toFixed(2)+' · '+(row.estado==='draft'?'Borrador':row.estado);
   const a=document.createElement('a');a.textContent='Revisar gasto';a.href='/odoo/vendor-bills/'+Number(row.id);div.append(text,a);history.append(div);}
 }
 async function load(){const value=await api();if(!value.enabled)throw new Error('Esta función requiere permiso de contabilidad.');csrf=value.csrf_token;drawHistory(value.history||[]);button.disabled=false;status.textContent='Lista para preparar un borrador.';}
 photo.addEventListener('change',()=>{const file=photo.files[0],img=document.getElementById('expense-preview');if(preview)URL.revokeObjectURL(preview);img.hidden=true;if(file){preview=URL.createObjectURL(file);img.src=preview;img.hidden=false;}});
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;const file=photo.files[0];if(!file)return;
  if(!['image/jpeg','image/png'].includes(file.type)||file.size>2000000){status.textContent='Usa una foto JPEG o PNG de hasta 2 MB.';return;}
  busy=true;button.disabled=true;status.textContent='Jenifer está leyendo la factura y comprobando el borrador…';reply.replaceChildren();
  try{const image=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});
   const result=await api({filename:file.name,image,message:document.getElementById('expense-message').value});
   reply.textContent=result.reply;
   if(result.draft){const a=document.createElement('a');a.textContent='Abrir borrador para revisión';a.className='ux-button';a.href='/odoo/vendor-bills/'+Number(result.draft.id);reply.append(document.createElement('br'),a);}
   status.textContent=result.draft?'Listo. No se confirmó ni se pagó la factura.':'Revisa el mensaje de Jenifer y completa lo que falta.';
   drawHistory(result.history||[]);
  }catch(error){status.textContent=error.message||'No se pudo completar. Antes de repetir, revisa tus gastos preparados.';}
  finally{busy=false;button.disabled=false;}
 });
 load().catch(error=>{status.textContent=error.message;button.disabled=true;});
})();
