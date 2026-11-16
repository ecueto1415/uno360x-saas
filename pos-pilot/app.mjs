import {money,totals,margin} from './domain.mjs';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modes={Mesas:'Mesas',Caja:'Caja',Cocina:'Cocina',Barra:'Barra',Inventario:'Inventario y mermas',Reportes:'Reportes y cierre de caja',Menú:'Menú y recetas'};
let mode='Caja',state,summary,selected,locked=false,formData,category='',query='',stationPoll;
const cash=v=>Math.round(Number(v)*100);
const picked=()=>state.orders.find(o=>o.id===selected);
const orderName=o=>o.service==='mesa'?'Mesa '+String(o.table).padStart(2,'0'):o.service==='barra'?'Barra':'Para llevar';
const title=l=>esc(l.name);
const action=(name,label,value='',style='')=>'<button type="button" class="'+style+'" data-action="'+name+'" data-value="'+esc(value)+'">'+label+'</button>';
const panel=(label,content)=>'<section class="panel"><h2>'+label+'</h2>'+content+'</section>';
const form=(type,content)=>'<form data-command="'+type+'">'+content+'<button class="primary" type="submit">'+({open:'Abrir turno',add:'Añadir a la cuenta',pay:'Registrar pago',product:'Guardar producto',order:'Abrir pedido',close:'Confirmar cierre',waste:'Registrar merma',count:'Guardar conteo',void:'Autorizar anulación',discount:'Autorizar descuento'}[type]||'Guardar')+'</button></form>';
const input=(name,label,type='text',extra='')=>'<label>'+label+'<input name="'+name+'" type="'+type+'" '+extra+'></label>';
const options=(entries,chosen)=>entries.map(([v,t])=>'<option value="'+esc(v)+'" '+(v===chosen?'selected':'')+'>'+esc(t)+'</option>').join('');
const select=(name,label,entries,chosen)=>'<label>'+label+'<select name="'+name+'">'+options(entries,chosen)+'</select></label>';
const line=(label,value,cls='item')=>'<div class="'+cls+'"><span>'+label+'</span><strong>'+value+'</strong></div>';
const prices=(t)=>line('Subtotal',money(t.subtotal))+line('ITBIS',money(t.tax))+line('Propina legal',money(t.tip))+line('Total',money(t.total),'total');
function flash(t,error=false){$('#status').className=error?'error':'';$('#status').textContent=t;}
function modal(title,html,data={}){
 formData=data;$('#modal-content').innerHTML='<h2>'+title+'</h2>'+html+'<div class="space">'+action('dismiss','Cancelar')+'</div>';
 if(!$('#modal').open)$('#modal').showModal();
}
async function refresh(renderNow=true){
 const res=await fetch('/api/state');
 const data=await res.json();if(!res.ok)throw new Error(data.error);
 ({state,summary}=data);
 if(data.connected){
  $('.rail-foot').hidden=true;
  $('#role').value=data.connected.role;
  $('header p').textContent='UNO360X POS / '+data.connected.branchName;
 }
 if(renderNow)render();
}
function switchTo(next){mode=next;render();}
function render(){
 $('#nav').innerHTML=Object.keys(modes).map(n=>action('nav',n,n,n===mode?'active':'')).join('');
 $('#title').textContent=modes[mode];
 $('#view').innerHTML=({Mesas:tables,Caja:register,Cocina:()=>station('cocina'),Barra:()=>station('barra'),Inventario:inventory,Reportes:reports,Menú:menu})[mode]();
}
function tables(){
 const active=state.orders.filter(o=>!o.closed);
 return '<div class="layout">'+panel('Salón principal','<div class="grid">'+Array.from({length:9},(_,i)=>{
  const n=i+1,o=active.find(o=>o.table===n);
  return action('table','Mesa '+String(n).padStart(2,'0')+'<br><small>'+(o?o.people+' personas · En servicio':'Libre')+'</small>',n,o?'selected':'');
 }).join('')+'</div>')+panel('Otros servicios',action('new','Para llevar','llevar')+' '+action('new','Pedido en barra','barra')+
 active.filter(o=>!o.table).map(o=>line(orderName(o)+' #'+o.number,action('pick','Abrir',o.id))).join(''))+'</div>';
}
function register(){
 if(!state.shift||state.shift.closed)return '<div class="layout">'+panel('Caja 01',line('Estado','Cerrada')+line('Sucursal','Centro'))+panel('Apertura de turno',form('open',input('fund','Fondo inicial (RD$)','number','min="0" step=".01" value="2000" required')))+'</div>';
 const o=picked();
 const cats=[...new Set(state.products.map(p=>p.category))];
 const products=state.products.filter(p=>(!category||p.category===category)&&p.name.toLowerCase().includes(query.toLowerCase()));
 const catalog='<div class="tabs">'+action('nav','En mesa','Mesas')+action('new','Para llevar','llevar')+action('new','Barra','barra')+'</div><input class="search" id="search" type="search" aria-label="Buscar producto" placeholder="Buscar producto" value="'+esc(query)+'"><div class="tabs">'+action('category','Todos','',!category?'active':'')+cats.map(c=>action('category',esc(c),c,c===category?'active':'')).join('')+'</div><div class="grid catalog">'+products.map(p=>{
 const src=p.photo?.startsWith('data:')?p.photo:p.photo?'/images/'+p.photo:'';
 return action('product',(src?'<img src="'+esc(src)+'" alt="">':'<span class="placeholder">'+(p.station==='barra'?'🍹':'🍽')+'</span>')+'<strong>'+title(p)+'</strong><small>'+money(p.cents)+'</small>',p.id,'tile');
 }).join('')+'</div>';
 if(!o)return '<div class="layout">'+panel('Menú',catalog)+panel('Cuenta', '<p>Abre una mesa o selecciona un pedido.</p>'+action('nav','Ver mesas','Mesas','primary'))+'</div>';
 const items=o.lines.map(l=>line(title(l)+'<br><small>'+esc([l.station,l.status,'ITBIS '+l.tax+'%',...l.modifiers,l.note].filter(Boolean).join(' · '))+'</small>',
 money(l.cents)+(l.payment?' ✓':'')+(!l.payment&&!o.closed&&$('#role').value==='supervisor'?' '+action('void','Anular',l.id)+' '+action('discount','Descuento',l.id):''))).join('');
 let bill=items+prices(totals(o.lines,o.service));
 if(o.closed&&o.fiscal)bill+=line('Pago','Registrado')+line('Comprobante '+o.fiscal.kind,esc(o.fiscal.status))+action('fiscal','Reintentar comprobante',o.id);
 else if(!o.closed)bill+='<div class="actions">'+action('send','Enviar comanda',o.id)+action('pay','Dividir y cobrar',o.id)+action('charge','Cobrar',o.id,'primary')+'</div>';
 return '<div class="layout">'+panel('Menú',catalog)+panel(orderName(o)+' · #'+o.number,(o.people?'<p class="muted">'+o.people+' personas</p>':'')+bill)+'</div>';
}
function station(key){
 const cards=state.orders.flatMap(o=>[...new Set(o.lines.filter(l=>l.station===key&&l.batch).map(l=>l.batch))].map(batch=>{
  const items=o.lines.filter(l=>l.batch===batch&&l.station===key);
  return panel(orderName(o)+' · #'+o.number,items.map(l=>line(title(l)+'<br><small>'+esc([...l.modifiers,l.note].filter(Boolean).join(' · '))+'</small>',
   l.status==='lista'?'Lista':action('ready','Marcar lista',o.id+','+l.id,'primary'))).join(''));
 }));
 return '<div class="grid">'+(cards.join('')||panel('Sin comandas','<p>Las partidas enviadas aparecerán aquí.</p>'))+'</div>';
}
function inventory(){
 let rows=Object.entries(state.ingredients).map(([k,v])=>line(esc(v.name),v.stock+' '+v.unit)).join('');
 for(const e of state.events.filter(e=>e.type!=='sale').slice(-6).reverse())rows+=line(esc(state.ingredients[e.ingredient].name)+' · '+(e.type==='count'?'Conteo':'Merma'),esc(e.type==='count'?'Diferencia: '+e.difference:'−'+e.quantity+' · '+e.reason));
 const choices=Object.entries(state.ingredients).map(([k,v])=>[k,v.name]);
 const fields=select('ingredient','Ingrediente',choices)+input('quantity','Cantidad','number','min="0" step="1" required');
 return '<div class="layout">'+panel('Existencia esperada',rows)+'<div class="stack">'+panel('Registrar merma',form('waste',fields+input('reason','Motivo','text','required')))+panel('Conteo real',form('count',fields))+'</div></div>';
}
function reports(){
 if(!state.shift)return panel('Sin turno','<p>Abre caja para ver los movimientos.</p>');
 const s=state.shift;
 return '<div class="layout">'+panel('Movimientos de caja',line('Fondo inicial',money(s.fund))+Object.entries(summary.methods).map(([n,m])=>line(n,money(m))).join('')+line('Efectivo esperado',money(summary.expected),'total'))+
 panel('Arqueo de efectivo',s.closed?line('Efectivo contado',money(s.counted))+line('Diferencia',money(s.difference))+line('Cerró',esc(s.userClosed)):form('close',input('counted','Efectivo contado','number','min="0" step=".01" required')))+
 panel('Comprobantes del turno',state.orders.filter(o=>o.shift===s.id&&o.fiscal).map(o=>line(orderName(o)+' #'+o.number,esc(o.fiscal.kind)+' · '+esc(o.fiscal.status))).join('')||'Sin comprobantes')+
 panel('Autorizaciones',state.audits.map(a=>line(esc(a.action)+' · '+esc(a.user),esc(a.details.reason))).join('')||'Sin autorizaciones')+'</div>';
}
function menu(){
 return '<div class="layout">'+panel('Productos',action('edit','+ Nuevo producto','','primary')+state.products.map(p=>{
  const info=margin(p,state.ingredients);
  return line(title(p)+'<br><small>'+esc(p.category)+' · '+money(p.cents)+' · '+esc(p.station)+'</small>'+
  (Object.keys(p.recipe||{}).length?'<br><small>Costo estimado '+money(info.cost)+' · Margen normal '+money(info.normal)+(info.happy===null?'':' · Happy hour '+money(info.happy))+'</small>':''),action('edit','Editar',p.id));
 }).join(''))+panel('Menú y recetas','<p>Agrega categorías, modificadores y precios. Edita el mojito para revisar su receta y el precio de happy hour.</p>')+'</div>';
}
async function command(type,data){
 if(locked)return;locked=true;
 document.querySelectorAll('button').forEach(b=>b.disabled=true);
 try{
  const response=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':$('#role').value},body:JSON.stringify({key:crypto.randomUUID(),type,...data})});
  const r=await response.json();if(!response.ok)throw new Error(r.error);
  state=r.state;summary=r.summary;
  if($('#modal').open)$('#modal').close();
  if(type==='order'){selected=r.result.id;mode='Caja';}
  if(type==='send')flash('Comandas nuevas · Cocina: '+r.result.cocina+' · Barra: '+r.result.barra);
  else if(type==='pay')flash('Pago registrado: '+money(r.result.amount));
  else if(type==='fiscal')flash('Mismo comprobante · '+r.result.status);
  else flash('Operación registrada.');
 }catch(e){flash(e.message,true);if($('#modal').open){const msg=document.createElement('p');msg.textContent=e.message;msg.setAttribute('role','alert');$('#modal-content').prepend(msg);}}
 finally{locked=false;render();document.querySelectorAll('#modal button').forEach(b=>b.disabled=false);}
}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-action]');if(!b||locked)return;
 const {action:a,value:v}=b.dataset;
 if(a==='nav')switchTo(v);
 if(a==='dismiss')$('#modal').close();
 if(a==='category'){category=v;render();}
 if(a==='table'){
  const n=Number(v),o=state.orders.find(o=>o.table===n&&!o.closed);
  if(o){selected=o.id;switchTo('Caja');}
  else modal('Mesa '+v.padStart(2,'0'),form('order',input('people','Personas','number','min="1" max="30" value="3" required')),{service:'mesa',table:n});
 }
 if(a==='new')modal(v==='barra'?'Pedido en barra':'Pedido para llevar',form('order','<p>Se abrirá una cuenta nueva.</p>'),{service:v});
 if(a==='pick'){selected=v;switchTo('Caja');}
 if(a==='product'){
  const o=picked(),p=state.products.find(p=>p.id===v);
  if(!o||o.closed){flash('Abre un pedido para agregar productos.',true);return;}
  modal(title(p),form('add',p.modifiers.map(m=>'<label class="check"><input type="checkbox" name="modifiers" value="'+esc(m)+'">'+esc(m)+'</label>').join('')+
  (p.happy!=null?'<label class="check"><input type="checkbox" name="happy">Happy hour · '+money(p.happy)+'</label>':'')+input('note','Nota para '+p.station)),{order:o.id,product:v});
 }
 if(a==='send')command('send',{order:v});
 if(a==='ready'){const [order,line]=v.split(',');command('ready',{order,line});}
 if(a==='void')modal('Anular partida',form('void',input('reason','Motivo','text','required')),{order:selected,line:v});
 if(a==='discount')modal('Descuento autorizado',form('discount',input('discount','Descuento (RD$)','number','min="0.01" step=".01" required')+input('reason','Motivo','text','required')),{order:selected,line:v});
 if(a==='fiscal')command('fiscal',{order:v});
 if(a==='pay'||a==='charge'){
  const o=picked(),unpaid=o.lines.filter(l=>!l.payment);
  if(!unpaid.length){flash('Selecciona partidas pendientes.',true);return;}
  const check=unpaid.map(l=>'<label class="check"><input type="checkbox" name="lines" value="'+l.id+'" '+(a==='charge'?'checked':'')+'>'+title(l)+' · '+money(l.cents)+'</label>').join('');
  modal(a==='charge'?'Cobrar · '+orderName(o):'Dividir cuenta',form('pay',check+'<div id="payment-total">'+prices(totals(a==='charge'?unpaid:[],o.service))+'</div>'+
   select('method','Método de pago',[['efectivo','Efectivo'],['tarjeta','Tarjeta'],['transferencia','Transferencia']])+
   select('kind','Comprobante de prueba',[['E32','Consumo electrónico E32'],['E31','Crédito fiscal E31']],o.billing?.kind)+input('rnc','RNC para E31','text','inputmode="numeric" value="'+esc(o.billing?.rnc)+'"')+'<small>Comprobante simulado. Sin envío a DGII.</small>'),{order:o.id});
 }
 if(a==='edit'){
  const p=state.products.find(p=>p.id===v)||{};
  const attrs=x=>'value="'+esc(x)+'"';
  const recipe=p.id==='mojito'?'<h3>Receta del mojito</h3>'+Object.entries(state.ingredients).map(([k,i])=>input('recipe_'+k,esc(i.name)+' ('+i.unit+')','number','min="0" '+attrs(p.recipe?.[k]||0))).join(''):'';
  modal(p.id?'Editar producto':'Nuevo producto',form('product',
   input('name','Nombre','text',attrs(p.name)+' required')+input('category','Categoría','text',attrs(p.category)+' required')+
   input('price','Precio (RD$)','number','min="0" step=".01" '+attrs(p.cents==null?'':p.cents/100)+' required')+
   input('happyPrice','Precio happy hour (RD$)','number','min="0" step=".01" '+attrs(p.happy==null?'':p.happy/100))+
   select('tax','ITBIS',[[0,'Exento'],[16,'16 %'],[18,'18 %']],p.tax??18)+
   select('station','Estación',[['cocina','Cocina'],['barra','Barra']],p.station)+
   input('modifiers','Modificadores separados por comas','text',attrs(p.modifiers?.join(', ')))+
   select('photo','Imagen',[['','Ícono de categoría'],['burger.jpg','Genérica · Comida'],['wings.jpg','Genérica · Alitas'],['mojito.jpg','Genérica · Bebida'],...(p.photo?.startsWith('data:')?[['keep','Conservar foto actual']]:[])],p.photo?.startsWith('data:')?'keep':p.photo)+
   input('upload','Subir foto (JPG, PNG o WebP)','file','accept="image/jpeg,image/png,image/webp"')+recipe),{id:p.id,existingPhoto:p.photo});
 }
});
document.addEventListener('input',e=>{
 if(e.target.id==='search'){query=e.target.value;render();const q=$('#search');q.focus();q.setSelectionRange(query.length,query.length);}
 if(e.target.name==='lines'&&$('#payment-total')){
  const o=picked(),f=e.target.form;const selected=new Set(new FormData(f).getAll('lines'));
  $('#payment-total').innerHTML=prices(totals(o.lines.filter(l=>selected.has(l.id)),o.service));
 }
});
document.addEventListener('submit',async e=>{
 if(!e.target.dataset.command)return;e.preventDefault();if(locked)return;
 const data=new FormData(e.target),type=e.target.dataset.command;
 const values=Object.fromEntries(data);
 const payload={...formData,...values}; delete payload.upload;delete payload.existingPhoto;
 if(type==='open')payload.fund=cash(values.fund);
 if(type==='order')payload.people=values.people?Number(values.people):undefined;
 if(type==='add'){payload.modifiers=data.getAll('modifiers');payload.happy=data.has('happy');}
 if(type==='pay')payload.lines=data.getAll('lines');
 if(type==='discount')payload.cents=cash(values.discount);
 if(type==='close')payload.counted=cash(values.counted);
 if(type==='waste'||type==='count')payload.quantity=Number(values.quantity);
 if(type==='product'){
  payload.cents=cash(values.price);payload.tax=Number(values.tax);payload.happy=values.happyPrice?cash(values.happyPrice):null;
  if(values.photo==='keep')payload.photo=formData.existingPhoto;
  if(values.upload?.size){
   if(values.upload.size>480000){flash('La foto supera 480 KB.',true);return;}
   payload.photo=await new Promise(resolve=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.readAsDataURL(values.upload);});
  }
  if(data.has('recipe_ron'))payload.recipe=Object.fromEntries(Object.keys(state.ingredients).map(k=>[k,Number(data.get('recipe_'+k))]));
  for(const key of Object.keys(payload))if(key.startsWith('recipe_')||key==='price'||key==='happyPrice')delete payload[key];
 }
 command(type,payload);
});
$('#role').addEventListener('change',()=>render());
refresh().catch(e=>flash(e.message,true));
stationPoll=setInterval(()=>{if(!locked&&!$('#modal').open&&['Cocina','Barra'].includes(mode))refresh().catch(()=>flash('Sin conexión con la caja.',true));},2500);
