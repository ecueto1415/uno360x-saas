const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
test('Tablet and phone: floor editor, manual named guests, single/separate invoices, exact mixed payments',async()=>{
 const {makeDemoServer}=await import('./server.mjs'),browser=await chromium.launch({channel:'msedge',headless:true});
 const out=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/floor-guests');fs.mkdirSync(out,{recursive:true});
 try{for(const device of [{name:'tablet',width:768,height:1024},{name:'phone',width:390,height:844}])for(const mode of ['table','person']){
  const staff=[{id:'1',name:'Administrador'},{id:'2',name:'Ana camarera'},{id:'3',name:'Luis camarero'}];
  const server=makeDemoServer(':memory:',{close(){},authorize(req){return {scope:'touch-qa',account:req.headers['x-fixture-role']==='camarero'?'2':'1',role:req.headers['x-fixture-role']||'supervisor',staff,branchName:'Local piloto',displayName:'Administrador'};}});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
  const context=await browser.newContext({viewport:{width:device.width,height:device.height},hasTouch:true,isMobile:true});
  try{
   await context.addInitScript(()=>{window.print=()=>{window.testPrints=(window.testPrints||0)+1;};});const p=await context.newPage();p.setDefaultTimeout(8000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
   const b=n=>p.getByRole('button',{name:n,exact:true}),snap=async()=> (await(await fetch(base+'/api/state')).json()).state;
   async function nav(n){const target=p.locator('#nav [data-value="'+n+'"]');if(!await target.isVisible())await p.locator('#mobile-nav-toggle').tap();await target.tap();}
   async function shot(n){assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),device.width);await p.screenshot({path:path.join(out,device.name+'-'+mode+'-'+n+'.png'),fullPage:true});}
   await p.goto(base);await b('Abrir turno').tap();await nav('Mesas');await shot('plano');await b('Editar plano').tap();await p.locator('[data-action="floorSelect"][data-value="3"]').tap();
   await b('Derecha →').tap();assert.equal(Number(await p.getByLabel('Posición horizontal (%)').inputValue()),55);
   await p.getByLabel('Nombre de la mesa').fill('Mesa 03');await p.getByLabel('Posición horizontal (%)').fill('45');await p.getByLabel('Posición vertical (%)').fill('43');await p.getByLabel('Forma').selectOption('round');await b('Guardar plano').tap();await p.getByText('Plano guardado.',{exact:true}).waitFor();
   assert.equal((await snap()).tables.find(t=>t.number===3).x,45);assert.equal((await snap()).tables.find(t=>t.number===3).shape,'round');
   await b('Editar plano').tap();await p.getByLabel('Posición horizontal (%)').fill('99');await b('Cancelar').tap();assert.equal((await snap()).tables.find(t=>t.number===3).x,45);
   await p.locator('[data-action="floorSelect"][data-value="3"]').tap();await b('Abrir pedido').tap();await p.getByLabel('Personas',{exact:true}).fill('3');await p.getByLabel('Quién atiende').selectOption('2');await p.locator('#modal').getByRole('button',{name:'Abrir pedido',exact:true}).tap();await b('+ Crear persona').waitFor();
   assert.equal((await snap()).orders[0].guests.length,0);
   for(const name of ['Carlos','Ana']){await b('+ Crear persona').tap();await p.getByLabel('Nombre de la persona - opcional').fill(name);await b('Crear persona').tap();await p.getByText(name+' guardado en este pedido.',{exact:true}).waitFor();}
   await b('Editar Carlos').tap();await p.getByLabel('Nombre de la persona - opcional').fill('Carlos Pérez');await b('Guardar cambios').tap();await p.getByText('Carlos Pérez guardado en este pedido.',{exact:true}).waitFor();
   await b('Editar Carlos Pérez').tap();await p.getByLabel('Nombre de la persona - opcional').fill('Carlos');await b('Guardar cambios').tap();await p.getByText('Carlos guardado en este pedido.',{exact:true}).waitFor();
   const guestIds=(await snap()).orders[0].guests;
   for(const [product,name] of [['burger','Carlos'],['wings','Ana'],['mojito','Carlos']]){
    await p.getByLabel('Agregar productos a').selectOption(guestIds.find(g=>g.name===name).id);await p.locator('[data-action="product"][data-value="'+product+'"]').tap();await b('Añadir a la cuenta').tap();
   }
   await p.locator('.order-panel .total').getByText(/1,497.60/).waitFor();await b('Enviar comanda').tap();await p.getByText('Comandas nuevas · Cocina: 2 · Barra: 1').waitFor();await shot('pedido');
   for(let i=0;i<2;i++){
    await p.locator('#mobile-orderbar [data-action="pay"]').tap();await p.getByRole('button',{name:/^Por persona/}).tap();await p.getByLabel('Persona que paga').selectOption(guestIds[i].id);
    if(i===0)await p.getByLabel('¿Cómo se hará la factura?').selectOption(mode);
    else assert.equal(await p.getByLabel('¿Cómo se hará la factura?').count(),0);
    await p.getByLabel('Método de pago').selectOption(i===0?'efectivo':'tarjeta');
    if(mode==='person'&&i===0){await p.getByLabel('Comprobante de prueba').selectOption('E31');await p.getByLabel('RNC para E31').fill('101010101');await p.getByLabel('Razón social para E31').fill('Comprador de prueba');}
    await p.locator('#person-total .total').getByText(i===0?/960.00/:/537.60/).waitFor();await shot('cobro-'+i);await b('Registrar pago').tap();await p.getByText(/Pago registrado/).waitFor();
   }
   let s=await snap(),o=s.orders[0];assert.equal(o.closed,true);assert.equal(s.payments.length,2);assert.equal(s.payments.reduce((n,p)=>n+p.amount,0),149760);assert.equal(s.ingredients.ron.stock,2455);assert.equal(s.events.filter(e=>e.ingredient==='ron').length,1);
   assert.equal(mode==='person'?o.invoices.length:1,mode==='person'?2:1);await shot('comprobantes');await p.getByRole('button',{name:'Imprimir ticket',exact:true}).first().tap();const ticket=await p.locator('#printed-ticket').textContent();assert.match(ticket,mode==='person'?/Persona: Carlos/:/1,497.60/);assert.equal(await p.evaluate(()=>window.testPrints),1);if(mode==='person'){assert.match(ticket,/960.00/);assert.doesNotMatch(ticket,/Alitas/);}
   await p.getByRole('button',{name:'Ver estado fiscal',exact:true}).first().tap();await p.getByText(/Mismo comprobante/).waitFor();assert.equal((await snap()).payments.length,2);
   await nav('Reportes');await p.getByLabel('Efectivo contado').fill('2960');await b('Confirmar cierre').tap();await p.getByText('Diferencia',{exact:true}).waitFor();assert.equal((await snap()).shift.difference,0);
   await context.setExtraHTTPHeaders({'X-Fixture-Role':'camarero'});await p.reload();await nav('Mesas');assert.equal(await b('Editar plano').count(),0);assert.equal(await b('Administrar mesas').count(),0);assert.deepEqual(errors,[]);
   console.log(device.name+' '+mode+': manual guests; floor save/cancel; two payments; '+(mode==='person'?'two invoices':'one invoice')+'; stock once; zero difference; cashier permissions PASSED');
  }finally{await context.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
 }}finally{await browser.close();}
});









test('Desktop floor: drag a selected table, save and reload persistently',async()=>{
 const {makeDemoServer}=await import('./server.mjs');const server=makeDemoServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({channel:'msedge',headless:true});try{
  const p=await browser.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(7000);await p.goto('http://127.0.0.1:'+server.address().port);
  await p.locator('#role').selectOption('supervisor');await p.locator('#nav [data-value="Mesas"]').click();await p.getByRole('button',{name:'Editar plano',exact:true}).click();
  const tile=p.locator('[data-action="floorSelect"][data-value="3"]');await tile.click();await p.waitForFunction(()=>document.querySelector('[data-floor-field=x]')?.value==='50');const r=await tile.boundingBox();
  await p.mouse.move(r.x+r.width/2,r.y+r.height/2);await p.mouse.down();await p.mouse.move(r.x+r.width/2+30,r.y+r.height/2+15,{steps:5});await p.mouse.up();
  await p.waitForFunction(()=>{const f=document.querySelector('[data-floor-field=x]');return f&&Number(f.value)>50;});const x=Number(await p.getByLabel('Posición horizontal (%)').inputValue());assert.ok(x>50,'Dragged x='+x);
  await p.getByRole('button',{name:'Guardar plano',exact:true}).click();await p.getByText('Plano guardado.',{exact:true}).waitFor();
  await p.reload();await p.locator('#role').selectOption('supervisor');await p.locator('#nav [data-value="Mesas"]').click();await p.getByRole('button',{name:'Editar plano',exact:true}).click();await tile.click();await p.waitForFunction(x=>Number(document.querySelector('[data-floor-field=x]')?.value)===x,x);assert.equal(Number(await p.getByLabel('Posición horizontal (%)').inputValue()),x);
 }finally{await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
});
