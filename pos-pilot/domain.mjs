
export const money = c => new Intl.NumberFormat('es-DO',{style:'currency',currency:'DOP'}).format(c/100);
export const products = [
 {id:'burger',name:'Hamburguesa',category:'Comida',cents:45000,tax:18,station:'cocina',photo:'burger.jpg',modifiers:['Sin cebolla','Bien cocida']},
 {id:'wings',name:'Alitas',category:'Comida',cents:42000,tax:18,station:'cocina',photo:'wings.jpg',modifiers:['BBQ','Picante']},
 {id:'mojito',name:'Mojito',category:'Bebidas',cents:30000,happy:25000,tax:18,station:'barra',photo:'mojito.jpg',modifiers:['Sin hielo','Poco dulce'],recipe:{ron:45,limon:25,jarabe:20,menta:8,soda:60}},
];
export const seed = () => ({tables:defaultTables(),shift:null,orders:[],payments:[],audits:[],events:[],operations:{},products:structuredClone(products),
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
export function apply(s,command,user,actor=user,staff=[]){
 const {type}=command;
 if(type==='table'){
  role(user,'supervisor');const number=command.number,name=label(command.name,40);
  fail(Number.isInteger(number)&&number>=1&&number<=200&&name&&typeof command.active==='boolean','Indica un número de mesa de 1 a 200 y su nombre.');
  const tables=restaurantTables(s),table=tables.find(t=>t.number===number);
  fail(command.active||!s.orders.some(o=>!o.closed&&o.table===number),'No puedes desactivar una mesa con una cuenta abierta.');
  const previous=table?{...table}:null,next={number,name,active:command.active};
  if(table)Object.assign(table,next);else tables.push(next);s.tables=tables;
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
  fail(name&&category&&nonnegative(command.cents)&&[0,16,18].includes(command.tax)&&['cocina','barra'].includes(command.station),'Datos del producto inválidos.');
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
  fail(order?.fiscal,'El pedido todavía no tiene comprobante.');
  return order.fiscal;
 }
 fail(s.shift&&!s.shift.closed,'Abre un turno para operar la caja.');
 if(type==='close'){
  role(user,'caja','supervisor');fail(nonnegative(command.counted),'Efectivo contado inválido.');
  fail(!s.orders.some(o=>o.shift===s.shift.id&&!o.closed),'Hay pedidos abiertos en este turno.');
  return Object.assign(s.shift,{closed:new Date().toISOString(),userClosed:actor,counted:command.counted,...cashSummary(s),difference:command.counted-cashSummary(s).expected});
 }
 if(type==='refund'){
  role(user,'supervisor');
  const order=s.orders.find(o=>o.id===command.order&&o.shift===s.shift.id&&o.closed&&o.fiscal);
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
  if(command.service==='mesa')fail(restaurantTables(s).some(t=>t.number===command.table&&t.active)&&Number.isInteger(command.people)&&command.people>=1&&command.people<=30,'Mesa no habilitada o cantidad de personas inválida.');
  if(command.service==='mesa') fail(!s.orders.some(o=>!o.closed&&o.table===command.table),'Esa mesa ya tiene un pedido.');
  const assigned=staff.find(person=>person.id===(command.waiter||actor));
  fail(!command.waiter||assigned,'El responsable no está habilitado en esta empresa.');
  if(user==='camarero')fail(!command.waiter||command.waiter===actor,'Solo un supervisor puede asignar otra persona.');
  const waiter=assigned||{id:actor,name:actor};
  const o={id:id(),number:s.orders.length+1042,shift:s.shift.id,service:command.service,table:command.service==='mesa'?command.table:null,tableName:restaurantTables(s).find(t=>t.number===command.table)?.name,people:command.people,waiter:{id:waiter.id,name:waiter.name},lines:[],closed:false};
  s.orders.push(o);return o;
 }
 const o=s.orders.find(o=>o.id===command.order);
 fail(o&&o.shift===s.shift.id&&(!o.closed||type==='ready'),'Pedido cerrado o fuera del turno.');
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
  const p=s.products.find(p=>p.id===command.product);fail(p,'Producto inválido.');
  const modifiers=Array.isArray(command.modifiers)?command.modifiers.filter(m=>p.modifiers.includes(m)):[];
  const l={id:id(),product:p.id,name:p.name,cents:command.happy&&p.happy!=null?p.happy:p.cents,tax:p.tax,station:p.station,modifiers,note:label(command.note,180),recipe:structuredClone(p.recipe||{}),status:'pendiente'};
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
  const equal=command.split==='equal';
  fail(!o.equalSplit||equal,'Continúa cobrando las partes de esta cuenta.');
  let amounts;
  if(equal){
   fail(o.lines.length>0&&!o.lines.some(l=>l.payment),'No se puede dividir una cuenta con productos ya pagados.');
   fail(o.equalSplit||!s.payments.some(p=>p.order===o.id),'La cuenta ya tiene pagos.');
   amounts=o.equalSplit?.amounts||equalShares(totals(o.lines,o.service).total,command.people);
   fail(!o.equalSplit||command.people===o.equalSplit.people,'La cantidad de personas ya quedó fijada con el primer pago.');
   fail(Number.isInteger(command.part)&&command.part>=0&&command.part<amounts.length&&!s.payments.some(p=>p.order===o.id&&p.equalPart===command.part),'Esa parte ya está pagada o no es válida.');
  }else fail(Array.isArray(command.lines)&&command.lines.length>0&&new Set(command.lines).size===command.lines.length,'Selecciona las partidas a cobrar.');
  fail(['efectivo','tarjeta','transferencia'].includes(command.method),'Método inválido.');
  const lines=equal?o.lines:command.lines.map(k=>o.lines.find(l=>l.id===k));
  fail(lines.every(l=>l&&!l.payment),'Alguna partida ya está pagada.');
  fail(lines.every(l=>l.status!=='pendiente'),'Envía las comandas antes de cobrar.');
  const kind=command.kind,rnc=label(command.rnc,11);
  fail(['E31','E32'].includes(kind)&&(kind!=='E31'||/^[0-9]{9}$/.test(rnc)),'E31 requiere un RNC de nueve dígitos.');
  fail(!o.billing||o.billing.kind===kind&&o.billing.rnc===(kind==='E31'?rnc:''),'Ya se eligió el comprobante para esta cuenta.');
  const use={};if(!equal||!o.equalSplit)for(const l of lines)for(const [key,qty] of Object.entries(l.recipe||{}))use[key]=(use[key]||0)+qty;
  fail(Object.entries(use).every(([k,n])=>s.ingredients[k]?.stock>=n),'Existencia insuficiente para registrar esta venta.');
  const record={id:id(),method:command.method,order:o.id,shift:o.shift,user:actor,lines:equal?[]:command.lines,amount:equal?amounts[command.part]:totals(lines,o.service).total,...(equal?{equalPart:command.part}:{})};
  s.payments.push(record);
  if(equal)o.equalSplit={people:command.people,amounts};
  const settled=!equal||s.payments.filter(p=>p.order===o.id).length===amounts.length;
  if(settled)for(const l of lines)l.payment=record.id;
  for(const [k,n] of Object.entries(use)){s.ingredients[k].stock-=n;s.events.push({type:'sale',reference:record.id+':'+k,ingredient:k,quantity:n,payment:record.id});}
  o.billing={kind,rnc:kind==='E31'?rnc:''};
  if(o.lines.every(l=>l.payment)){
   o.closed=true;
   o.fiscal={id:id(),status:'Simulado · sin envío a DGII',...o.billing,amount:totals(o.lines,o.service).total, route:o.billing.kind==='E32' && totals(o.lines,o.service).total<25000000?'RFCE':'ECF'};
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
