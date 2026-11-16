import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { businessAccess } from './access.mjs';
import { seed, apply, cashSummary } from './domain.mjs';
const here=dirname(fileURLToPath(import.meta.url));
const roles=new Set(['caja','camarero','cocina','barra','supervisor']);
export function makeServer(file, access=null){
 if(file!==':memory:')mkdirSync(dirname(file),{recursive:true});
 const db=new DatabaseSync(file);
 db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS pilot (id TEXT PRIMARY KEY, state TEXT NOT NULL)');
 const read=db.prepare('SELECT state FROM pilot WHERE id=?');
 const write=db.prepare('INSERT INTO pilot VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state');
 function state(scope){const row=read.get(scope);return row?JSON.parse(row.state):seed();}
 function mutation(command,user,scope,actor){
  db.exec('BEGIN IMMEDIATE');
  try{
   const s=state(scope);
   const key=command.key;
   if(!/^[0-9a-f-]{36}$/.test(key||''))throw new Error('Falta la referencia de operación.');
   const {key:ignored,...payload}=command;
   const signature=JSON.stringify(payload);
   const prior=s.operations[key];
   if(prior&&(prior.user!==actor||prior.signature!==signature))throw new Error('La referencia ya corresponde a otra operación.');
   const result=prior?.result??apply(s,command,user,actor);
   s.operations[key]={user:actor,signature,result};
   write.run(scope,JSON.stringify(s));db.exec('COMMIT');
   return {result,state:s,summary:cashSummary(s)};
  }catch(error){db.exec('ROLLBACK');throw error;}
 }
 const files={'/':'index.html','/app.mjs':'app.mjs','/domain.mjs':'domain.mjs','/style.css':'style.css',
  '/images/burger.jpg':'images/burger.jpg','/images/wings.jpg':'images/wings.jpg','/images/mojito.jpg':'images/mojito.jpg'};
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
   if(req.method==='GET'&&url.pathname==='/api/state'){
    const s=state(scope);return reply(res,200,{state:s,summary:cashSummary(s),connected:connected?{role:connected.role,branchName:connected.branchName}:null});
   }
   if(req.method==='POST'&&url.pathname==='/api/command'){
    if(req.headers.origin&&req.headers.origin!=='http://'+req.headers.host)return reply(res,403,{error:'Origen inválido.'});
    if(!req.headers['content-type']?.startsWith('application/json'))return reply(res,415,{error:'Tipo de solicitud inválido.'});
    const user=connected?.role||req.headers['x-pos-role'];if(!roles.has(user))return reply(res,403,{error:'Rol de laboratorio inválido.'});
    let body='';
    for await(const block of req){
     body+=block;if(body.length>850000)return reply(res,413,{error:'Archivo demasiado grande.'});
    }
    return reply(res,200,mutation(JSON.parse(body),user,scope,connected?.account||user));
   }
   reply(res,404,{error:'Ruta no encontrada.'});
  }catch(e){reply(res,400,{error:e.message});}
 });
 server.on('close',()=>{db.close();access?.close();});
 return server;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const port=Number(process.env.POS_PORT||4177);
 const {POS_IDENTITY_DB,POS_ENTITLEMENTS}=process.env;
 if(Boolean(POS_IDENTITY_DB)!==Boolean(POS_ENTITLEMENTS))throw new Error('Configura la base de identidad y las autorizaciones POS juntas.');
 const access=POS_IDENTITY_DB?businessAccess(POS_IDENTITY_DB,POS_ENTITLEMENTS):null;
 makeServer(process.env.POS_DB||join(here,'var','pilot.sqlite'),access).listen(port,'127.0.0.1',()=>console.log('UNO360X POS de pruebas: http://127.0.0.1:'+port));
}
