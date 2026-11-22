import test from 'node:test';
import assert from 'node:assert/strict';
import {makeServer} from './server.mjs';
import {equalShares} from './domain.mjs';
test('Five configurable tables; equal parts are atomic, cent-exact, mixed-method and consume once',async()=>{
 const server=makeServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port;
 const snap=async()=> (await(await fetch(base+'/api/state')).json()).state;
 async function call(type,data={},role='supervisor',key=crypto.randomUUID()){
  const r=await fetch(base+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':role},body:JSON.stringify({type,key,...data})});return {status:r.status,...await r.json()};
 }
 try{
  assert.equal((await snap()).tables.length,5);
  assert.equal((await call('table',{number:6,name:'Terraza',active:true},'caja')).status,400);
  assert.equal((await call('table',{number:6,name:'Terraza',active:true})).status,200);
  await call('open',{fund:200000});const o=(await call('order',{service:'mesa',table:6,people:3})).result;
  assert.equal((await call('table',{number:6,name:'Terraza',active:false})).status,400);
  for(const product of ['burger','wings','mojito'])await call('add',{order:o.id,product});
  await call('send',{order:o.id});
  assert.deepEqual(equalShares(149760,7),[21395,21395,21394,21394,21394,21394,21394]);
  const pay={order:o.id,split:'equal',people:7,part:0,method:'efectivo',kind:'E32'},key=crypto.randomUUID();
  const results=await Promise.all([call('pay',pay,'caja',key),call('pay',pay,'caja',key)]);
  assert.equal(results[0].result.id,results[1].result.id);
  assert.equal((await snap()).payments.length,1);assert.equal((await snap()).ingredients.ron.stock,2455);
  assert.equal((await call('pay',pay,'caja')).status,400);
  assert.equal((await call('pay',{...pay,part:1,people:8},'caja')).status,400);
  assert.equal((await call('add',{order:o.id,product:'mojito'})).status,400);
  assert.equal((await call('pay',{order:o.id,lines:[o.lines?.[0]?.id],method:'efectivo',kind:'E32'},'caja')).status,400);
  for(let part=1;part<7;part++)assert.equal((await call('pay',{...pay,part,method:part%2?'tarjeta':'transferencia'},'caja')).status,200);
  const s=await snap();assert.equal(s.payments.reduce((a,p)=>a+p.amount,0),149760);assert.equal(s.orders[0].closed,true);
  assert.equal(s.orders[0].fiscal.amount,149760);assert.equal(s.ingredients.ron.stock,2455);
  assert.equal(s.events.filter(e=>e.type==='sale'&&e.ingredient==='ron').length,1);
  const before=s.orders[0].fiscal.id;await call('fiscal',{order:o.id});assert.equal((await snap()).orders[0].fiscal.id,before);
  assert.equal((await call('refund',{order:o.id,lines:[s.orders[0].lines[0].id],reason:'Prueba'})).status,400);
  const refund=await call('refund',{order:o.id,lines:s.orders[0].lines.map(l=>l.id),reason:'Prueba de devolución completa'});
  assert.equal(refund.result.amount,149760);assert.equal(Object.values(refund.result.methods).reduce((a,n)=>a+n,0),149760);
  assert.equal((await call('table',{number:6,name:'Terraza',active:false})).status,200);
 }finally{await new Promise(r=>server.close(r));}
});
