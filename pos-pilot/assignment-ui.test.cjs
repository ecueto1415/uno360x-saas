const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
const {mkdirSync}=require('node:fs');const path=require('node:path');
test('Assigned waiter and supervisor-only reassignment on tablet and phone',async()=>{
 const {makeDemoServer:makeServer}=await import('./server.mjs');const browser=await chromium.launch({channel:'msedge',headless:true});
 const staff=[{id:'1',name:'Responsable POS'},{id:'2',name:'Ana García'},{id:'3',name:'Carlos Pérez'}];
 try{for(const device of [{name:'phone',width:390,height:844},{name:'tablet',width:768,height:1024}]){
  const access={close(){},authorize(req){const id=req.headers['x-fixture-user'];return ['1','2','3'].includes(id)?{scope:'test',account:id,displayName:staff.find(p=>p.id===id).name,branchName:'Local piloto',staff,role:id==='1'?'supervisor':id==='2'?'camarero':'caja'}:null;}};
  const server=makeServer(':memory:',access);await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const ctx=await browser.newContext({viewport:{width:device.width,height:device.height},hasTouch:true,isMobile:true,extraHTTPHeaders:{'X-Fixture-User':'1'}});
  try{
   const p=await ctx.newPage();const url='http://127.0.0.1:'+server.address().port;
   const b=n=>p.getByRole('button',{name:n,exact:true});
   async function nav(n){const target=p.locator('#nav [data-value="'+n+'"]');if(!await target.isVisible())await p.locator('#mobile-nav-toggle').tap();await target.tap();}
   await p.goto(url);await b('Abrir turno').tap();await nav('Mesas');await p.locator('[data-action="floorSelect"][data-value="3"]').tap();await p.locator('[data-action="table"][data-value="3"]').tap();await p.getByLabel('Quién atiende').selectOption('2');await p.locator('#modal').getByRole('button',{name:'Abrir pedido',exact:true}).tap();
   await p.locator('.assignment').getByText('Ana García',{exact:true}).waitFor();assert.equal(await p.locator('.rail-foot').isVisible(),false);
   await b('Reasignar mesa').tap();await p.getByLabel('Nuevo responsable').selectOption('3');await p.getByLabel('Motivo del cambio').fill('Cambio de turno - prueba touch');
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),device.width);
   const out=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/design-review');mkdirSync(out,{recursive:true});await p.screenshot({path:path.join(out,'mesa-responsable-'+device.name+'-reasignar.png'),fullPage:true});
   await b('Guardar').tap();await p.locator('.assignment').getByText('Carlos Pérez',{exact:true}).waitFor();
   await nav('Mesas');await p.getByRole('button',{name:/Mesa 03.*Carlos Pérez/}).waitFor();
   await p.screenshot({path:path.join(out,'mesa-responsable-'+device.name+'-mesas.png'),fullPage:true});
   await nav('Reportes');await p.getByText(/Cambio de turno - prueba touch/).waitFor();assert.match(await p.locator('#view').innerText(),/Responsable POS/);assert.match(await p.locator('#view').innerText(),/Ana García/);assert.match(await p.locator('#view').innerText(),/Carlos Pérez/);
   for(const user of ['2','3']){
    await ctx.setExtraHTTPHeaders({'X-Fixture-User':user});await p.reload();await nav('Mesas');
    if(user==='3'){await p.locator('[data-action="floorSelect"][data-value="3"]').tap();await p.locator('[data-action="table"][data-value="3"]').tap();await p.locator('.assignment').getByText('Carlos Pérez',{exact:true}).waitFor();}
    else await p.getByText('Cuenta reservada al responsable y a Caja.',{exact:true}).waitFor();
    assert.equal(await b('Reasignar mesa').count(),0);
    await p.locator('#mobile-nav-toggle').tap();assert.equal(await p.locator('#role').isVisible(),false);await p.locator('#mobile-nav-toggle').tap();
   }
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),device.width);console.log(device.name+': assignment visible, reassignment audited, cashier/waiter button absent, trusted role hidden PASSED');
  }finally{await ctx.close();await new Promise(r=>server.close(r));}
 }}finally{await browser.close();}
});
