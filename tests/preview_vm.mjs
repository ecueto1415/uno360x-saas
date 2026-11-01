// Regression: preview must not overwrite Odoo/jQuery globals or call signup APIs.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const elements=new Map();
function element(){return {hidden:false,textContent:'',innerHTML:'',disabled:false,
 classList:{add(){},remove(){}},addEventListener(){},scrollIntoView(){},append(){},
 querySelector(){return element();},querySelectorAll(){return [];}};}
const jquery=()=>{};jquery.expr={':':{}};
let networkCalls=0;
const context={console,URL,URLSearchParams,FormData,Map,Date,
 location:{hash:'',pathname:'/prueba-saas'},history:{pushState(){},replaceState(){}},
 sessionStorage:{getItem(){return null;},setItem(){}},
 document:{title:'',querySelector(selector){if(!elements.has(selector))elements.set(selector,element());return elements.get(selector);},
 querySelectorAll(){return [];},addEventListener(){},createElement(){return element();},body:element()},
 fetch(){networkCalls++;throw new Error('Preview attempted a real request');},
 addEventListener(){},scrollTo(){},setTimeout(){return 0;},clearTimeout(){},$:jquery,jQuery:jquery};
context.window=context;
vm.createContext(context);new vm.Script(readFileSync(process.argv[2],'utf8')).runInContext(context);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(context.$,jquery);assert.equal(context.jQuery,jquery);
assert.match(elements.get('#screen').innerHTML,/Arma tu espacio de trabajo/);
await context.UNO360X_PREVIEW_API('/trial/register',{body:JSON.stringify({email:'example@example.test',modules:[]})});
const response=await context.UNO360X_PREVIEW_API('/login',{body:JSON.stringify({email:'example@example.test',password:'not-stored'})});
assert.equal(response.ok,true);assert.equal(networkCalls,0);
console.log(JSON.stringify({existing_jquery_preserved:true,initial_screen_rendered:true,real_network_calls:networkCalls}));
