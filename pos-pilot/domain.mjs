
export const money = c => new Intl.NumberFormat('es-DO',{style:'currency',currency:'DOP'}).format(c/100);
export const products = [
 {id:'burger',name:'Hamburguesa',category:'Comida',cents:45000,tax:18,station:'cocina',photo:'burger.jpg',modifiers:['Sin cebolla','Bien cocida']},
 {id:'wings',name:'Alitas',category:'Comida',cents:42000,tax:18,station:'cocina',photo:'wings.jpg',modifiers:['BBQ','Picante']},
 {id:'mojito',name:'Mojito',category:'Bebidas',cents:30000,happy:25000,tax:18,station:'barra',photo:'mojito.jpg',modifiers:['Sin hielo','Poco dulce'],recipe:{ron:45,limon:25,jarabe:20,menta:8,soda:60}},
];
export const seed = ({demo=false}={}) => ({...(demo?{}:{setup:{step:'business',business:null,tablesEnabled:true,completed:false}}),tables:defaultTables(),shift:null,orders:[],payments:[],audits:[],events:[],operations:{},products:demo?structuredClone(products):[],
 ingredients:{ron:{name:'Ron blanco',unit:'ml',stock:2500,cost:55},limon:{name:'Jugo de limón',unit:'ml',stock:1200,cost:16},jarabe:{name:'Jarabe',unit:'ml',stock:900,cost:12},menta:{name:'Hierbabuena',unit:'hojas',stock:120,cost:50},soda:{name:'Soda',unit:'ml',stock:2000,cost:6}}});
export function totals(lines,service) {
 const subtotal=lines.reduce((a,l)=>a+l.cents,0);
 const tax=lines.reduce((a,l)=>a+Math.round(l.cents*l.tax/100),0);
 const tip=service==='mesa'||service==='barra'? lines.reduce((a,l)=>a+Math.round(l.cents/10),0):0;
 return {subtotal,tax,tip,total:subtotal+tax+tip};
}
const id=()=>globalThis.crypto.randomUUID();
function fail(ok,msg){if(!ok)throw new Error(msg);}
const role=(user,...roles)=>fail(roles.includes(user),'Este rol no tiene permiso para esta operación.');
const nonnegative=(n,max=100000000)=>Number.isSafeInteger(n)&&n>=0&&n<=max;
const label=(s,max=100)=>String(s??'').trim().slice(0,max);
const log=(s,user,action,details)=>s.audits.push({user,action,details,at:new Date().toISOString()});
function defaultTables(){return Array.from({length:5},(_,i)=>({number:i+1,name:'Mesa '+String(i+1).padStart(2,'0'),active:true}));}
export function restaurantTables(s){
 const tables=structuredClone(s.tables||defaultTables());
 for(const o of s.orders.filter(o=>!o.closed&&o.table))if(!tables.some(t=>t.number===o.table))tables.push({number:o.table,name:'Mesa '+String(o.table).padStart(2,'0'),active:true});
 return tables.sort((a,b)=>a.number-b.number);
}
export function equalShares(total,people){
 fail(Number.isSafeInteger(total)&&total>0&&Number.isInteger(people)&&people>=2&&people<=30&&total>=people,'Indica entre 2 y 30 personas para dividir la cuenta.');
 return Array.from({length:people},(_,i)=>Math.floor(total/people)+(i<total%people?1:0));
}
export const businessTypes=[['restaurant','Restaurante y bar'],['bakery','Cafetería y panadería'],['retail','Tienda y comercio'],['quick','Venta rápida']];
export const setupRequired=s=>Boolean(s.setup&&!s.setup.completed);
function configureTables(s,enabled,count){
 fail(typeof enabled==='boolean'&&Number.isInteger(count)&&count>=1&&count<=200,'Indica entre 1 y 200 mesas.');
 fail(!s.orders.some(o=>!o.closed&&o.table&&(!enabled||o.table>count)),'Hay mesas con cuentas abiertas. Ciérralas antes de reducir o desactivar el salón.');
 const tables=restaurantTables(s);
 const previousCount=s.setup.tableCount||5,wasEnabled=s.setup.tablesEnabled;
 for(let number=1;number<=count;number++)if(!tables.some(t=>t.number===number))tables.push({number,name:'Mesa '+String(number).padStart(2,'0'),active:enabled});
 for(const t of tables){if(t.archived){t.active=false;continue;}if(!enabled||t.number>count)t.active=false;else if(!wasEnabled||t.number>previousCount)t.active=true;}
 s.tables=tables;s.setup.tablesEnabled=enabled;s.setup.tableCount=count;
}
export function apply(s,command,user,actor=user,staff=[]){
 const {type}=command;
 if(['zone-archive','zone-restore','table-archive'].includes(type))return archiveFloorItem(s,command,user,actor);
 if(['menu-save','menu-publish'].includes(type))return digitalMenuCommand(s,command,user,actor);
 if(type==='staff-role'){
  role(user,'supervisor');fail(staff.some(p=>p.id===command.account)&&['caja','camarero','cocina','barra'].includes(command.role),'Selecciona un usuario habilitado de esta empresa y un rol del POS.');
  (s.staffRoles??={})[command.account]=command.role;log(s,actor,'rol del equipo POS',{account:command.account,role:command.role});return {account:command.account,role:command.role};
 }
 if(['floor-save','zone-save'].includes(type)){fail(!setupRequired(s),'Completa primero la configuración inicial.');return configureFloor(s,command,user,actor);}
 if(['business-change','tables-config','stations-config'].includes(type)){
  role(user,'supervisor');fail(!setupRequired(s),'Completa primero la configuración inicial.');
  s.setup??={business:'restaurant',tablesEnabled:true,tableCount:Math.max(5,...restaurantTables(s).filter(t=>t.active).map(t=>t.number)),completed:true,step:'products'};
  if(type==='business-change'){
   fail(command.confirmed===true,'Confirma el cambio de tipo de negocio desde Ajustes del POS.');
   fail(command.previousBusiness===s.setup.business,'El tipo de negocio cambió. Revisa los ajustes antes de confirmar.');
   fail(businessTypes.some(([id])=>id===command.business)&&command.business!==s.setup.business,'Selecciona un tipo de negocio diferente.');
   const previous=s.setup.business;s.setup.business=command.business;
   log(s,actor,'cambio de tipo de negocio POS',{previous,next:command.business,confirmed:true});return s.setup;
  }
  if(type==='tables-config'){
   configureTables(s,command.enabled,command.count);
   log(s,actor,'ajustes de mesas POS',{enabled:command.enabled,count:command.count});return s.setup;
  }
  fail(typeof command.kitchen==='boolean'&&typeof command.bar==='boolean','Selecciona el estado de Cocina y Barra.');
  for(const [station,enabled] of [['cocina',command.kitchen],['barra',command.bar]]){
   fail(enabled||!s.products.some(p=>p.station===station),'Reasigna los productos de '+station+' antes de desactivar esa estación.');
   fail(enabled||!s.orders.some(o=>!o.closed&&o.lines.some(l=>l.station===station&&l.status!=='lista')),'Hay comandas pendientes en '+station+'.');
  }
  s.setup.stations={cocina:command.kitchen,barra:command.bar};log(s,actor,'ajustes de estaciones POS',s.setup.stations);return s.setup;
 }
 if(type.startsWith('setup-')){
  role(user,'supervisor');
  fail(setupRequired(s),'Este POS ya está configurado. Usa Ajustes del POS.');
  if(type==='setup-business'){
   fail(businessTypes.some(([id])=>id===command.business),'Selecciona un tipo de negocio.');
   const tableBusiness=['restaurant','bakery'].includes(command.business);
   if(!tableBusiness)configureTables(s,false,s.setup.tableCount||5);
   s.setup.business=command.business;s.setup.step=tableBusiness?'tables':'products';
   log(s,actor,'tipo de negocio POS',{business:command.business});return s.setup;
  }
  if(type==='setup-step'){
   fail(['business','tables','products'].includes(command.step)&&(!['tables','products'].includes(command.step)||s.setup.business),'Paso de configuración inválido.');
   s.setup.step=command.step;return s.setup;
  }
  fail(s.setup.business,'Selecciona primero el tipo de negocio.');
  if(type==='setup-tables'){
   fail(['restaurant','bakery'].includes(s.setup.business),'Este tipo de negocio trabaja sin mesas.');
   configureTables(s,command.enabled,command.count);s.setup.step='products';
   log(s,actor,'configuración inicial de mesas',{enabled:command.enabled,count:command.count});return s.setup;
  }
  if(type==='setup-examples'){
   if(s.setup.examplesLoaded)return {added:0};
   const examples=s.setup.business==='restaurant'?products:s.setup.business==='bakery'?[
    {id:'example-coffee',name:'Café',category:'Bebidas',cents:10000,tax:18,station:'barra',photo:'',modifiers:[]},
    {id:'example-bread',name:'Pan',category:'Panadería',cents:2500,tax:0,station:'ninguna',photo:'',modifiers:[]}
   ]:[{id:'example-water',name:'Agua embotellada',category:'Bebidas',cents:5000,tax:18,station:'ninguna',photo:'',modifiers:[]}];
   const added=examples.filter(p=>!s.products.some(old=>old.id===p.id));
   s.products.push(...structuredClone(added));s.setup.examplesLoaded=true;
   log(s,actor,'productos de ejemplo',{count:added.length});return {added:added.length};
  }
  if(type==='setup-finish'){
   fail(s.setup.step==='products','Completa los pasos de configuración antes de abrir el POS.');
   s.setup.completed=true;s.setup.completedAt=new Date().toISOString();
   log(s,actor,'configuración POS completada',{business:s.setup.business,products:s.products.length});return s.setup;
  }
  throw new Error('Paso de configuración desconocido.');
 }
 if(setupRequired(s))fail(['product','table'].includes(type),'El administrador debe completar la configuración inicial del POS.');
 if(type==='table'){
  role(user,'supervisor');const number=command.number,name=label(command.name,40);
  fail(Number.isInteger(number)&&number>=1&&number<=200&&name&&typeof command.active==='boolean','Indica un número de mesa de 1 a 200 y su nombre.');
  const tables=restaurantTables(s),table=tables.find(t=>t.number===number);
  fail(command.active||!s.orders.some(o=>!o.closed&&o.table===number),'No puedes desactivar una mesa con una cuenta abierta.');
  const previous=table?{...table}:null,next={number,name,active:command.active,archived:false};
  if(table){Object.assign(table,next);if(command.active&&!floorZones(s).some(z=>z.id===(table.zone||'salon')))table.zone=floorZones(s)[0].id;}else tables.push(next);s.tables=tables;
  if(s.setup&&command.active)s.setup.tableCount=Math.max(s.setup.tableCount||5,number);
  if(s.floor)s.floor.version=(s.floor.version||0)+1;
  log(s,actor,'configuración de mesa',{previous,next});return next;
 }
 if(type==='open'){
  role(user,'caja','supervisor');fail(!s.shift||s.shift.closed,'Ya hay un turno abierto.');
  fail(nonnegative(command.fund),'Fondo inválido.');
  return s.shift={id:id(),fund:command.fund,user:actor,opened:new Date().toISOString()};
 }
 if(type==='product'){
  role(user,'supervisor');
  const name=label(command.name),category=label(command.category,40),p=s.products.find(p=>p.id===command.id);
  fail(name&&category&&nonnegative(command.cents)&&[0,16,18].includes(command.tax)&&['cocina','barra','ninguna'].includes(command.station),'Datos del producto inválidos.');
  fail(command.station==='ninguna'||s.setup?.stations?.[command.station]!==false,'La estación está desactivada. Actívala en Ajustes del POS.');
  const photo=String(command.photo||'');
  fail(!photo||['burger.jpg','wings.jpg','mojito.jpg'].includes(photo)||/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(photo)&&photo.length<=700000,'Imagen inválida o grande.');
  const recipe=p?.recipe||{};
  if(p&&command.recipe) for(const k of Object.keys(s.ingredients)){
   fail(nonnegative(command.recipe[k],10000),'Cantidad de receta inválida.');
   if(command.recipe[k]) recipe[k]=command.recipe[k]; else delete recipe[k];
  }
  const happy=command.happy;
  fail(happy==null||nonnegative(happy),'Precio de happy hour inválido.');
  const next={id:p?.id||id(),name,category,cents:command.cents,tax:command.tax,station:command.station,photo,happy,
   description:command.description==null?(p?.description||''):label(command.description,600),available:p?.available!==false,
   modifiers:String(command.modifiers||'').split(',').map(v=>label(v,40)).filter(Boolean).slice(0,12),recipe};
  if(p) Object.assign(p,next);else s.products.push(next);
  return next;
 }
 if(type==='waste'||type==='count'){
  role(user,'barra','supervisor');const item=s.ingredients[command.ingredient];
  fail(item&&nonnegative(command.quantity,100000),'Cantidad inválida.');
  if(type==='waste')fail(command.quantity>0&&item.stock>=command.quantity&&label(command.reason),'Indica una merma válida y su motivo.');
  const event={type,reference:id()+':'+command.ingredient,ingredient:command.ingredient,quantity:command.quantity,expected:item.stock,
   difference:type==='count'?command.quantity-item.stock:-command.quantity,user:actor,reason:label(command.reason),at:new Date().toISOString()};
  if(type==='waste')item.stock-=command.quantity;
  s.events.push(event);return event;
 }
 if(type==='fiscal'){
  role(user,'caja','supervisor');
  const order=s.orders.find(o=>o.id===command.order);
  const document=order&&invoicesFor(order).find(d=>!command.invoice||d.id===command.invoice);
  fail(document,'El comprobante no está disponible para este pedido.');
  return document;
 }
 fail(s.shift&&!s.shift.closed,'Abre un turno para operar la caja.');
 if(type==='close'){
  role(user,'caja','supervisor');fail(nonnegative(command.counted),'Efectivo contado inválido.');
  fail(!s.orders.some(o=>o.shift===s.shift.id&&!o.closed),'Hay pedidos abiertos en este turno.');
  return Object.assign(s.shift,{closed:new Date().toISOString(),userClosed:actor,counted:command.counted,...cashSummary(s),difference:command.counted-cashSummary(s).expected});
 }
 if(type==='refund'){
  role(user,'supervisor');
  const order=s.orders.find(o=>o.id===command.order&&o.shift===s.shift.id&&o.closed&&invoicesFor(o).length);
  fail(order,'La venta debe estar pagada y pertenecer al turno abierto.');
  const reason=label(command.reason,180);
  const selection=command.lines;
  fail(reason&&Array.isArray(selection)&&selection.length&&new Set(selection).size===selection.length,
   'Selecciona partidas y escribe el motivo.');
  const lines=selection.map(ref=>order.lines.find(l=>l.id===ref));
  fail(lines.every(l=>l?.payment&&!l.refund),'Alguna partida no está pagada o ya fue devuelta.');
  const methods={efectivo:0,tarjeta:0,transferencia:0};
  if(order.equalSplit){
   fail(lines.length===order.lines.length,'Una cuenta dividida en partes iguales se devuelve completa.');
   for(const payment of s.payments.filter(p=>p.order===order.id))methods[payment.method]+=payment.amount;
  }else for(const l of lines){
   const payment=s.payments.find(p=>p.id===l.payment&&p.order===order.id);
   fail(payment,'Falta el pago original.');
   methods[payment.method]+=totals([l],order.service).total;
  }
  const refund={id:id(),order:order.id,shift:order.shift,lines:selection,methods,reason,
   user:actor,amount:Object.values(methods).reduce((sum,n)=>sum+n,0),at:new Date().toISOString()};
  fail(methods.efectivo<=cashSummary(s).expected,'Efectivo insuficiente en esta caja.');
  (s.refunds??=[]).push(refund);
  for(const l of lines)l.refund=refund.id;
  log(s,actor,'devolución',{order:order.number,reference:refund.id,reason,amount:refund.amount});
  return refund;
 }
 if(type==='order'){
  role(user,'caja','camarero','supervisor');
  fail(['mesa','barra','llevar'].includes(command.service),'Tipo de pedido inválido.');
  if(command.service==='mesa')fail(s.setup?.tablesEnabled!==false&&restaurantTables(s).some(t=>t.number===command.table&&t.active)&&Number.isInteger(command.people)&&command.people>=1&&command.people<=30,'Mesa no habilitada o cantidad de personas inválida.');
  if(command.service==='mesa') fail(!s.orders.some(o=>!o.closed&&o.table===command.table),'Esa mesa ya tiene un pedido.');
  const assigned=staff.find(person=>person.id===(command.waiter||actor));
  fail(!command.waiter||assigned,'El responsable no está habilitado en esta empresa.');
  if(user==='camarero')fail(!command.waiter||command.waiter===actor,'Solo un supervisor puede asignar otra persona.');
  const waiter=assigned||{id:actor,name:actor};
  const o={id:id(),number:s.orders.length+1042,shift:s.shift.id,service:command.service,table:command.service==='mesa'?command.table:null,tableName:restaurantTables(s).find(t=>t.number===command.table)?.name,people:command.people,waiter:{id:waiter.id,name:waiter.name},guests:[],opened:new Date().toISOString(),lines:[],closed:false};
  s.orders.push(o);return o;
 }
 const o=s.orders.find(o=>o.id===command.order);
 fail(o&&o.shift===s.shift.id&&(!o.closed||type==='ready'),'Pedido cerrado o fuera del turno.');
 if(['guest-save','guest-assign','guest-distribute','invoice-mode','request-check'].includes(type))return guestCommand(s,o,command,user,actor);
 if(['add','send'].includes(type))ownOrder(o,user,actor);
 if(type==='cancel-order'){
  role(user,'supervisor');const reason=String(command.reason||'').trim();
  fail(command.confirmed===true&&reason.length>=3&&reason.length<=180,'Confirma la cancelación y escribe un motivo de 3 a 180 caracteres.');
  fail(!s.payments.some(p=>p.order===o.id)&&!invoicesFor(o).length,'La cuenta tiene pagos o comprobantes. Usa el proceso de devolución correspondiente.');
  o.cancelled={reason,user:actor,at:new Date().toISOString()};o.closed=true;
  for(const line of o.lines)line.status='anulada';
  log(s,actor,'cancelación de cuenta',{order:o.number,table:o.table,reason});return {cancelled:true,order:o.id};
 }
 if(type==='reassign'){
  role(user,'supervisor');
  const next=staff.find(person=>person.id===command.waiter),reason=label(command.reason,180);
  fail(o.service==='mesa'&&next&&reason,'Selecciona un responsable habilitado y escribe el motivo.');
  fail(o.waiter?.id!==next.id,'La mesa ya está asignada a esa persona.');
  const previous=o.waiter||null;o.waiter={id:next.id,name:next.name};
  log(s,actor,'reasignación de mesa',{order:o.number,table:o.table,previous,next:o.waiter,reason});
  return o.waiter;
 }
 if(type==='add'){
  role(user,'caja','camarero','supervisor');
  fail(!s.payments.some(p=>p.order===o.id),'La cuenta ya tiene pagos.');
  const p=s.products.find(p=>p.id===command.product);fail(p,'Producto inválido.');fail(p.available!==false,'Este producto está agotado.');
  fail(!command.guest||command.guest==='shared'||(o.guests||[]).some(g=>g.id===command.guest),'La persona no pertenece a esta mesa.');
  const modifiers=Array.isArray(command.modifiers)?command.modifiers.filter(m=>p.modifiers.includes(m)):[];
  const l={id:id(),product:p.id,name:p.name,cents:command.happy&&p.happy!=null?p.happy:p.cents,tax:p.tax,station:p.station,modifiers,note:label(command.note,180),recipe:structuredClone(p.recipe||{}),status:p.station==='ninguna'?'lista':'pendiente',guest:command.guest||null};
  o.lines.push(l);return l;
 }
 if(type==='send'){
  role(user,'caja','camarero','supervisor');const pending=o.lines.filter(l=>l.status==='pendiente');
  const batch=id();for(const l of pending){l.status='enviada';l.batch=batch;}
  return {cocina:pending.filter(l=>l.station==='cocina').length,barra:pending.filter(l=>l.station==='barra').length,batch};
 }
 if(type==='ready'){
  const l=o.lines.find(l=>l.id===command.line);fail(l?.status==='enviada','Comanda no disponible.');
  role(user,l.station,'supervisor');l.status='lista';return l;
 }
 if(type==='discount'){
  role(user,'supervisor');
  fail(!o.equalSplit,'La división ya tiene pagos; no se puede cambiar el importe.');
  const l=o.lines.find(item=>item.id===command.line);
  fail(l&&!l.payment&&nonnegative(command.cents,l.cents)&&command.cents>0&&label(command.reason),'Indica un descuento y su motivo.');
  l.cents-=command.cents;
  log(s,actor,'descuento',{order:o.number,line:l.id,cents:command.cents,reason:label(command.reason)});
  return l;
 }
 if(type==='void'){
  role(user,'supervisor');const l=o.lines.find(l=>l.id===command.line);
  fail(!o.equalSplit,'La división ya tiene pagos; no se puede cambiar el importe.');
  fail(l&&!l.payment&&label(command.reason),'Indica una partida sin pagar y un motivo.');
  log(s,actor,'anulación',{order:o.number,line:l.id,reason:label(command.reason)});
  o.lines=o.lines.filter(x=>x!==l);if(!o.lines.length)o.closed=true;
  return {voided:l.id};
 }
 if(type==='pay'){
  role(user,'caja','supervisor');
  if(command.invoiceMode!==undefined)guestCommand(s,o,{type:'invoice-mode',mode:command.invoiceMode},user,actor);
  const equal=command.split==='equal',byPerson=command.split==='person',separate=o.invoiceMode==='person';
  fail(!separate||byPerson,'Cobra por persona para conservar las facturas separadas.');
  const guest=byPerson&&(o.guests||[]).find(g=>g.id===command.guest);
  if(byPerson)fail(guest,'Selecciona una persona de esta mesa.');
  if(separate)fail(o.lines.every(l=>(o.guests||[]).some(g=>g.id===l.guest))&&!invoicesFor(o).some(d=>d.guest===guest.id),'Asigna todos los productos a personas y evita facturar una persona dos veces.');
  fail(!o.equalSplit||equal,'Continúa cobrando las partes de esta cuenta.');
  let amounts;
  if(equal){
   fail(o.lines.length>0&&!o.lines.some(l=>l.payment),'No se puede dividir una cuenta con productos ya pagados.');
   fail(o.equalSplit||!s.payments.some(p=>p.order===o.id),'La cuenta ya tiene pagos.');
   amounts=o.equalSplit?.amounts||equalShares(totals(o.lines,o.service).total,command.people);
   fail(!o.equalSplit||command.people===o.equalSplit.people,'La cantidad de personas ya quedó fijada con el primer pago.');
   fail(Number.isInteger(command.part)&&command.part>=0&&command.part<amounts.length&&!s.payments.some(p=>p.order===o.id&&p.equalPart===command.part),'Esa parte ya está pagada o no es válida.');
  }else if(!byPerson)fail(Array.isArray(command.lines)&&command.lines.length>0&&new Set(command.lines).size===command.lines.length,'Selecciona las partidas a cobrar.');
  fail(['efectivo','tarjeta','transferencia'].includes(command.method),'Método inválido.');
  const lines=equal?o.lines:byPerson?o.lines.filter(l=>l.guest===guest.id&&!l.payment):command.lines.map(k=>o.lines.find(l=>l.id===k));
  fail(lines.length>0&&lines.every(l=>l&&!l.payment),'Alguna partida ya está pagada o no hay productos pendientes.');
  fail(lines.every(l=>l.status!=='pendiente'),'Envía las comandas antes de cobrar.');
  const kind=command.kind,rnc=label(command.rnc,11);
  fail(['E31','E32'].includes(kind)&&(kind!=='E31'||/^[0-9]{9}$/.test(rnc)),'E31 requiere un RNC de nueve dígitos.');
  const buyer=label(command.buyer,150);
  if(separate&&kind==='E31')fail(buyer,'Completa la razón social del comprador para E31.');
  fail(separate||!o.billing||o.billing.kind===kind&&o.billing.rnc===(kind==='E31'?rnc:''),'Ya se eligió el comprobante para esta cuenta.');
  const use={};if(!equal||!o.equalSplit)for(const l of lines)for(const [key,qty] of Object.entries(l.recipe||{}))use[key]=(use[key]||0)+qty;
  fail(Object.entries(use).every(([k,n])=>s.ingredients[k]?.stock>=n),'Existencia insuficiente para registrar esta venta.');
  const record={id:id(),method:command.method,order:o.id,shift:o.shift,user:actor,lines:equal?[]:lines.map(l=>l.id),amount:equal?amounts[command.part]:totals(lines,o.service).total,...(equal?{equalPart:command.part}:{}),...(guest?{guest:guest.id}:{}),at:new Date().toISOString()};
  s.payments.push(record);
  if(equal)o.equalSplit={people:command.people,amounts};
  const settled=!equal||s.payments.filter(p=>p.order===o.id).length===amounts.length;
  if(settled)for(const l of lines)l.payment=record.id;
  for(const [k,n] of Object.entries(use)){s.ingredients[k].stock-=n;s.events.push({type:'sale',reference:record.id+':'+k,ingredient:k,quantity:n,payment:record.id});}
  o.invoiceMode??='table';
  const billing={kind,rnc:kind==='E31'?rnc:'',buyer:buyer||guest?.name||''};
  if(!separate)o.billing??=billing;
  else{
   const document=simulatedInvoice(o,lines,billing,guest);(o.invoices??=[]).push(document);record.invoice=document.id;
   for(const l of lines)l.invoice=document.id;
  }
  if(o.lines.every(l=>l.payment)){
   o.closed=true;
   if(!separate)o.fiscal=simulatedInvoice(o,o.lines,o.billing);
  }
  return record;
 }
 throw new Error('Operación desconocida.');
}
export function cashSummary(s){
 const methods={efectivo:0,tarjeta:0,transferencia:0};
 for(const p of s.payments.filter(p=>p.shift===s.shift?.id))methods[p.method]+=p.amount;
 const refunds={efectivo:0,tarjeta:0,transferencia:0};
 for(const refund of (s.refunds||[]).filter(r=>r.shift===s.shift?.id)){
  for(const method of Object.keys(refunds))refunds[method]+=refund.methods[method];
 }
 return {methods,refunds,expected:(s.shift?.fund||0)+methods.efectivo-refunds.efectivo};
}
export function margin(p,ingredients){const cost=Object.entries(p.recipe||{}).reduce((sum,[k,n])=>sum+n*ingredients[k].cost,0);
 return {cost,normal:p.cents-cost,happy:p.happy==null?null:p.happy-cost};}

const modelAssert=(ok,text)=>{if(!ok)throw Error(text);};
const manager=user=>modelAssert(user==='supervisor','Solo el administrador puede editar el plano.');
const clean=(v,n=60)=>String(v??'').trim().slice(0,n);
export const invoicesFor=o=>o.invoices|| (o.fiscal?[o.fiscal]:[]);
export const floorZones=s=>(s.floor?.zones||[{id:'salon',name:'Salón'},{id:'terraza',name:'Terraza'},{id:'barra',name:'Barra'}]).filter(z=>z.active!==false);
export function floorTables(s){
 const positions=[[6,5],[94,5],[50,45],[6,94],[94,94]];
 const tables=restaurantTables(s),rows=Math.ceil(tables.length/3);
 return tables.map((t,i)=>({zone:'salon',shape:'rect',seats:4,x:tables.length<=5?positions[i][0]:(i%3)*50,y:tables.length<=5?positions[i][1]:rows<=1?0:Math.floor(i/3)/(rows-1)*100,...t}));
}
export function configureFloor(s,command,user,actor){
 manager(user);const zones=floorZones(s),archived=(s.floor?.zones||[]).filter(z=>z.active===false);
 if(command.type==='zone-save'){
  const name=clean(command.name,35);modelAssert(name,'Escribe el nombre de la zona.');
  modelAssert(!zones.some(z=>z.name.toLowerCase()===name.toLowerCase()&&z.id!==command.id),'Ya existe una zona con ese nombre.');
  const zone=zones.find(z=>z.id===command.id);modelAssert(!command.id||zone,'Zona no disponible.');
  if(zone)zone.name=name;else zones.push({id:crypto.randomUUID(),name});
  s.floor={...s.floor,zones:[...zones,...archived],version:(s.floor?.version||0)+1};
  s.audits.push({user:actor,action:'zona del salón',details:{reason:name},at:new Date().toISOString()});return s.floor;
 }
 modelAssert(command.version===(s.floor?.version||0),'El plano cambió. Vuelve a abrirlo antes de guardar.');
 modelAssert(Array.isArray(command.tables)&&command.tables.length>0&&command.tables.length<=200&&new Set(command.tables.map(t=>t.number)).size===command.tables.length,'Plano inválido.');
 const tables=floorTables(s);
 for(const input of command.tables){
  const table=tables.find(t=>t.number===input.number);
  modelAssert(table&&(zones.some(z=>z.id===input.zone)||!table.active&&archived.some(z=>z.id===input.zone))&&['rect','round'].includes(input.shape)&&Number.isInteger(input.seats)&&input.seats>=1&&input.seats<=30&&['x','y'].every(k=>Number.isFinite(input[k])&&input[k]>=0&&input[k]<=100)&&clean(input.name,40),'Revisa la zona, posición, nombre y lugares de las mesas.');
  Object.assign(table,{zone:input.zone,shape:input.shape,seats:input.seats,x:input.x,y:input.y,name:clean(input.name,40)});
 }
 s.tables=tables;s.floor={zones:[...zones,...archived],version:(s.floor?.version||0)+1};
 s.audits.push({user:actor,action:'edición del plano',details:{reason:'Posiciones y configuración del salón guardadas'},at:new Date().toISOString()});return s.floor;
}
export function ownOrder(o,user,actor){modelAssert(user!=='camarero'||o.waiter?.id===actor,'Solo puedes modificar las mesas que atiendes.');}
export function guestCommand(s,o,command,user,actor){
 const type=command.type;
 modelAssert(['caja','supervisor','camarero'].includes(user),'Este rol no puede organizar la cuenta.');ownOrder(o,user,actor);
 if(type==='request-check'){o.checkRequested=true;return {requested:true};}
 const paid=s.payments.some(p=>p.order===o.id)||invoicesFor(o).length>0;
 if(type==='invoice-mode'){
  modelAssert(['caja','supervisor'].includes(user),'Solo Caja o el administrador elige la facturación.');
  modelAssert(['table','person'].includes(command.mode),'Elige una modalidad de facturación.');
  modelAssert(!paid||(o.invoiceMode||'table')===command.mode,'La modalidad ya está fijada por un pago o comprobante.');
  if(command.mode==='person')modelAssert(!o.equalSplit&&(o.guests||[]).length>0&&o.lines.length>0&&o.lines.every(l=>(o.guests||[]).some(g=>g.id===l.guest)),'Asigna todos los productos de Cuenta general y Compartido antes de facturar por persona.');
  o.invoiceMode=command.mode;return {mode:o.invoiceMode};
 }
 modelAssert(!paid,'La organización de personas y productos queda fija después del primer pago.');
 o.guests??=[];
 if(type==='guest-distribute'){
  const rows=command.assignments,pending=o.lines.filter(l=>!l.payment);
  modelAssert(Array.isArray(rows)&&rows.length===pending.length&&rows.length>0&&new Set(rows.map(r=>r.line)).size===rows.length,'Revisa todos los productos pendientes.');
  modelAssert(rows.every(r=>pending.some(l=>l.id===r.line)&&o.guests.some(g=>g.id===r.guest)),'Asigna cada producto a una persona de esta cuenta.');
  for(const r of rows)o.lines.find(l=>l.id===r.line).guest=r.guest;
  log(s,actor,'distribución por persona',{order:o.number,reason:'Asignación de productos antes del cobro'});return {assigned:rows.length};
 }
 if(type==='guest-save'){
  const guest=o.guests.find(g=>g.id===command.guest);modelAssert(!command.guest||guest,'Persona no disponible en esta mesa.');
  modelAssert(guest||o.guests.length<30,'Se permiten hasta 30 personas por pedido.');
  modelAssert(String(command.name??'').trim().length<=60,'El nombre debe tener hasta 60 caracteres.');
  const sequence=guest?o.guestSequence||o.guests.length:(o.guestSequence||o.guests.length)+1;
  const name=clean(command.name)||guest?.name||'Persona '+sequence;
  modelAssert(!o.guests.some(g=>g.id!==guest?.id&&g.name.toLowerCase()===name.toLowerCase()),'Ya existe una persona con ese nombre en esta mesa.');
  if(guest)guest.name=name;else{o.guests.push({id:crypto.randomUUID(),name});o.guestSequence=sequence;}
  return guest||o.guests.at(-1);
 }
 const line=o.lines.find(l=>l.id===command.line);modelAssert(line&&!line.payment,'Selecciona un producto pendiente.');
 modelAssert(!command.guest||command.guest==='shared'||o.guests.some(g=>g.id===command.guest),'La persona no pertenece a esta mesa.');
 line.guest=command.guest||null;return line;
}
export function simulatedInvoice(o,lines,billing,guest){
 const amount=totals(lines,o.service).total;
 return {id:crypto.randomUUID(),status:'Simulado · sin envío a DGII',...billing,guest:guest?.id||null,guestName:guest?.name||'',lines:lines.map(l=>l.id),amount,totals:totals(lines,o.service),created:new Date().toISOString(),route:billing.kind==='E32'&&amount<25000000?'RFCE':'ECF'};
}
export function publicState(s,user,actor){
 if(['supervisor','caja'].includes(user))return s;
 const out=structuredClone(s);delete out.publicMenu;out.operations={};out.audits=[];out.events=[];out.refunds=[];out.staffRoles={};
 const station=['cocina','barra'].includes(user);
 const owned=new Set(s.orders.filter(o=>o.waiter?.id===actor).map(o=>o.id));
 out.payments=station?[]:out.payments.filter(p=>owned.has(p.order));
 out.orders=out.orders.map(o=>{
  if(!station&&owned.has(o.id)){delete o.billing;delete o.fiscal;delete o.invoices;return o;}
  const meta={id:o.id,number:o.number,table:o.table,tableName:o.tableName,service:o.service,people:o.people,waiter:o.waiter,closed:o.closed,shift:o.shift,opened:o.opened,checkRequested:o.checkRequested,cancelled:o.cancelled,amountsHidden:true,lineCount:o.lines.length};
  meta.lines=station?o.lines.filter(l=>l.station===user).map(l=>({id:l.id,name:l.name,station:l.station,batch:l.batch,status:l.status,modifiers:l.modifiers,note:l.note})):[];
  return meta;
 });
 if(out.shift)out.shift={id:out.shift.id,opened:out.shift.opened,closed:out.shift.closed};
 for(const item of Object.values(out.ingredients))delete item.cost;
 if(station)out.products=out.products.map(p=>({id:p.id,name:p.name,category:p.category,station:p.station,photo:p.photo,modifiers:p.modifiers}));
 return out;
}


export function digitalMenuCommand(s,command,user,actor){
 role(user,'supervisor');fail(!setupRequired(s),'Completa la configuración inicial del POS.');
 const current=s.publicMenu||{revision:0};
 fail(Number.isInteger(command.revision)&&command.revision===current.revision,'El menú cambió. Vuelve a abrirlo antes de guardar.');
 if(command.type==='menu-save'){
  const name=String(command.name||'').trim(),logo=String(command.logo||'');
  fail(name.length>=2&&name.length<=100,'Escribe un nombre de negocio de 2 a 100 caracteres.');
  fail(typeof command.enabled==='boolean'&&Number.isInteger(command.interval)&&command.interval>=8&&command.interval<=60,'Revisa la activación y los segundos de rotación (8 a 60).');
  fail(!logo||/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(logo)&&logo.length<=180000,'Usa un logo JPG, PNG o WebP de hasta 120 KB.');
  fail(Array.isArray(command.items)&&command.items.length<=500&&new Set(command.items.map(i=>i.id)).size===command.items.length,'Revisa los productos del menú.');
  fail(command.items.every(i=>s.products.some(p=>p.id===i.id)&&typeof i.published==='boolean'&&typeof i.available==='boolean'),'Un producto no existe o su configuración no es válida.');
  fail(command.items.filter(i=>i.published).length<=120,'Publica hasta 120 productos por menú.');
  s.publicMenu={...current,token:current.token||crypto.randomUUID().replaceAll('-',''),revision:current.revision+1,dirty:true,
   draft:{name,logo,enabled:command.enabled,interval:command.interval,items:command.items.map(i=>({id:i.id,published:i.published,available:i.available}))}};
  log(s,actor,'borrador del menú digital',{products:command.items.filter(i=>i.published).length});return {saved:true};
 }
 fail(current.draft,'Guarda primero la configuración del menú.');
 const draft=current.draft;
 fail(!draft.enabled||draft.items.some(i=>i.published&&s.products.some(p=>p.id===i.id)),'Selecciona al menos un producto para publicar.');
 for(const i of draft.items){const p=s.products.find(p=>p.id===i.id);if(p)p.available=i.available;}
 s.publicMenu={...current,revision:current.revision+1,dirty:false,live:{...structuredClone(draft),publishedAt:new Date().toISOString()}};
 log(s,actor,'publicación del menú digital',{enabled:draft.enabled,products:draft.items.filter(i=>i.published).length});return {published:draft.enabled};
}

export function archiveFloorItem(s,command,user,actor){
 role(user,'supervisor');fail(!setupRequired(s),'Completa primero la configuración inicial.');
 fail(command.confirmed===true||command.type==='zone-restore','Confirma que deseas quitar este elemento del plano.');
 if(command.type==='table-archive'){
  const tables=restaurantTables(s),table=tables.find(t=>t.number===command.number);
  fail(table,'Mesa no disponible.');fail(!s.orders.some(o=>!o.closed&&o.table===table.number),'La mesa tiene una cuenta abierta. Ciérrala antes de quitarla.');
  table.active=false;table.archived=true;s.tables=tables;
  s.floor={...s.floor,zones:s.floor?.zones||floorZones(s),version:(s.floor?.version||0)+1};
  log(s,actor,'mesa retirada del plano',{number:table.number,name:table.name});return {archived:true};
 }
 const zones=s.floor?.zones||floorZones(s),zone=zones.find(z=>z.id===command.id);fail(zone,'Zona no disponible.');
 if(command.type==='zone-archive'){
  fail(floorZones(s).length>1,'Conserva al menos una zona activa.');
  const tables=floorTables(s).filter(t=>t.zone===zone.id);
  fail(!tables.some(t=>t.active||s.orders.some(o=>!o.closed&&o.table===t.number)),'Mueve o quita primero las mesas de esta zona; no debe tener cuentas abiertas.');zone.active=false;
 }else{fail(!zones.some(z=>z.id!==zone.id&&z.active!==false&&z.name.toLowerCase()===zone.name.toLowerCase()),'Hay otra zona activa con ese nombre. Renómbrala antes de restaurar.');zone.active=true;}
 s.floor={...s.floor,zones,version:(s.floor?.version||0)+1};
 log(s,actor,command.type==='zone-archive'?'zona retirada del plano':'zona restaurada',{id:zone.id,name:zone.name});return {archived:zone.active===false};
}
