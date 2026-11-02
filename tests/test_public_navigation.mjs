import vm from 'node:vm';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../deployment/public_navigation.js',import.meta.url),'utf8');
function run(origin,path='/'){
 const callbacks={};const login={href:'https://cuenta.uno360x.com/web/login',textContent:'Iniciar sesión',addEventListener(){throw new Error('Login must remain a normal link');}};
 const trial={href:'https://cuenta.uno360x.com/prueba/inicio',addEventListener(name,fn){callbacks[name]=fn;}};
 const document={title:'UNO360X | My Website',querySelectorAll(selector){return selector==='a'?[login,trial]:[{dataset:{module:'Proyectos y Servicios'}},{dataset:{module:'unknown'}}];}};
 vm.runInNewContext(source,{location:{origin,pathname:path},document,URL});return {login,trial,callbacks,document};
}
for(const origin of ['https://uno360x.com','https://www.uno360x.com']){const result=run(origin);assert.equal(result.login.textContent,'Iniciar sesión');assert.equal(result.login.href,'https://cuenta.uno360x.com/web/login');assert.equal(result.document.title,'UNO360X');}
const plan=run('https://uno360x.com','/planes-y-precios');plan.callbacks.click();assert.equal(new URL(plan.trial.href).searchParams.get('modules'),'projects_services');
assert.equal(run('https://erp.uno360x.com').document.title,'UNO360X | My Website');
console.log('Public Iniciar sesión remains an ordinary account-entry link; pricing selection and ERP exclusion passed.');
