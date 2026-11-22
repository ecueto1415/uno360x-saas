import {createHmac,timingSafeEqual,createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
export function proxyAccess(keyFile){
 const key=readFileSync(keyFile,'utf8').trim();if(key.length<48)throw Error('Proxy key unavailable');
 return {close(){},authorize(req){
  try{
   const token=req.headers['x-uno-pos-proof'];if(typeof token!=='string'||token.length>14000)return null;
   const [payload,signature,...extra]=token.split('.');if(extra.length)return null;
   const expected=createHmac('sha256',key).update(payload).digest();const supplied=Buffer.from(signature,'hex');
   if(supplied.length!==expected.length||!timingSafeEqual(supplied,expected))return null;
   const value=JSON.parse(Buffer.from(payload,'base64url').toString('utf8'));
   if(value.exp<Date.now()/1000||value.exp>Date.now()/1000+65||value.method!==req.method||value.path!==req.url)return null;
   if(!/^[a-f0-9]{32}:company-[0-9]+$/.test(value.scope)||typeof value.account!=='string'||!['caja','camarero','cocina','barra','supervisor'].includes(value.role))return null;
   if(!Array.isArray(value.staff)||value.staff.length>50||value.staff.some(p=>typeof p.id!=='string'||typeof p.name!=='string'))return null;
   return value;
  }catch{return null;}
 }};
}
export function bodyMatches(connected,body){return !connected?.bodyHash||createHash('sha256').update(body).digest('hex')===connected.bodyHash;}
