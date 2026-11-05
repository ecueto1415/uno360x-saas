"""Configure a new private instance and serve it with the same Odoo registry.

No HTTP bootstrap endpoint. The trusted worker mounts one private script and
the normal per-instance configuration. An existing completed bootstrap is never
reapplied when the application restarts.
"""
import json,pathlib,re

def isolate_bus_database(sql_db,database):
 """Keep Odoo notification connections inside the single tenant database.

 Odoo bus uses a hard-coded postgres connection for LISTEN/NOTIFY. Shared
 tenant roles deliberately cannot connect to that maintenance database.
 This process serves exactly one validated database; redirect only that
 literal maintenance target, preserving the tenant role and other calls.
 """
 if not isinstance(database,str) or not re.fullmatch(r"tenant_[a-f0-9]{32}",database):
  raise ValueError("Expected a single private tenant database")
 original=sql_db.db_connect
 def connect(name,*args,**kwargs):
  return original(database if name=="postgres" else name,*args,**kwargs)
 sql_db.db_connect=connect


def main():
 import odoo
 from odoo.modules.registry import Registry
 from odoo.service import server
 config=odoo.tools.config
 config.parse_config(['-c','/etc/odoo/odoo.conf'],setup_logging=True)
 assert not config['workers'] and not config['init'] and not config['update']
 payload=json.loads(pathlib.Path('/run/uno360x/initial-owner.json').read_text())
 names=config['db_name']
 if isinstance(names,str):names=[n.strip() for n in names.split(',') if n.strip()]
 assert len(names)==1 and names[0]==payload.get('database_name','tenant_'+payload['tenant_id'])
 isolate_bus_database(odoo.sql_db,names[0])
 server.load_server_wide_modules()
 registry=Registry(names[0])
 with registry.cursor() as cr:
  env=odoo.api.Environment(cr,odoo.SUPERUSER_ID,{})
  parameters=env['ir.config_parameter'].sudo()
  marker=parameters.get_param('uno360x.initial_owner.completed')
  if marker:
   assert marker==payload['fingerprint']
  else:
   identity=env['uno360x.tenant.identity'].search([])
   assert not identity or (len(identity)==1 and identity.tenant_id==payload['tenant_id'] and identity.hostname==payload['hostname'])
   exec(compile(payload['script'],'<private-instance-initialization>','exec'),{'env':env})
   parameters.set_param('uno360x.initial_owner.completed',payload['fingerprint'])
   cr.commit()
  identity=env['uno360x.tenant.identity'].search([])
  assert len(identity)==1 and identity.tenant_id==payload['tenant_id'] and identity.hostname==payload['hostname']
 # The loaded registry is reused. No second shell process or second preload.
 raise SystemExit(server.start(preload=[],stop=False))
if __name__=='__main__':main()
