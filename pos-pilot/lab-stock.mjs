import { readFileSync } from 'node:fs';

export function stockConnector(file) {
 const config=JSON.parse(readFileSync(file,'utf8'));
 const url=new URL(config.origin);
 if(!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||url.protocol!=='http:'||
    url.pathname!=='/'||url.username||url.password||url.search||url.hash||
    !/^uno360x_pos_lab[a-z0-9_]*$/.test(config.database))throw Error('El conector requiere Odoo de laboratorio en loopback.');
 const secret=process.env.POS_ODOO_KEY;
 if(!secret)throw Error('Configura POS_ODOO_KEY para el usuario de inventario de pruebas.');
 const rpc=async(service,method,args)=>{
  const response=await fetch(new URL('/jsonrpc',url),{method:'POST',redirect:'error',
   signal:AbortSignal.timeout(6000),headers:{'Content-Type':'application/json'},
   body:JSON.stringify({jsonrpc:'2.0',id:1,method:'call',params:{service,method,args}})});
  const body=await response.json();
  if(!response.ok||body.error)throw Error('Odoo de pruebas rechazó la solicitud de inventario.');
  return body.result;
 };
 return async (scope,event)=>{
  if(!Object.hasOwn(config.branches,scope))throw Error('Sucursal de inventario sin configurar.');
  const branch=config.branches[scope];
  const mapped=Object.hasOwn(branch.products,event.ingredient)?branch.products[event.ingredient]:null;
  if(!mapped||!Number.isInteger(mapped.id)||!Number.isFinite(mapped.factor)||mapped.factor<=0)
   throw Error('Ingrediente sin equivalencia en inventario de pruebas.');
  const uid=await rpc('common','authenticate',[config.database,config.login,secret,{}]);
  if(!uid)throw Error('Usuario de inventario de pruebas no autorizado.');
  const move=await rpc('object','execute_kw',[config.database,uid,secret,'stock.move','uno360x_pos_consume',
   [event.reference,mapped.id,branch.source,branch.destination,event.quantity*mapped.factor],
   {context:{allowed_company_ids:[branch.company]}}]);
  if(move?.state!=='done')throw Error('El movimiento no se confirmó.');
  return move.id;
 };
}
