const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
const path=require('node:path');
const {mkdirSync}=require('node:fs');
test('Approved POS design keeps restaurant workflow on desktop and mobile',async()=>{
 const {makeDemoServer:makeServer}=await import('./server.mjs');
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
  await nav('Mesas').click();await page.locator('[data-action="floorSelect"][data-value="3"]').click();await page.locator('[data-action="table"][data-value="3"]').click();await page.getByLabel('Personas').fill('4');await page.locator('#modal').getByRole('button',{name:'Abrir pedido',exact:true}).click();
  for(const product of ['burger','wings','mojito']){await page.locator('[data-action="product"][data-value="'+product+'"]').click();await button('Añadir a la cuenta').click();}
  await page.locator('.order-panel .total').getByText(/1,497.60/).waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('.tile img')].every(img=>img.complete&&img.naturalWidth>=1000));
  assert.equal(await page.locator('.tile img').evaluateAll(images=>images.filter(img=>img.naturalWidth>=1000).length),3);
  assert.equal(await page.locator('h1').textContent(),'Mesa 03');
  await page.getByRole('searchbox').fill('moj');assert.equal(await page.locator('.tile').count(),1);await page.getByRole('searchbox').fill('');
  await button('Bebidas').click();assert.equal(await page.locator('.tile').count(),1);await page.locator('[data-action=category]').filter({hasText:/^Todos$/}).click();
  await page.screenshot({path:path.join(output,'pos-primer-diseno-desktop.png'),fullPage:true});
  for(const width of [1024,768,390,320]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width,'overflow at '+width);assert.ok(await button('Cobrar').isVisible());}
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'pos-primer-diseno-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await button('Enviar comanda').click();await page.getByText('Comandas nuevas · Cocina: 2 · Barra: 1').waitFor();
  await page.locator('[data-action="product"][data-value="mojito"]').click();await button('Añadir a la cuenta').click();await button('Enviar comanda').click();await page.getByText('Comandas nuevas · Cocina: 0 · Barra: 1').waitFor();
  await nav('Pedidos').click();await page.locator('[data-action="pick"]').first().click();
  await button('Dividir y cobrar').click();await page.getByRole('button',{name:/^Por productos/}).click();await page.getByLabel(/Hamburguesa/).check();await page.getByLabel(/Alitas/).check();await button('Registrar pago').click();
  await button('Cobrar').click();await page.getByLabel('Método de pago').selectOption('tarjeta');await button('Registrar pago').click();
  await page.getByText('Simulado · sin envío a DGII',{exact:true}).waitFor();
  await button('Ver estado fiscal').click();await page.getByText(/Mismo comprobante/).waitFor();
  const state=(await (await fetch(base+'/api/state')).json()).state;
  assert.equal(state.payments.length,2);assert.equal(state.ingredients.ron.stock,2410);
  for(const mode of ['Cocina','Barra','Inventario','Reportes','Menú','Mesas','Pedidos','Caja']){await nav(mode).click();await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390,'overflow in '+mode);await page.setViewportSize({width:1440,height:1000});}
  await nav('Reportes').click();await page.getByLabel('Efectivo contado').fill('3113.60');await button('Confirmar cierre').click();
  await nav('Caja').click();await button('Abrir turno').click();await button('Para llevar').click();await page.locator('#modal').getByRole('button',{name:'Abrir pedido',exact:true}).click();
  for(const product of ['burger','wings','mojito']){await page.locator('[data-action="product"][data-value="'+product+'"]').click();await button('Añadir a la cuenta').click();}
  await page.locator('.order-panel .total').getByText(/1,380.60/).waitFor();
  assert.equal(await page.locator('.catalog-panel .tabs').first().locator('.active').textContent(),'Para llevar');
  assert.deepEqual(errors,[]);
  console.log('Photos, responsive 320/390/768/1024/1440, stations, second round, split payment, inventory, close and takeaway passed.');
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});

test('Touch phone and tablet: product modifiers, keyboard forms and reachable order',async()=>{
 const {makeDemoServer:makeServer}=await import('./server.mjs');
 const server=makeServer(':memory:');await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  for(const device of [{name:'phone',width:390,height:844,mobile:true},{name:'tablet-portrait',width:768,height:1024,mobile:true},{name:'tablet-landscape',width:1024,height:768,mobile:true}]){
   const context=await browser.newContext({viewport:{width:device.width,height:device.height},hasTouch:true,isMobile:device.mobile});
   const page=await context.newPage();const base='http://127.0.0.1:'+server.address().port;
   const b=name=>page.getByRole('button',{name,exact:true});
   await page.goto(base);
   if(device.name==='phone')await b('Abrir turno').tap();
   await page.locator('#mobile-nav-toggle').isVisible().then(async visible=>{if(visible)await page.locator('#mobile-nav-toggle').tap()});await page.locator('#nav [data-value="Mesas"]').tap();await page.locator('[data-action="floorSelect"][data-value="'+({phone:1,'tablet-portrait':2,'tablet-landscape':3}[device.name])+'"]').tap();await page.locator('[data-action="table"][data-value="'+({phone:1,'tablet-portrait':2,'tablet-landscape':3}[device.name])+'"]').tap();await page.locator('#modal').getByRole('button',{name:'Abrir pedido',exact:true}).tap();
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

test('Mesa 03 complete touch journey: kitchen, bar, second round and split cash/card',async()=>{
 const {makeDemoServer:makeServer}=await import('./server.mjs');const browser=await chromium.launch({channel:'msedge',headless:true});
 try{for(const device of [{name:'phone',width:390,height:844},{name:'tablet',width:768,height:1024}]){
 const server=makeServer(':memory:');await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const context=await browser.newContext({viewport:{width:device.width,height:device.height},hasTouch:true,isMobile:true});
 try{
  const origin='http://127.0.0.1:'+server.address().port;const errors=[];
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const b=name=>page.getByRole('button',{name,exact:true});
  async function navigate(target,name){const item=target.locator('#nav [data-value="'+name+'"]');if(!await item.isVisible())await target.locator('#mobile-nav-toggle').tap();await item.tap();}
  async function setRole(target,role){if(!await target.locator('#role').isVisible())await target.locator('#mobile-nav-toggle').tap();await target.locator('#role').selectOption(role);}
  const snapshot=async()=> (await (await fetch(origin+'/api/state')).json()).state;
  await page.goto(origin);await b('Abrir turno').tap();await navigate(page,'Mesas');await page.locator('[data-action="floorSelect"][data-value="3"]').tap();await page.locator('[data-action="table"][data-value="3"]').tap();await page.getByLabel('Personas').fill('4');await page.locator('#modal').getByRole('button',{name:'Abrir pedido',exact:true}).tap();
  for(const id of ['burger','wings','mojito']){await page.locator('[data-action="product"][data-value="'+id+'"]').tap();await b('Añadir a la cuenta').tap();}
  await page.locator('.order-panel .total').getByText(/1,497.60/).waitFor();await b('Enviar comanda').tap();await page.getByText('Comandas nuevas · Cocina: 2 · Barra: 1').waitFor();
  const kitchen=await context.newPage();await kitchen.goto(origin);await setRole(kitchen,'cocina');await navigate(kitchen,'Cocina');
  assert.equal(await kitchen.locator('#view .item').count(),2);assert.ok((await kitchen.locator('#view').textContent()).includes('Hamburguesa'));assert.ok((await kitchen.locator('#view').textContent()).includes('Alitas'));assert.ok(!(await kitchen.locator('#view').textContent()).includes('Mojito'));
  for(const remaining of [1,0]){await kitchen.locator('[data-action="ready"]').first().tap();await kitchen.waitForFunction(n=>document.querySelectorAll('[data-action="ready"]').length===n,remaining);}
  const bar=await context.newPage();await bar.goto(origin);await setRole(bar,'barra');await navigate(bar,'Barra');assert.equal(await bar.locator('#view .item').count(),1);assert.ok((await bar.locator('#view').textContent()).includes('Mojito'));assert.ok(!(await bar.locator('#view').textContent()).includes('Hamburguesa'));await bar.locator('[data-action="ready"]').tap();await bar.waitForFunction(()=>document.querySelectorAll('[data-action="ready"]').length===0);
  await page.locator('[data-action="product"][data-value="mojito"]').tap();await page.getByLabel('Nota para barra').fill('Segunda ronda');await b('Añadir a la cuenta').tap();await b('Enviar comanda').tap();await page.getByText('Comandas nuevas · Cocina: 0 · Barra: 1').waitFor();
  await bar.locator('[data-action="ready"]').waitFor();assert.equal(await bar.locator('[data-action="ready"]').count(),1);await bar.locator('[data-action="ready"]').tap();await bar.waitForFunction(()=>document.querySelectorAll('[data-action="ready"]').length===0);
  let s=await snapshot();assert.equal(s.orders[0].lines.filter(line=>line.station==='cocina').length,2);assert.equal(s.orders[0].lines.filter(line=>line.station==='barra').length,2);assert.equal(new Set(s.orders[0].lines.map(line=>line.batch)).size,2);assert.ok(s.orders[0].lines.every(line=>line.status==='lista'));
  await b('Dividir y cobrar').tap();await page.getByRole('button',{name:/^Por productos/}).tap();await page.getByLabel(/Hamburguesa/).check();await page.getByLabel(/Alitas/).check();await page.getByLabel('Método de pago').selectOption('efectivo');await b('Registrar pago').tap();await page.getByText(/Pago registrado/).waitFor();
  await b('Cobrar').tap();await page.getByLabel('Método de pago').selectOption('tarjeta');await b('Registrar pago').tap();await page.getByText('Simulado · sin envío a DGII',{exact:true}).waitFor();
  s=await snapshot();assert.equal(s.payments.length,2);assert.equal(s.payments[0].amount,111360);assert.equal(s.payments[1].amount,76800);assert.equal(s.orders[0].fiscal.amount,188160);assert.equal(s.ingredients.ron.stock,2410);assert.ok(s.orders[0].closed);
  await b('Ver estado fiscal').tap();s=await snapshot();assert.equal(s.payments.length,2);assert.equal(s.ingredients.ron.stock,2410);
  await navigate(page,'Reportes');assert.ok((await page.locator('#view').textContent()).includes('3,113.60'));await page.getByLabel('Efectivo contado').fill('3113.60');await b('Confirmar cierre').tap();
  assert.ok((await snapshot()).shift.closed);assert.equal((await snapshot()).shift.difference,0);
  for(const target of [page,kitchen,bar])assert.equal(await target.evaluate(()=>document.documentElement.scrollWidth),device.width);
  const output=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/design-review');mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,'mesa08-'+device.name+'-cierre.png'),fullPage:true});await kitchen.screenshot({path:path.join(output,'mesa08-'+device.name+'-cocina.png'),fullPage:true});await bar.screenshot({path:path.join(output,'mesa08-'+device.name+'-barra.png'),fullPage:true});
  assert.deepEqual(errors,[]);console.log(device.name+': Mesa03 food=2 kitchen, mojitos=2 bar, incremental rounds, cash 1113.60 + card 768.00, stock once, closure zero difference PASSED');
 }finally{await context.close();await new Promise(resolve=>server.close(resolve));}
 }}finally{await browser.close();}
});
