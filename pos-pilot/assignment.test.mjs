import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID,createHmac,createHash} from 'node:crypto';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {makeDemoServer as makeServer} from './server.mjs';
import {proxyAccess} from './proxy-access.mjs';

test('Trusted SaaS roles, assignment audit, retry and tenant separation',async t=>{
 const dir=mkdtempSync(join(tmpdir(),'pos-proof-'));const key='a'.repeat(64),keyFile=join(dir,'key');writeFileSync(keyFile,key);
 const server=makeServer(':memory:',proxyAccess(keyFile));await new Promise(r=>server.listen(0,'127.0.0.1',r));
 t.after(async()=>{await new Promise(r=>server.close(r));rmSync(dir,{recursive:true});});
 const origin='http://127.0.0.1:'+server.address().port;
 const people=[{id:'1',name:'Responsable POS'},{id:'2',name:'Ana García'},{id:'3',name:'Carlos Pérez'}];
 const a='a'.repeat(32)+':company-1',b='b'.repeat(32)+':company-1';
 async function send(type,data={},role='supervisor',account='1',scope=a,status=200,id=randomUUID(),tamper=false){
  const path='/api/command';const body=JSON.stringify({key:id,type,...data});
  const value={exp:Date.now()/1000+40,method:'POST',path,scope,account,role,staff:people,bodyHash:createHash('sha256').update(body).digest('hex')};
  const payload=Buffer.from(JSON.stringify(value)).toString('base64url');const proof=payload+'.'+createHmac('sha256',key).update(payload).digest('hex');
  const res=await fetch(origin+path,{method:'POST',headers:{'Content-Type':'application/json','X-UNO-POS-Proof':proof,'X-Pos-Role':'supervisor'},body:tamper?body+' ':body});
  const json=await res.json();assert.equal(res.status,status,json.error);return json;
 }
 assert.equal((await fetch(origin+'/api/state')).status,403);
 await send('open',{fund:0});
 const o=(await send('order',{service:'mesa',table:3,people:4,waiter:'2'})).result;
 assert.deepEqual(o.waiter,people[1]);
 for(const role of ['caja','camarero','cocina','barra'])await send('reassign',{order:o.id,waiter:'3',reason:'Cambio de turno'},role,'2',a,400);
 await send('reassign',{order:o.id,waiter:'99',reason:'Fuera de empresa'},'supervisor','1',a,400);
 await send('reassign',{order:o.id,waiter:'3',reason:''},'supervisor','1',a,400);
 await send('reassign',{order:o.id,waiter:'3',reason:'Cambio de turno'},'supervisor','1',a,403,randomUUID(),true);
 const id=randomUUID(),data={order:o.id,waiter:'3',reason:'Cambio de turno'};
 const changed=await send('reassign',data,'supervisor','1',a,200,id);
 const retried=await send('reassign',data,'supervisor','1',a,200,id);
 assert.equal(retried.state.audits.length,1);assert.deepEqual(changed.result,people[2]);
 const audit=changed.state.audits[0];assert.equal(audit.user,'1');assert.equal(audit.userName,'Responsable POS');assert.deepEqual(audit.details.previous,people[1]);assert.deepEqual(audit.details.next,people[2]);assert.equal(audit.details.reason,'Cambio de turno');assert.ok(audit.at);
 await send('open',{fund:0},'supervisor','1',b);
 await send('reassign',data,'supervisor','1',b,400);
 await send('order',{service:'mesa',table:4,people:2,waiter:'3'},'camarero','2',a,400);
 const own=(await send('order',{service:'mesa',table:4,people:2},'camarero','2')).result;assert.deepEqual(own.waiter,people[1]);
});
