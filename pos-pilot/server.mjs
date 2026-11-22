import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync, realpathSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { stockConnector } from './lab-stock.mjs';
import { businessAccess } from './access.mjs';
import {proxyAccess,bodyMatches} from './proxy-access.mjs';
import { seed, apply, cashSummary,publicState } from './domain.mjs';
const here=dirname(fileURLToPath(import.meta.url));
const roles=new Set(['caja','camarero','cocina','barra','supervisor']);
const demoStaff=[{id:'caja',name:'Cajero de prueba'},{id:'camarero',name:'Camarero de prueba'},{id:'supervisor',name:'Supervisor de prueba'},{id:'ana',name:'Ana García'},{id:'carlos',name:'Carlos Pérez'}];
export function makeServer(file, access=null, inventory=null, origin=null, options={}){
 if(origin&&(!access||new URL(origin).protocol!=='https:'||new URL(origin).origin!==origin))
  throw Error('El acceso por red local requiere HTTPS y una identidad del negocio.');
 if(file!==':memory:')mkdirSync(dirname(file),{recursive:true});
 const db=new DatabaseSync(file);
 db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS pilot (id TEXT PRIMARY KEY, state TEXT NOT NULL)');
 const read=db.prepare('SELECT state FROM pilot WHERE id=?');
 const write=db.prepare('INSERT INTO pilot VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state');
 function state(scope){const row=read.get(scope);return row?JSON.parse(row.state):seed(options);}
 function view(body,user,actor){
  if(['supervisor','caja'].includes(user))return body;
  const result=['cocina','barra'].includes(user)&&body.result?Object.fromEntries(['id','status','station','type','ingredient','quantity','expected','difference','reason'].filter(k=>Object.hasOwn(body.result,k)).map(k=>[k,body.result[k]])):body.result;
  return {...body,result,state:publicState(body.state,user,actor),summary:{restricted:true,methods:{},refunds:{}}};
 }
 function mutation(command,user,scope,actor,staff){
  db.exec('BEGIN IMMEDIATE');
  try{
   const s=state(scope);
   const key=command.key;
   if(!/^[0-9a-f-]{36}$/.test(key||''))throw new Error('Falta la referencia de operación.');
   const {key:ignored,...payload}=command;
   const signature=JSON.stringify(payload);
   const prior=s.operations[key];
   if(prior&&(prior.user!==actor||prior.signature!==signature))throw new Error('La referencia ya corresponde a otra operación.');
   const auditStart=s.audits.length;
   const result=prior?.result??apply(s,command,user,actor,staff);
   for(const audit of s.audits.slice(auditStart))audit.userName=staff.find(p=>p.id===actor)?.name||actor;
   s.operations[key]={user:actor,signature,result};
   write.run(scope,JSON.stringify(s));db.exec('COMMIT');
   return {result,state:s,summary:cashSummary(s)};
  }catch(error){db.exec('ROLLBACK');throw error;}
 }
 async function syncInventory(scope){
  const pending=state(scope).events.filter(e=>['sale','waste'].includes(e.type)&&e.reference&&!e.centralMove);
  const replies=[];
  for(const event of pending){
   try{
    const move=await inventory(scope,event);
    db.exec('BEGIN IMMEDIATE');
    try{
     const s=state(scope);
     const current=s.events.find(row=>row.reference===event.reference);
     if(!current)throw Error('Movimiento local no disponible.');
     current.centralMove=move;
     write.run(scope,JSON.stringify(s));db.exec('COMMIT');
    }catch(e){db.exec('ROLLBACK');throw e;}
    replies.push({reference:event.reference,state:'confirmado',move});
   }catch(e){replies.push({reference:event.reference,state:'pendiente',reason:e.message});}
  }
  return replies;
 }
 const files={'/':'index.html','/app.mjs':'app.mjs','/domain.mjs':'domain.mjs','/style.css':'style.css',
  '/images/burger.jpg':'images/burger-hq.jpg','/images/wings.jpg':'images/wings-hq.jpg','/images/mojito.jpg':'images/mojito-hq.jpg'};
 const content={html:'text/html; charset=utf-8',mjs:'text/javascript; charset=utf-8',css:'text/css; charset=utf-8',jpg:'image/jpeg'};
 function reply(res,status,body,mime='application/json; charset=utf-8'){
  res.writeHead(status,{'Content-Type':mime,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
   'Content-Security-Policy':"default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"});
  res.end(mime.startsWith('application/json')?JSON.stringify(body):body);
 }
 const server=createServer(async(req,res)=>{
  try{
   const url=new URL(req.url,'http://localhost');
   if(req.method==='GET'&&Object.hasOwn(files,url.pathname)){
    const file=files[url.pathname];return reply(res,200,readFileSync(join(here,file)),content[file.split('.').at(-1)]);
   }
   const connected=access?.authorize(req);
   if(access&&!connected)return reply(res,403,{error:'La cuenta no tiene acceso al POS de esta sucursal.'});
   const scope=connected?.scope||'negocio-demostracion:sucursal-centro';
   const authorizedRole=()=>connected?.role==='caja'?(state(scope).staffRoles?.[connected.account]||'caja'):connected?.role||req.headers['x-pos-role']||(req.method==='GET'?'supervisor':undefined);
   const staff=connected?(connected.staff||[{id:connected.account,name:connected.displayName||connected.account}]):demoStaff;
   if(req.method==='GET'&&url.pathname==='/api/state'){
    const s=state(scope),user=authorizedRole();if(!roles.has(user))return reply(res,403,{error:'Rol inválido.'});
    return reply(res,200,view({state:s,summary:cashSummary(s),inventoryConnected:Boolean(inventory),staff,connected:connected?{role:user,branchName:connected.branchName,displayName:connected.displayName||'',account:connected.account}:null},user,connected?.account||user));
   }
   if(req.method==='POST'&&url.pathname==='/api/command'){
    if(req.headers.origin&&req.headers.origin!==(origin||'http://'+req.headers.host))return reply(res,403,{error:'Origen inválido.'});
    if(!req.headers['content-type']?.startsWith('application/json'))return reply(res,415,{error:'Tipo de solicitud inválido.'});
    let user=authorizedRole();if(!roles.has(user))return reply(res,403,{error:'Rol de laboratorio inválido.'});
    let body='';
    for await(const block of req){
     body+=block;if(body.length>850000)return reply(res,413,{error:'Archivo demasiado grande.'});
    }
    if(!bodyMatches(connected,body))return reply(res,403,{error:'Solicitud no autorizada.'});
    user=authorizedRole();if(!roles.has(user))return reply(res,403,{error:'Rol inválido.'});
    const command=JSON.parse(body);
    if(command.type==='sync-inventory'){
     if(!inventory||!['caja','supervisor'].includes(user))return reply(res,403,{error:'Inventario central de pruebas no disponible para este rol.'});
     const result=await syncInventory(scope),s=state(scope);
     return reply(res,200,{result,state:s,summary:cashSummary(s)});
    }
    return reply(res,200,view(mutation(command,user,scope,connected?.account||user,staff),user,connected?.account||user));
   }
   reply(res,404,{error:'Ruta no encontrada.'});
  }catch(e){reply(res,400,{error:e.message});}
 });
 server.on('close',()=>{db.close();access?.close();});
 return server;
}
export function makeDemoServer(...args){args[4]={demo:true};return makeServer(...args);}
if(process.argv[1]&&import.meta.url===pathToFileURL(realpathSync(process.argv[1])).href){
 const port=Number(process.env.POS_PORT||4177);
 const {POS_IDENTITY_DB,POS_ENTITLEMENTS}=process.env;
 if(Boolean(POS_IDENTITY_DB)!==Boolean(POS_ENTITLEMENTS))throw new Error('Configura la base de identidad y las autorizaciones POS juntas.');
 const access=process.env.POS_PROXY_KEY?proxyAccess(process.env.POS_PROXY_KEY):POS_IDENTITY_DB?businessAccess(POS_IDENTITY_DB,POS_ENTITLEMENTS):null;
 makeServer(process.env.POS_DB||join(here,'var','pilot.sqlite'),access,process.env.POS_ODOO_CONFIG?stockConnector(process.env.POS_ODOO_CONFIG):null,process.env.POS_ORIGIN).listen(port,process.env.POS_BIND_HOST||'127.0.0.1',()=>console.log('UNO360X POS de pruebas: http://127.0.0.1:'+port));
}
