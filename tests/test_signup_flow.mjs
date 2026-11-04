import vm from 'node:vm';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const file=new URL('../control/web/app.js',import.meta.url);
// Exercise the actual UI functions; initialization is invoked explicitly below.
const source=fs.readFileSync(file,'utf8').replace(/^\(async\(\)=>\{.*$/m,'');
const elements=new Map(),calls=[],navLinks=[{},{}],redirects=[],listeners={};
function element(key){if(!elements.has(key))elements.set(key,{innerHTML:'',hidden:false,classList:{add(){},remove(){}},scrollIntoView(){},addEventListener(){}});return elements.get(key);}
let companiesState=[{id:'existing-company',name:'Existing Company',slug:'existing-company'}];let loginStatus=200;let authenticated=true,launchFailure=false,readyState={is_trial:true,local_ready:true,trial_active:true,expires:2000000000,days_remaining:15,name:"Existing Company"};const submissions=[];let nativeLaunch=false,nativeLaunchUrl="https://erp.uno360x.com/__operational/enter";
const context=vm.createContext({
 document:{createElement:tag=>({tag,append(){},submit(){submissions.push(this.action);}}),body:{append(){}},querySelector:selector=>selector==='#login-message'&&!element('#screen').innerHTML.includes('id="login-message"')?null:element(selector),querySelectorAll:selector=>selector==='[data-session-action]'?navLinks:[],addEventListener(){}},
 location:{pathname:'/prueba/inicio',search:''},history:{state:null,pushState(a,b,path){this.state=a;const u=new URL(path,'https://cuenta.uno360x.com');context.location.pathname=u.pathname;context.location.search=u.search;},replaceState(a,b,path){this.state=a;const u=new URL(path,'https://cuenta.uno360x.com');context.location.pathname=u.pathname;context.location.search=u.search;}},window:{location:{replace(path){redirects.push(path);}},addEventListener(name,handler){listeners[name]=handler;},scrollTo(){}},
 sessionStorage:{getItem:()=>JSON.stringify({name:'Old name',email:'old@example.test',modules:['payroll_hr','jenifer_ai','projects_services']}),setItem(){}},
 setTimeout,clearTimeout,URLSearchParams,URL,
 fetch:async(path)=>{calls.push(path);if(path==='/logout')authenticated=false;return {ok:(path!='/session'||authenticated)&&!(path==='/spaces/open'&&launchFailure)&&!(path==='/login'&&loginStatus!==200),status:path==='/session'&&!authenticated?401:path==='/login'?loginStatus:200,json:async()=>path==='/session'?{email:'existing@example.test',csrf_token:'fictional-csrf'}:path==='/companies'?{companies:companiesState}:path==='/trial/draft'?{name:'Saved signup name',modules:['projects_services']}:path==='/trial/status'?readyState:path==='/spaces/open'?(launchFailure?{error:'Acceso temporalmente no disponible'}:{launch_url:nativeLaunch?nativeLaunchUrl:'http://127.0.0.1:18001/__launch',grant:'fictional-grant',operational_access:nativeLaunch}):{logged_out:true}};},
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
assert.equal(element('.stepper').innerHTML,'','Existing ready companies must not show creation steps');
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

const draftRequests=calls.filter(path=>path==='/trial/draft').length;
authenticated=true;companiesState=[];
await vm.runInContext("draft.name='';draft.modules=[];refreshSession().then(()=>afterLogin())",context);
await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
assert.equal(calls.filter(path=>path==='/trial/draft').length,draftRequests+1);
assert.equal(vm.runInContext('draft.name',context),'Saved signup name');
assert.equal(vm.runInContext('draft.modules.join()',context),'projects_services');
assert(element('#screen').innerHTML.includes('id="company-form"'));
console.log('Only new-company setup loads its saved signup draft; existing-company entry skips that round trip.');

authenticated=false;loginStatus=400;
await assert.rejects(vm.runInContext("api('/login',{email:'fixture@example.test',password:'incorrect'})",context),error=>error.message==='Contraseña incorrecta.');
await vm.runInContext("account=null;location.pathname='/web/login';render()",context);
assert(element('#screen').innerHTML.includes('id="login-message"'));
await vm.runInContext("message('Contraseña incorrecta.')",context);
assert.equal(element('#login-message').textContent,'Contraseña incorrecta.');
assert.equal(element('#notice').hidden,true,'Login errors must not use the global red strip');
await vm.runInContext("message('')",context);assert.equal(element('#login-message').hidden,true);
loginStatus=429;
await assert.rejects(vm.runInContext("api('/login',{})",context),error=>error.message!=='Contraseña incorrecta.');
console.log('Incorrect credentials use inline login feedback; rate limits retain their own error.');

// Operational entry must skip trial setup and accept only the fixed ERP exchange.
authenticated=true;loginStatus=200;nativeLaunch=true;
companiesState=[{id:'__operational__',name:'OUTSOLUTECH',operational:true}];
const nativeBefore=submissions.length,nativeTrialCalls=calls.filter(p=>p==='/trial/status').length;
await vm.runInContext('refreshSession().then(()=>afterLogin())',context);
assert.equal(submissions.length,nativeBefore+1);
assert.equal(submissions.at(-1),'https://erp.uno360x.com/__operational/enter');
assert.equal(calls.filter(p=>p==='/trial/status').length,nativeTrialCalls,'Native companies must never be prepared as a SaaS trial');
assert.equal(element('.stepper').innerHTML,'');
nativeLaunchUrl='https://erp.uno360x.com.evil.example/__operational/enter';
await vm.runInContext("openOdoo('__operational__')",context);
assert.equal(submissions.length,nativeBefore+1,'A response flag must not permit an untrusted handoff destination');
console.log('Unified native entry skips creation steps and rejects altered ERP destinations.');

// A queued creation must not trap its owner in the same session or create again.
nativeLaunch=false;authenticated=true;companiesState=[{id:'existing-company',name:'Existing Company'}];
readyState={is_trial:true,local_ready:false,status:'queued',current_step:'capacity',completed_steps:[],name:'Queued Company'};
await vm.runInContext("tenantId='existing-company';history.replaceState({},'','/prueba/preparando');refreshSession().then(()=>render())",context);
assert(element('#screen').innerHTML.includes('Iniciar sesión con otra cuenta'));
const createsBefore=calls.filter(p=>p==='/trial/create').length;
await element('#switch-pending-account').onclick({target:{disabled:false}});
await new Promise(resolve=>setImmediate(resolve));
assert.equal(context.location.pathname,'/web/login');
assert(element('#screen').innerHTML.includes('id="login-form"'));
assert.equal(vm.runInContext('tenantId',context),'');
assert.equal(calls.filter(p=>p==='/trial/create').length,createsBefore);
authenticated=true;
await vm.runInContext("history.replaceState({},'','/web/login?cambiar=cuenta');refreshSession().then(()=>render())",context);
assert(element('#screen').innerHTML.includes('Iniciar sesión con otra cuenta'));
vm.runInContext('clearTimeout(timer)',context);
console.log('Pending creation permits account switching without cancelling or duplicating the company.');

const pendingMarkup=vm.runInContext("preparationMarkup({name:'Empresa <script>',status:'preparing',completed_steps:['network']})",context);
assert(pendingMarkup.includes('Empresa &lt;script&gt;'));
assert(pendingMarkup.includes('aria-current="step"'));
assert.equal((pendingMarkup.match(/class="complete"/g)||[]).length,1,'Only completed server steps may be shown as done');
assert(pendingMarkup.includes('creation-wait is-running'));
const queuedMarkup=vm.runInContext("preparationMarkup({name:'Empresa',status:'queued',current_step:'capacity',completed_steps:[]})",context);
assert(!queuedMarkup.includes('is-running'),'Capacity queues must not pretend to be configuring');
assert(!queuedMarkup.includes('aria-current="step"'));
const failedMarkup=vm.runInContext("preparationMarkup({name:'Empresa',status:'failed',completed_steps:['network']})",context);
assert(!failedMarkup.includes('is-running'),'Failure must stop the waiting animation');
assert(failedMarkup.includes('Pendiente de revisión'));
console.log('Creation stages follow server progress, escape company names and stop animation for queues or failures.');

// A temporary status outage must keep the account and schedule another poll.
const originalFetch=context.fetch;const originalTimer=context.setTimeout;let scheduled=[];
context.setTimeout=(fn,delay)=>{scheduled.push(delay);return 999;};
await vm.runInContext("account={email:'keep@example.test'};csrf='keep-csrf';tenantId='existing-company';",context);
context.fetch=async()=>{throw new Error('temporary network outage');};
await vm.runInContext('recoverPreparation()',context);
assert.equal(vm.runInContext('account.email',context),'keep@example.test');
assert(scheduled.includes(8000),'Preparation must recover after a transient request failure');
assert(element('#notice').textContent.includes('automáticamente'));
context.fetch=originalFetch;context.setTimeout=originalTimer;
const markup=vm.runInContext("preparationMarkup({name:'Queued',status:'queued',current_step:'capacity',completed_steps:[]})",context);
assert(markup.includes('Tu correo y tu solicitud están confirmados'));
assert(!markup.includes('is-running'),'Waiting capacity must not pretend work is running');
vm.runInContext('clearTimeout(timer)',context);
console.log('Transient preparation recovery retains account; capacity wait is explicit and does not animate false progress.');
