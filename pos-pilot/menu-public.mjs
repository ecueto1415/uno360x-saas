const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>new Intl.NumberFormat('es-DO',{style:'currency',currency:'DOP'}).format(n/100);
const base=location.pathname.replace(/\/$/,''),tv=new URL(location.href).searchParams.get('view')==='tv';
document.body.classList.toggle('tv',tv);
let data,category='',query='',page=0,lastRotation=Date.now(),lastResponse='',detailId;
const categoryIcon=p=>p.category.toLocaleLowerCase().match(/bebida|bar|jugo|café/)?'🍹':'🍽';
const filtered=()=>data.items.filter(p=>(!category||p.category===category)&&(!query||(p.name+' '+p.description).toLocaleLowerCase().includes(query.toLocaleLowerCase())));
const priceNote='Precios sin ITBIS. El impuesto aplicable se indica en cada producto. Consumo en el local: 10% de propina legal adicional. Para llevar: sin propina legal.';
function card(p){const tag=tv?'article':'button',attrs=tv?'':`type="button" data-product="${esc(p.id)}"`;return `<${tag} ${attrs} class="product ${p.available?'':'unavailable'}" aria-label="${esc(p.name+' · '+money(p.cents)+(p.available?'':' · No disponible'))}">${p.photo?`<img src="${esc(p.photo)}" alt="" loading="lazy" decoding="async">`:`<span class="category-icon" aria-hidden="true">${categoryIcon(p)}</span>`}<span class="product-copy"><strong>${esc(p.name)}</strong><span class="description">${esc(p.description||p.category)}</span><span class="price">${money(p.cents)}</span><small class="tax-caption">${p.tax?'ITBIS '+p.tax+'% adicional':'Exento de ITBIS'}</small><span class="availability-space">${p.available?'':'<span class="unavailable-label">No disponible</span>'}</span></span></${tag}>`;}
function render(){
 const categories=[...new Set(data.items.map(p=>p.category))];if(tv&&!categories.includes(category)){category=categories[0]||'';page=0;}const list=filtered(),pages=Math.max(1,Math.ceil(list.length/3));page=Math.min(page,pages-1);
 $('#business').innerHTML=(data.logo?`<img src="${esc(data.logo)}" alt="Logo del negocio">`:'')+esc(data.name);document.title=data.name+' | Menú UNO360X';
 $('#menu').innerHTML=`<section class="menu-heading"><div><h1>${tv?esc(category==='Comida'?'Comidas':category||'Nuestro menú'):'Nuestro menú'}</h1><p>Elige tu favorito y pídelo a nuestro equipo.</p></div></section>${tv?'':`<label class="search-label">Buscar producto<input type="search" id="search" placeholder="Buscar comida o bebida" value="${esc(query)}"></label>`}<div class="menu-layout"><section class="products-area">${tv?'':`<nav class="categories" aria-label="Categorías"><button type="button" data-category="" class="${category?'':'active'}">Todos</button>${categories.map(c=>`<button type="button" data-category="${esc(c)}" class="${c===category?'active':''}">${esc(c)}</button>`).join('')}</nav>`}<div class="products${tv?' tv-count-'+Math.min(3,list.length-page*3):''}">${(tv?list.slice(page*3,page*3+3):list).map(card).join('')||'<p class="empty">No hay productos para esta búsqueda.</p>'}</div>${tv?`<div class="pagination" aria-label="Página de productos">${page+1} / ${pages} · ${category||'Todos'}</div>`:''}</section></div><footer><p>${priceNote}</p><small>Para pedir, habla con nuestro equipo. Menú de consulta · UNO360X.</small><p id="connection" role="status"></p></footer>`;
 if(detailId){const p=data.items.find(p=>p.id===detailId);if(p)detail(p);else{$('#detail').close();detailId=undefined;}}
}
function detail(p){
 detailId=p.id;const tax=Math.round(p.cents*p.tax/100),tip=Math.round(p.cents/10);
 $('#detail-content').innerHTML=`<button class="back" data-action="close">‹ Volver al menú</button>${p.photo?`<img class="detail-photo" src="${esc(p.photo)}" alt="${esc(p.name)}">`:`<div class="category-icon">${categoryIcon(p)}</div>`}<div class="detail-name"><h2>${esc(p.name)}</h2><span class="availability">${p.available?'Disponible':'No disponible'}</span></div><p>${esc(p.description||p.category)}</p><strong class="detail-price">${money(p.cents)}</strong><div class="tax-details"><p>${p.tax?'ITBIS ('+p.tax+'%) adicional: '+money(tax):'Producto exento de ITBIS'}</p><p>En el local: propina legal ${money(tip)}</p><p><strong>Total en el local: ${money(p.cents+tax+tip)}</strong></p><p>Para llevar: ${money(p.cents+tax)}</p></div><div class="consultation">${p.available?'Para pedir, habla con tu camarero.':'Consulta con nuestro equipo por otras opciones.'}<small>Esta versión es de consulta.</small></div>`;
 if(!$('#detail').open)$('#detail').showModal();
}
async function load(){
 try{
  const r=await fetch(base+'/data',{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(10000)});
  if(r.status===404){data=undefined;lastResponse='';detailId=undefined;$('#detail').close();$('#business').textContent='Menú digital';$('#menu').innerHTML='<section class="unavailable-menu"><h1>Menú no disponible</h1><p>Consulta al equipo del local. Volveremos a comprobar automáticamente.</p></section>';return;}
  if(!r.ok)throw Error('Sin conexión');
  const next=await r.json(),signature=JSON.stringify(next);
  data=next;if(signature!==lastResponse){lastResponse=signature;render();}
  else if($('#connection'))$('#connection').textContent='';
 }catch(e){if(data){$('#connection').textContent='Sin conexión. Estos datos pueden no estar actualizados; confirma precios y disponibilidad con el local.';}else $('#menu').innerHTML='<section class="unavailable-menu"><h1>No pudimos cargar el menú</h1><p>Revisa la conexión. Volveremos a intentar automáticamente.</p></section>';}
}
function rotate(){
 if(!tv||!data||document.hidden||$('#detail').open||Date.now()-lastRotation<data.interval*1000)return;
 const list=filtered();if(page+1<Math.ceil(list.length/3))page++;else{page=0;const cats=[...new Set(data.items.map(p=>p.category))];category=cats.length?cats[(cats.indexOf(category)+1)%cats.length]:'';}
 lastRotation=Date.now();render();
}
document.addEventListener('click',e=>{
 if(tv)return;
 const cat=e.target.closest('[data-category]');if(cat){category=cat.dataset.category;page=0;lastRotation=Date.now();render();}
 const product=e.target.closest('[data-product]');if(product){const p=data?.items.find(p=>p.id===product.dataset.product);if(p)detail(p);}
 const a=e.target.closest('[data-action]')?.dataset.action;if(a==='close'){$('#detail').close();detailId=undefined;}
});
document.addEventListener('input',e=>{if(e.target.id==='search'){query=e.target.value;const at=e.target.selectionStart;render();$('#search').focus();$('#search').setSelectionRange(at,at);}});
$('#detail').addEventListener('close',()=>{detailId=undefined;});
await load();setInterval(load,30000);setInterval(rotate,1000);
