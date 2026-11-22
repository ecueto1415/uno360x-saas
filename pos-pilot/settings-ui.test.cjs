const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
test('Touch settings: direct entry, independent controls, confirmation/cancel, admin-only business change',async()=>{
 const {makeDemoServer}=await import('./server.mjs');const browser=await chromium.launch({channel:'msedge',headless:true});
 const out=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/settings-review');fs.mkdirSync(out,{recursive:true});
 try{for(const device of [{name:'tablet',width:768,height:1024},{name:'phone',width:390,height:844}]){
  const access={close(){},authorize(req){return {scope:'settings-qa',account:req.headers['x-fixture-role']==='caja'?'2':'1',role:req.headers['x-fixture-role']||'supervisor',staff:[],displayName:'Administrador',branchName:'Local piloto'};}};
  const server=makeDemoServer(':memory:',access);await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const context=await browser.newContext({viewport:{width:device.width,height:device.height},hasTouch:true,isMobile:true});
  try{
   const p=await context.newPage();p.setDefaultTimeout(7000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
   const b=n=>p.getByRole('button',{name:n,exact:true}),base='http://127.0.0.1:'+server.address().port;
   const snap=async()=> (await(await fetch(base+'/api/state')).json()).state;
   async function nav(n){const target=p.locator('#nav [data-value="'+n+'"]');if(!await target.isVisible())await p.locator('#mobile-nav-toggle').tap();await target.tap();}
   const shot=async n=>{assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),device.width);await p.screenshot({path:path.join(out,device.name+'-'+n+'.png'),fullPage:true});};
   await p.goto(base);await b('Abrir turno').waitFor();assert.equal(await p.getByRole('heading',{name:/Paso 1/}).count(),0);
   await nav('Menú');assert.equal(await b('Configurar mi POS').count(),0);await b('Ajustes del POS').tap();
   await p.getByRole('heading',{name:'Ajustes del POS',exact:true}).waitFor();for(const n of ['Configurar mesas','Administrar productos','Configurar estaciones','Cambiar tipo de negocio'])assert.ok(await b(n).isVisible());await shot('ajustes');
   await b('Configurar estaciones').tap();await p.locator('#modal').getByLabel('Cocina',{exact:false}).selectOption('yes');await p.locator('#modal').getByLabel('Barra',{exact:false}).selectOption('yes');await b('Guardar').tap();await p.getByText('Ajustes del POS guardados.',{exact:true}).waitFor();
   const original=await snap();assert.equal(original.setup.business,'restaurant');
   await b('Cambiar tipo de negocio').tap();await p.getByLabel('Nuevo tipo de negocio').selectOption('retail');await b('Revisar cambio').tap();await p.getByRole('heading',{name:'Confirmar cambio de negocio',exact:true}).waitFor();assert.equal((await snap()).setup.business,'restaurant');await shot('confirmacion');await b('Cancelar').tap();assert.equal((await snap()).setup.business,'restaurant');
   await b('Cambiar tipo de negocio').tap();await p.getByLabel('Nuevo tipo de negocio').selectOption('retail');await b('Revisar cambio').tap();await b('Confirmar cambio').tap();await p.getByText(/Tipo de negocio actualizado/).waitFor();
   const after=await snap();assert.equal(after.setup.business,'retail');assert.deepEqual(after.products,original.products);assert.deepEqual(after.tables,original.tables);assert.deepEqual(after.setup.stations,original.setup.stations);assert.deepEqual(after.orders,original.orders);assert.equal(after.setup.completed,true);
   await p.reload();await b('Abrir turno').waitFor();assert.equal(await b('Elegir').count(),0);
   await context.setExtraHTTPHeaders({'X-Fixture-Role':'caja'});await p.reload();await b('Abrir turno').waitFor();await nav('Menú');assert.equal(await b('Ajustes del POS').count(),0);assert.equal(await b('Cambiar tipo de negocio').count(),0);assert.deepEqual(errors,[]);
   console.log(device.name+': direct POS; separate settings; cancel unchanged; confirmed change preserves data; cashier controls absent PASSED');
  }finally{await context.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
 }}finally{await browser.close();}
});
