"""Real CRM opportunity/quotation rehearsal with transaction rollback in WSL."""
import os,json
from pathlib import Path
from tenants import run,inspect
assert os.geteuid()==0 and 'microsoft' in Path('/proc/sys/kernel/osrelease').read_text().lower()
for slug in ['empresa-alfa','empresa-beta']:
 app='uno360x-lab-'+slug+'-app';info=inspect(app)
 assert info['Config']['Labels']['uno360x.environment']=='local-development'
 assert not any(info['NetworkSettings']['Ports'].values())
 code="""import json
assert env.cr.dbname in ['tenant_c7b3008a169345d9','tenant_21603ac130714afb']
assert env['ir.module.module'].search([('name','=','crm')]).state=='installed'
before=env['crm.lead'].search_count([])
partner=env['res.partner'].create({'name':'CONTACTO FICTICIO CRM TEMPORAL'})
lead=env['crm.lead'].create({'name':'OPORTUNIDAD FICTICIA CRM TEMPORAL','type':'opportunity','partner_id':partner.id,'expected_revenue':100})
assert lead.partner_id==partner and lead.type=='opportunity'
quote=env['sale.order'].create({'partner_id':partner.id,'opportunity_id':lead.id})
assert quote.opportunity_id==lead and quote.state=='draft'
lead.action_set_won();assert lead.stage_id.is_won and lead.probability==100
assert quote in lead.order_ids
env.cr.rollback()
assert env['crm.lead'].search_count([])==before
print('CRM_ROLLBACK_OK')
"""
 p=run('exec','-i',app,'odoo','shell','-c','/etc/odoo/odoo.conf','--no-http',input=code,check=False)
 if p.returncode or 'CRM_ROLLBACK_OK' not in p.stdout:raise RuntimeError(p.stderr[-2000:])
 print(json.dumps({'company':slug,'crm_installed':True,'contact_opportunity_quotation_won':True,'transaction_rolled_back':True}),flush=True)
