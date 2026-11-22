const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
const path=require('node:path');
const {mkdirSync}=require('node:fs');
test('Approved POS design keeps restaurant workflow on desktop and mobile',async()=>{
 const {makeServer}=await import('./server.mjs');
 const server=makeServer(':memory:');await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const base='http://127.0.0.1:'+server.address().port;
  const button=name=>page.getByRole('button',{name,exact:true});
  const nav=name=>page.locator('#nav [data-value="'+name+'"]');
  const output=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/design-review');mkdirSync(output,{recursive:true});
  await page.goto(base);
  await button('Abrir turno').click();
  await nav('Mesas').click();await page.locator('[data-action="table"][data-value="8"]').click();await page.getByLabel('Personas').fill('4');await button('Abrir pedido').click();
  for(const product of ['burger','wings','mojito']){await page.locator('[data-action="product"][data-value="'+product+'"]').click();await button('Añadir a la cuenta').click();}
  await page.locator('.order-panel .total').getByText(/1,497.60/).waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('.tile img')].every(img=>img.complete&&img.naturalWidth>=1000));
  assert.equal(await page.locator('.tile img').evaluateAll(images=>images.filter(img=>img.naturalWidth>=1000).length),3);
  assert.equal(await page.locator('h1').textContent(),'Mesa 08');
  await page.getByRole('searchbox').fill('moj');assert.equal(await page.locator('.tile').count(),1);await page.getByRole('searchbox').fill('');
  await button('Bebidas').click();assert.equal(await page.locator('.tile').count(),1);await button('Todos').click();
  await page.screenshot({path:path.join(output,'pos-primer-diseno-desktop.png'),fullPage:true});
  for(const width of [1024,768,390,320]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width,'overflow at '+width);assert.ok(await button('Cobrar').isVisible());}
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'pos-primer-diseno-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await button('Enviar comanda').click();await page.getByText('Comandas nuevas · Cocina: 2 · Barra: 1').waitFor();
  await page.locator('[data-action="product"][data-value="mojito"]').click();await button('Añadir a la cuenta').click();await button('Enviar comanda').click();await page.getByText('Comandas nuevas · Cocina: 0 · Barra: 1').waitFor();
  await nav('Pedidos').click();await page.locator('[data-action="pick"]').first().click();
  await button('Dividir y cobrar').click();await page.getByLabel(/Hamburguesa/).check();await page.getByLabel(/Alitas/).check();await button('Registrar pago').click();
  await button('Cobrar').click();await page.getByLabel('Método de pago').selectOption('tarjeta');await button('Registrar pago').click();
  await page.getByText('Simulado · sin envío a DGII',{exact:true}).waitFor();
  await button('Ver estado fiscal').click();await page.getByText(/Mismo comprobante/).waitFor();
  const state=(await (await fetch(base+'/api/state')).json()).state;
  assert.equal(state.payments.length,2);assert.equal(state.ingredients.ron.stock,2410);
  for(const mode of ['Cocina','Barra','Inventario','Reportes','Menú','Mesas','Pedidos','Caja']){await nav(mode).click();await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390,'overflow in '+mode);await page.setViewportSize({width:1440,height:1000});}
  await nav('Reportes').click();await page.getByLabel('Efectivo contado').fill('3113.60');await button('Confirmar cierre').click();
  await nav('Caja').click();await button('Abrir turno').click();await button('Para llevar').click();await button('Abrir pedido').click();
  for(const product of ['burger','wings','mojito']){await page.locator('[data-action="product"][data-value="'+product+'"]').click();await button('Añadir a la cuenta').click();}
  await page.locator('.order-panel .total').getByText(/1,380.60/).waitFor();
  assert.equal(await page.locator('.catalog-panel .tabs').first().locator('.active').textContent(),'Para llevar');
  assert.deepEqual(errors,[]);
  console.log('Photos, responsive 320/390/768/1024/1440, stations, second round, split payment, inventory, close and takeaway passed.');
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});

test('Touch phone and tablet: product modifiers, keyboard forms and reachable order',async()=>{
 const {makeServer}=await import('./server.mjs');
 const server=makeServer(':memory:');await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  for(const device of [{name:'phone',width:390,height:844,mobile:true},{name:'tablet-portrait',width:768,height:1024,mobile:true},{name:'tablet-landscape',width:1024,height:768,mobile:true}]){
   const context=await browser.newContext({viewport:{width:device.width,height:device.height},hasTouch:true,isMobile:device.mobile});
   const page=await context.newPage();const base='http://127.0.0.1:'+server.address().port;
   const b=name=>page.getByRole('button',{name,exact:true});
   await page.goto(base);
   if(device.name==='phone')await b('Abrir turno').tap();
   await page.locator('#mobile-nav-toggle').isVisible().then(async visible=>{if(visible)await page.locator('#mobile-nav-toggle').tap()});await page.locator('#nav [data-value="Mesas"]').tap();await page.locator('[data-action="table"][data-value="'+({phone:8,'tablet-portrait':7,'tablet-landscape':6}[device.name])+'"]').tap();await b('Abrir pedido').tap();
   await page.locator('[data-action="product"][data-value="mojito"]').tap();await page.getByLabel('Poco dulce').check();await page.getByLabel('Nota para barra').fill('Prueba touch');await b('Añadir a la cuenta').tap();
   await page.locator('.order-panel .line-description').filter({hasText:'Mojito'}).waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),device.width);
   assert.ok(await page.locator('.order-panel').getByText(/Prueba touch/).isVisible());
   if(device.width<=850){assert.ok(await page.locator('#mobile-orderbar').isVisible());await b('Ver pedido').tap();await b('Cobrar').tap();await page.locator('#modal[open]').waitFor();await b('Cancelar').tap();}
   const tooSmall=await page.locator('button').evaluateAll(buttons=>buttons.filter(button=>{const r=button.getBoundingClientRect();return r.width>0&&r.height>0&&(r.width<43||r.height<43)}).map(button=>button.textContent));
   assert.deepEqual(tooSmall,[],device.name+' has undersized buttons');
   const output=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/design-review');mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,'pos-touch-'+device.name+'.png'),fullPage:true});
   await b('Enviar comanda').tap();await b('Cobrar').tap();await page.getByLabel('Método de pago').selectOption(device.name==='phone'?'efectivo':device.name==='tablet-portrait'?'tarjeta':'transferencia');await b('Registrar pago').tap();await page.getByText('Simulado · sin envío a DGII',{exact:true}).waitFor();
   const paid=(await (await fetch(base+'/api/state')).json()).state;assert.equal(paid.payments.length,({phone:1,'tablet-portrait':2,'tablet-landscape':3}[device.name]));assert.equal(paid.ingredients.ron.stock,2500-45*paid.payments.length);
   await context.close();
  }
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});
