import {money,totals,margin,restaurantTables,equalShares,businessTypes,setupRequired} from './domain.mjs';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modes={Mesas:'Mesas',Pedidos:'Pedidos',Cocina:'Cocina',Barra:'Barra',Caja:'Caja',Inventario:'Inventario y mermas',Reportes:'Reportes y cierre de caja',Menú:'Menú y recetas'};
const iconPaths={Mesas:'M4 9h16M6 9V5h12v4M6 9l-2 11M18 9l2 11M8 15h8',Pedidos:'M9 4H5v17h14V4h-4M9 3h6v4H9zM8 12h8M8 16h6',Cocina:'M7 14a4 4 0 0 1-2-7 4 4 0 0 1 7-3 4 4 0 0 1 7 3 4 4 0 0 1-2 7v7H7zM7 17h10',Barra:'M3 3h18l-9 10zM12 13v8M7 21h10',Caja:'M4 9h16v12H4zM7 9V3h10v6M7 14h3M14 14h3M7 17h3M14 17h3',Inventario:'M3 7l9-4 9 4-9 4zM3 7v10l9 4 9-4V7M12 11v10',Reportes:'M4 3v18h17M8 17v-5M13 17V7M18 17v-9',Menú:'M4 4h16v16H4zM8 8h8M8 12h8M8 16h4'};
const icon=name=>'<svg class="icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="'+(iconPaths[name]||iconPaths.Menú)+'"/></svg>';
let inventoryConnected=false;
let staff=[],displayName='',currentAccount='';
const basePath=new URL(import.meta.url).pathname.replace(/\/app.mjs$/,'');
const staffOptions=()=>staff.map(person=>[person.id,person.name]);
let pendingRequest;
let setupOpen=false,setupChoice;
let mode='Caja',state,summary,selected,locked=false,formData,category='',query='',stationPoll;
const cash=v=>Math.round(Number(v)*100);
const picked=()=>state.orders.find(o=>o.id===selected);
const orderName=o=>o.service==='mesa'?(restaurantTables(state).find(t=>t.number===o.table)?.name||o.tableName||'Mesa '+String(o.table).padStart(2,'0')):o.service==='barra'?'Barra':'Para llevar';
const title=l=>esc(l.name);
const action=(name,label,value='',style='')=>'<button type="button" class="'+style+'" data-action="'+name+'" data-value="'+esc(value)+'">'+label+'</button>';
const panel=(label,content)=>'<section class="panel"><h2>'+label+'</h2>'+content+'</section>';
const form=(type,content)=>'<form data-command="'+type+'">'+content+'<button class="primary" type="submit">'+({open:'Abrir turno',add:'Añadir a la cuenta',pay:'Registrar pago',product:'Guardar producto',order:'Abrir pedido',close:'Confirmar cierre',waste:'Registrar merma',count:'Guardar conteo',void:'Autorizar anulación',discount:'Autorizar descuento',refund:'Registrar devolución','setup-business':'Continuar','setup-tables':'Continuar'}[type]||'Guardar')+'</button></form>';
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
 const res=await fetch(basePath+'/api/state',{signal:AbortSignal.timeout(10000)});
 const data=await res.json();if(!res.ok)throw new Error(data.error);
 ({state,summary,inventoryConnected}=data);
 staff=data.staff||[];displayName=data.connected?.displayName||'';currentAccount=data.connected?.account||'';
 if(!selected){
  const table=Number(new URL(location.href).searchParams.get('mesa'));
  const current=state.orders.find(o=>o.table===table&&!o.closed);
  if(current){selected=current.id;mode='Caja';}
 }
 if(data.connected){
  $('.rail-foot').hidden=true;
  $('#role').value=data.connected.role;
  $('header p').textContent='UNO360X POS / '+data.connected.branchName;
 }
 if(renderNow)render();
}
function switchTo(next){mode=configuring()?'Caja':next;render();}
const configuring=()=>setupOpen||setupRequired(state);
function setupWizard(){
 if($('#role').value!=='supervisor')return panel('Configuración inicial pendiente','<p>El administrador debe elegir el negocio, preparar las mesas y agregar los productos antes de abrir el POS.</p>');
 const setup=state.setup||{step:'business',business:'restaurant',tablesEnabled:true};
 const step=setup.step||'business';
 const back=action('setupBack','Atrás');
 if(step==='business'){
  const chosen=setupChoice||setup.business||'restaurant';
  const descriptions={restaurant:'Atención en mesas, Cocina y Barra.',bakery:'Venta en mostrador y mesas opcionales.',retail:'Venta de productos y cobro directo, sin mesas.',quick:'Pedidos para llevar o en barra, sin salón.'};
  return panel('Paso 1 de 3 · Elige tu negocio','<p class="muted">Esta configuración aparece solo al crear tu POS. Después puedes cambiarla desde Menú.</p>')+
   '<div class="layout">'+businessTypes.map(([id,name])=>panel(name,'<p>'+descriptions[id]+'</p><div class="actions">'+action('chooseBusiness',chosen===id?'Seleccionado':'Elegir',id,chosen===id?'primary':'')+'</div>')).join('')+'</div>'+
   '<form data-command="setup-business"><input type="hidden" name="business" value="'+esc(chosen)+'"><div class="actions">'+(setup.completed?action('finishSetupView','Atrás'):'<button type="button" disabled>Atrás</button>')+'<button class="primary" type="submit">Continuar</button></div></form>';
 }
 if(step==='tables'){
  const cards=restaurantTables(state).map(t=>action('editTable',icon('Mesas')+'<strong>'+esc(t.name)+'</strong><small>'+(t.active?'Editar nombre o desactivar':'Inactiva · Editar')+'</small>',t.number,'table-card')).join('');
  return panel('Paso 2 de 3 · Configura tus mesas','<p class="muted">Para Restaurante y bar empezamos con 5 mesas. En negocios sin mesas se omite este paso.</p>')+
   '<form data-command="setup-tables"><div class="layout">'+panel('Tus mesas','<p class="muted">Toca una mesa para editar su nombre o desactivarla.</p><div class="grid">'+cards+'</div><div class="actions">'+action('editTable','+ Agregar mesa')+'</div>')+
   panel('Configuración',select('enabled','¿Atiendes en mesas?',[['yes','Sí, con mesas'],['no','No, solo mostrador']],setup.tablesEnabled?'yes':'no')+input('count','Cantidad inicial','number','min="1" max="200" value="'+(setup.tableCount||5)+'" required')+'<p class="muted">Puedes agregar más o editar cada mesa. Una mesa con cuenta abierta no se desactiva.</p>')+'</div><div class="actions">'+back+'<button class="primary" type="submit">Continuar</button></div></form>';
 }
 const rows=state.products.map(p=>line(title(p)+'<br><small>'+esc(p.category)+' · '+money(p.cents)+' · '+esc(p.station==='ninguna'?'Sin comanda':p.station)+'</small>',action('edit','Editar',p.id))).join('');
 return panel('Paso 3 de 3 · Agrega tus productos','<p class="muted">Usa el botón Nuevo producto del Menú actual. Los productos de ejemplo son opcionales y no se agregan solos.</p>')+
  '<div class="layout">'+panel('Productos','<div class="actions">'+action('edit','+ Nuevo producto','','primary')+(!setup.examplesLoaded?action('setupExamples','Cargar ejemplos'):'')+'</div>'+(rows||'<p class="muted">Todavía no hay productos. Crea el primero o continúa y agrégalo después.</p>'))+
  panel('Antes de empezar','<p>1. Crea el producto con su nombre y precio.</p><p>2. Selecciona su categoría, imagen y destino: Cocina o Barra, o Sin comanda para venta directa.</p><p>3. Guarda y repite para el siguiente producto.</p><p class="muted">No hace falta completar todos los productos ahora. Los agregas después desde Menú.</p>')+'</div><div class="actions">'+back+action('setupFinish','Guardar y abrir el POS','','primary')+'</div>';
}
function render(){
 $('#nav').innerHTML=Object.keys(modes).map((n,i)=>(i===5?'<div class="nav-divider"></div>':'')+action('nav',icon(n)+'<span>'+n+'</span>',n,(n===mode?'active ':'')+(i>4?'secondary-nav':''))).join('');
 const current=picked();
 $('#title').textContent=mode==='Caja'&&current?orderName(current):modes[mode];
 $('#context').textContent=mode==='Caja'&&current?(current.people?current.people+' personas · ':'')+'Atiende: '+(current.waiter?.name||'Sin asignar'):'Restaurantes y bares';
 $('#shift-status').textContent=state.shift&&!state.shift.closed?'Turno abierto':'Caja cerrada';
 $('#shift-status').classList.toggle('closed',!state.shift||Boolean(state.shift.closed));
 $('#view').innerHTML=configuring()?setupWizard():({Mesas:tables,Pedidos:orders,Caja:register,Cocina:()=>station('cocina'),Barra:()=>station('barra'),Inventario:inventory,Reportes:reports,Menú:menu})[mode]();
 $('#mobile-orderbar').hidden=configuring()||mode!=='Caja'||!current||current.closed;
 document.querySelectorAll('#mobile-orderbar button').forEach(b=>b.disabled=locked);
 $('#mobile-nav-toggle').disabled=locked;
 document.body.classList.toggle('has-mobile-order',!configuring()&&mode==='Caja'&&Boolean(current));
 $('#mobile-total').textContent=current?money(totals(current.lines,current.service).total-state.payments.filter(p=>p.order===current.id).reduce((n,p)=>n+p.amount,0)):'';
}
function orders(){
 const open=state.orders.filter(o=>!o.closed);
 return panel('Pedidos en curso','<div class="actions">'+action('nav','Ver mesas','Mesas')+action('new','Para llevar','llevar')+action('new','Pedido en barra','barra')+'</div><div class="grid order-grid">'+(open.map(o=>action('pick','<strong>'+orderName(o)+'</strong><small>Pedido #'+o.number+' · '+o.lines.length+' productos</small><small>Atiende: '+esc(o.waiter?.name||'Sin asignar')+'</small><b>'+money(totals(o.lines,o.service).total)+'</b>',o.id,'order-card')).join('')||'<p class="muted">No hay pedidos abiertos.</p>')+'</div>');
}
function tables(){
 if(state.setup?.tablesEnabled===false)return panel('Venta sin mesas','<p>Este POS está configurado para mostrador o pedidos para llevar. Puedes cambiarlo desde Menú → Configurar mi POS.</p>'+action('nav','Ir a Caja','Caja','primary'));
 const active=state.orders.filter(o=>!o.closed);
 return '<div class="layout">'+panel('Salón principal','<p class="muted">Toca una mesa para abrir su pedido.</p>'+($('#role').value==='supervisor'?'<div class="actions">'+action('manageTables','Administrar mesas')+'</div>':'')+'<div class="grid">'+restaurantTables(state).filter(t=>t.active).map(t=>{
  const n=t.number,o=active.find(o=>o.table===n);
  return action('table',icon('Mesas')+'<strong>'+esc(t.name)+'</strong><small>'+(o?o.people+' personas · En servicio':'Libre')+'</small>'+(o?'<small>Atiende: '+esc(o.waiter?.name||'Sin asignar')+'</small>':''),n,'table-card '+(o?'selected':''));
 }).join('')+'</div>')+panel('Otros servicios',action('new','Para llevar','llevar')+' '+action('new','Pedido en barra','barra')+
 active.filter(o=>!o.table).map(o=>line(orderName(o)+' #'+o.number,action('pick','Abrir',o.id))).join(''))+'</div>';
}
function register(){
 if(!state.shift||state.shift.closed)return '<div class="layout">'+panel('Caja 01',line('Estado','Cerrada')+line('Sucursal','Centro'))+panel('Apertura de turno',form('open',input('fund','Fondo inicial (RD$)','number','min="0" step=".01" value="2000" required')))+'</div>';
 const o=picked();
 const cats=[...new Set(state.products.map(p=>p.category))];
 const products=state.products.filter(p=>(!category||p.category===category)&&p.name.toLowerCase().includes(query.toLowerCase()));
 const catalog='<div class="tabs">'+action('nav','En mesa','Mesas',!o||o.service==='mesa'?'active':'')+action('new','Para llevar','llevar',o?.service==='llevar'?'active':'')+action('new','Barra','barra',o?.service==='barra'?'active':'')+'</div><input class="search" id="search" type="search" aria-label="Buscar producto" placeholder="Buscar producto" value="'+esc(query)+'"><div class="tabs">'+action('category','Todos','',!category?'active':'')+cats.map(c=>action('category',esc(c),c,c===category?'active':'')).join('')+'</div><div class="grid catalog">'+products.map(p=>{
 const src=p.photo?.startsWith('data:')?p.photo:p.photo?basePath+'/images/'+p.photo:'';
 return action('product',(src?'<img src="'+esc(src)+'" alt="">':'<span class="placeholder">'+(p.station==='barra'?'🍹':'🍽')+'</span>')+'<strong>'+title(p)+'</strong><small>'+money(p.cents)+'</small><span class="add-product-label">+ Agregar al pedido</span>',p.id,'tile');
 }).join('')+'</div>';
 if(!o)return '<div class="layout">'+panel('Menú',catalog)+panel('Cuenta', '<p>Abre una mesa o selecciona un pedido.</p>'+action('nav','Ver mesas','Mesas','primary'))+'</div>';
 const items=o.lines.map(l=>line('<span class="line-quantity">1</span><span class="line-description">'+title(l)+'<small>'+esc([l.station==='barra'?'Barra':'Cocina',l.status,'ITBIS '+l.tax+'%',...l.modifiers,l.note].filter(Boolean).join(' · '))+'</small></span>',
 money(l.cents)+(l.refund?' · Devuelta':l.payment?' ✓':'')+(!l.payment&&!o.closed&&$('#role').value==='supervisor'?' '+action('void','Anular',l.id)+' '+action('discount','Descuento',l.id):''))).join('');
 const paid=state.payments.filter(p=>p.order===o.id).reduce((n,p)=>n+p.amount,0);
 let bill=items+prices(totals(o.lines,o.service))+(paid?line('Pagado',money(paid))+line('Pendiente',money(totals(o.lines,o.service).total-paid)): '');
 if(o.closed&&o.fiscal)bill+=line('Pago','Registrado')+line('Comprobante '+o.fiscal.kind,esc(o.fiscal.status))+'<div class="actions">'+action('print','Imprimir ticket',o.id,'primary')+action('fiscal','Ver estado fiscal',o.id)+
 (state.shift?.id===o.shift&&!state.shift.closed&&$('#role').value==='supervisor'&&o.lines.some(l=>!l.refund)?action('refund','Devolver partidas',o.id):'')+'</div>'+
 (state.refunds||[]).filter(r=>r.order===o.id).map(r=>line('Devolución registrada',money(r.amount))).join('');
 else if(!o.closed)bill+='<div class="checkout-actions">'+action('charge',icon('Caja')+'Cobrar',o.id,'primary')+'<div>'+action('send','Enviar comanda',o.id)+action('pay','Dividir y cobrar',o.id)+'</div></div>';
 const assignment='<div class="assignment"><span>Atiende: <strong>'+esc(o.waiter?.name||'Sin asignar')+'</strong></span>'+(!o.closed&&o.service==='mesa'&&$('#role').value==='supervisor'?action('reassign','Reasignar mesa',o.id):'')+'</div>';
 return '<div class="layout register-layout"><section class="panel catalog-panel"><h2>Menú</h2><p class="catalog-guide"><strong>1. Agrega productos</strong><br>Toca la foto, elige las opciones y pulsa «Añadir a la cuenta».</p>'+catalog+'</section><section class="panel order-panel"><div class="order-heading"><h2>Pedido · '+orderName(o)+'</h2><span class="station-badge">Cocina · Barra</span></div>'+(o.people?'<p class="muted">'+o.people+' personas · Pedido #'+o.number+'</p>':'')+assignment+bill+'</section></div>';
}
function station(key){
 const cards=state.orders.flatMap(o=>[...new Set(o.lines.filter(l=>l.station===key&&l.batch).map(l=>l.batch))].map(batch=>{
  const items=o.lines.filter(l=>l.batch===batch&&l.station===key);
  return panel(orderName(o)+' · #'+o.number,'<p class="muted">Atiende: '+esc(o.waiter?.name||'Sin asignar')+'</p>'+items.map(l=>line(title(l)+'<br><small>'+esc([...l.modifiers,l.note].filter(Boolean).join(' · '))+'</small>',
   l.status==='lista'?'Lista':action('ready','Marcar lista',o.id+','+l.id,'primary'))).join(''));
 }));
 return '<div class="grid">'+(cards.join('')||panel('Sin comandas','<p>Las partidas enviadas aparecerán aquí.</p>'))+'</div>';
}
function inventory(){
 let rows=Object.entries(state.ingredients).map(([k,v])=>line(esc(v.name),v.stock+' '+v.unit)).join('');
 for(const e of state.events.filter(e=>e.type!=='sale').slice(-6).reverse())rows+=line(esc(state.ingredients[e.ingredient].name)+' · '+(e.type==='count'?'Conteo':'Merma'),esc(e.type==='count'?'Diferencia: '+e.difference:'−'+e.quantity+' · '+e.reason));
 const choices=Object.entries(state.ingredients).map(([k,v])=>[k,v.name]);
 const fields=select('ingredient','Ingrediente',choices)+input('quantity','Cantidad','number','min="0" step="1" required');
 const central=inventoryConnected?action('syncInventory','Sincronizar inventario de pruebas','','primary'):'';
 return '<div class="layout">'+panel('Existencia esperada',rows+central)+'<div class="stack">'+panel('Registrar merma',form('waste',fields+input('reason','Motivo','text','required')))+panel('Conteo real',form('count',fields))+'</div></div>';
}
function reports(){
 if(!state.shift)return panel('Sin turno','<p>Abre caja para ver los movimientos.</p>');
 const s=state.shift;
 return '<div class="layout">'+panel('Movimientos de caja',line('Fondo inicial',money(s.fund))+Object.entries(summary.methods).map(([n,m])=>line(n,money(m))).join('')+Object.entries(summary.refunds||{}).filter(([,m])=>m>0).map(([n,m])=>line('Devoluciones · '+n,money(m))).join('')+line('Efectivo esperado',money(summary.expected),'total'))+
 panel('Arqueo de efectivo',s.closed?line('Efectivo contado',money(s.counted))+line('Diferencia',money(s.difference))+line('Cerró',esc(s.userClosed)):form('close',input('counted','Efectivo contado','number','min="0" step=".01" required')))+
 panel('Comprobantes del turno',state.orders.filter(o=>o.shift===s.id&&o.fiscal).map(o=>line(orderName(o)+' #'+o.number,esc(o.fiscal.kind)+' · '+esc(o.fiscal.status)+' '+action('pick','Abrir venta',o.id)+' '+action('print','Imprimir',o.id))).join('')||'Sin comprobantes')+
 panel('Autorizaciones',state.audits.map(a=>line(esc(a.action)+' · '+esc(a.userName||a.user),esc(a.details.previous?.name||'')+(a.details.next?' → '+esc(a.details.next.name)+'<br>':'')+esc(a.details.reason)+'<br><small>'+esc(new Date(a.at).toLocaleString('es-DO'))+'</small>')).join('')||'Sin autorizaciones')+'</div>';
}
function menu(){
 return '<div class="layout">'+panel('Productos',($('#role').value==='supervisor'?'<div class="actions">'+action('edit','+ Nuevo producto','','primary')+action('configureSetup','Configurar mi POS')+'</div>':'')+state.products.map(p=>{
  const info=margin(p,state.ingredients);
  return line(title(p)+'<br><small>'+esc(p.category)+' · '+money(p.cents)+' · '+esc(p.station)+'</small>'+
  (Object.keys(p.recipe||{}).length?'<br><small>Costo estimado '+money(info.cost)+' · Margen normal '+money(info.normal)+(info.happy===null?'':' · Happy hour '+money(info.happy))+'</small>':''),action('edit','Editar',p.id));
 }).join(''))+panel('Menú y recetas','<p>Agrega categorías, modificadores y precios. Edita el mojito para revisar su receta y el precio de happy hour.</p>')+'</div>';
}
function printTicket(order){
 const lines=order.lines.map(l=>line(title(l),money(l.cents))).join('');
 const payments=state.payments.filter(p=>p.order===order.id).map(p=>line(esc(p.method),money(p.amount))).join('');
 const refunds=(state.refunds||[]).filter(r=>r.order===order.id).map(r=>line('Devolución registrada',money(r.amount))).join('');
 $('#printed-ticket').innerHTML='<h2>UNO360X POS</h2><p>Ticket de prueba · Sin valor fiscal</p><h3>'+orderName(order)+' · #'+order.number+'</h3>'+
  lines+prices(totals(order.lines,order.service))+payments+refunds+'<p>Comprobante '+esc(order.fiscal.kind)+' · '+esc(order.fiscal.status)+'</p>';
 window.print();
}
async function command(type,data){
 if(locked)return;locked=true;
 document.querySelectorAll('button').forEach(b=>b.disabled=true);
 try{
  const role=$('#role').value;
  const payload=JSON.stringify({type,...data});
  if(pendingRequest&&(pendingRequest.payload!==payload||pendingRequest.role!==role)){
   throw new Error('Hay una operación sin confirmar. Repite la misma acción y datos antes de continuar.');
  }
  pendingRequest??={payload,role,key:crypto.randomUUID()};
  const response=await fetch(basePath+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':role},
   body:JSON.stringify({key:pendingRequest.key,...JSON.parse(payload)})});
  const r=await response.json();
  pendingRequest=undefined;
  if(!response.ok)throw new Error(r.error);
  state=r.state;summary=r.summary;
  if($('#modal').open)$('#modal').close();
  if(type==='order'){selected=r.result.id;mode='Caja';}
  if(type==='setup-finish'){setupOpen=false;setupChoice=undefined;mode='Caja';}
  if(type==='sync-inventory')flash('Inventario: '+r.result.filter(x=>x.state==='confirmado').length+' confirmados, '+r.result.filter(x=>x.state==='pendiente').length+' pendientes.');
  else if(type==='send')flash('Comandas nuevas · Cocina: '+r.result.cocina+' · Barra: '+r.result.barra);
  else if(type==='reassign')flash('Mesa reasignada a '+r.result.name+'.');
  else if(type==='refund')flash('Devolución de prueba registrada: '+money(r.result.amount));
  else if(type==='pay')flash('Pago registrado: '+money(r.result.amount));
  else if(type==='add')flash(r.result.name+' agregado al pedido. Envía la comanda cuando termines de elegir.');
  else if(type==='setup-examples')flash(r.result.added+' productos de ejemplo agregados.');
  else if(type==='setup-finish')flash('Tu POS quedó configurado. Abre un turno cuando estés listo para vender.');
  else if(type==='fiscal')flash('Mismo comprobante · '+r.result.status);
  else flash('Operación registrada.');
 }catch(e){const message=e instanceof TypeError&&pendingRequest?'Sin comunicación con caja. Repite la misma operación al reconectar.':e.message;flash(message,true);if($('#modal').open){const msg=document.createElement('p');msg.textContent=message;msg.setAttribute('role','alert');$('#modal-content').prepend(msg);}}
 finally{locked=false;render();document.querySelectorAll('#modal button').forEach(b=>b.disabled=false);}
}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-action]');if(!b||locked)return;
 const {action:a,value:v}=b.dataset;
 if(a==='toggleNav'){
  const expanded=$('.rail').classList.toggle('menu-open');
  $('#mobile-nav-toggle').setAttribute('aria-expanded',String(expanded));
 }
 if(a==='nav'){
  $('.rail').classList.remove('menu-open');
  $('#mobile-nav-toggle').setAttribute('aria-expanded','false');
  switchTo(v);
 }
 if(a==='dismiss')$('#modal').close();
 if(a==='chooseBusiness'){setupChoice=v;render();}
 if(a==='configureSetup'){setupOpen=true;setupChoice=undefined;command('setup-step',{step:'business'});}
 if(a==='finishSetupView'){setupOpen=false;render();}
 if(a==='setupBack'){const step=state.setup?.step;command('setup-step',{step:step==='products'&&['restaurant','bakery'].includes(state.setup.business)?'tables':'business'});}
 if(a==='setupExamples')command('setup-examples',{});
 if(a==='setupFinish')command('setup-finish',{});
 if(a==='manageTables')modal('Administrar mesas','<p>Empiezas con 5 mesas. Agrega más o edita su nombre. Solo el supervisor puede hacerlo.</p>'+action('editTable','+ Agregar mesa','','primary')+restaurantTables(state).map(t=>line(esc(t.name)+' · '+(t.active?'Activa':'Inactiva'),action('editTable','Editar',t.number))).join(''));
 if(a==='editTable'){
  const t=restaurantTables(state).find(t=>t.number===Number(v));
  const number=t?.number||Math.max(0,...restaurantTables(state).map(t=>t.number))+1;
  modal(t?'Editar mesa':'Agregar mesa',form('table',input('number','Número de mesa','number','min="1" max="200" value="'+number+'" '+(t?'readonly':'')+' required')+input('name','Nombre de la mesa','text','maxlength="40" value="'+esc(t?.name||'Mesa '+String(number).padStart(2,'0'))+'" required')+select('active','Estado',[['yes','Activa'],['no','Inactiva']],t?.active===false?'no':'yes')));
 }
 if(a==='showOrder')$('.order-panel')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
 if(a==='category'){category=v;render();}
 if(a==='table'){
  const n=Number(v),o=state.orders.find(o=>o.table===n&&!o.closed);
  if(o){selected=o.id;switchTo('Caja');}
  else modal('Mesa '+v.padStart(2,'0'),form('order',input('people','Personas','number','min="1" max="30" value="3" required')+($('#role').value==='camarero'?'<p>Atiende: '+esc(displayName||'Camarero de prueba')+'</p>':select('waiter','Quién atiende',staffOptions(),currentAccount||$('#role').value))),{service:'mesa',table:n});
 }
 if(a==='new')modal(v==='barra'?'Pedido en barra':'Pedido para llevar',form('order','<p>Se abrirá una cuenta nueva.</p>'),{service:v});
 if(a==='pick'){selected=v;switchTo('Caja');}
 if(a==='product'){
  const o=picked(),p=state.products.find(p=>p.id===v);
  if(!o||o.closed){flash('Abre un pedido para agregar productos.',true);return;}
  modal('Agregar '+title(p),'<p>Se agregará una unidad a '+esc(orderName(o))+'. Para otra unidad, toca el producto de nuevo.</p>'+form('add',p.modifiers.map(m=>'<label class="check"><input type="checkbox" name="modifiers" value="'+esc(m)+'">'+esc(m)+'</label>').join('')+
  (p.happy!=null?'<label class="check"><input type="checkbox" name="happy">Happy hour · '+money(p.happy)+'</label>':'')+input('note','Nota para '+p.station)),{order:o.id,product:v});
 }
 if(a==='send')command('send',{order:v});
 if(a==='reassign')modal('Reasignar mesa',form('reassign',select('waiter','Nuevo responsable',staffOptions(),picked()?.waiter?.id)+input('reason','Motivo del cambio','text','maxlength="180" required')),{order:v});
 if(a==='ready'){const [order,line]=v.split(',');command('ready',{order,line});}
 if(a==='void')modal('Anular partida',form('void',input('reason','Motivo','text','required')),{order:selected,line:v});
 if(a==='discount')modal('Descuento autorizado',form('discount',input('discount','Descuento (RD$)','number','min="0.01" step=".01" required')+input('reason','Motivo','text','required')),{order:selected,line:v});
 if(a==='syncInventory')command('sync-inventory',{});
 if(a==='print'){const o=state.orders.find(order=>order.id===v&&order.fiscal);if(o)printTicket(o);}
 if(a==='refund'){
  const o=state.orders.find(order=>order.id===v);
  const choices=o.lines.filter(l=>l.payment&&!l.refund).map(l=>'<label class="check"><input type="checkbox" name="lines" value="'+l.id+'">'+title(l)+' · '+money(totals([l],o.service).total)+'</label>').join('');
  modal('Devolver partidas',form('refund',choices+input('reason','Motivo','text','required')+
    '<small>Se registra el ajuste de prueba en el método original. No se emite documento fiscal ni se procesa un abono bancario.</small>'),{order:o.id});
 }
 if(a==='fiscal')command('fiscal',{order:v});
 if(a==='pay'){
  const o=picked();if(!o||o.closed)return;
  modal('Dividir cuenta','<p>Elige cómo repartir lo que falta por pagar. Cada persona puede usar un método de pago diferente.</p><div class="split-options">'+(!o.equalSplit?action('splitProducts','Por productos<br><small>Cada persona elige lo que consumió.</small>','','primary'):'')+action('splitEqual','En partes iguales<br><small>Reparte el total entre varias personas.</small>','','primary')+'</div>');
 }
 if(a==='splitEqual')openEqualPayment();
 if(a==='splitProducts'||a==='charge'){
  const o=picked(),unpaid=o.lines.filter(l=>!l.payment);
  if(o.equalSplit){openEqualPayment();return;}
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
   select('station','Estación',[['cocina','Cocina'],['barra','Barra'],['ninguna','Sin comanda']],p.station||(['retail','quick'].includes(state.setup?.business)?'ninguna':'cocina'))+
   input('modifiers','Modificadores separados por comas','text',attrs(p.modifiers?.join(', ')))+
   select('photo','Imagen',[['','Ícono de categoría'],['burger.jpg','Genérica · Comida'],['wings.jpg','Genérica · Alitas'],['mojito.jpg','Genérica · Bebida'],...(p.photo?.startsWith('data:')?[['keep','Conservar foto actual']]:[])],p.photo?.startsWith('data:')?'keep':p.photo)+
   input('upload','Subir foto (JPG, PNG o WebP)','file','accept="image/jpeg,image/png,image/webp"')+recipe),{id:p.id,existingPhoto:p.photo});
 }
});

function openEqualPayment(people){
 const o=picked();if(!o||o.closed)return;
 if(!o.lines.length){flash('Agrega productos antes de dividir la cuenta.',true);return;}
 if(state.payments.some(p=>p.order===o.id)&&!o.equalSplit){flash('Esta cuenta ya tiene productos pagados. Continúa por productos.',true);return;}
 const n=o.equalSplit?.people||Number(people)||Math.max(2,o.people||2);
 let amounts;try{amounts=o.equalSplit?.amounts||equalShares(totals(o.lines,o.service).total,n);}catch(e){flash(e.message,true);return;}
 const payments=state.payments.filter(p=>p.order===o.id);
 const entries=amounts.map((amount,i)=>[String(i),'Persona '+(i+1)+' · '+money(amount)]).filter(([i])=>!payments.some(p=>p.equalPart===Number(i)));
 modal('Dividir en partes iguales','<p>El total incluye ITBIS y propina legal cuando aplica. Los centavos se distribuyen sin cambiar el total. Se conserva una sola cuenta y un comprobante.</p>'+form('pay',input('people','Cantidad de personas','number','min="2" max="30" value="'+n+'" '+(o.equalSplit?'readonly':'')+' required')+action('recalculateSplit','Calcular partes')+'<div class="equal-summary">'+amounts.map((m,i)=>line('Persona '+(i+1),money(m)+(payments.some(p=>p.equalPart===i)?' · Pagada':''))).join('')+'</div>'+select('part','Parte que va a pagar',entries,entries[0]?.[0])+select('method','Método de pago',[['efectivo','Efectivo'],['tarjeta','Tarjeta'],['transferencia','Transferencia']])+select('kind','Comprobante de prueba',[['E32','Consumo electrónico E32'],['E31','Crédito fiscal E31']],o.billing?.kind)+input('rnc','RNC para E31','text','inputmode="numeric" value="'+esc(o.billing?.rnc)+'"')+'<small>Comprobante simulado. Sin envío a DGII. La cantidad de personas queda fija al registrar el primer pago.</small>'),{order:o.id,split:'equal',calculatedPeople:n});
}
document.addEventListener('click',e=>{
 if(e.target.closest('[data-action="recalculateSplit"]')){
  const n=Number($('#modal input[name="people"]').value);
  if(!Number.isInteger(n)||n<2||n>30){flash('Indica entre 2 y 30 personas.',true);return;}
  openEqualPayment(n);
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
 const payload={...(e.target.closest('#modal')?formData:{}),...values}; delete payload.upload;delete payload.existingPhoto;
 if(type==='open')payload.fund=cash(values.fund);
 if(type==='order')payload.people=values.people?Number(values.people):undefined;
 if(type==='table'){payload.number=Number(values.number);payload.active=values.active==='yes';}
 if(type==='setup-tables'){payload.count=Number(values.count);payload.enabled=values.enabled==='yes';}
 if(type==='add'){payload.modifiers=data.getAll('modifiers');payload.happy=data.has('happy');}
 if(type==='pay'||type==='refund')payload.lines=data.getAll('lines');
 if(type==='pay'&&payload.split==='equal'){
  payload.people=Number(values.people);payload.part=Number(values.part);
  if(payload.people!==formData.calculatedPeople){flash('Pulsa Calcular partes antes de registrar el pago.',true);return;}
  delete payload.calculatedPeople;
 }
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
