"use strict";
document.querySelectorAll('.ux-primary-item').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)document.querySelectorAll('.ux-primary-item').forEach(other=>{if(other!==d)other.open=false;});}));
document.addEventListener('click',e=>document.querySelectorAll('.ux-primary-item[open]').forEach(d=>{if(!d.contains(e.target))d.open=false;}));
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.ux-primary-item').forEach(d=>d.open=false);});
const opener=document.querySelector('.ux-mobile-toggle');if(opener)opener.addEventListener('click',()=>{const side=document.getElementById('ux-sidebar');const open=side.classList.toggle('is-open');opener.setAttribute('aria-expanded',String(open));});

// Revalidate an authenticated page restored from browser history.
window.addEventListener('pageshow',function(event){if(event.persisted)window.location.reload();});


(() => {
    const desktop = window.matchMedia('(min-width: 701px)');
    const flyouts = document.querySelectorAll('.ux-primary-item > .ux-flyout');
    if (!flyouts.length) return;

    function fitFlyouts() {
        for (const flyout of flyouts) {
            if (!desktop.matches || !flyout.parentElement.open) {
                flyout.style.removeProperty('top');
                continue;
            }
            const anchor = flyout.parentElement.getBoundingClientRect();
            const availableTop = window.innerHeight - flyout.offsetHeight - 12;
            const top = Math.max(12, Math.min(anchor.top, availableTop));
            flyout.style.top = `${top - anchor.top}px`;
        }
    }

    const observer = new ResizeObserver(fitFlyouts);
    flyouts.forEach(flyout => observer.observe(flyout));
    document.addEventListener('toggle', fitFlyouts, true);
    window.addEventListener('resize', fitFlyouts);
    fitFlyouts();
})();

