import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';

const roles=new Set(['caja','camarero','cocina','barra','supervisor']);

export function businessAccess(identityFile, grantsFile){
 const db=new DatabaseSync(identityFile,{readOnly:true});
 const account=db.prepare(`SELECT a.id FROM identity_sessions s JOIN accounts a ON a.id=s.account_id
  WHERE s.digest=? AND s.expires>? AND a.active=1 AND a.verified=1`);
 const member=db.prepare('SELECT role FROM memberships WHERE account_id=? AND tenant_id=? AND active=1');
 return {
  close(){db.close();},
  authorize(req){
   const cookies=Object.fromEntries((req.headers.cookie||'').split(';').map(x=>x.trim().split(/=(.*)/s).slice(0,2)));
   const session=cookies.uno360x_lab_session;
   if(!session||session.length>128)return null;
   const person=account.get(createHash('sha256').update(session).digest('hex'),Date.now()/1000);
   if(!person)return null;
   const grants=JSON.parse(readFileSync(grantsFile,'utf8'));
   const tenant=req.headers['x-pos-tenant']||grants.defaultTenant;
   if(typeof tenant!=='string'||!Object.hasOwn(grants.tenants??{},tenant))return null;
   const config=grants.tenants[tenant];
   const membership=member.get(person.id,tenant);
   if(!membership||config.enabled!==true||typeof config.branch!=='string'||!/^[-a-z0-9]+$/.test(config.branch))return null;
   const role=Object.hasOwn(config.users??{},person.id)?config.users[person.id]:
    ['owner','admin'].includes(membership.role)?'supervisor':null;
   if(!roles.has(role))return null;
   return {scope:tenant+':'+config.branch,role,account:person.id,branchName:config.branchName||config.branch};
  },
 };
}
