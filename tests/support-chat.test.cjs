const {test}=require('node:test');
const assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../support_center/web/chat.js'),'utf8');
const wait=()=>new Promise(r=>setTimeout(r,20));
function setup(t,fetcher,lang='es_DO'){
 const dom=new JSDOM(`<html lang="${lang}"><body><a href="/uno360x-ayuda">Ayuda</a></body></html>`,{url:'https://piloto.uno360x.com/uno360x-resumen',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,calls=[];
 w.fetch=async(url,options)=>{calls.push({url,options});const result=fetcher?await fetcher(url,options):{cases:[],selected:null,messages:[],csrf_token:'safe-token'};return {ok:true,json:async()=>result};};
 w.eval(source);t.after(()=>w.close());return {w,d:w.document,calls};
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
