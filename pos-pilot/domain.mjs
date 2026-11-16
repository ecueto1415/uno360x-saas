
export const money = c => new Intl.NumberFormat('es-DO',{style:'currency',currency:'DOP'}).format(c/100);
export const products = [
 {id:'burger',name:'Hamburguesa',category:'Comida',cents:45000,tax:18,station:'cocina',photo:'burger.jpg',modifiers:['Sin cebolla','Bien cocida']},
 {id:'wings',name:'Alitas',category:'Comida',cents:42000,tax:18,station:'cocina',photo:'wings.jpg',modifiers:['BBQ','Picante']},
 {id:'mojito',name:'Mojito',category:'Bebidas',cents:30000,happy:25000,tax:18,station:'barra',photo:'mojito.jpg',modifiers:['Sin hielo','Poco dulce'],recipe:{ron:45,limon:25,jarabe:20,menta:8,soda:60}},
];
export const seed = () => ({shift:null,orders:[],payments:[],audits:[],events:[],operations:{},products:structuredClone(products),
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
export function apply(s,command,user,actor=user){
 const {type}=command;
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
 if(type==='order'){
  role(user,'caja','camarero','supervisor');
  fail(['mesa','barra','llevar'].includes(command.service),'Tipo de pedido inválido.');
  if(command.service==='mesa')fail(Number.isInteger(command.table)&&command.table>=1&&command.table<=9&&Number.isInteger(command.people)&&command.people>=1&&command.people<=30,'Mesa o cantidad de personas inválida.');
  if(command.service==='mesa') fail(!s.orders.some(o=>!o.closed&&o.table===command.table),'Esa mesa ya tiene un pedido.');
  const o={id:id(),number:s.orders.length+1042,shift:s.shift.id,service:command.service,table:command.service==='mesa'?command.table:null,people:command.people,lines:[],closed:false};
  s.orders.push(o);return o;
 }
 const o=s.orders.find(o=>o.id===command.order);
 fail(o&&o.shift===s.shift.id&&(!o.closed||type==='ready'),'Pedido cerrado o fuera del turno.');
 if(type==='add'){
  role(user,'caja','camarero','supervisor');
  fail(!o.lines.some(l=>l.payment),'La cuenta ya tiene pagos.');
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
  const l=o.lines.find(item=>item.id===command.line);
  fail(l&&!l.payment&&nonnegative(command.cents,l.cents)&&command.cents>0&&label(command.reason),'Indica un descuento y su motivo.');
  l.cents-=command.cents;
  log(s,actor,'descuento',{order:o.number,line:l.id,cents:command.cents,reason:label(command.reason)});
  return l;
 }
 if(type==='void'){
  role(user,'supervisor');const l=o.lines.find(l=>l.id===command.line);
  fail(l&&!l.payment&&label(command.reason),'Indica una partida sin pagar y un motivo.');
  log(s,actor,'anulación',{order:o.number,line:l.id,reason:label(command.reason)});
  o.lines=o.lines.filter(x=>x!==l);if(!o.lines.length)o.closed=true;
  return {voided:l.id};
 }
 if(type==='pay'){
  role(user,'caja','supervisor');
  fail(Array.isArray(command.lines)&&command.lines.length>0&&new Set(command.lines).size===command.lines.length,'Selecciona las partidas a cobrar.');
  fail(['efectivo','tarjeta','transferencia'].includes(command.method),'Método inválido.');
  const lines=command.lines.map(k=>o.lines.find(l=>l.id===k));
  fail(lines.every(l=>l&&!l.payment),'Alguna partida ya está pagada.');
  fail(lines.every(l=>l.status!=='pendiente'),'Envía las comandas antes de cobrar.');
  const kind=command.kind,rnc=label(command.rnc,11);
  fail(['E31','E32'].includes(kind)&&(kind!=='E31'||/^[0-9]{9}$/.test(rnc)),'E31 requiere un RNC de nueve dígitos.');
  fail(!o.billing||o.billing.kind===kind&&o.billing.rnc===(kind==='E31'?rnc:''),'Ya se eligió el comprobante para esta cuenta.');
  const use={};for(const l of lines)for(const [key,qty] of Object.entries(l.recipe||{}))use[key]=(use[key]||0)+qty;
  fail(Object.entries(use).every(([k,n])=>s.ingredients[k]?.stock>=n),'Existencia insuficiente para registrar esta venta.');
  const record={id:id(),method:command.method,order:o.id,shift:o.shift,user:actor,lines:command.lines,amount:totals(lines,o.service).total};
  s.payments.push(record);
  for(const l of lines)l.payment=record.id;
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
 return {methods,expected:(s.shift?.fund||0)+methods.efectivo};
}
export function margin(p,ingredients){const cost=Object.entries(p.recipe||{}).reduce((sum,[k,n])=>sum+n*ingredients[k].cost,0);
 return {cost,normal:p.cents-cost,happy:p.happy==null?null:p.happy-cost};}
