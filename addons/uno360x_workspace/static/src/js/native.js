(function(){
if(!document.body.classList.contains('o_web_client')){return;}
var header=document.getElementById('ux-native-header');
var sidebar=document.getElementById('ux-sidebar');
var opener=document.getElementById('ux-native-open');
var backdrop=document.getElementById('ux-native-backdrop');
var pending=false;
function closeMenu(){document.body.classList.remove('ux-native-menu-open');if(opener){opener.setAttribute('aria-expanded','false');}}
function updateNavigation(){pending=false;var bar=document.querySelector('.o_main_navbar');if(bar){if(header){if(header.parentElement!==bar){bar.prepend(header);}}var brand=bar.querySelector('.o_menu_brand');var label=brand?brand.textContent.trim():'';var output=document.getElementById('ux-native-title');if(output){if(output.textContent!==label){output.textContent=label;}}document.querySelectorAll('.ux-native-shell .ux-primary-item').forEach(function(item){var summary=item.querySelector('summary');var title=summary?summary.textContent.replace('›','').trim():'';item.classList.toggle('ux-current',title===label);});document.querySelectorAll('.ux-native-shell .ux-side-bottom a').forEach(function(a){a.classList.toggle('ux-current',a.textContent.trim()===label);});}}
function schedule(){if(!pending){pending=true;requestAnimationFrame(updateNavigation);}}
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});schedule();
document.querySelectorAll('.ux-native-shell .ux-primary-item').forEach(function(d){d.addEventListener('toggle',function(){if(d.open){document.querySelectorAll('.ux-native-shell .ux-primary-item').forEach(function(other){if(other!==d){other.open=false;}});}});});
document.addEventListener('click',function(e){document.querySelectorAll('.ux-native-shell .ux-primary-item[open]').forEach(function(d){if(!d.contains(e.target)){d.open=false;}});});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){closeMenu();document.querySelectorAll('.ux-native-shell .ux-primary-item[open]').forEach(function(d){d.open=false;});}});
if(opener){opener.addEventListener('click',function(){var isOpen=document.body.classList.toggle('ux-native-menu-open');opener.setAttribute('aria-expanded',isOpen?'true':'false');});}
if(backdrop){backdrop.addEventListener('click',closeMenu);}
if(sidebar){var closer=sidebar.querySelector('.ux-mobile-toggle');if(closer){closer.addEventListener('click',closeMenu);}sidebar.addEventListener('click',function(e){if(e.target.closest('a')){closeMenu();document.querySelectorAll('.ux-native-shell .ux-primary-item[open]').forEach(function(d){d.open=false;});}});}
})();