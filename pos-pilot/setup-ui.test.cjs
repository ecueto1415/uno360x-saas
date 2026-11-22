const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.POS_PLAYWRIGHT_PATH||'playwright');
test('Approved setup on tablet and phone: all business types, persisted tables/products, actual shell',async()=>{
 const {makeServer}=await import('./server.mjs');const browser=await chromium.launch({channel:'msedge',headless:true});
 const out=process.env.POS_SCREENSHOTS||path.resolve('pos-pilot/var/setup-review');fs.mkdirSync(out,{recursive:true});
 try{for(const device of [{name:'tablet',width:768,height:1024},{name:'phone',width:390,height:844}]){
  for(const [business,label] of [['restaurant','Restaurante y bar'],['bakery','Cafetería y panadería'],['retail','Tienda y comercio'],['quick','Venta rápida']]){
   const access={close(){},authorize(){return {scope:'qa-setup',account:'1',role:'supervisor',branchName:'Local piloto',displayName:'Administrador',staff:[{id:'1',name:'Administrador'}]};}};
   const server=makeServer(':memory:',access);await new Promise(r=>server.listen(0,'127.0.0.1',r));
   const context=await browser.newContext({viewport:{width:device.width,height:device.height},hasTouch:true,isMobile:true});
   try{
    const p=await context.newPage();p.setDefaultTimeout(8000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
    const b=n=>p.getByRole('button',{name:n,exact:true}),base='http://127.0.0.1:'+server.address().port;
    const snap=async()=> (await(await fetch(base+'/api/state')).json()).state;
    const shot=async n=>{assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),device.width);await p.screenshot({path:path.join(out,device.name+'-'+business+'-'+n+'.png'),fullPage:true});};
    await p.goto(base);await p.getByRole('heading',{name:'Paso 1 de 3 · Elige tu negocio',exact:true}).waitFor();
    const brand=await p.locator('.brand').evaluate(el=>el.outerHTML);const menu=await p.locator('#nav button').allTextContents();
    if(business!=='restaurant')await p.locator('section.panel').filter({has:p.getByRole('heading',{name:label,exact:true})}).getByRole('button',{name:'Elegir',exact:true}).tap();
    await shot('negocio');await b('Continuar').tap();
    if(['restaurant','bakery'].includes(business)){
     await p.getByRole('heading',{name:'Paso 2 de 3 · Configura tus mesas',exact:true}).waitFor();assert.equal(await p.locator('.table-card').count(),5);
     if(business==='restaurant'){
      await p.locator('.table-card').first().tap();await p.getByLabel('Nombre de la mesa').fill('Terraza 01');await b('Guardar').tap();await p.getByRole('button',{name:/Terraza 01/}).waitFor();
      await p.getByLabel('Cantidad inicial').fill('6');
     }else await p.getByLabel('¿Atiendes en mesas?').selectOption('no');
     await shot('mesas');await b('Continuar').tap();
    }
    await p.getByRole('heading',{name:'Paso 3 de 3 · Agrega tus productos',exact:true}).waitFor();
    await p.reload();await p.getByRole('heading',{name:'Paso 3 de 3 · Agrega tus productos',exact:true}).waitFor();assert.equal((await snap()).products.length,0);
    await b('+ Nuevo producto').tap();await p.getByLabel('Nombre',{exact:true}).fill('Producto de prueba');await p.getByLabel('Categoría',{exact:true}).fill('General');await p.getByLabel('Precio (RD$)',{exact:true}).fill('125');
    await p.getByLabel('Estación').selectOption(business==='restaurant'?'barra':'ninguna');
    await b('Guardar producto').tap();await p.locator('.item').filter({hasText:'Producto de prueba'}).waitFor();await shot('productos');
    const s=await snap();assert.equal(s.products.length,1);assert.equal(s.products[0].cents,12500);assert.equal(s.setup.business,business);
    if(business==='restaurant'){assert.equal(s.tables.filter(t=>t.active).length,6);assert.equal(s.tables[0].name,'Terraza 01');}
    if(business==='restaurant'){
     await b('Cargar ejemplos').tap();await p.getByText('3 productos de ejemplo agregados.').waitFor();assert.equal((await snap()).products.length,4);
    }
    await b('Guardar y abrir el POS').tap();await b('Abrir turno').waitFor();assert.equal((await snap()).shift,null);assert.equal((await snap()).payments.length,0);assert.equal((await snap()).setup.completed,true);
    await p.reload();await b('Abrir turno').waitFor();assert.equal(await p.getByRole('heading',{name:'Paso 1 de 3 · Elige tu negocio',exact:true}).count(),0);
    assert.equal(await p.locator('.brand').evaluate(el=>el.outerHTML),brand);assert.deepEqual(await p.locator('#nav button').allTextContents(),menu);
    await p.locator('#mobile-nav-toggle').tap();await p.locator('#nav [data-value="Menú"]').tap();await b('Ajustes del POS').tap();await p.getByRole('heading',{name:'Ajustes del POS',exact:true}).waitFor();assert.equal((await snap()).setup.completed,true);assert.equal((await snap()).products.length,business==='restaurant'?4:1);
    assert.deepEqual(errors,[]);console.log(device.name+' '+business+': saved/resumed/completed; shell preserved; no sale; reopen without resetting PASSED');
   }finally{await context.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
  }
 }}finally{await browser.close();}
});
