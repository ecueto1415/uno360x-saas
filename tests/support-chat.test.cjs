const {test}=require('node:test');
const assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../support_center/web/chat.js'),'utf8');
const wait=()=>new Promise(r=>setTimeout(r,20));
function setup(t,fetcher,lang='es_DO',expenseAllowed=false){
 const dom=new JSDOM(`<html lang="${lang}"><body><a href="/uno360x-ayuda">Ayuda</a></body></html>`,{url:'https://piloto.uno360x.com/uno360x-resumen',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,calls=[];
 w.fetch=async(url,options)=>{if(url==='/__expenses')return {ok:true,json:async()=>({enabled:expenseAllowed})};calls.push({url,options});const result=fetcher?await fetcher(url,options):{cases:[],selected:null,messages:[],csrf_token:'safe-token'};return {ok:true,json:async()=>result};};
 w.eval(source);t.after(()=>w.close());return {w,d:w.document,calls};
}
async function openExisting(w,d){
 d.querySelector('.us-launch').click();await wait();
}
test('idle chat makes no requests; support link opens it and escape closes it',async t=>{
 const {w,d,calls}=setup(t);assert.equal(calls.length,0);
 d.querySelector('a').click();await wait();assert.equal(d.querySelector('#us-panel').hidden,false);assert.equal(calls.length,1);
 d.querySelector('#us-text').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(d.querySelector('#us-panel').hidden,true);
});
test('double submit sends one message and renders untrusted text safely',async t=>{
 let resolvePost;
 const selected={id:'a'.repeat(32),title:'Consulta',human:0,status:'open'};
 const empty={cases:[],selected:null,messages:[],csrf_token:'safe-token'};
 const {w,d,calls}=setup(t,(url,o)=>o.method==='POST'?new Promise(r=>{resolvePost=r;}):empty);
 d.querySelector('.us-launch').click();await wait();d.querySelector('#us-text').value='Tengo un problema';
 const event=()=>new w.Event('submit',{bubbles:true,cancelable:true});d.querySelector('form').dispatchEvent(event());d.querySelector('form').dispatchEvent(event());await wait();
 assert.equal(calls.filter(c=>c.options.method==='POST').length,1);
 const posted=JSON.parse(calls[1].options.body);assert.equal(posted.body,'Tengo un problema');assert.equal(calls[1].options.headers['X-CSRF-Token'],'safe-token');
 resolvePost({cases:[selected],selected,messages:[{id:1,role:'user',body:'<img src=x onerror=alert(1)>',state:'done'}],csrf_token:'safe-token'});await wait();
 assert.equal(d.querySelector('.us-messages img'),null);assert.match(d.querySelector('.us-messages').textContent,/<img/);assert.equal(d.querySelector('#us-text').value,'');
});
test('human first sends the next message directly to the team; English labels',async t=>{
 const {d}=setup(t,null,'en_US');d.querySelector('.us-launch').click();await wait();d.querySelector('.us-human').click();assert.match(d.querySelector('.us-status').textContent,/Write your message/);assert.equal(d.querySelector('.us-send').textContent,'Send');
});
test('loader is idempotent across partial navigation',t=>{const {w,d}=setup(t);w.eval(source);assert.equal(d.querySelectorAll('#uno-support').length,1);});
test('handoff keeps sending available without waiting for a refresh',async t=>{
 const selected={id:'a'.repeat(32),title:'Consulta',human:0,status:'open'};
 const messages=[{id:1,role:'user',body:'Consulta de prueba',state:'done'},{id:2,role:'assistant',body:'Respuesta de prueba',state:'done'}];
 const {w,d,calls}=setup(t,(url,options)=>({cases:[{...selected,human:options.method==='POST'?1:0}],selected:{...selected,human:options.method==='POST'?1:0},messages,csrf_token:'safe-token'}));
 await openExisting(w,d);d.querySelector('.us-human').click();await wait();
 assert.equal(d.querySelector('.us-send').disabled,false);
 assert.match(d.querySelector('.us-status').textContent,/Enviado al equipo/);
 assert.equal(JSON.parse(calls.find(c=>c.options.method==='POST').options.body).handoff,true);
});
test('resolved human conversation displays its resolved state',async t=>{
 const selected={id:'a'.repeat(32),title:'Consulta',human:1,status:'resolved'};
 const {w,d}=setup(t,()=>({cases:[selected],selected,messages:[],csrf_token:'safe-token'}));
 await openExisting(w,d);
 assert.match(d.querySelector('.us-status').textContent,/resolvió/);
 assert.doesNotMatch(d.querySelector('.us-status').textContent,/Enviado al equipo/);
});
test('active human conversation can explicitly return to Jenifer',async t=>{
 const selected={id:'a'.repeat(32),title:'Consulta',human:1,status:'open'};
 const {w,d,calls}=setup(t,(url,o)=>({cases:[selected],selected:{...selected,human:o.method==='POST'?0:1},messages:[],csrf_token:'safe-token'}));
 await openExisting(w,d);
 assert.equal(d.querySelector('.us-ai').hidden,false);
 d.querySelector('.us-ai').click();await wait();
 assert.equal(JSON.parse(calls.find(c=>c.options.method==='POST').options.body).resume,true);
 assert.equal(d.querySelector('.us-ai').hidden,true);
 assert.equal(d.querySelector('.us-send').disabled,false);
});
test('verified local paths become clickable while external links remain text',async t=>{
 const selected={id:'a'.repeat(32),title:'CRM',human:0,status:'open'};
 const {w,d}=setup(t,()=>({cases:[selected],selected,messages:[{id:1,role:'assistant',state:'done',body:'Comercial → CRM. Abrir: /uno360x/area/crm. https://evil.example/uno360x/data'}],csrf_token:'safe-token'}));
 await openExisting(w,d);
 const links=d.querySelectorAll('.us-message a');assert.equal(links.length,1);
 assert.equal(links[0].getAttribute('href'),'/uno360x/area/crm');
 assert.match(d.querySelector('.us-message').textContent,/https:\/\/evil.example/);
});
test('reopening and a fresh page retain the continuous history without a selector',async t=>{
 const selected={id:'a'.repeat(32),title:'Cerrada',human:1,status:'resolved'};
 const {d}=setup(t,()=>({cases:[selected],selected,messages:[{id:1,role:'team',body:'Mensaje viejo',state:'done'}],csrf_token:'safe-token'}));
 d.querySelector('.us-launch').click();await wait();
 assert.equal(d.querySelector('select'),null);assert.equal(d.querySelector('.us-new'),null);
 assert.match(d.querySelector('.us-messages').textContent,/Mensaje viejo/);
 assert.match(d.querySelector('.us-status').textContent,/Jenifer está disponible/);
 d.querySelector('.us-close').click();d.querySelector('.us-launch').click();await wait();
 assert.match(d.querySelector('.us-messages').textContent,/Mensaje viejo/);
});

test('older history is loaded once and retained across refreshes without duplication',async t=>{
 const selected={id:'a'.repeat(32),human:0,status:'open'};
 const message=(id)=>({id,role:'assistant',body:'Mensaje '+id,state:'done'});
 const {w,d,calls}=setup(t,(url)=>({cases:[selected],selected,messages:url.includes('before=')?[message(1)]:[message(2),message(3)],has_older:!url.includes('before='),csrf_token:'safe-token'}));
 await openExisting(w,d);assert.equal(d.querySelector('.us-older').hidden,false);
 d.querySelector('.us-older').click();await wait();
 assert.match(calls.at(-1).url,/case_id=a{32}&before=2/);
 assert.equal(d.querySelectorAll('.us-message').length,3);
 assert.equal(d.querySelector('.us-older').hidden,true);
 d.querySelector('.us-close').click();d.querySelector('.us-launch').click();await wait();
 assert.equal(d.querySelectorAll('.us-message').length,3);assert.equal(d.querySelector('.us-older').hidden,true);
});

test('expense shortcut is shown only after accounting capability is verified',async t=>{
 const allowed=setup(t,null,'es_DO',true);
 allowed.d.querySelector('.us-launch').click();await wait();
 assert.equal(allowed.d.querySelector('.us-expense').hidden,false);
 assert.equal(allowed.d.querySelector('.us-expense').getAttribute('href'),'/uno360x/jenifer/gastos');
 const denied=setup(t,null,'es_DO',false);
 denied.d.querySelector('.us-launch').click();await wait();
 assert.equal(denied.d.querySelector('.us-expense').hidden,true);
});
