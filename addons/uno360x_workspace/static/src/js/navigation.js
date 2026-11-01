"use strict";
document.querySelectorAll('.ux-primary-item').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)document.querySelectorAll('.ux-primary-item').forEach(other=>{if(other!==d)other.open=false;});}));
document.addEventListener('click',e=>document.querySelectorAll('.ux-primary-item[open]').forEach(d=>{if(!d.contains(e.target))d.open=false;}));
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.ux-primary-item').forEach(d=>d.open=false);});
const opener=document.querySelector('.ux-mobile-toggle');if(opener)opener.addEventListener('click',()=>{const side=document.getElementById('ux-sidebar');const open=side.classList.toggle('is-open');opener.setAttribute('aria-expanded',String(open));});
