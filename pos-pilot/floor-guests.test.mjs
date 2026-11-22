import test from 'node:test';
import assert from 'node:assert/strict';
import {makeDemoServer} from './server.mjs';
import {floorTables} from './domain.mjs';
async function fixture(run){
 const staff=[{id:'1',name:'Administrador'},{id:'2',name:'Ana camarera'},{id:'3',name:'Luis camarero'},{id:'4',name:'Caja'}];
 const access={close(){},authorize(req){const actor=req.headers['x-user']||'1';return {scope:req.headers['x-company']||'a',account:actor,role:({'1':'supervisor','2':'camarero','3':'camarero','4':'caja','5':'cocina','6':'barra'})[actor],staff};}};
 const srv=makeDemoServer(':memory:',access);await new Promise(r=>srv.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+srv.address().port;
 const snap=async(user='1',company='a')=>(await(await fetch(base+'/api/state',{headers:{'X-User':user,'X-Company':company}})).json()).state;
 const cmd=async(type,data={},user='1',key=crypto.randomUUID())=>{const r=await fetch(base+'/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Pos-Role':'supervisor','X-User':user},body:JSON.stringify({type,key,...data})});return {status:r.status,...await r.json()};};
 try{await run({snap,cmd});}finally{srv.closeAllConnections();await new Promise(r=>srv.close(r));}
}
test('Floor persistence, optimistic version, admin-only layout and money redaction on server',()=>fixture(async({snap,cmd})=>{
 const tables=floorTables(await snap());tables[0]={...tables[0],name:'Terraza 01',zone:'terraza',x:20,y:30,shape:'round',seats:6};
 assert.equal((await cmd('floor-save',{version:0,tables},'2')).status,400);
 assert.equal((await cmd('floor-save',{version:0,tables:[{...tables[0],x:101}]})).status,400);
 const key=crypto.randomUUID();await cmd('floor-save',{version:0,tables},'1',key);await cmd('floor-save',{version:0,tables},'1',key);
 assert.equal((await snap()).floor.version,1);assert.equal((await snap()).tables[0].zone,'terraza');
 assert.equal((await cmd('floor-save',{version:0,tables})).status,400);
 await cmd('zone-save',{name:'Patio'});assert.equal((await snap()).floor.zones.length,4);
 await cmd('open',{fund:200000});const a=(await cmd('order',{service:'mesa',table:1,people:3,waiter:'2'})).result,b=(await cmd('order',{service:'mesa',table:2,people:2,waiter:'3'})).result;
 await cmd('add',{order:a.id,product:'burger'},'2');await cmd('add',{order:b.id,product:'mojito'},'3');
 assert.equal((await cmd('add',{order:b.id,product:'burger'},'2')).status,400);
 const cam=await snap('2'),hidden=cam.orders.find(o=>o.id===b.id);
 assert.equal(hidden.amountsHidden,true);assert.deepEqual(hidden.lines,[]);assert.equal(cam.orders.find(o=>o.id===a.id).lines[0].cents,45000);
 assert.deepEqual(cam.operations,{});assert.equal(cam.shift.fund,undefined);
 for(const actor of ['5','6']){const s=await snap(actor);assert.equal(s.payments.length,0);assert.ok(s.products.every(p=>p.cents===undefined));assert.ok(s.orders.every(o=>o.lines.every(l=>l.cents===undefined)));}
 const other=await snap('1','b');assert.equal(other.orders.length,0);assert.equal(other.floor,undefined);
}));
for(const mode of ['table','person'])test('Named guests and '+mode+' invoices: exact payments, no duplicate documents or stock',()=>fixture(async({snap,cmd})=>{
 await cmd('open',{fund:0});const o=(await cmd('order',{service:'mesa',table:3,people:3,waiter:'2'})).result;assert.deepEqual(o.guests,[]);
 const c=(await cmd('guest-save',{order:o.id,name:'Carlos'},'2')).result,a=(await cmd('guest-save',{order:o.id,name:'Ana'},'2')).result;
 assert.equal((await cmd('guest-save',{order:o.id,name:'Carlos'},'2')).status,400);
 assert.equal((await cmd('guest-save',{order:o.id,name:'Intruso'},'3')).status,400);
 for(const [product,guest] of [['burger',c.id],['wings',a.id],['mojito',null]])await cmd('add',{order:o.id,product,guest},'2');
 assert.equal((await cmd('invoice-mode',{order:o.id,mode:'person'},'4')).status,400);
 let current=(await snap()).orders[0];await cmd('guest-assign',{order:o.id,line:current.lines[2].id,guest:c.id},'2');await cmd('send',{order:o.id},'2');
 await cmd('invoice-mode',{order:o.id,mode},'4');
 const pay={order:o.id,split:'person',guest:c.id,method:'efectivo',kind:mode==='person'?'E31':'E32',rnc:'101010101',buyer:'Comprador de prueba'},key=crypto.randomUUID();
 const first=await Promise.all([cmd('pay',pay,'4',key),cmd('pay',pay,'4',key)]);assert.equal(first[0].status,200,first[0].error);assert.equal(first[0].result.id,first[1].result.id);
 let s=await snap();assert.equal(s.payments.length,1);assert.equal(s.payments[0].amount,96000);assert.equal(s.ingredients.ron.stock,2455);assert.equal(s.orders[0].closed,false);
 assert.equal((await cmd('pay',pay,'4')).status,400);assert.equal((await cmd('invoice-mode',{order:o.id,mode:mode==='person'?'table':'person'},'4')).status,400);
 assert.equal((await cmd('guest-assign',{order:o.id,line:current.lines[1].id,guest:c.id},'2')).status,400);
 assert.equal((await cmd('pay',{order:o.id,split:'person',guest:a.id,method:'tarjeta',kind:'E31',rnc:'invalid'},'4')).status,400);
 const last=await cmd('pay',{order:o.id,split:'person',guest:a.id,method:'tarjeta',kind:'E32'},'4');assert.equal(last.status,200,last.error);
 s=await snap();current=s.orders[0];assert.equal(s.payments.reduce((n,p)=>n+p.amount,0),149760);assert.equal(current.closed,true);assert.equal(s.ingredients.ron.stock,2455);assert.equal(s.events.filter(e=>e.ingredient==='ron').length,1);
 if(mode==='table'){assert.equal(current.fiscal.amount,149760);assert.equal(current.invoices,undefined);}
 else{assert.equal(current.fiscal,undefined);assert.equal(current.invoices.length,2);assert.equal(new Set(current.invoices.map(i=>i.id)).size,2);assert.equal(current.invoices.reduce((n,i)=>n+i.amount,0),149760);assert.equal(new Set(current.invoices.flatMap(i=>i.lines)).size,3);assert.equal(current.invoices[0].guestName,'Carlos');
  const doc=(await cmd('fiscal',{order:o.id,invoice:current.invoices[0].id},'4')).result;assert.equal(doc.id,current.invoices[0].id);assert.equal((await snap()).orders[0].invoices.length,2);
 }
}));
test('Guest creation is manual, blank names are numbered, and retries do not add another person',()=>fixture(async({cmd,snap})=>{
 await cmd('open',{fund:0});const o=(await cmd('order',{service:'mesa',table:1,people:6})).result;
 assert.equal(o.guests.length,0);const key=crypto.randomUUID();const r=await cmd('guest-save',{order:o.id,name:''},'1',key);await cmd('guest-save',{order:o.id,name:''},'1',key);
 assert.equal(r.result.name,'Persona 1');assert.equal((await snap()).orders[0].guests.length,1);
 await cmd('guest-save',{order:o.id,guest:r.result.id,name:'Carlos'});assert.equal((await snap()).orders[0].guests[0].name,'Carlos');
}));

test('Persisted team roles override base cash access; forged headers cannot grant admin or cross-company access',()=>fixture(async({snap,cmd})=>{
 assert.equal((await cmd('staff-role',{account:'4',role:'camarero'},'4')).status,400);
 assert.equal((await cmd('staff-role',{account:'external',role:'caja'})).status,400);
 assert.equal((await cmd('staff-role',{account:'4',role:'supervisor'})).status,400);
 assert.equal((await cmd('staff-role',{account:'4',role:'camarero'})).status,200);
 await cmd('open',{fund:10000});const o=(await cmd('order',{service:'mesa',table:1,people:1,waiter:'2'})).result;
 const added=(await cmd('add',{order:o.id,product:'burger'},'2')).result;await cmd('send',{order:o.id},'2');
 assert.equal((await snap('4')).orders[0].amountsHidden,true);
 assert.equal((await cmd('pay',{order:o.id,lines:[added.id],method:'efectivo',kind:'E32'},'4')).status,400);
 assert.equal((await cmd('staff-role',{account:'2',role:'caja'},'4')).status,400);
 assert.equal((await snap('4','b')).staffRoles?.['4'],undefined);
 await cmd('staff-role',{account:'1',role:'barra'});
 assert.equal((await cmd('staff-role',{account:'4',role:'caja'})).status,200,'Verified manager remains administrator');
 assert.equal((await cmd('pay',{order:o.id,lines:[added.id],method:'efectivo',kind:'E32'},'4')).status,200);
}));
