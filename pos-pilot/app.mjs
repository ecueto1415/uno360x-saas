import {money,totals,margin,restaurantTables,equalShares,businessTypes,setupRequired,floorTables,floorZones,invoicesFor} from './domain.mjs';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modes={Mesas:'Mesas',Pedidos:'Pedidos',Cocina:'Cocina',Barra:'Barra',Caja:'Caja',Inventario:'Inventario y mermas',Reportes:'Reportes y cierre de caja',Menú:'Menú y recetas'};
const iconPaths={Mesas:'M4 9h16M6 9V5h12v4M6 9l-2 11M18 9l2 11M8 15h8',Pedidos:'M9 4H5v17h14V4h-4M9 3h6v4H9zM8 12h8M8 16h6',Cocina:'M7 14a4 4 0 0 1-2-7 4 4 0 0 1 7-3 4 4 0 0 1 7 3 4 4 0 0 1-2 7v7H7zM7 17h10',Barra:'M3 3h18l-9 10zM12 13v8M7 21h10',Caja:'M4 9h16v12H4zM7 9V3h10v6M7 14h3M14 14h3M7 17h3M14 17h3',Inventario:'M3 7l9-4 9 4-9 4zM3 7v10l9 4 9-4V7M12 11v10',Reportes:'M4 3v18h17M8 17v-5M13 17V7M18 17v-9',Menú:'M4 4h16v16H4zM8 8h8M8 12h8M8 16h4'};
const icon=name=>'<svg class="icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="'+(iconPaths[name]||iconPaths.Menú)+'"/></svg>';
let inventoryConnected=false,publicMenuOrigin=location.origin;
let staff=[],displayName='',currentAccount='';
const basePath=new URL(import.meta.url).pathname.replace(/\/app.mjs$/,'');
const staffOptions=()=>staff.map(person=>[person.id,person.name]);
let pendingRequest;
let settingsOpen=false,digitalMenuOpen=false,menuUnsaved=false,setupChoice;
let floorZone='salon',floorSelection,floorEditing=false,floorDraft,floorVersion=0,guestToAdd='',guestFilter='all',roleInitialized=false;
let mode='Caja',state,summary,selected,locked=false,formData,category='',query='',stationPoll;
const cash=v=>Math.round(Number(v)*100);
const picked=()=>state.orders.find(o=>o.id===selected);
const orderName=o=>o.service==='mesa'?(restaurantTables(state).find(t=>t.number===o.table)?.name||o.tableName||'Mesa '+String(o.table).padStart(2,'0')):o.service==='barra'?'Barra':'Para llevar';
const title=l=>esc(l.name);
const action=(name,label,value='',style='')=>'<button type="button" class="'+style+'" data-action="'+name+'" data-value="'+esc(value)+'">'+label+'</button>';
const panel=(label,content)=>'<section class="panel"><h2>'+label+'</h2>'+content+'</section>';
const form=(type,content)=>'<form data-command="'+type+'">'+content+'<button class="primary" type="submit">'+({open:'Abrir turno',add:'Añadir a la cuenta',pay:'Registrar pago',product:'Guardar producto',order:'Abrir pedido',close:'Confirmar cierre',waste:'Registrar merma',count:'Guardar conteo',void:'Autorizar anulación',discount:'Autorizar descuento',refund:'Registrar devolución','setup-business':'Continuar','setup-tables':'Continuar','review-business-change':'Revisar cambio','guest-save':'Crear persona','guest-distribute':'Continuar al cobro','cancel-order':'Confirmar cancelación'}[type]||'Guardar')+'</button></form>';
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
 const res=await fetch(basePath+'/api/state',{headers:{'X-Pos-Role':$('#role').value},signal:AbortSignal.timeout(10000)});
 const data=await res.json();if(!res.ok)throw new Error(data.error);
 ({state,summary,inventoryConnected}=data);publicMenuOrigin=data.menuOrigin||location.origin;
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
 if(!roleInitialized){if(['cocina','barra'].includes($('#role').value))mode=$('#role').value==='cocina'?'Cocina':'Barra';else if($('#role').value==='camarero')mode='Mesas';roleInitialized=true;}
 if(renderNow)render();
}
function switchTo(next){settingsOpen=false;digitalMenuOpen=false;mode=configuring()?'Caja':next;render();}
const configuring=()=>setupRequired(state);
const stationEntries=()=>[['cocina','Cocina'],['barra','Barra'],['ninguna','Sin comanda']].filter(([id])=>id==='ninguna'||state.setup?.stations?.[id]!==false);
function posSettings(){
 if($('#role').value!=='supervisor'){settingsOpen=false;return menu();}
 return panel('Ajustes del POS','<p class="muted">Mesas, productos y estaciones se administran por separado. El POS abre directamente para el trabajo diario.</p>')+'<div class="layout">'+
 panel('Mesas','<p>Activa el salón, ajusta su cantidad y edita los nombres de las mesas.</p>'+action('tableSettings','Configurar mesas'))+
 panel('Menú digital','<p>Muestra tu catálogo en televisión o por QR. Solo publica lo que elijas.</p>'+action('digitalMenu','Configurar menú digital'))+
 panel('Productos','<p>Crea o edita tu catálogo, precios, imágenes y destino de las comandas.</p>'+action('manageProducts','Administrar productos'))+
 panel('Estaciones','<p>Activa Cocina o Barra sin cambiar el tipo de negocio.</p>'+action('stationSettings','Configurar estaciones'))+
 panel('Equipo del POS','<p>Define quién trabaja en Caja, atiende mesas o recibe comandas. No cambia permisos de Odoo.</p>'+action('teamRoles','Roles del equipo'))+
 panel('Tipo de negocio',line('Actual',esc(businessTypes.find(([id])=>id===(state.setup?.business||'restaurant'))?.[1]))+'<p class="muted">Solo el administrador puede cambiarlo, después de revisar y confirmar.</p>'+action('changeBusiness','Cambiar tipo de negocio'))+'</div><div class="actions">'+action('backToPOS','Volver al POS','','primary')+'</div>';
}
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
   '<form data-command="setup-business"><input type="hidden" name="business" value="'+esc(chosen)+'"><div class="actions">'+'<button type="button" disabled>Atrás</button>'+'<button class="primary" type="submit">Continuar</button></div></form>';
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
 $('#title').textContent=digitalMenuOpen?'Menú digital':mode==='Caja'&&current?orderName(current):modes[mode];
 $('#context').textContent=mode==='Caja'&&current?(current.people?current.people+' personas · ':'')+'Atiende: '+(current.waiter?.name||'Sin asignar'):'Restaurantes y bares';
 $('#shift-status').textContent=state.shift&&!state.shift.closed?'Turno abierto':'Caja cerrada';
 $('#shift-status').classList.toggle('closed',!state.shift||Boolean(state.shift.closed));
 const role=$('#role').value;
 const restricted=['cocina','barra'].includes(role)?mode!==(role==='cocina'?'Cocina':'Barra'):role==='camarero'&&['Reportes','Inventario'].includes(mode);
 $('#view').innerHTML=restricted?panel('Acceso reservado','<p>Esta opción corresponde a otro rol del equipo.</p>'):configuring()?setupWizard():settingsOpen?(digitalMenuOpen?digitalMenuSettings():posSettings()):({Mesas:tables,Pedidos:orders,Caja:register,Cocina:()=>station('cocina'),Barra:()=>station('barra'),Inventario:inventory,Reportes:reports,Menú:menu})[mode]();
 $('#mobile-orderbar').hidden=configuring()||settingsOpen||mode!=='Caja'||!current||current.closed||current.amountsHidden;
 document.querySelectorAll('#mobile-orderbar button').forEach(b=>b.disabled=locked);
 $('#mobile-nav-toggle').disabled=locked;
 document.body.classList.toggle('has-mobile-order',!configuring()&&!settingsOpen&&mode==='Caja'&&Boolean(current));
 $('#mobile-total').textContent=current?money(totals(current.lines,current.service).total-state.payments.filter(p=>p.order===current.id).reduce((n,p)=>n+p.amount,0)):'';
 $('#mobile-orderbar [data-action="pay"]').hidden=!['caja','supervisor'].includes(role);
}
function orders(){
 const open=state.orders.filter(o=>!o.closed);
 return panel('Pedidos en curso','<div class="actions">'+action('nav','Ver mesas','Mesas')+action('new','Para llevar','llevar')+action('new','Pedido en barra','barra')+'</div><div class="grid order-grid">'+(open.map(o=>action('pick','<strong>'+orderName(o)+'</strong><small>Pedido #'+o.number+' · '+(o.lineCount??o.lines.length)+' productos</small><small>Atiende: '+esc(o.waiter?.name||'Sin asignar')+'</small><b>'+(o.amountsHidden?'Cuenta reservada':money(totals(o.lines,o.service).total))+'</b>',o.id,'order-card')).join('')||'<p class="muted">No hay pedidos abiertos.</p>')+'</div>');
}
function floorDimensions(){const small=innerWidth<=450;const count=(floorDraft||floorTables(state)).filter(t=>t.active&&t.zone===floorZone).length;return {w:small?520:800,h:Math.max(small?650:600,Math.ceil(count/3)*180+40),tw:small?145:198,th:small?150:145};}
function tables(){
 if(state.setup?.tablesEnabled===false)return panel('Venta sin mesas','<p>Este POS está configurado sin salón. Puedes activarlo desde Menú → Ajustes del POS → Mesas.</p>'+action('nav','Ir a Caja','Caja','primary'));
 const list=(floorDraft||floorTables(state)).filter(t=>t.active),zones=floorZones(state);
 if(!zones.some(z=>z.id===floorZone))floorZone=zones[0].id;
 const visible=list.filter(t=>t.zone===floorZone),open=state.orders.filter(o=>!o.closed);
 let table=list.find(t=>t.number===floorSelection&&t.zone===floorZone)||visible.find(t=>open.some(o=>o.table===t.number))||visible[0];floorSelection=table?.number;
 const d=floorDimensions(),paidFor=o=>state.payments.filter(p=>p.order===o.id).reduce((n,p)=>n+p.amount,0);
 const svg=visible.map(t=>{
  const o=open.find(o=>o.table===t.number),selected=t.number===floorSelection;
  const waiting=o&&(o.checkRequested||paidFor(o)>0),cls=o?(waiting?'waiting':'occupied'):'free';
  const x=12+t.x/100*(d.w-d.tw-24),y=12+t.y/100*(d.h-d.th-24),mid=d.tw/2;
  const detail=o?(o.people||'')+' comensales · '+(o.waiter?.name||'Sin asignar'):t.seats+' lugares · Libre';
  const amount=o&&!o.amountsHidden?money(totals(o.lines,o.service).total-paidFor(o)):o?'Cuenta reservada':'';
  return '<g role="button" tabindex="0" aria-label="'+esc(t.name+' · '+detail)+'" data-action="floorSelect" data-value="'+t.number+'" class="floor-table '+cls+(selected?' selected-floor':'')+'" transform="translate('+x+','+y+')"><title>'+esc(t.name+' · '+detail)+'</title><rect width="'+d.tw+'" height="'+d.th+'" rx="'+(t.shape==='round'?60:14)+'"/><svg x="'+(mid-16)+'" y="14" width="32" height="32" viewBox="0 0 24 24"><path d="'+iconPaths.Mesas+'"/></svg><text class="floor-name" x="'+mid+'" y="65">'+esc(t.name.length>17?t.name.slice(0,16)+'…':t.name)+'</text><text class="floor-meta" x="'+mid+'" y="88">'+esc(detail.length>27?detail.slice(0,26)+'…':detail)+'</text><text class="floor-amount" x="'+mid+'" y="111">'+esc(floorEditing?'Selecciona para ubicar':amount)+'</text><text class="floor-meta" x="'+mid+'" y="132">'+(floorEditing?'':o?.opened?Math.max(0,Math.floor((Date.now()-Date.parse(o.opened))/60000))+' min':'')+'</text></g>';
 }).join('');
 const tools=$('#role').value==='supervisor'?'<div class="actions">'+action('manageTables','Administrar mesas')+action('manageZones','Administrar zonas')+(!floorEditing?action('editFloor','Editar plano'):action('newZone','+ Agregar zona'))+'</div>':'';
 const plan=panel(floorEditing?'Editar plano':'Plano de mesas','<p class="muted">Zonas del local</p><div class="tabs">'+zones.map(z=>action('zone',esc(z.name),z.id,z.id===floorZone?'primary':'')).join('')+'</div>'+tools+'<div class="floor-stage"><svg class="floor-canvas '+(floorEditing?'is-editing':'')+'" viewBox="0 0 '+d.w+' '+d.h+'" aria-label="Plano del salón">'+svg+'</svg></div><div class="floor-legend"><span>○ Libre</span><span>● En servicio</span><span>● Por cobrar</span></div>');
 const o=table&&open.find(o=>o.table===table.number);
 let detail;
 if(floorEditing&&table)detail=panel('Mesa seleccionada','<div class="floor-fields">'+input('floorName','Nombre de la mesa','text','data-floor-field="name" maxlength="40" value="'+esc(table.name)+'"')+select('floorZone','Zona de la mesa',zones.map(z=>[z.id,z.name]),table.zone).replace('<select','<select data-floor-field="zone"')+input('floorSeats','Lugares','number','data-floor-field="seats" min="1" max="30" value="'+table.seats+'"')+select('floorShape','Forma',[['rect','Rectangular'],['round','Redonda']],table.shape).replace('<select','<select data-floor-field="shape"')+input('floorX','Posición horizontal (%)','number','data-floor-field="x" min="0" max="100" step="0.1" value="'+table.x+'"')+input('floorY','Posición vertical (%)','number','data-floor-field="y" min="0" max="100" step="0.1" value="'+table.y+'"')+'</div><div class="seat-controls" aria-label="Mover mesa">'+action('moveFloor','← Izquierda','left')+action('moveFloor','Arriba ↑','up')+action('moveFloor','Abajo ↓','down')+action('moveFloor','Derecha →','right')+'</div><p class="muted">Solo el administrador edita el plano. Usa las flechas para mover la mesa; con mouse también puedes arrastrarla.</p><div class="actions">'+action('cancelFloor','Cancelar')+action('saveFloor','Guardar plano','','primary')+'</div>');
 else if(table)detail=panel(esc(table.name),'<p class="muted">'+esc(zones.find(z=>z.id===table.zone)?.name)+' · '+(o?o.people+' comensales':table.seats+' lugares')+'</p>'+(o?line('Atiende',esc(o.waiter?.name||'Sin asignar'))+line('Tiempo de atención',o.opened?Math.max(0,Math.floor((Date.now()-Date.parse(o.opened))/60000))+' min':'Sin tiempo previo')+(o.amountsHidden?'<p>Cuenta reservada al responsable y a Caja.</p>':line('Pendiente de la mesa',money(totals(o.lines,o.service).total-paidFor(o)),'total')):'<p>Mesa libre.</p>')+(!o?.amountsHidden?'<div class="actions">'+action('table','Abrir pedido',table.number,'primary')+(o?action('requestCheck','Marcar por cobrar',o.id):'')+'</div>':'')+'<p class="muted">Crea personas dentro del pedido solo si necesitas organizar su consumo.</p>');
 else detail=panel('Sin mesas en esta zona','<p>El administrador puede asignar mesas desde Editar plano.</p>');
 return '<div class="layout">'+plan+detail+'</div>'+panel('Otros servicios','<div class="actions">'+action('new','Para llevar','llevar')+action('new','Pedido en barra','barra')+'</div>'+open.filter(o=>!o.table).map(o=>line(orderName(o)+' #'+o.number,action('pick','Abrir',o.id))).join(''));
}

function register(){
 if($('#role').value==='camarero'&&(!state.shift||state.shift.closed))return panel('Caja cerrada','<p>Caja o el administrador debe abrir un turno para comenzar la atención.</p>');
 if(!state.shift||state.shift.closed)return '<div class="layout">'+panel('Caja 01',line('Estado','Cerrada')+line('Sucursal','Centro'))+panel('Apertura de turno',form('open',input('fund','Fondo inicial (RD$)','number','min="0" step=".01" value="2000" required')))+'</div>';
 const o=picked();
 if(o?.amountsHidden)return panel('Cuenta reservada','<p>Solo puedes abrir los pedidos de las mesas que atiendes.</p>'+action('nav','Ver mesas','Mesas'));
 const cats=[...new Set(state.products.map(p=>p.category))];
 const products=state.products.filter(p=>(!category||p.category===category)&&p.name.toLowerCase().includes(query.toLowerCase()));
 const guestOptions=[['','Cuenta general'],...(o?.guests||[]).map(g=>[g.id,g.name]),['shared','Compartido']];
 if(!guestOptions.some(([id])=>id===guestToAdd))guestToAdd='';
 const catalog=(o?select('guestToAdd','Agregar productos a',guestOptions,guestToAdd).replace('<select','<select id="guest-add" class="photo-guide"'):'')+'<div class="tabs">'+action('nav','En mesa','Mesas',!o||o.service==='mesa'?'active':'')+action('new','Para llevar','llevar',o?.service==='llevar'?'active':'')+action('new','Barra','barra',o?.service==='barra'?'active':'')+'</div><input class="search" id="search" type="search" aria-label="Buscar producto" placeholder="Buscar producto" value="'+esc(query)+'"><div class="tabs">'+action('category','Todos','',!category?'active':'')+cats.map(c=>action('category',esc(c),c,c===category?'active':'')).join('')+'</div><div class="grid catalog">'+products.map(p=>{
 const src=p.photo?.startsWith('data:')?p.photo:p.photo?basePath+'/images/'+p.photo:'';
 return action('product',(src?'<img src="'+esc(src)+'" alt="">':'<span class="placeholder">'+(p.station==='barra'?'🍹':'🍽')+'</span>')+'<strong>'+title(p)+'</strong><small>'+money(p.cents)+'</small><span class="add-product-label">'+(p.available===false?'Agotado':'+ Agregar al pedido')+'</span>',p.id,'tile').replace('<button','<button'+(p.available===false?' disabled':''));
 }).join('')+'</div>';
 if(!o)return '<div class="layout">'+panel('Menú',catalog)+panel('Cuenta', '<p>Abre una mesa o selecciona un pedido.</p>'+action('nav','Ver mesas','Mesas','primary'))+'</div>';
 const hasPayments=state.payments.some(p=>p.order===o.id),guests=o.guests||[];
 if(guestFilter!=='all'&&guestFilter!=='general'&&guestFilter!=='shared'&&!guests.some(g=>g.id===guestFilter))guestFilter='all';
 const guestName=l=>guests.find(g=>g.id===l.guest)?.name||(l.guest==='shared'?'Compartido':'Cuenta general');
 const visibleLines=o.lines.filter(l=>guestFilter==='all'||(guestFilter==='general'?!l.guest:l.guest===guestFilter));
 const items=visibleLines.map(l=>line('<span class="line-quantity">1</span><span class="line-description">'+title(l)+'<small>'+esc([l.station==='barra'?'Barra':l.station==='cocina'?'Cocina':'Sin comanda',l.status,'ITBIS '+l.tax+'%',...l.modifiers,l.note].filter(Boolean).join(' · '))+'</small><small class="person-tag">'+esc(guestName(l))+'</small>'+(!hasPayments&&!o.closed&&guests.length?action('assignGuest','Asignar persona',l.id,'guest-assign'):'')+'</span>',
 money(l.cents)+(l.refund?' · Devuelta':l.payment?' ✓':'')+(!l.payment&&!o.closed&&$('#role').value==='supervisor'?' '+action('void','Anular',l.id)+' '+action('discount','Descuento',l.id):''))).join('');
 const paid=state.payments.filter(p=>p.order===o.id).reduce((n,p)=>n+p.amount,0);
 let bill=items+prices(totals(o.lines,o.service))+(paid?line('Pagado',money(paid))+line('Pendiente',money(totals(o.lines,o.service).total-paid)): '');
 const documents=invoicesFor(o);
 if(documents.length)bill+=documents.map(d=>'<section class="invoice-card"><strong>'+esc(d.guestName?'Factura de '+d.guestName:'Factura de la mesa')+' · '+esc(d.kind)+'</strong><small><span>'+esc(d.status)+'</span> · '+money(d.amount)+'</small><small>Sin e-NCF · documento de prueba</small><div class="actions">'+action('print','Imprimir ticket',o.id+','+d.id,'primary')+action('fiscal','Ver estado fiscal',o.id+','+d.id)+'</div></section>').join('');
 if(o.cancelled)bill='<div class="cancelled-order"><strong>Cuenta cancelada · Sin cobro</strong><p>'+esc(o.cancelled.reason)+'</p></div>'+bill;
 if(o.closed)bill+=(o.cancelled?'':line('Pago','Registrado'))+(state.shift?.id===o.shift&&!state.shift.closed&&$('#role').value==='supervisor'&&documents.length&&o.lines.some(l=>!l.refund)?'<div class="actions">'+action('refund','Devolver partidas',o.id)+'</div>':'')+(state.refunds||[]).filter(r=>r.order===o.id).map(r=>line('Devolución registrada',money(r.amount))).join('');
 else if(['caja','supervisor'].includes($('#role').value))bill+='<div class="checkout-actions">'+action('charge',icon('Caja')+'Cobrar',o.id,'primary')+'<div>'+action('send','Enviar comanda',o.id)+action('pay','Dividir y cobrar',o.id)+'</div></div>';
 else bill+='<div class="actions">'+action('send','Enviar comanda',o.id,'primary')+action('requestCheck','Marcar por cobrar',o.id)+'</div>';
 if(!o.closed&&!hasPayments&&!documents.length&&$('#role').value==='supervisor')bill+='<div class="actions space">'+action('cancelOrder','Cancelar cuenta',o.id)+'</div>';
 const assignment='<div class="assignment"><span>Atiende: <strong>'+esc(o.waiter?.name||'Sin asignar')+'</strong></span>'+(!o.closed&&o.service==='mesa'&&$('#role').value==='supervisor'?action('reassign','Reasignar mesa',o.id):'')+'</div>';
 const guestControls='<div class="seat-controls">'+action('guestFilter','Todos','all',guestFilter==='all'?'primary':'')+action('guestFilter','Cuenta general','general',guestFilter==='general'?'primary':'')+guests.map(g=>action('guestFilter',esc(g.name),g.id,guestFilter===g.id?'primary':'')).join('')+action('guestFilter','Compartido','shared',guestFilter==='shared'?'primary':'')+(!hasPayments&&!o.closed?action('createGuest','+ Crear persona'):'')+'</div>'+(!guests.length?'<p class="muted">No hay personas creadas. La cuenta puede cobrarse completa o dividirse sin crear personas.</p>':!hasPayments&&!o.closed?'<div class="guest-edit">'+guests.map(g=>action('editGuest','Editar '+esc(g.name),g.id)).join('')+'</div>':'')+(guestFilter!=='all'?'<p class="muted">Se filtran los productos; los totales corresponden a toda la mesa.</p>':'');
 return '<div class="layout register-layout"><section class="panel catalog-panel"><h2>Menú</h2><p class="catalog-guide"><strong>1. Agrega productos</strong><br>Elige Cuenta general o crea una persona. Toca la foto y pulsa «Añadir a la cuenta».</p>'+catalog+'</section><section class="panel order-panel"><div class="order-heading"><h2>Pedido · '+orderName(o)+'</h2><span class="station-badge">Cocina · Barra</span></div>'+(o.people?'<p class="muted">'+o.people+' comensales · Pedido #'+o.number+'</p>':'')+assignment+guestControls+bill+'</section></div>';
}
function station(key){
 const cards=state.orders.filter(o=>!o.cancelled).flatMap(o=>[...new Set(o.lines.filter(l=>l.station===key&&l.batch).map(l=>l.batch))].map(batch=>{
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
 panel('Comprobantes del turno',state.orders.filter(o=>o.shift===s.id).flatMap(o=>invoicesFor(o).map(d=>line(orderName(o)+' #'+o.number+(d.guestName?' · '+esc(d.guestName):''),esc(d.kind)+' · '+esc(d.status)+' '+action('pick','Abrir venta',o.id)+' '+action('print','Imprimir',o.id+','+d.id)))).join('')||'Sin comprobantes')+
 panel('Cuentas canceladas',state.orders.filter(o=>o.shift===s.id&&o.cancelled).map(o=>line(orderName(o)+' #'+o.number,esc(o.cancelled.reason)+' '+action('pick','Ver cuenta cancelada',o.id))).join('')||'Sin cuentas canceladas')+
 panel('Autorizaciones',state.audits.map(a=>line(esc(a.action)+' · '+esc(a.userName||a.user),esc(a.details.previous?.name||'')+(a.details.next?' → '+esc(a.details.next.name)+'<br>':'')+esc(a.details.reason)+'<br><small>'+esc(new Date(a.at).toLocaleString('es-DO'))+'</small>')).join('')||'Sin autorizaciones')+'</div>';
}
function menu(){
 return '<div class="layout">'+panel('Productos',($('#role').value==='supervisor'?'<div class="actions">'+action('edit','+ Nuevo producto','','primary')+action('posSettings','Ajustes del POS')+action('digitalMenu','Menú digital y QR')+'</div>':'')+state.products.map(p=>{
  const info=$('#role').value==='supervisor'?margin(p,state.ingredients):null;
  return line(title(p)+'<br><small>'+esc(p.category)+' · '+money(p.cents)+' · '+esc(p.station)+'</small>'+
  (info&&Object.keys(p.recipe||{}).length?'<br><small>Costo estimado '+money(info.cost)+' · Margen normal '+money(info.normal)+(info.happy===null?'':' · Happy hour '+money(info.happy))+'</small>':''),$('#role').value==='supervisor'?action('edit','Editar',p.id):'');
 }).join(''))+panel('Menú y recetas','<p>Agrega categorías, modificadores y precios. Edita el mojito para revisar su receta y el precio de happy hour.</p>')+'</div>';
}
function printTicket(order,document){
 const selectedLines=document?.lines?order.lines.filter(l=>document.lines.includes(l.id)):order.lines;
 const lines=selectedLines.map(l=>line(title(l),money(l.cents))).join('');
 const payments=state.payments.filter(p=>p.order===order.id&&(!document?.guest||p.guest===document.guest)).map(p=>line(esc(p.method),money(p.amount))).join('');
 const refunds=(state.refunds||[]).filter(r=>r.order===order.id).map(r=>line('Devolución registrada',money(r.amount))).join('');
 $('#printed-ticket').innerHTML='<h2>UNO360X POS</h2><p>Ticket de prueba · Sin valor fiscal</p><h3>'+orderName(order)+' · #'+order.number+'</h3>'+
  (document?.guestName?'<p>Persona: '+esc(document.guestName)+'</p>':'')+lines+prices(totals(selectedLines,order.service))+payments+refunds+'<p>Comprobante '+esc(document?.kind)+' · '+esc(document?.status)+'</p><p>Sin e-NCF · Sin valor fiscal</p>';
 window.print();
}
async function command(type,data,after){
 let succeeded=false;
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
  if(!response.ok)throw new Error(r.error);succeeded=true;if(type==='guest-distribute')after=openPersonPayment;
  state=r.state;summary=r.summary;
  if($('#modal').open)$('#modal').close();
  if(type==='order'){selected=r.result.id;mode='Caja';}
  if(type==='order'){guestToAdd='';guestFilter='all';}
  if(type==='guest-save')guestToAdd=r.result.id;
  if(type==='floor-save'){floorEditing=false;floorDraft=undefined;}
  if(['menu-save','menu-publish','menu-save-publish'].includes(type))menuUnsaved=false;
  if(type==='zone-save')floorVersion=state.floor.version;
  if(type==='setup-finish'){setupChoice=undefined;mode='Caja';}
  if(type==='sync-inventory')flash('Inventario: '+r.result.filter(x=>x.state==='confirmado').length+' confirmados, '+r.result.filter(x=>x.state==='pendiente').length+' pendientes.');
  else if(type==='send')flash('Comandas nuevas · Cocina: '+r.result.cocina+' · Barra: '+r.result.barra);
  else if(type==='reassign')flash('Mesa reasignada a '+r.result.name+'.');
  else if(type==='refund')flash('Devolución de prueba registrada: '+money(r.result.amount));
  else if(type==='pay')flash('Pago registrado: '+money(r.result.amount));
  else if(type==='add')flash(r.result.name+' agregado al pedido. Envía la comanda cuando termines de elegir.');
  else if(type==='setup-examples')flash(r.result.added+' productos de ejemplo agregados.');
  else if(type==='setup-finish')flash('Tu POS quedó configurado. Abre un turno cuando estés listo para vender.');
  else if(type==='business-change')flash('Tipo de negocio actualizado. Se conservaron mesas, productos, estaciones y ventas.');
  else if(type==='stations-config'||type==='tables-config')flash('Ajustes del POS guardados.');
  else if(type==='guest-save')flash(r.result.name+' guardado en este pedido.');
  else if(type==='floor-save')flash('Plano guardado.');
  else if(type==='cancel-order')flash('Cuenta cancelada. La mesa quedó libre y el historial se conserva.');
  else if(type==='guest-distribute')flash('Productos asignados. Continúa con el cobro por persona.');
  else if(type==='table-archive')flash('Mesa retirada del plano. Su historial se conserva.');
  else if(type==='zone-archive'){floorZone=floorZones(state)[0].id;floorSelection=undefined;flash('Zona retirada del plano. Puedes restaurarla desde Administrar zonas.');}
  else if(type==='zone-restore')flash('Zona restaurada.');
  else if(type==='menu-save')flash('Configuración guardada. Pulsa Publicar menú para aplicar la selección y disponibilidad.');
  else if(['menu-publish','menu-save-publish'].includes(type))flash(r.result.published?'Menú publicado. Ya puedes abrir el enlace y descargar el QR.':'Menú desactivado. El enlace público ya no muestra productos.');
  else if(type==='fiscal')flash('Mismo comprobante · '+r.result.status);
  else flash('Operación registrada.');
 }catch(e){const message=e instanceof TypeError&&pendingRequest?'Sin comunicación con caja. Repite la misma operación al reconectar.':e.message;flash(message,true);if($('#modal').open){const msg=document.createElement('p');msg.textContent=message;msg.setAttribute('role','alert');$('#modal-content').prepend(msg);}}
 finally{locked=false;render();document.querySelectorAll('#modal button').forEach(b=>b.disabled=false);if(succeeded)after?.();}
}
document.addEventListener('click',async e=>{
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
 if(a==='zone'){floorZone=v;floorSelection=undefined;render();}
 if(a==='floorSelect'){floorSelection=Number(v);render();}
 if(a==='editFloor'){floorEditing=true;floorDraft=structuredClone(floorTables(state));floorVersion=state.floor?.version||0;render();}
 if(a==='cancelFloor'){floorEditing=false;floorDraft=undefined;render();}
 if(a==='moveFloor'&&floorEditing){const t=floorDraft.find(t=>t.number===floorSelection);if(t){const key=['left','right'].includes(v)?'x':'y';t[key]=Math.max(0,Math.min(100,t[key]+(['left','up'].includes(v)?-5:5)));render();}}
 if(a==='saveFloor')command('floor-save',{version:floorVersion,tables:floorDraft});
 if(a==='newZone')modal('Agregar zona',form('zone-save',input('name','Nombre de la zona','text','maxlength="35" required')));
 if(a==='createGuest'||a==='editGuest'){
  const o=picked(),guest=(o?.guests||[]).find(g=>g.id===v);if(!o||o.closed)return;
  const body=form('guest-save',input('name','Nombre de la persona - opcional','text','maxlength="60" placeholder="Ej.: Carlos" value="'+esc(guest?.name||'')+'"')+'<p class="muted">'+(guest?'Se conserva el nombre actual si lo dejas vacío.':'Si lo dejas vacío, se usará Persona '+((o.guestSequence||o.guests?.length||0)+1)+'.')+' Solo identifica el consumo; no crea un usuario ni un cliente fiscal.</p>');
  modal(guest?'Editar nombre':'Crear persona · '+orderName(o),guest?body.replace('>Crear persona</button>','>Guardar cambios</button>'):body,{order:o.id,guest:guest?.id});
 }
 if(a==='guestFilter'){guestFilter=v;render();}
 if(a==='assignGuest')modal('Asignar producto a una persona',form('guest-assign',select('guest','Persona',[['','Cuenta general'],...(picked()?.guests||[]).map(g=>[g.id,g.name]),['shared','Compartido']],picked()?.lines.find(l=>l.id===v)?.guest||'')),{order:selected,line:v});
 if(a==='requestCheck')command('request-check',{order:v});
 if(a==='chooseBusiness'){setupChoice=v;render();}
 if(a==='posSettings'){settingsOpen=true;digitalMenuOpen=false;render();}
 if(a==='digitalMenu'){if($('#role').value!=='supervisor')return;settingsOpen=true;digitalMenuOpen=true;menuUnsaved=false;render();}
 if(a==='digitalBack'){digitalMenuOpen=false;render();}
 if(a==='publishDigital')$('#digital-form')?.requestSubmit();
 if(a==='previewDigital')await previewDigitalMenu();
 if(a==='allDigital'){document.querySelectorAll('#digital-form input[name=published]').forEach(c=>c.checked=true);menuUnsaved=true;}
 if(a==='backToPOS')switchTo('Caja');
 if(a==='manageProducts')switchTo('Menú');
 if(a==='tableSettings')modal('Configurar mesas',form('tables-config',select('enabled','¿Atiendes en mesas?',[['yes','Sí, con mesas'],['no','No, solo mostrador']],state.setup?.tablesEnabled===false?'no':'yes')+input('count','Cantidad de mesas','number','min="1" max="200" value="'+(state.setup?.tableCount||Math.max(5,...restaurantTables(state).filter(t=>t.active).map(t=>t.number)))+'" required')+'<p class="muted">Los nombres se editan desde Mesas → Administrar mesas. No se desactivan mesas con cuentas abiertas.</p>'));
 if(a==='stationSettings')modal('Configurar estaciones',form('stations-config',select('kitchen','Cocina',[['yes','Activa'],['no','Inactiva']],state.setup?.stations?.cocina===false?'no':'yes')+select('bar','Barra',[['yes','Activa'],['no','Inactiva']],state.setup?.stations?.barra===false?'no':'yes')+'<p class="muted">Antes de desactivar una estación, reasigna sus productos y completa las comandas pendientes.</p>'));
 if(a==='teamRoles')modal('Roles del equipo',form('staff-role',select('account','Usuario del equipo',staffOptions())+select('role','Rol en este POS',[['caja','Caja'],['camarero','Camarero'],['cocina','Cocina'],['barra','Barra']])+'<p class="muted">El camarero ve montos solo de sus mesas. Cocina y Barra no ven importes. Los administradores conservan su permiso de supervisión.</p>')+'<div class="space">'+staff.map(p=>line(esc(p.name),esc(state.staffRoles?.[p.id]||'Según su permiso de POS'))).join('')+'</div>');
 if(a==='changeBusiness')modal('Cambiar tipo de negocio',form('review-business-change',select('business','Nuevo tipo de negocio',businessTypes.filter(([id])=>id!==(state.setup?.business||'restaurant')))),{previousBusiness:state.setup?.business||'restaurant'});
 if(a==='confirmBusinessChange')command('business-change',{...formData,confirmed:true});
 if(a==='setupBack'){const step=state.setup?.step;command('setup-step',{step:step==='products'&&['restaurant','bakery'].includes(state.setup.business)?'tables':'business'});}
 if(a==='setupExamples')command('setup-examples',{});
 if(a==='setupFinish')command('setup-finish',{});
 if(a==='manageTables'){
  const list=restaurantTables(state);
  modal('Administrar mesas','<p>Agrega mesas o quítalas del plano. Quitar conserva su historial y permite restaurarlas.</p>'+action('editTable','+ Agregar mesa','','primary')+list.filter(t=>!t.archived).map(t=>line(esc(t.name)+' · '+(t.active?'Activa':'Inactiva'),action('editTable','Editar',t.number)+' '+action('archiveTable','Quitar mesa',t.number))).join('')+(list.some(t=>t.archived)?'<h3 class="space">Mesas retiradas</h3>'+list.filter(t=>t.archived).map(t=>line(esc(t.name),action('editTable','Restaurar mesa',t.number))).join(''):''));
 }
 if(a==='archiveTable'){
  const t=restaurantTables(state).find(t=>t.number===Number(v));if(t)modal('Quitar '+t.name,'<p>Se quitará del plano y se conservará su historial. Puedes restaurarla desde Administrar mesas. No se permite si tiene una cuenta abierta.</p>'+action('confirmArchiveTable','Sí, quitar mesa',v,'primary'));
 }
 if(a==='confirmArchiveTable')command('table-archive',{number:Number(v),confirmed:true});
 if(a==='manageZones'){
  const zones=state.floor?.zones||floorZones(state);
  modal('Administrar zonas','<p>Solo puedes quitar zonas sin mesas activas ni cuentas abiertas. Puedes restaurarlas después.</p>'+action('newZone','+ Agregar zona')+zones.filter(z=>z.active!==false).map(z=>line(esc(z.name),action('editZone','Editar zona',z.id)+' '+action('archiveZone','Quitar zona',z.id))).join('')+(zones.some(z=>z.active===false)?'<h3 class="space">Zonas retiradas</h3>'+zones.filter(z=>z.active===false).map(z=>line(esc(z.name),action('restoreZone','Restaurar zona',z.id))).join(''):''));
 }
 if(a==='editZone'){const z=floorZones(state).find(z=>z.id===v);if(z)modal('Editar zona',form('zone-save',input('name','Nombre de la zona','text','maxlength="35" required value="'+esc(z.name)+'"')),{id:z.id});}
 if(a==='archiveZone'){const z=floorZones(state).find(z=>z.id===v);if(z)modal('Quitar zona '+z.name,'<p>Se quitará del plano sin borrar el historial. La zona debe estar vacía de mesas activas y cuentas abiertas.</p>'+action('confirmArchiveZone','Sí, quitar zona',v,'primary'));}
 if(a==='confirmArchiveZone')command('zone-archive',{id:v,confirmed:true});
 if(a==='restoreZone')command('zone-restore',{id:v});
 if(a==='editTable'){
  const t=restaurantTables(state).find(t=>t.number===Number(v));
  const number=t?.number||Math.max(0,...restaurantTables(state).map(t=>t.number))+1;
  modal(t?'Editar mesa':'Agregar mesa',form('table',input('number','Número de mesa','number','min="1" max="200" value="'+number+'" '+(t?'readonly':'')+' required')+input('name','Nombre de la mesa','text','maxlength="40" value="'+esc(t?.name||'Mesa '+String(number).padStart(2,'0'))+'" required')+select('active','Estado',[['yes','Activa'],['no','Inactiva']],t?.active===false&&!t?.archived?'no':'yes')));
 }
 if(a==='showOrder')$('.order-panel')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
 if(a==='category'){category=v;render();}
 if(a==='table'){
  const n=Number(v),o=state.orders.find(o=>o.table===n&&!o.closed);
  if(o){selected=o.id;switchTo('Caja');}
  else modal('Mesa '+v.padStart(2,'0'),form('order',input('people','Personas','number','min="1" max="30" value="3" required')+($('#role').value==='camarero'?'<p>Atiende: '+esc(displayName||'Camarero de prueba')+'</p>':select('waiter','Quién atiende',staffOptions(),currentAccount||$('#role').value))),{service:'mesa',table:n});
 }
 if(a==='new')modal(v==='barra'?'Pedido en barra':'Pedido para llevar',form('order','<p>Se abrirá una cuenta nueva.</p>'),{service:v});
 if(a==='pick'){if(state.orders.find(o=>o.id===v)?.amountsHidden){flash('Solo puedes abrir las mesas que atiendes.',true);return;}selected=v;guestToAdd='';guestFilter='all';switchTo('Caja');}
 if(a==='product'){
  const o=picked(),p=state.products.find(p=>p.id===v);
  if(!o||o.closed){flash('Abre un pedido para agregar productos.',true);return;}
  modal('Agregar '+title(p),'<p>Se agregará una unidad a '+esc(orderName(o))+'. Para otra unidad, toca el producto de nuevo.</p>'+form('add',p.modifiers.map(m=>'<label class="check"><input type="checkbox" name="modifiers" value="'+esc(m)+'">'+esc(m)+'</label>').join('')+
  (p.happy!=null?'<label class="check"><input type="checkbox" name="happy">Happy hour · '+money(p.happy)+'</label>':'')+input('note','Nota para '+p.station)),{order:o.id,product:v,guest:guestToAdd});
 }
 if(a==='send')command('send',{order:v});
 if(a==='reassign')modal('Reasignar mesa',form('reassign',select('waiter','Nuevo responsable',staffOptions(),picked()?.waiter?.id)+input('reason','Motivo del cambio','text','maxlength="180" required')),{order:v});
 if(a==='ready'){const [order,line]=v.split(',');command('ready',{order,line});}
 if(a==='void')modal('Anular partida',form('void',input('reason','Motivo','text','required')),{order:selected,line:v});
 if(a==='discount')modal('Descuento autorizado',form('discount',input('discount','Descuento (RD$)','number','min="0.01" step=".01" required')+input('reason','Motivo','text','required')),{order:selected,line:v});
 if(a==='syncInventory')command('sync-inventory',{});
 if(a==='print'){const [orderId,invoiceId]=v.split(',');const o=state.orders.find(order=>order.id===orderId);const doc=o&&invoicesFor(o).find(d=>!invoiceId||d.id===invoiceId);if(o&&doc)printTicket(o,doc);}
 if(a==='refund'){
  const o=state.orders.find(order=>order.id===v);
  const choices=o.lines.filter(l=>l.payment&&!l.refund).map(l=>'<label class="check"><input type="checkbox" name="lines" value="'+l.id+'">'+title(l)+' · '+money(totals([l],o.service).total)+'</label>').join('');
  modal('Devolver partidas',form('refund',choices+input('reason','Motivo','text','required')+
    '<small>Se registra el ajuste de prueba en el método original. No se emite documento fiscal ni se procesa un abono bancario.</small>'),{order:o.id});
 }
 if(a==='fiscal'){const [order,invoice]=v.split(',');command('fiscal',{order,invoice});}
 if(a==='pay'){
  const o=picked();if(!o||o.closed)return;
  modal('Dividir cuenta','<p>Elige cómo repartir lo que falta por pagar. Cada persona puede usar un método de pago diferente.</p><div class="split-options">'+(!o.equalSplit?action('splitPerson','Por persona<br><small>Crear personas o asignar lo que consumió cada una.</small>','','primary'):'')+(!o.equalSplit&&o.invoiceMode!=='person'?action('splitProducts','Por productos<br><small>Cada persona elige lo que consumió.</small>','','primary'):'')+(o.invoiceMode!=='person'?action('splitEqual','En partes iguales<br><small>Reparte el total entre varias personas.</small>','','primary'):'')+'</div>');
 }
 if(a==='splitPerson')openPersonPayment();
 if(a==='sendForPersonPay')command('send',{order:v},openPersonPayment);
 if(a==='cancelOrder'){const o=picked();if(o&&o.id===v)modal('Cancelar cuenta · '+orderName(o),'<p>La mesa quedará libre. Se conservarán el pedido, el usuario y el motivo. Las comandas se retirarán de Cocina y Barra. Si ya se prepararon productos, registra la merma correspondiente.</p>'+form('cancel-order',input('reason','Motivo de la cancelación','text','minlength="3" maxlength="180" required')),{order:o.id,confirmed:true});}
 if(a==='splitEqual')openEqualPayment();
 if(a==='splitProducts'||a==='charge'){
  const o=picked(),unpaid=o.lines.filter(l=>!l.payment);
  if(o.invoiceMode==='person'){openPersonPayment();return;}
  if(o.equalSplit){openEqualPayment();return;}
  if(!unpaid.length){flash('Selecciona partidas pendientes.',true);return;}
  const check=unpaid.map(l=>'<label class="check"><input type="checkbox" name="lines" value="'+l.id+'" '+(a==='charge'?'checked':'')+'>'+title(l)+' · '+money(l.cents)+'</label>').join('');
  modal(a==='charge'?'Cobrar · '+orderName(o):'Dividir cuenta',form('pay',check+'<div id="payment-total">'+prices(totals(a==='charge'?unpaid:[],o.service))+'</div>'+
   '<p>Una factura para la mesa. Para facturas separadas usa Dividir y cobrar → Por persona.</p>'+select('method','Método de pago',[['efectivo','Efectivo'],['tarjeta','Tarjeta'],['transferencia','Transferencia']])+
   select('kind','Comprobante de prueba',[['E32','Consumo electrónico E32'],['E31','Crédito fiscal E31']],o.billing?.kind)+input('rnc','RNC para E31','text','inputmode="numeric" value="'+esc(o.billing?.rnc)+'"')+'<small>Comprobante simulado. Sin envío a DGII.</small>'),{order:o.id});
 }
 if(a==='edit'){
  const p=state.products.find(p=>p.id===v)||{};
  const attrs=x=>'value="'+esc(x)+'"';
  const recipe=p.id==='mojito'?'<h3>Receta del mojito</h3>'+Object.entries(state.ingredients).map(([k,i])=>input('recipe_'+k,esc(i.name)+' ('+i.unit+')','number','min="0" '+attrs(p.recipe?.[k]||0))).join(''):'';
  modal(p.id?'Editar producto':'Nuevo producto',form('product',
   input('name','Nombre','text',attrs(p.name)+' required')+input('category','Categoría','text',attrs(p.category)+' required')+
   input('description','Descripción para el menú digital','text','maxlength="600" '+attrs(p.description||''))+
   input('price','Precio (RD$)','number','min="0" step=".01" '+attrs(p.cents==null?'':p.cents/100)+' required')+
   input('happyPrice','Precio happy hour (RD$)','number','min="0" step=".01" '+attrs(p.happy==null?'':p.happy/100))+
   select('tax','ITBIS',[[0,'Exento'],[16,'16 %'],[18,'18 %']],p.tax??18)+
   select('station','Estación',stationEntries(),p.station||(['retail','quick'].includes(state.setup?.business)?'ninguna':stationEntries()[0][0]))+
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

function openPersonPayment(){
 const o=picked();if(!o||o.closed)return;
 const pending=o.lines.filter(l=>!l.payment),people=o.guests||[];
 if(!pending.length){modal('Cuenta sin productos pendientes','<p>Agrega productos al pedido o revisa los pagos ya registrados.</p>');return;}
 if(!people.length){modal('Crea las personas de esta cuenta','<p>Agrega un nombre por persona. Después podrás asignar sus productos y elegir una factura de mesa o facturas separadas.</p>'+action('createGuest','+ Crear persona','','primary'));return;}
 if(pending.some(l=>!people.some(g=>g.id===l.guest))){
  const fields=pending.map((l,i)=>select('guest_'+l.id,'Producto '+(i+1)+' · '+l.name+' · '+money(l.cents),[['','Elegir persona'],...people.map(g=>[g.id,g.name])],people.some(g=>g.id===l.guest)?l.guest:'').replace('<select','<select required')).join('');
  modal('Asignar productos a personas','<p>Ya creaste las personas. Ahora indica quién consumió cada producto. Los productos de Cuenta general o Compartido deben asignarse para facturar por persona.</p>'+form('guest-distribute',fields),{order:o.id});return;
 }
 if(pending.some(l=>l.status==='pendiente')){modal('Enviar pedido antes de cobrar','<p>Hay productos pendientes de enviar a Cocina o Barra. Puedes enviarlos y continuar al cobro por persona.</p>'+action('sendForPersonPay','Enviar comanda y continuar',o.id,'primary'));return;}
 const guests=(o.guests||[]).filter(g=>o.lines.some(l=>l.guest===g.id&&!l.payment));
 if(!guests.length){flash('Crea personas y asigna sus productos antes de cobrar por persona.',true);return;}
 const paid=state.payments.some(p=>p.order===o.id),mode=o.invoiceMode||'table';
 const modes=[['table','Una factura para la mesa'],['person','Facturas separadas por persona']];
 const modeField=paid?line('Facturación fijada',mode==='table'?'Una factura para la mesa':'Facturas separadas por persona')+'<input type="hidden" name="invoiceMode" value="'+mode+'">':select('invoiceMode','¿Cómo se hará la factura?',modes,mode)+'<p class="muted">Elige antes del primer pago. Después no se puede cambiar. Para facturas separadas, asigna todos los productos de Cuenta general y Compartido.</p>';
 const lines=o.lines.filter(l=>l.guest===guests[0].id&&!l.payment);
 modal('Cobrar por persona · '+orderName(o),form('pay',select('guest','Persona que paga',guests.map(g=>[g.id,g.name]),guests[0].id)+'<div id="person-total">'+prices(totals(lines,o.service))+'</div>'+modeField+
 select('method','Método de pago',[['efectivo','Efectivo'],['tarjeta','Tarjeta'],['transferencia','Transferencia']])+
 select('kind','Comprobante de prueba',mode==='table'&&o.billing?[[o.billing.kind,o.billing.kind==='E31'?'Crédito fiscal E31':'Consumo electrónico E32']]:[['E32','Consumo electrónico E32'],['E31','Crédito fiscal E31']],mode==='table'?o.billing?.kind:undefined)+input('rnc','RNC para E31','text','inputmode="numeric" value="'+esc(mode==='table'?o.billing?.rnc:'')+'" '+(mode==='table'&&o.billing?'readonly':''))+
 input('buyer','Razón social para E31','text','maxlength="150" value="'+esc(mode==='table'?o.billing?.buyer:'')+'" '+(mode==='table'&&o.billing?'readonly':''))+
 '<p class="muted">E31 requiere el RNC y, en facturas separadas, la razón social de ese comprador. Los productos pagados no se facturan de nuevo.</p><p>Pago y comprobante se registran por separado. Comprobantes simulados, sin envío a DGII.</p>'),{order:o.id,split:'person'});
}
document.addEventListener('click',e=>{
 if(e.target.closest('[data-action="recalculateSplit"]')){
  const n=Number($('#modal input[name="people"]').value);
  if(!Number.isInteger(n)||n<2||n>30){flash('Indica entre 2 y 30 personas.',true);return;}
  openEqualPayment(n);
 }
});
document.addEventListener('input',e=>{
 if(e.target.closest('#digital-form'))menuUnsaved=true;
 if(e.target.id==='guest-add')guestToAdd=e.target.value;
 if(e.target.dataset.floorField&&floorEditing){
  const t=floorDraft.find(t=>t.number===floorSelection),key=e.target.dataset.floorField;
  if(t)t[key]=['x','y','seats'].includes(key)?Number(e.target.value):e.target.value;
 }
 if(e.target.name==='guest'&&$('#person-total')&&formData?.split==='person'){
  const o=picked();$('#person-total').innerHTML=prices(totals(o.lines.filter(l=>l.guest===e.target.value&&!l.payment),o.service));
 }
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
 if(type==='review-business-change'){
  modal('Confirmar cambio de negocio','<p>Vas a cambiar de <strong>'+esc(businessTypes.find(([id])=>id===payload.previousBusiness)?.[1])+'</strong> a <strong>'+esc(businessTypes.find(([id])=>id===payload.business)?.[1])+'</strong>.</p><p>Se conservarán las mesas, los productos, las estaciones, las cuentas abiertas y las ventas. El asistente inicial no volverá a mostrarse.</p>'+action('confirmBusinessChange','Confirmar cambio','','primary'),{business:payload.business,previousBusiness:payload.previousBusiness});return;
 }
 if(type==='open')payload.fund=cash(values.fund);
 if(type==='order')payload.people=values.people?Number(values.people):undefined;
 if(type==='table'){payload.number=Number(values.number);payload.active=values.active==='yes';}
 if(type==='setup-tables'||type==='tables-config'){payload.count=Number(values.count);payload.enabled=values.enabled==='yes';}
 if(type==='stations-config'){payload.kitchen=values.kitchen==='yes';payload.bar=values.bar==='yes';}
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
 if(type==='guest-distribute'){payload.assignments=picked().lines.filter(l=>!l.payment).map(l=>({line:l.id,guest:values['guest_'+l.id]}));for(const k of Object.keys(payload))if(k.startsWith('guest_'))delete payload[k];}
 if(['menu-save','menu-save-publish'].includes(type)){
  payload.revision=state.publicMenu?.revision||0;payload.enabled=values.enabled==='yes';payload.interval=Number(values.interval);
  const published=new Set(data.getAll('published')),available=new Set(data.getAll('available'));
  payload.items=state.products.map(p=>({id:p.id,published:published.has(p.id),available:available.has(p.id)}));
  payload.logo=data.has('removeLogo')?'':state.publicMenu?.draft?.logo||'';
  if(values.logoUpload?.size){if(values.logoUpload.size>120000){flash('El logo supera 120 KB.',true);return;}payload.logo=await new Promise(resolve=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.readAsDataURL(values.logoUpload);});}
  delete payload.logoUpload;delete payload.published;delete payload.available;delete payload.removeLogo;
 }
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
$('#role').addEventListener('change',()=>{roleInitialized=false;refresh().catch(e=>flash(e.message,true));});
refresh().catch(e=>flash(e.message,true));
stationPoll=setInterval(()=>{if(!locked&&!$('#modal').open&&!floorEditing&&['Cocina','Barra','Mesas'].includes(mode))refresh().catch(()=>flash('Sin conexión con la caja.',true));},2500);

let floorDrag;
document.addEventListener('pointerdown',e=>{
 const node=e.target.closest?.('.floor-table');if(e.pointerType==='touch'||!floorEditing||!node||$('#role').value!=='supervisor')return;
 const svg=node.closest('.floor-canvas'),t=floorDraft.find(t=>t.number===Number(node.dataset.value));
 const point=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
 floorSelection=t.number;floorDrag={svg,node,table:t,start:point,x:t.x,y:t.y};svg.setPointerCapture(e.pointerId);
});
document.addEventListener('pointermove',e=>{
 if(!floorDrag)return;floorDrag.moved=true;const {svg,node,table,start,x,y}=floorDrag,d=floorDimensions();
 const point=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
 table.x=Math.round(Math.min(100,Math.max(0,x+(point.x-start.x)/(d.w-d.tw-24)*100))*10)/10;
 table.y=Math.round(Math.min(100,Math.max(0,y+(point.y-start.y)/(d.h-d.th-24)*100))*10)/10;
 node.setAttribute('transform','translate('+(12+table.x/100*(d.w-d.tw-24))+','+(12+table.y/100*(d.h-d.th-24))+')');
});
document.addEventListener('pointerup',e=>{if(floorDrag){const {svg,moved}=floorDrag;floorDrag=undefined;if(svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId);requestAnimationFrame(()=>{if(floorEditing)render();}); }});
document.addEventListener('pointercancel',()=>{floorDrag=undefined;});
document.addEventListener('keydown',e=>{const node=e.target.closest?.('.floor-table');if(node&&['Enter',' '].includes(e.key)){e.preventDefault();node.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});

function digitalMenuSettings(){
 if($('#role').value!=='supervisor'){digitalMenuOpen=false;return posSettings();}
 const m=state.publicMenu||{},d=m.draft||{name:$('header p').textContent.replace('UNO360X POS / ',''),enabled:true,interval:12,items:[]};
 const live=Boolean(m.live?.enabled),url=m.token?publicMenuOrigin+'/menu-pos/'+m.token+'/':'';
 const rows=state.products.map(p=>{
  const i=d.items.find(i=>i.id===p.id)||{published:false,available:p.available!==false},photo=p.photo?.startsWith('data:')?p.photo:p.photo?basePath+'/images/'+p.photo:'';
  return '<div class="digital-row"><div class="digital-product">'+(photo?'<img src="'+esc(photo)+'" alt="">':'<span class="digital-icon">🍽</span>')+'<div><strong>'+title(p)+'</strong><small>'+esc(p.category)+'</small></div></div><strong class="digital-price">'+money(p.cents)+'</strong><label class="digital-toggle"><span>Disponible</span><input type="checkbox" name="available" aria-label="Disponible '+esc(p.name)+'" value="'+esc(p.id)+'" '+(i.available?'checked':'')+'></label><label class="digital-toggle"><span>Publicar</span><input type="checkbox" name="published" aria-label="Publicar '+esc(p.name)+'" value="'+esc(p.id)+'" '+(i.published?'checked':'')+'></label></div>';
 }).join('');
 return panel('Tu catálogo, listo para mostrar','<p class="muted">Publica los productos del POS que quieras mostrar a tus clientes.</p><div class="actions">'+action('digitalBack','Volver a Ajustes')+action('previewDigital','Vista previa')+action('publishDigital','Publicar menú','','primary')+'</div>')+
 '<div class="digital-layout"><section class="panel"><form id="digital-form" data-command="menu-save-publish">'+
 input('name','Nombre del negocio','text','maxlength="100" minlength="2" required value="'+esc(d.name)+'"')+
 '<div class="digital-fields">'+select('enabled','Menú público',[['yes','Activado'],['no','Desactivado']],d.enabled?'yes':'no')+input('interval','Rotar pantalla cada (segundos)','number','min="8" max="60" value="'+d.interval+'" required')+'</div>'+
 input('logoUpload','Logo del negocio (opcional, hasta 120 KB)','file','accept="image/png,image/jpeg,image/webp"')+(d.logo?'<label class="check"><input type="checkbox" name="removeLogo">Quitar logo actual</label>':'')+
 '<p class="muted">Estado: '+(m.dirty?'Cambios guardados sin publicar':live?'Publicado':'No publicado')+'. Quita o marca los productos y pulsa Guardar y publicar cambios para actualizar el menú. Los precios, descripciones y fotos publicados se actualizan desde el catálogo.</p><div class="actions">'+action('allDigital','Seleccionar todos')+'</div><div class="digital-list">'+(rows||'<p>Agrega productos desde Menú antes de publicar.</p>')+'</div><p class="muted">Los agotados se muestran como No disponible. La disponibilidad también se respeta al agregar productos a una cuenta del POS.</p><button class="primary" type="submit">Guardar y publicar cambios</button></form></section>'+
 panel('Tu menú público',live?'<img class="digital-qr" src="'+url+'qr.svg" alt="QR para abrir el menú"><p>Un enlace para este negocio. No pide iniciar sesión.</p><div class="actions"><a class="digital-link" href="'+url+'" target="_blank" rel="noopener noreferrer">Abrir menú en celular</a><a class="digital-link" href="'+url+'?view=tv" target="_blank" rel="noopener noreferrer">Abrir en televisor</a><a class="digital-link" href="'+url+'qr.svg" download="UNO360X-menu-QR.svg">Descargar QR</a></div><label>Enlace del menú<input readonly value="'+url+'"></label>':'<p>Selecciona los productos y pulsa Guardar y publicar cambios para generar el menú y su QR.</p>')+'</div>'+panel('Precios e impuestos claros','<p>Se muestran el precio base, el ITBIS de cada producto y la propina legal para consumo en el local. El menú es solo de consulta y no permite ordenar ni pagar.</p>');
}
async function previewDigitalMenu(){
 if($('#role').value!=='supervisor'||!$('#digital-form'))return;
 const form=new FormData($('#digital-form')),name=String(form.get('name')||'').trim()||'Tu negocio';
 const selected=new Set(form.getAll('published')),available=new Set(form.getAll('available'));
 let logo=form.has('removeLogo')?'':state.publicMenu?.draft?.logo||'';
 try{
  const upload=form.get('logoUpload');
  if(upload?.size){
   if(upload.size>120000||!['image/png','image/jpeg','image/webp'].includes(upload.type))throw Error('Usa un logo JPG, PNG o WebP de hasta 120 KB.');
   logo=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(Error('No pudimos leer el logo. Intenta seleccionarlo de nuevo.'));r.readAsDataURL(upload);});
  }
  const rows=state.products.filter(p=>selected.has(p.id)).map(p=>{
   const photo=p.photo?.startsWith('data:')?p.photo:p.photo?basePath+'/images/'+p.photo:'';
   return '<div class="digital-preview-item">'+(photo?'<img src="'+esc(photo)+'" alt="">':'')+'<div><strong>'+title(p)+'</strong><p>'+esc(p.description||p.category)+'</p><strong>'+money(p.cents)+'</strong><small>'+(available.has(p.id)?'Disponible':'No disponible')+' · '+(p.tax?'ITBIS '+p.tax+'% adicional':'Exento de ITBIS')+'</small></div></div>';
  }).join('');
  modal('Vista previa · '+esc(name),(logo?'<img class="digital-preview-logo" src="'+esc(logo)+'" alt="Logo del negocio">':'')+'<p>Así se ve tu selección actual. Esta vista no guarda ni publica cambios.</p>'+(rows||'<p role="status">Selecciona al menos un producto en Publicar para verlo aquí.</p>'));
 }catch(e){modal('No se pudo abrir la vista previa','<p role="alert">'+esc(e.message)+'</p>');}
}
