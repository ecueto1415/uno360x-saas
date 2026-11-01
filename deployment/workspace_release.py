"""Versioned, tenant-scoped workspace rollout. Never targets the native Odoo.
Run as uno360x-saas from an immutable release. Default is a read-only plan.
Stop SaaS worker and pilot before --apply; the operational odoo18 stays running.
"""
import argparse,datetime,json,os,shutil,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.shared_adapter import SharedHostAdapter
from control.catalog import installation_profile
CONTROL=Path('/var/lib/uno360x-saas/control/control.sqlite3')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('tenant');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 os.umask(0o077);adapter=SharedHostAdapter();db=sqlite3.connect(CONTROL);db.row_factory=sqlite3.Row
 row=db.execute('SELECT * FROM preparation_jobs WHERE tenant_id=?',(args.tenant,)).fetchone()
 if not row or row['status']!='ready_local':raise RuntimeError('Ready SaaS tenant required')
 old=json.loads(row['snapshot']);n=adapter.names(old)
 modules=json.loads(db.execute('SELECT modules FROM tenants WHERE id=?',(args.tenant,)).fetchone()[0])
 target=installation_profile(modules)
 # This rollout installs the approved common workspace; business migrations need their own review.
 if set(target['addons'])-set(old['installation']['addons'])-{'uno360x_workspace'}:raise RuntimeError('Unexpected new business module')
 for name,version in old['installation']['addons'].items():
  if name!='uno360x_workspace' and target['addons'].get(name)!=version:raise RuntimeError('Unreviewed business change: '+name)
 new=dict(old,installation=target,resource_fingerprint=old.get('resource_fingerprint',old['installation']['fingerprint']))
 adapter.check_container(n['app'],old);adapter.check_container(n['database'],old)
 if not args.apply:
  print(json.dumps({'tenant':args.tenant,'release':target['release'],'target_fingerprint':target['fingerprint'],'new_addons':sorted(set(target['addons'])-set(old['installation']['addons'])),'native_odoo_touched':False}));return
 with adapter.lock(args.tenant):
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
  backup=adapter.state.parent/'release-backups'/args.tenant/stamp;backup.mkdir(parents=True,mode=0o700)
  backupdb=sqlite3.connect(backup/'control-before.sqlite3');db.backup(backupdb);backupdb.close()
  (backup/'before.json').write_text(json.dumps({'snapshot':old,'target':target,'source':str(ROOT),'trial':dict(db.execute('SELECT started,expires FROM trial_workspaces WHERE tenant_id=?',(args.tenant,)).fetchone())}))
  shutil.copytree(n['directory'],backup/'tenant-state')
  adapter.run('stop',n['app'])
  (backup/'tenant.sql').write_text(adapter.run('exec',n['database'],'pg_dump','-U','postgres','--no-owner','--no-acl',n['role']).stdout)
  adapter.run('volume','export','--output',str(backup/'files.tar'),n['files'])
  result=adapter.run('run','--rm','--name',n['prefix']+'-workspace-upgrade',*adapter.common(new),adapter.images['odoo:18.0'],'odoo','-c','/etc/odoo/odoo.conf','-i','uno360x_workspace','-u','uno360x_workspace','--without-demo=all','--stop-after-init','--test-enable','--test-tags','/uno360x_workspace',check=False)
  (backup/'upgrade.log').write_text(result.stdout+'\n'+result.stderr)
  if result.returncode:raise RuntimeError('Workspace update failed. SaaS backup retained; native Odoo unaffected.')
  adapter.shell(new,"""home=env.ref('uno360x_workspace.action_home')
users=env['res.users'].search([('uno360x_account_id','!=',False)])
if 'action_id' in users._fields:users.write({'action_id':home.id})
env['ir.config_parameter'].sudo().set_param('uno360x.workspace.release',%r)
env['ir.cron'].search([]).write({'active':False})
env.cr.commit();print('UNO360X_OK')
"""%target['fingerprint'])
  adapter.run('rm',n['app'])
  adapter.validation(new)
  adapter.check_modules(new)
  (n['directory']/'installed.json').write_text(json.dumps({'fingerprint':target['fingerprint']}))
  with db:
   db.execute('CREATE TABLE IF NOT EXISTS tenant_releases (tenant_id TEXT NOT NULL, fingerprint TEXT NOT NULL, previous_fingerprint TEXT NOT NULL, applied REAL NOT NULL, backup TEXT NOT NULL, PRIMARY KEY(tenant_id,fingerprint))')
   import time
   db.execute('INSERT OR REPLACE INTO tenant_releases VALUES (?,?,?,?,?)',(args.tenant,target['fingerprint'],row['fingerprint'],time.time(),str(backup)))
   db.execute('UPDATE preparation_jobs SET snapshot=?,fingerprint=? WHERE id=?',(json.dumps(new,sort_keys=True),target['fingerprint'],row['id']))
  current=dict(db.execute('SELECT started,expires FROM trial_workspaces WHERE tenant_id=?',(args.tenant,)).fetchone())
  assert current==json.loads((backup/'before.json').read_text())['trial']
  print(json.dumps({'tenant':args.tenant,'workspace':'installed','release':target['release'],'backup':str(backup),'trial_dates_preserved':True,'native_odoo_touched':False}))
if __name__=='__main__':main()
