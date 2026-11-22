const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
test('Touch: five tables, manage tables, add products and equal split with mixed payments',async()=>{
 const {makeDemoServer:makeServer}=await import('./server.mjs');const browser=await chromium.launch({channel:'msedge',headless:true});
 const output=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/split-review');fs.mkdirSync(output,{recursive:true});
 try{for(const device of [{name:'tablet',width:768,height:1024},{name:'phone',width:390,height:844}]){
  const server=makeServer(':memory:');await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const context=await browser.newContext({viewport:device,hasTouch:true,isMobile:true});
  try{
   const p=await context.newPage(),base='http://127.0.0.1:'+server.address().port;p.setDefaultTimeout(6000);const errors=[];p.on('pageerror',e=>{errors.push(e.message);console.log('PAGE ERROR',e.message);});
   const b=n=>p.getByRole('button',{name:n,exact:true});
   async function nav(n){const link=p.locator('#nav [data-value="'+n+'"]');if(!await link.isVisible())await p.locator('#mobile-nav-toggle').tap();await link.tap();}
   async function role(n){if(!await p.locator('#role').isVisible())await p.locator('#mobile-nav-toggle').tap();await p.locator('#role').selectOption(n);await p.locator('#mobile-nav-toggle').tap();}
   const shot=async name=>{assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),device.width);await p.screenshot({path:path.join(output,device.name+'-'+name+'.png'),fullPage:true});};
   await p.goto(base);await b('Abrir turno').tap();await nav('Mesas');assert.equal(await p.locator('.table-card').count(),5);assert.equal(await b('Administrar mesas').count(),0);
   await role('supervisor');await nav('Mesas');await b('Administrar mesas').tap();await b('+ Agregar mesa').tap();await p.getByLabel('Nombre de la mesa').fill('Terraza 06');await b('Guardar').tap();await p.locator('[data-action="table"][data-value="6"]').waitFor();assert.equal(await p.locator('.table-card').count(),6);await shot('mesas');
   await p.locator('[data-action="table"][data-value="6"]').tap();await p.getByLabel('Personas',{exact:true}).fill('3');await b('Abrir pedido').tap();
   for(const id of ['burger','wings','mojito']){await p.locator('[data-action="product"][data-value="'+id+'"]').tap();await p.getByText(/Se agregará una unidad/).waitFor();await b('Añadir a la cuenta').tap();}
   await p.getByText(/Mojito agregado al pedido/).waitFor();await shot('agregar');await b('Enviar comanda').tap();
   await p.locator('#mobile-orderbar [data-action="pay"]').tap();console.log(device.name+' split chooser');await p.getByRole('button',{name:/^En partes iguales/}).tap();console.log(device.name+' equal form');await p.getByLabel('Cantidad de personas').fill('7');await b('Calcular partes').tap();
   assert.equal(await p.locator('.equal-summary .item').count(),7);await shot('dividir');
   const amounts=[21395,21395,21394,21394,21394,21394,21394];
   for(let part=0;part<7;part++){
    if(part){await p.locator('#mobile-orderbar [data-action="pay"]').tap();await p.getByRole('button',{name:/^En partes iguales/}).tap();}
    assert.equal(await p.getByLabel('Parte que va a pagar').inputValue(),String(part));
    if(part)assert.equal(await p.getByLabel('Cantidad de personas').getAttribute('readonly'),'');
    await p.getByLabel('Método de pago').selectOption(part===0?'efectivo':'tarjeta');await b('Registrar pago').tap();await p.getByText(/Pago registrado/).waitFor();
    const state=(await(await fetch(base+'/api/state')).json()).state;assert.equal(state.payments.length,part+1);assert.equal(state.payments[part].amount,amounts[part]);assert.equal(state.ingredients.ron.stock,2455);
   }
   await p.getByText('Simulado · sin envío a DGII',{exact:true}).waitFor();await shot('pagado');
   const s=(await(await fetch(base+'/api/state')).json()).state;assert.equal(s.orders[0].closed,true);assert.equal(s.payments.reduce((n,v)=>n+v.amount,0),149760);assert.deepEqual(errors,[]);
   await nav('Reportes');await p.getByLabel('Efectivo contado').fill('2213.95');await b('Confirmar cierre').tap();assert.equal((await(await fetch(base+'/api/state')).json()).state.shift.difference,0);
   console.log(device.name+': 5 initial tables, add/rename, product guide, equal split 7 people, mixed payments, stock once, zero difference PASSED');
  }finally{await context.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
 }}finally{await browser.close();}
});
