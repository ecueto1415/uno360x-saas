const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
test('Tablet and phone: confirm/cancel removing tables and empty zones; restore; protect occupied tables',async()=>{
 const {makeDemoServer}=await import('./server.mjs'),browser=await chromium.launch({channel:'msedge',headless:true});
 try{for(const width of [768,390]){
  const access={close(){},authorize(){return {scope:'qa',account:'1',role:'supervisor',staff:[{id:'1',name:'Administrador'}]};}};
  const server=makeDemoServer(':memory:',access);await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port,ctx=await browser.newContext({viewport:{width,height:1024},hasTouch:true,isMobile:true});
  try{
   const p=await ctx.newPage();p.setDefaultTimeout(7000);const b=n=>p.getByRole('button',{name:n,exact:true});await p.goto(base);await b('Abrir turno').tap();await p.locator('#mobile-nav-toggle').tap();await p.locator('#nav [data-value="Mesas"]').tap();await b('Administrar mesas').tap();
   const row=name=>p.locator('#modal .item').filter({hasText:name});await row('Mesa 02').getByRole('button',{name:'Quitar mesa',exact:true}).tap();await b('Cancelar').tap();assert.equal(await p.locator('[data-action=floorSelect][data-value="2"]').count(),1);
   await b('Administrar mesas').tap();await row('Mesa 02').getByRole('button',{name:'Quitar mesa',exact:true}).tap();await b('Sí, quitar mesa').tap();await p.getByText('Mesa retirada del plano. Su historial se conserva.',{exact:true}).waitFor();assert.equal(await p.locator('[data-action=floorSelect][data-value="2"]').count(),0);
   await b('Administrar mesas').tap();await row('Mesa 02').getByRole('button',{name:'Restaurar mesa',exact:true}).tap();await b('Guardar').tap();await p.getByText('Operación registrada.',{exact:true}).waitFor();assert.equal(await p.locator('[data-action=floorSelect][data-value="2"]').count(),1);
   await b('Administrar zonas').tap();await row('Barra').getByRole('button',{name:'Quitar zona',exact:true}).tap();await b('Sí, quitar zona').tap();await p.getByText(/Zona retirada del plano/).waitFor();await b('Administrar zonas').tap();assert.equal(await p.locator('#modal').evaluate(e=>e.scrollWidth<=e.clientWidth),true);await row('Barra').getByRole('button',{name:'Restaurar zona',exact:true}).tap();await p.getByText('Zona restaurada.',{exact:true}).waitFor();
   await p.locator('[data-action=floorSelect][data-value="1"]').tap();await b('Abrir pedido').tap();await p.locator('#modal').getByRole('button',{name:'Abrir pedido',exact:true}).tap();await p.locator('#mobile-nav-toggle').tap();await p.locator('#nav [data-value="Mesas"]').tap();await b('Administrar mesas').tap();await row('Mesa 01').getByRole('button',{name:'Quitar mesa',exact:true}).tap();await b('Sí, quitar mesa').tap();await p.getByText(/La mesa tiene una cuenta abierta/).first().waitFor();
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),width);
  }finally{await ctx.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
 }}finally{await browser.close();}
});
