import test from 'node:test';
import assert from 'node:assert/strict';
import {makeDemoServer} from './server.mjs';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
async function fixture(run){
 const dir=mkdtempSync(join(tmpdir(),'uno-menu-')),file=join(dir,'pos.sqlite');
 const access={close(){},authorize(req){return req.headers['x-user']?{scope:req.headers['x-company']||'a',account:req.headers['x-user'],role:req.headers['x-user']==='admin'?'supervisor':'camarero',staff:[]}:null;}};
 let server=makeDemoServer(file,access);await new Promise(r=>server.listen(0,'127.0.0.1',r));let base='http://127.0.0.1:'+server.address().port;
 const fetcher=(path,options)=>fetch(base+path,options),headers=(u='admin',company='a')=>({'Content-Type':'application/json','X-User':u,'X-Company':company,'X-Pos-Role':'supervisor'});
 const cmd=async(type,data={},u='admin',company='a',key=crypto.randomUUID())=>{const r=await fetcher('/api/command',{method:'POST',headers:headers(u,company),body:JSON.stringify({type,key,...data})});return {status:r.status,...await r.json()};};
 const snap=async(u='admin',company='a')=>(await(await fetcher('/api/state',{headers:headers(u,company)})).json()).state;
 try{await run({fetcher,cmd,snap,restart:async()=>{server.closeAllConnections();await new Promise(r=>server.close(r));server=makeDemoServer(file,access);await new Promise(r=>server.listen(0,'127.0.0.1',r));base='http://127.0.0.1:'+server.address().port;}});}finally{server.closeAllConnections();await new Promise(r=>server.close(r));rmSync(dir,{recursive:true,force:true});}
}
const config=(s,extra={})=>({revision:s.publicMenu?.revision||0,name:'Restaurante piloto',logo:'',interval:12,enabled:true,items:s.products.map(p=>({id:p.id,published:p.id!=='wings',available:true})),...extra});

test('Digital menu: explicit publication, public whitelist, no customer authentication, tenant separation and revoke',()=>fixture(async({cmd,snap,fetcher,restart})=>{
 const initial=await snap();assert.equal((await cmd('menu-save',config(initial),'waiter')).status,400);
 assert.equal((await cmd('menu-save',config(initial,{logo:'data:image/svg+xml;base64,PHN2Zy8+'}))).status,400);
 const key=crypto.randomUUID();assert.equal((await cmd('menu-save',config(initial),'admin','a',key)).status,200);assert.equal((await cmd('menu-save',config(initial),'admin','a',key)).status,200);
 let s=await snap(),token=s.publicMenu.token;assert.match(token,/^[a-f0-9]{32}$/);assert.equal((await fetcher('/menu-pos/'+token+'/data')).status,404);
 assert.equal((await cmd('menu-publish',{revision:0})).status,400);assert.equal((await cmd('menu-publish',{revision:1})).status,200);
 let r=await fetcher('/menu-pos/'+token+'/data');assert.equal(r.status,200);let d=await r.json();assert.equal(d.name,'Restaurante piloto');assert.deepEqual(d.items.map(p=>p.id),['burger','mojito']);
 assert.deepEqual(Object.keys(d).sort(),['name','logo','interval','items','publishedAt','consultationOnly'].sort());assert.deepEqual(Object.keys(d.items[0]).sort(),['id','name','description','category','cents','tax','available','photo'].sort());
 assert.equal((await snap('waiter')).publicMenu,undefined);assert.equal((await snap('admin','b')).publicMenu,undefined);
 assert.equal((await fetcher('/menu-pos/'+token+'/photo/wings')).status,404);assert.equal((await fetcher('/menu-pos/'+token+'/photo/burger')).headers.get('content-type'),'image/jpeg');
 assert.equal((await fetcher('/menu-pos/'+token+'/api/state')).status,404);assert.equal((await fetcher('/menu-pos/'+token+'/data',{method:'POST',body:'{}'})).status,405);
 assert.equal((await fetcher('/api/state')).status,403);assert.equal((await fetcher('/menu-pos/'+'0'.repeat(32)+'/data')).status,404);
 const qr=await(await fetcher('/menu-pos/'+token+'/qr.svg')).text();assert.ok(qr.includes('<svg')&&qr.includes('shape-rendering="crispEdges"'));assert.ok(!qr.includes('script'));
 await restart();assert.equal((await fetcher('/menu-pos/'+token+'/data')).status,200,'Public index persists through restart');
 s=await snap();await cmd('menu-save',config(s,{enabled:false}));assert.equal((await fetcher('/menu-pos/'+token+'/data')).status,200,'Draft does not revoke before publish');
 s=await snap();await cmd('menu-publish',{revision:s.publicMenu.revision});assert.equal((await fetcher('/menu-pos/'+token+'/data')).status,404);assert.equal((await fetcher('/menu-pos/'+token+'/photo/burger')).status,404);
}));

test('Published catalog changes refresh without republication; unavailable products cannot be added; no stock or financial mutation',()=>fixture(async({cmd,snap,fetcher})=>{
 let s=await snap();const items=s.products.map(p=>({id:p.id,published:true,available:p.id!=='wings'}));await cmd('menu-save',config(s,{items}));s=await snap();await cmd('menu-publish',{revision:s.publicMenu.revision});s=await snap();const token=s.publicMenu.token;
 const before={ingredients:s.ingredients,payments:s.payments,orders:s.orders,events:s.events};
 for(let i=0;i<8;i++)await fetcher('/menu-pos/'+token+'/data');let current=await snap();assert.deepEqual({ingredients:current.ingredients,payments:current.payments,orders:current.orders,events:current.events},before);
 const p=s.products.find(p=>p.id==='burger');await cmd('product',{...p,cents:50000,description:'Con queso <script>alert(1)</script>',modifiers:p.modifiers.join(',')});
 let d=await(await fetcher('/menu-pos/'+token+'/data')).json();assert.equal(d.items[0].cents,50000);assert.ok(d.items[0].description.includes('<script>'));assert.equal(d.items.find(p=>p.id==='wings').available,false);
 await cmd('open',{fund:0});const o=(await cmd('order',{service:'llevar'})).result;const denied=await cmd('add',{order:o.id,product:'wings'});assert.equal(denied.status,400);assert.match(denied.error,/agotado/);
 assert.equal((await snap()).events.length,0);assert.equal((await snap()).payments.length,0);
}));

test('Save and publish is atomic: clearing Publicar removes the product from the live menu in one operation',()=>fixture(async({cmd,snap,fetcher})=>{
 let s=await snap();assert.equal((await cmd('menu-save-publish',config(s),'waiter')).status,400);
 assert.equal((await cmd('menu-save-publish',config(s))).status,200);s=await snap();const token=s.publicMenu.token;assert.equal(s.publicMenu.dirty,false);
 const items=s.publicMenu.draft.items.map(i=>({...i,published:i.id==='mojito'}));const key=crypto.randomUUID(),command=config(s,{items});await cmd('menu-save-publish',command,'admin','a',key);await cmd('menu-save-publish',command,'admin','a',key);
 let d=await(await fetcher('/menu-pos/'+token+'/data')).json();assert.deepEqual(d.items.map(p=>p.id),['mojito']);s=await snap();assert.equal(s.publicMenu.revision,4);assert.equal(s.publicMenu.dirty,false);
 const before=JSON.stringify(s);assert.equal((await cmd('menu-save-publish',config(s,{items:items.map(i=>({...i,published:false}))}))).status,400);assert.equal(JSON.stringify(await snap()),before,'Invalid publication rolls back the draft and revision as well');
}));
