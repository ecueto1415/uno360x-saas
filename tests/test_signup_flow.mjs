import vm from 'node:vm';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const file=new URL('../control/web/app.js',import.meta.url);
// Exercise the actual UI functions; initialization is invoked explicitly below.
const source=fs.readFileSync(file,'utf8').replace(/^\(async\(\)=>\{const params=.*$/m,'');
const elements=new Map(),calls=[],navLinks=[{},{}];
function element(key){if(!elements.has(key))elements.set(key,{innerHTML:'',hidden:false,classList:{add(){},remove(){}},scrollIntoView(){},addEventListener(){}});return elements.get(key);}
let authenticated=true;
const context=vm.createContext({
 document:{querySelector:element,querySelectorAll:selector=>selector==='[data-session-action]'?navLinks:[],addEventListener(){}},
 location:{pathname:'/prueba/inicio'},history:{pushState(a,b,path){context.location.pathname=path;}},window:{addEventListener(){},scrollTo(){}},
 sessionStorage:{getItem:()=>JSON.stringify({name:'Old name',email:'old@example.test',modules:['payroll_hr','jenifer_ai','projects_services']}),setItem(){}},
 setTimeout,clearTimeout,URLSearchParams,
 fetch:async(path)=>{calls.push(path);if(path==='/logout')authenticated=false;return {ok:path!='/session'||authenticated,json:async()=>path==='/session'?{email:'existing@example.test',csrf_token:'fictional-csrf'}:path==='/companies'?{companies:[{id:'existing-company',name:'Existing Company',slug:'existing-company'}]}:{logged_out:true}};},
});
vm.runInContext(source,context);
await vm.runInContext('render()',context);
assert.equal(vm.runInContext('draft.modules.length',context),0,'Fresh entry must discard previous optional choices');
assert(!element('#screen').innerHTML.includes('checked'));
await vm.runInContext("draft.modules=['projects_services'];location.pathname='/prueba';render()",context);
assert(element('#screen').innerHTML.includes('checked'),'Changing selection must preserve current choices');
await vm.runInContext("location.pathname='/prueba/cuenta';render()",context);
assert(element('#screen').innerHTML.includes('existing@example.test'));
assert(element('#screen').innerHTML.includes('Crear una cuenta con otro correo'));
assert(navLinks.every(link=>link.textContent==='Salir'));
assert(!calls.includes('/companies'),'Existing sessions must not silently jump to their company');
await element('#different-account').onclick({target:{disabled:false}});
await new Promise(resolve=>setImmediate(resolve));
assert(calls.includes('/logout'));
assert(element('#screen').innerHTML.includes('id="register-form"'));
assert(!element('#screen').innerHTML.includes('old@example.test'));
assert.equal(vm.runInContext('draft.modules.join()',context),'projects_services');
assert(!calls.includes('/trial/register'),'Displaying signup must not create an account');
authenticated=true;
await vm.runInContext("location.pathname='/prueba/empresa';render()",context);
assert(element('#screen').innerHTML.includes('Tu cuenta ya tiene una empresa'));
assert(!element('#screen').innerHTML.includes('id="company-form"'));
assert(!calls.includes('/trial/create'),'Returning to company setup must not recreate a company');
assert(navLinks.every(link=>link.textContent==='Salir'));
await element('#logout-for-new-company').onclick({target:{disabled:false}});
await new Promise(resolve=>setImmediate(resolve));
assert(navLinks.every(link=>link.textContent==='Iniciar sesión'));
assert.equal(vm.runInContext('draft.email',context),'');
await vm.runInContext("draft.email='existing@example.test';existingEmail({account_exists:true,verification_required:false,message:'Ya existe una cuenta.'})",context);
assert(element('#screen').innerHTML.includes('Este correo ya tiene una cuenta'));
assert(element('#screen').innerHTML.includes('Crear cuenta con otro correo'));
element('#use-other-email').onclick();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(vm.runInContext('draft.email',context),'');
console.log('Signup flow passed: clean defaults, existing-email recovery, explicit account choice, logout navigation and existing-company history guard.');
