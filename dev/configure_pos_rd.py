"""Spanish/DOP visual fixture, only isolated Alfa WSL laboratory."""
import os
from pathlib import Path
from tenants import run, inspect
assert os.geteuid()==0 and 'microsoft' in Path('/proc/sys/kernel/osrelease').read_text().lower()
app='uno360x-lab-empresa-alfa-app'
info=inspect(app)
assert info['Config']['Labels']['uno360x.environment']=='local-development'
assert not any(info['NetworkSettings']['Ports'].values())
code="""import json
assert env.cr.dbname=='tenant_c7b3008a169345d9'
lang=env['res.lang'].with_context(active_test=False).search([('code','=','es_DO')])
env['base.language.install'].create({'lang_ids':[(6,0,lang.ids)],'overwrite':False}).lang_install()
dop=env['res.currency'].with_context(active_test=False).search([('name','=','DOP')]);dop.active=True
company=env['res.company'].search([('name','=','UNO360X DEMO RD - LABORATORIO')])
if not company:
 company=env['res.company'].create({'name':'UNO360X DEMO RD - LABORATORIO','country_id':env.ref('base.do').id,'currency_id':dop.id})
 env['account.chart.template'].try_loading('do',company,install_demo=False)
admin=env.ref('base.user_admin');admin.write({'company_ids':[(4,company.id)],'company_id':company.id,'lang':'es_DO'})
env=env(context=dict(env.context,allowed_company_ids=[company.id],lang='es_DO'))
if not env['stock.warehouse'].search([('company_id','=',company.id)]):
 env['stock.warehouse'].create({'name':'ALMACEN FICTICIO RD','code':'LRD','company_id':company.id})
config=env['pos.config'].search([('name','=','CAJA DEMO RD - LABORATORIO'),('company_id','=',company.id)])
if not config:
 config=env['pos.config'].create({'name':'CAJA DEMO RD - LABORATORIO','company_id':company.id,'receipt_header':'LABORATORIO - SIN VALIDEZ FISCAL','receipt_footer':'PRUEBA FICTICIA - NO ES UNA VENTA REAL'})
 for name,price in [('ARTICULO DEMO RD A',100),('ARTICULO DEMO RD B',250)]:
  env['product.product'].create({'name':name,'company_id':company.id,'available_in_pos':True,'type':'consu','list_price':price,'taxes_id':[(5,0,0)]})
assert config.currency_id.name=='DOP'
env['ir.cron'].search([('active','=',True)]).active=False
env.cr.commit();env.registry.signal_changes()
print('RD_LAB_READY '+json.dumps({'company':company.id,'config':config.id,'lang':admin.lang,'currency':config.currency_id.name,'original_company_currency':env['res.company'].browse(1).currency_id.name}))
"""
p=run('exec','-i',app,'odoo','shell','-c','/etc/odoo/odoo.conf','--no-http',input=code,check=False)
if p.returncode: raise RuntimeError(p.stderr[-2500:])
print('\n'.join(l for l in p.stdout.splitlines() if 'RD_LAB_READY' in l))
