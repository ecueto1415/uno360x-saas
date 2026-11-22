import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {makeServer} from './server.mjs';
import {totals,margin} from './domain.mjs';

test('Piloto Mesa 03, segunda ronda, caja, simulación fiscal y para llevar',async t=>{
 const server=makeServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));
 t.after(()=>new Promise(r=>server.close(r)));
 const base='http://127.0.0.1:'+server.address().port;
 async function post(type,data={},role='caja',key=randomUUID(),status=200){
  const r=await fetch(base+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':role},body:JSON.stringify({type,key,...data})});
  const body=await r.json();assert.equal(r.status,status,body.error);return body;
 }
 const stock=async()=>(await (await fetch(base+'/api/state')).json()).state.ingredients.ron.stock;
 await post('open',{fund:200000});
 const {result:o}=await post('order',{service:'mesa',table:3,people:3},'camarero');
 const add=(product,order=o.id,fields={})=>post('add',{order,product,...fields},'camarero');
 const {result:b}=await add('burger',o.id,{note:'Sin cebolla',modifiers:['Sin cebolla']});
 const {result:w}=await add('wings');
 const {result:m,state:initial}=await add('mojito');
 assert.deepEqual(totals([b,w,m],'mesa'),{subtotal:117000,tax:21060,tip:11700,total:149760});
 assert.deepEqual(margin(initial.products.find(p=>p.id==='mojito'),initial.ingredients),{cost:3875,normal:26125,happy:21125});
 const {result:first}=await post('send',{order:o.id},'camarero');
 assert.equal(first.cocina,2);assert.equal(first.barra,1);
 await post('ready',{order:o.id,line:b.id},'barra',randomUUID(),400);
 await post('ready',{order:o.id,line:b.id},'cocina');
 const {result:round2}=await add('mojito',o.id,{note:'Segunda ronda'});
 const {result:second,state:sent}=await post('send',{order:o.id},'camarero');
 assert.equal(second.cocina,0);assert.equal(second.barra,1);
 assert.deepEqual(sent.orders[0].lines.filter(l=>l.batch===second.batch).map(l=>l.id),[round2.id]);
 await post('ready',{order:o.id,line:m.id},'barra');
 await post('ready',{order:o.id,line:round2.id},'barra');
 const request={order:o.id,lines:[b.id,w.id],method:'efectivo',kind:'E32'};
 const key=randomUUID();
 const [a,retry]=await Promise.all([post('pay',request,'caja',key),post('pay',request,'caja',key)]);
 assert.equal(a.result.id,retry.result.id);assert.equal(a.result.amount,111360);
 const secondPayment={order:o.id,lines:[m.id,round2.id],method:'tarjeta',kind:'E32'};
 const {result:card,state:paid}=await post('pay',secondPayment);
 assert.equal(card.amount,76800);assert.equal(await stock(),2410);
 await post('pay',secondPayment,'caja',randomUUID(),400);
 const fiscal=await post('fiscal',{order:o.id});
 const fiscalRetry=await post('fiscal',{order:o.id});
 assert.equal(fiscal.result.id,fiscalRetry.result.id);
 assert.equal(fiscal.result.amount,188160);
 assert.match(fiscal.result.status,/Simulado/);
 assert.equal(paid.payments.length,2);
 assert.equal(await stock(),2410);
 await post('waste',{ingredient:'ron',quantity:20,reason:'Derrame'},'barra');
 const {result:count}=await post('count',{ingredient:'ron',quantity:2385},'barra');
 assert.equal(count.expected,2390);assert.equal(count.difference,-5);
 const {result:closed}=await post('close',{counted:311000});
 assert.equal(closed.expected,311360);assert.equal(closed.difference,-360);
 assert.deepEqual(closed.methods,{efectivo:111360,tarjeta:76800,transferencia:0});

 await post('open',{fund:0});
 const {result:take}=await post('order',{service:'llevar'},'camarero');
 const items=[];
 for(const item of ['burger','wings','mojito'])items.push((await add(item,take.id)).result);
 assert.deepEqual(totals(items,'llevar'),{subtotal:117000,tax:21060,tip:0,total:138060});
 await post('send',{order:take.id},'camarero');
 const pay={order:take.id,lines:items.map(l=>l.id),method:'transferencia',kind:'E31'};
 await post('pay',pay,'caja',randomUUID(),400);
 const {result:transfer}=await post('pay',{...pay,rnc:'101000001'});
 assert.equal(transfer.amount,138060);assert.equal(await stock(),2345);
 const {result:e31}=await post('fiscal',{order:take.id});
 assert.equal(e31.kind,'E31');assert.equal(e31.rnc,'101000001');
 const {result:closing}=await post('close',{counted:0});
 assert.equal(closing.methods.transferencia,138060);
});

test('Menú configurable, permisos y anulación auditada',async t=>{
 const srv=makeServer(':memory:');await new Promise(r=>srv.listen(0,'127.0.0.1',r));
 t.after(()=>new Promise(r=>srv.close(r)));
 const url='http://127.0.0.1:'+srv.address().port+'/api/command';
 async function cmd(type,data,user,status=200){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':user},
   body:JSON.stringify({key:randomUUID(),type,...data})});
  const body=await r.json();assert.equal(r.status,status,body.error);return body;
 }
 const p={name:'Tacos',category:'Especiales',cents:35000,tax:18,modifiers:'Sin picante, Extra limón',station:'cocina',photo:'burger.jpg'};
 await cmd('product',p,'camarero',400);
 const {result:product}=await cmd('product',p,'supervisor');
 assert.deepEqual(product.modifiers,['Sin picante','Extra limón']);
 await cmd('open',{fund:0},'caja');
 const {result:o}=await cmd('order',{service:'barra'},'camarero');
 const {result:l}=await cmd('add',{order:o.id,product:product.id},'camarero');
 const data={order:o.id,line:l.id,reason:'Producto equivocado'};
 await cmd('void',data,'caja',400);
 const {state:s}=await cmd('void',data,'supervisor');
 assert.equal(s.audits[0].user,'supervisor');assert.equal(s.audits[0].details.reason,data.reason);
 assert.equal(s.orders[0].closed,true);
});
test('La misma sesión de UNO360X aplica contrato, rol y aislamiento de sucursal', async t=>{
 const {mkdtempSync,rmSync,writeFileSync}=await import('node:fs');
 const {tmpdir}=await import('node:os');
 const {join}=await import('node:path');
 const {DatabaseSync}=await import('node:sqlite');
 const {createHash}=await import('node:crypto');
 const {businessAccess}=await import('./access.mjs');
 const dir=mkdtempSync(join(tmpdir(),'uno360x-pos-'));
 const identity=join(dir,'identity.sqlite'),grants=join(dir,'grants.json');
 const fixture=new DatabaseSync(identity);
 fixture.exec(`CREATE TABLE accounts(id TEXT, active INT, verified INT);
  CREATE TABLE identity_sessions(digest TEXT, account_id TEXT, expires REAL);
  CREATE TABLE memberships(account_id TEXT,tenant_id TEXT,role TEXT,active INT);
  INSERT INTO accounts VALUES ('c01',1,1);
  INSERT INTO memberships VALUES ('c01','a','member',1),('c01','b','member',1),('c01','c','member',1);`);
 const session=randomUUID();
 fixture.prepare('INSERT INTO identity_sessions VALUES (?,?,?)').run(createHash('sha256').update(session).digest('hex'),'c01',Date.now()/1000+300);
 fixture.close();
 writeFileSync(grants,JSON.stringify({defaultTenant:'a',tenants:{
  a:{enabled:true,branch:'centro',users:{c01:'caja'}},
  b:{enabled:false,branch:'centro',users:{c01:'caja'}},
  c:{enabled:true,branch:'norte',users:{c01:'caja'}},
 }}));
 const server=makeServer(':memory:',businessAccess(identity,grants));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 t.after(async()=>{await new Promise(r=>server.close(r));rmSync(dir,{recursive:true});});
 const url='http://127.0.0.1:'+server.address().port;
 const headers={cookie:'uno360x_lab_session='+session,'Content-Type':'application/json'};
 assert.equal((await fetch(url+'/api/state')).status,403);
 assert.equal((await fetch(url+'/api/state',{headers:{...headers,'x-pos-tenant':'b'}})).status,403);
 const opened=await fetch(url+'/api/command',{method:'POST',headers,body:JSON.stringify({key:randomUUID(),type:'open',fund:200000})});
 assert.equal(opened.status,200);
 assert.equal((await opened.json()).state.shift.user,'c01');
 const other=await fetch(url+'/api/state',{headers:{...headers,'x-pos-tenant':'c'}});
 assert.equal((await other.json()).state.shift,null);
 const forged=await fetch(url+'/api/command',{method:'POST',headers:{...headers,'x-pos-role':'supervisor'},body:JSON.stringify({key:randomUUID(),type:'product'})});
 assert.equal(forged.status,400);
 assert.match((await forged.json()).error,/permiso/);
});

test('El inventario pendiente se reintenta con la misma referencia',async t=>{
 const attempts=new Map();
 const inventory=async(scope,event)=>{
  assert.equal(scope,'negocio-demostracion:sucursal-centro');
  assert.equal(event.ingredient,'ron');
  const count=(attempts.get(event.reference)||0)+1;
  attempts.set(event.reference,count);
  if(count===1)throw Error('Tiempo de espera de laboratorio');
  return 99;
 };
 const server=makeServer(':memory:',null,inventory);
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 t.after(()=>new Promise(r=>server.close(r)));
 async function command(type,data,role){
  const res=await fetch('http://127.0.0.1:'+server.address().port+'/api/command',{
   method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':role},
   body:JSON.stringify({key:randomUUID(),type,...data})});
  const payload=await res.json();assert.equal(res.status,200,payload.error);return payload;
 }
 await command('waste',{ingredient:'ron',quantity:20,reason:'Prueba'},'barra');
 const first=await command('sync-inventory',{},'caja');
 const second=await command('sync-inventory',{},'caja');
 const third=await command('sync-inventory',{},'caja');
 assert.equal(first.result[0].state,'pendiente');
 assert.equal(second.result[0].state,'confirmado');
 assert.equal(second.result[0].reference,first.result[0].reference);
 assert.deepEqual(third.result,[]);
 assert.equal(third.state.ingredients.ron.stock,2480);
});

test('Una devolución de caja queda auditada y solo reduce una vez el efectivo esperado',async t=>{
 const server=makeServer(':memory:');
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 t.after(()=>new Promise(r=>server.close(r)));
 const url='http://127.0.0.1:'+server.address().port+'/api/command';
 async function send(type,data,role='caja',key=randomUUID(),status=200){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':role},body:JSON.stringify({type,key,...data})});
  const json=await r.json();assert.equal(r.status,status,json.error);return json;
 }
 await send('open',{fund:200000});
 const {result:o}=await send('order',{service:'llevar'});
 const {result:l}=await send('add',{order:o.id,product:'mojito'});
 await send('send',{order:o.id});
 await send('pay',{order:o.id,lines:[l.id],method:'efectivo',kind:'E32'});
 const payload={order:o.id,lines:[l.id],reason:'Cancelación después del cobro'};
 await send('refund',payload,'caja',randomUUID(),400);
 const key=randomUUID();
 const first=await send('refund',payload,'supervisor',key);
 const repeat=await send('refund',payload,'supervisor',key);
 await send('refund',payload,'supervisor',randomUUID(),400);
 assert.equal(first.result.id,repeat.result.id);
 assert.equal(repeat.result.amount,35400);
 assert.equal(repeat.state.refunds.length,1);
 assert.equal(repeat.state.audits.at(-1).user,'supervisor');
 assert.equal(repeat.state.ingredients.ron.stock,2455);
 assert.deepEqual(repeat.summary.refunds,{efectivo:35400,tarjeta:0,transferencia:0});
 const {result:closed}=await send('close',{counted:200000});
 assert.equal(closed.difference,0);
 assert.equal(closed.expected,200000);
});
