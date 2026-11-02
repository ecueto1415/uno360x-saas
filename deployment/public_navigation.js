"use strict";
(function(){
 if(!["https://uno360x.com","https://www.uno360x.com"].includes(location.origin))return;
 document.title=String(document.title||"UNO360X").replace(/\s*\|\s*My Website\s*$/i, "");
 if(location.pathname==='/planes-y-precios'){
  const names={'Nómina y RR. HH.':'payroll_hr','Jenifer IA':'jenifer_ai','Proyectos y Servicios':'projects_services'};
  Array.from(document.querySelectorAll('a')).filter(a=>a.href==='https://cuenta.uno360x.com/prueba/inicio').forEach(a=>a.addEventListener('click',()=>{const modules=Array.from(document.querySelectorAll('[data-module]:checked')).map(input=>names[input.dataset.module]).filter(Boolean);const target=new URL('https://cuenta.uno360x.com/prueba/inicio');if(modules.length)target.searchParams.set('modules',modules.join(','));a.href=target.href;}));
 }
 // Account entry always remains a normal link. The account portal recognizes
 // an existing session and opens its workspace without logging the user out.
 Array.from(document.querySelectorAll('a')).filter(a=>a.href==="https://cuenta.uno360x.com/web/login"&&/^(Iniciar sesión|Salir)$/.test(a.textContent.trim())).forEach(a=>{a.textContent="Iniciar sesión";a.title="Iniciar sesión";});
})();
