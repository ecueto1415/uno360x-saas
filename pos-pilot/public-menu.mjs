import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),qrcode=require('./vendor/qrcode.cjs');
export const PUBLIC_PREFIX='/menu-pos';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function qrSvg(url){
 const qr=qrcode(0,'M');qr.addData(url);qr.make();const n=qr.getModuleCount(),quiet=4;
 const path=[];for(let y=0;y<n;y++)for(let x=0;x<n;x++)if(qr.isDark(y,x))path.push(`M${x+quiet} ${y+quiet}h1v1h-1z`);
 return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${n+quiet*2} ${n+quiet*2}" width="512" height="512" role="img" aria-label="QR del menú" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="white"/><path d="${path.join('')}" fill="#11243e"/></svg>`;
}
export function menuData(s,token){
 const live=s.publicMenu?.live;if(!live?.enabled||s.publicMenu.token!==token)return null;
 const base=PUBLIC_PREFIX+'/'+token;
 const items=live.items.filter(i=>i.published).flatMap(i=>{
  const p=s.products.find(p=>p.id===i.id);if(!p)return [];
  return [{id:p.id,name:p.name,description:p.description||'',category:p.category,cents:p.cents,tax:p.tax,available:p.available!==false,
   photo:p.photo?base+'/photo/'+encodeURIComponent(p.id)+'?v='+createHash('sha256').update(p.photo).digest('hex').slice(0,12):''}];
 });
 return {name:live.name,logo:live.logo?base+'/logo?v='+createHash('sha256').update(live.logo).digest('hex').slice(0,12):'',interval:live.interval,items,publishedAt:live.publishedAt,consultationOnly:true};
}
export function publicPage(){return `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer"><title>Menú | UNO360X</title><link rel="stylesheet" href="/menu-pos/assets/menu.css"><script type="module" src="/menu-pos/assets/menu.mjs"></script></head><body><header class="public-header"><div class="identity"><span class="brand">UNO360<span>X</span></span><span class="menu-label">MENÚ DIGITAL</span></div><strong id="business">Nuestro menú</strong></header><main id="menu"><p role="status">Cargando menú…</p></main><dialog id="detail"><div id="detail-content"></div></dialog></body></html>`;}
export function imageBytes(photo){
 const data=/^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$/.exec(photo||'');
 if(data)return {mime:'image/'+data[1],body:Buffer.from(data[2],'base64')};
 if(['burger.jpg','wings.jpg','mojito.jpg'].includes(photo))return {mime:'image/jpeg',body:readFileSync(new URL('./images/'+photo.replace('.jpg','-hq.jpg'),import.meta.url))};
 return null;
}
export {esc};
