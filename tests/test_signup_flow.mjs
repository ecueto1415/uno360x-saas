import vm from 'node:vm';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const file=new URL('../control/web/app.js',import.meta.url);
// Exercise the actual UI functions; initialization is invoked explicitly below.
const source=fs.readFileSync(file,'utf8').replace(/^\(async\(\)=>\{.*$/m,'');
const elements=new Map(),calls=[],navLinks=[{},{}],redirects=[],listeners={};
function element(key){if(!elements.has(key))elements.set(key,{innerHTML:'',hidden:false,classList:{add(){},remove(){}},scrollIntoView(){},addEventListener(){}});return elements.get(key);}
let authenticated=true,launchFailure=false,readyState={is_trial:true,local_ready:true,trial_active:true,expires:2000000000,days_remaining:15,name:"Existing Company"};const submissions=[];
const context=vm.createContext({
 document:{createElement:tag=>({tag,append(){},submit(){submissions.push(this.action);}}),body:{append(){}},querySelector:element,querySelectorAll:selector=>selector==='[data-session-action]'?navLinks:[],addEventListener(){}},
 location:{pathname:'/prueba/inicio',search:''},history:{state:null,pushState(a,b,path){this.state=a;const u=new URL(path,'https://cuenta.uno360x.com');context.location.pathname=u.pathname;context.location.search=u.search;},replaceState(a,b,path){this.state=a;const u=new URL(path,'https://cuenta.uno360x.com');context.location.pathname=u.pathname;context.location.search=u.search;}},window:{location:{replace(path){redirects.push(path);}},addEventListener(name,handler){listeners[name]=handler;},scrollTo(){}},
 sessionStorage:{getItem:()=>JSON.stringify({name:'Old name',email:'old@example.test',modules:['payroll_hr','jenifer_ai','projects_services']}),setItem(){}},
 setTimeout,clearTimeout,URLSearchParams,URL,
 fetch:async(path)=>{calls.push(path);if(path==='/logout')authenticated=false;return {ok:(path!='/session'||authenticated)&&!(path==='/spaces/open'&&launchFailure),json:async()=>path==='/session'?{email:'existing@example.test',csrf_token:'fictional-csrf'}:path==='/companies'?{companies:[{id:'existing-company',name:'Existing Company',slug:'existing-company'}]}:path==='/trial/status'?readyState:path==='/spaces/open'?(launchFailure?{error:'Acceso temporalmente no disponible'}:{launch_url:'http://127.0.0.1:18001/__launch',grant:'fictional-grant'}):{logged_out:true}};},
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
assert(navLinks.every(link=>link.textContent==='Iniciar sesión'));
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
assert(navLinks.every(link=>link.textContent==='Iniciar sesión'));
await element('#logout-for-new-company').onclick({target:{disabled:false}});
await new Promise(resolve=>setImmediate(resolve));
assert(navLinks.every(link=>link.textContent==='Iniciar sesión'));
assert.equal(vm.runInContext('draft.email',context),'');
await vm.runInContext("draft.email='existing@example.test';existingEmail({account_exists:true,verification_required:false,message:'Ya existe una cuenta.'})",context);
assert(element('#screen').innerHTML.includes('Esta cuenta ya existe'));
assert(element('#screen').innerHTML.includes('Crear cuenta con otro correo'));
element('#use-other-email').onclick();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(vm.runInContext('draft.email',context),'');
console.log('Signup flow passed: clean defaults, existing-email recovery, explicit account choice, logout navigation and existing-company history guard.');

authenticated=true;
const logoutCount=calls.filter(path=>path==='/logout').length;
await vm.runInContext("refreshSession().then(()=>{location.pathname='/web/login';return render();})",context);
await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
assert.equal(submissions.length,1,'Iniciar sesión must open the ready workspace for an existing session');
assert.equal(calls.filter(path=>path==='/logout').length,logoutCount,'Account entry must never log out');
assert.equal(context.history.state.uno360xReturnHome,true);
listeners.pageshow({persisted:true});assert.equal(redirects.at(-1),'https://uno360x.com/','Back from the workspace must go home, without relaunching');
const before=submissions.length;listeners.popstate();assert.equal(submissions.length,before);
assert.equal(redirects.at(-1),'https://uno360x.com/');
vm.runInContext("history.replaceState({},'','/web/login')",context);
authenticated=false;await vm.runInContext('refreshSession().then(()=>render())',context);
assert(element('#screen').innerHTML.includes('id="login-form"'));
submissions.length=0;
console.log('Existing session opens directly; history restoration goes home without logout or relaunch.');

authenticated=true;
await vm.runInContext('refreshSession().then(()=>afterLogin())',context);
await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
assert.equal(submissions.length,1,'Successful login must automatically enter an existing ready company');
assert.equal(submissions[0],'http://127.0.0.1:18001/__launch');
launchFailure=true;
await vm.runInContext('preparation()',context);
assert.equal(submissions.length,1);
assert.equal(element('#enter-space,#open-odoo').disabled,false);
assert.equal(element('#enter-space,#open-odoo').textContent,'Volver a intentar');
launchFailure=false;
await element('#enter-space').onclick();assert.equal(submissions.length,2);
readyState={...readyState,expires:1,days_remaining:0};
await vm.runInContext('preparation()',context);
assert(element('#screen').innerHTML.includes('Tu prueba ha terminado'));assert.equal(submissions.length,2);
console.log('Automatic entry, retry after failure and expired-trial protection passed.');

await vm.runInContext("flowStarted=false;location.pathname='/prueba/inicio';location.search='?modules=projects_services,unknown,__proto__';render()",context);
assert.equal(vm.runInContext('draft.modules.join()',context),'projects_services');
await vm.runInContext("draft.modules=['payroll_hr'];render()",context);
assert.equal(vm.runInContext('draft.modules.join()',context),'payroll_hr','Back navigation must retain the current selection');
console.log('Pricing selection transfer, whitelist and history preservation passed.');
