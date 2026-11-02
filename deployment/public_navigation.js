"use strict";
(function(){
 if(!["https://uno360x.com","https://www.uno360x.com"].includes(location.origin))return;
 document.title=String(document.title||"UNO360X").replace(/\s*\|\s*My Website\s*$/i, "");
 if(location.pathname==='/planes-y-precios'){
  const names={'Nómina y RR. HH.':'payroll_hr','Jenifer IA':'jenifer_ai','Proyectos y Servicios':'projects_services'};
  Array.from(document.querySelectorAll('a')).filter(a=>a.href==='https://cuenta.uno360x.com/prueba/inicio').forEach(a=>a.addEventListener('click',()=>{const modules=Array.from(document.querySelectorAll('[data-module]:checked')).map(input=>names[input.dataset.module]).filter(Boolean);const target=new URL('https://cuenta.uno360x.com/prueba/inicio');if(modules.length)target.searchParams.set('modules',modules.join(','));a.href=target.href;}));
 }
 const origin="https://cuenta.uno360x.com";let state={authenticated:false},busy=false,pending=false,generation=0;
 const links=Array.from(document.querySelectorAll('a')).filter(a=>a.href===origin+"/web/login"&&a.textContent.trim()==="Iniciar sesión");
 function update(){links.forEach(a=>{a.textContent=state.authenticated?"Salir":"Iniciar sesión";a.title=state.authenticated?"Cerrar sesión de UNO360X":"Iniciar sesión";});}
 async function refresh(){if(pending||busy)return;pending=true;const revision=generation;try{const response=await fetch(origin+"/public/session-status",{credentials:"include",cache:"no-store"});if(response.ok){const result=await response.json();if(revision===generation&&!busy){state=result;update();}}}catch{}finally{pending=false;}}
 links.forEach(a=>a.addEventListener('click',async event=>{if(!state.authenticated)return;event.preventDefault();if(busy)return;busy=true;generation++;try{const response=await fetch(origin+"/public/logout",{method:"POST",credentials:"include",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:state.logout_token})});if(!response.ok)throw new Error();state={authenticated:false};update();}catch{location.href=origin+"/web/login";}finally{busy=false;}}));
 window.addEventListener('pageshow',refresh);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});refresh();
})();
