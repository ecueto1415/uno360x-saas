import test from 'node:test';
import assert from 'node:assert/strict';
import {makeServer,makeDemoServer} from './server.mjs';
test('Setup is persisted per business, supervisor-only, resumable and examples are opt-in',async()=>{
 const server=makeServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port;
 async function cmd(type,data={},role='supervisor',key=crypto.randomUUID()){
  const res=await fetch(url+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':role},body:JSON.stringify({type,key,...data})});return {status:res.status,...await res.json()};
 }
 const state=async()=> (await(await fetch(url+'/api/state')).json()).state;
 try{
  assert.equal((await state()).setup.step,'business');assert.equal((await state()).products.length,0);
  assert.equal((await cmd('open',{fund:0},'caja')).status,400);
  for(const type of ['setup-business','setup-tables','setup-step','setup-examples','setup-finish'])assert.equal((await cmd(type,{business:'restaurant',enabled:true,count:5,step:'products'},'caja')).status,400);
  assert.equal((await cmd('setup-business',{business:'invalid'})).status,400);
  await cmd('setup-business',{business:'restaurant'});assert.equal((await state()).setup.step,'tables');
  await cmd('table',{number:1,name:'Terraza',active:true});await cmd('table',{number:5,name:'Mesa 05',active:false});
  await cmd('table',{number:6,name:'Salón 06',active:true});assert.equal((await state()).setup.tableCount,6);
  assert.equal((await cmd('setup-tables',{enabled:true,count:0})).status,400);
  await cmd('setup-tables',{enabled:true,count:5});let s=await state();assert.equal(s.tables[0].name,'Terraza');assert.equal(s.tables[4].active,false);
  assert.equal(s.setup.step,'products');assert.equal(s.products.length,0);
  const key=crypto.randomUUID();await cmd('setup-examples',{},'supervisor',key);await cmd('setup-examples',{},'supervisor',key);await cmd('setup-examples');assert.equal((await state()).products.length,3);
  await cmd('setup-finish');assert.equal((await state()).setup.completed,true);await cmd('open',{fund:0});
  const order=(await cmd('order',{service:'mesa',table:1,people:2})).result;
  await cmd('setup-step',{step:'business'});assert.equal((await cmd('setup-business',{business:'retail'})).status,400);assert.equal((await state()).orders[0].id,order.id);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
test('Initial settings and product catalog never cross tenant boundaries',async()=>{
 const server=makeServer(':memory:',{close(){},authorize(req){return {scope:req.headers['x-test-tenant']||'a',account:'1',role:'supervisor',staff:[]};}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 try{
  const r=await fetch(base+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Test-Tenant':'a'},body:JSON.stringify({type:'setup-business',business:'quick',key:crypto.randomUUID()})});assert.equal(r.status,200);
  const other=(await(await fetch(base+'/api/state',{headers:{'X-Test-Tenant':'b'}})).json()).state;
  assert.equal(other.setup.business,null);assert.equal(other.setup.step,'business');assert.equal(other.products.length,0);assert.equal(other.tables.filter(t=>t.active).length,5);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
for(const business of ['bakery','retail','quick'])test(business+' can finish without examples or a sale; direct sale does not need a station',async()=>{
 const server=makeServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port;
 const call=async(type,data={})=>{const r=await fetch(base+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':'supervisor'},body:JSON.stringify({type,key:crypto.randomUUID(),...data})});const b=await r.json();assert.equal(r.status,200,b.error);return b;};
 try{
  let r=await call('setup-business',{business});if(business==='bakery')r=await call('setup-tables',{enabled:false,count:5});
  assert.equal(r.state.setup.step,'products');assert.equal(r.state.setup.tablesEnabled,false);
  r=await call('product',{name:'Artículo propio',category:'General',cents:10000,tax:18,station:'ninguna',photo:'',modifiers:''});const product=r.result;
  r=await call('setup-finish');assert.equal(r.state.payments.length,0);assert.equal(r.state.shift,null);assert.equal(r.state.products.length,1);
  await call('open',{fund:0});const o=(await call('order',{service:'llevar'})).result;const l=(await call('add',{order:o.id,product:product.id})).result;assert.equal(l.status,'lista');
  r=await call('pay',{order:o.id,lines:[l.id],method:'efectivo',kind:'E32'});assert.equal(r.result.amount,11800);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
test('Existing restaurant records remain operational without a forced setup or data migration',async()=>{
 const server=makeDemoServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{const r=await fetch('http://127.0.0.1:'+server.address().port+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':'caja'},body:JSON.stringify({type:'open',fund:0,key:crypto.randomUUID()})});assert.equal(r.status,200);assert.equal((await r.json()).state.setup,undefined);}
 finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
