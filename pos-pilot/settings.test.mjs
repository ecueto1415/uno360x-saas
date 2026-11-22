import test from 'node:test';
import assert from 'node:assert/strict';
import {makeServer} from './server.mjs';
test('Business settings require admin and explicit confirmation, preserve operations, and cannot reopen onboarding',async()=>{
 const server=makeServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 async function cmd(type,data={},role='supervisor',key=crypto.randomUUID()){
  const r=await fetch(base+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':role},body:JSON.stringify({type,key,...data})});return {status:r.status,...await r.json()};
 }
 const state=async()=> (await(await fetch(base+'/api/state')).json()).state;
 try{
  await cmd('setup-business',{business:'restaurant'});await cmd('setup-tables',{enabled:true,count:5});
  const p=(await cmd('product',{name:'Bebida',category:'Bebidas',cents:10000,tax:18,station:'barra',photo:'',modifiers:''})).result;
  await cmd('setup-finish');await cmd('open',{fund:0});const o=(await cmd('order',{service:'mesa',table:1,people:2})).result;await cmd('add',{order:o.id,product:p.id});await cmd('send',{order:o.id});
  const before=await state(),change={business:'retail',previousBusiness:'restaurant',confirmed:true};
  for(const type of ['setup-step','setup-business','setup-tables','setup-examples','setup-finish'])assert.equal((await cmd(type,{business:'quick',step:'business',enabled:false,count:1})).status,400);
  for(const role of ['caja','camarero','barra','cocina'])assert.equal((await cmd('business-change',change,role)).status,400);
  assert.equal((await cmd('business-change',{...change,confirmed:false})).status,400);
  const key=crypto.randomUUID();assert.equal((await cmd('business-change',change,'supervisor',key)).status,200);assert.equal((await cmd('business-change',change,'supervisor',key)).status,200);
  const after=await state();assert.equal(after.setup.business,'retail');assert.equal(after.setup.completed,true);
  for(const f of ['orders','tables','products','payments','shift','events','ingredients'])assert.deepEqual(after[f],before[f]);
  assert.equal(after.audits.filter(a=>a.action==='cambio de tipo de negocio POS').length,1);
  assert.equal((await cmd('business-change',{...change,business:'quick'})).status,400);
  assert.equal((await cmd('tables-config',{enabled:false,count:5})).status,400);
  assert.equal((await cmd('stations-config',{kitchen:true,bar:false})).status,400);
  const edited=await cmd('product',{id:p.id,name:p.name,category:p.category,cents:p.cents,tax:p.tax,photo:'',station:'ninguna',modifiers:''});assert.equal(edited.status,200,edited.error);
  assert.equal((await cmd('stations-config',{kitchen:true,bar:false})).status,400,'Pending order still routes to the old station');
  const pending=(await state()).orders[0].lines[0];await cmd('ready',{order:o.id,line:pending.id});
  const disabled=await cmd('stations-config',{kitchen:false,bar:false});assert.equal(disabled.status,200,disabled.error);assert.equal((await state()).setup.business,'retail');
  assert.equal((await cmd('product',{name:'Comida',category:'General',cents:10000,tax:18,station:'cocina'})).status,400);
  await cmd('stations-config',{kitchen:true,bar:false});assert.equal((await cmd('product',{name:'Comida',category:'General',cents:10000,tax:18,station:'cocina'})).status,200);
  for(const type of ['tables-config','stations-config'])assert.equal((await cmd(type,{enabled:true,count:5,kitchen:true,bar:true},'caja')).status,400);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
