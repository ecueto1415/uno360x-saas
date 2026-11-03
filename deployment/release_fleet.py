"""Resume a reviewed visual release across every active SaaS tenant.

Run as uno360x-saas from the candidate source. Stop the preparation worker
before --apply; keep the identity gateway up while runtimes are updated.
Stop the gateway briefly for --finalize and the common source-link switch.
Native Odoo is outside the control database and can never be a target here.
"""
import argparse,json,os,pathlib,re,sqlite3,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from control.catalog import installation_profile
CONTROL=pathlib.Path('/var/lib/uno360x-saas/control/control.sqlite3')

def reviewed_transition(old,new):
 if set(new['addons'])-set(old['addons'])-{'uno360x_workspace'}:raise RuntimeError('Unreviewed new business module')
 for name,version in old['addons'].items():
  if name not in {'uno360x_workspace','uno360x_payroll_hr','uno360x_quote_ui'} and new['addons'].get(name)!=version:raise RuntimeError('Unreviewed business migration: '+name)

def active_tenants(db,now):
 return db.execute("SELECT p.*,t.modules FROM preparation_jobs p JOIN tenants t ON t.id=p.tenant_id LEFT JOIN trial_workspaces w ON w.tenant_id=p.tenant_id WHERE p.status='ready_local' AND (w.expires IS NULL OR w.expires>?) ORDER BY p.updated,p.id",(now,)).fetchall()

def queued_rebases(db,state,profile=installation_profile):
 result=[]
 for row in db.execute("SELECT p.*,t.modules FROM preparation_jobs p JOIN tenants t ON t.id=p.tenant_id WHERE p.status='queued'"):
  new_profile=profile(json.loads(row['modules']))
  if new_profile['fingerprint']==row['fingerprint']:continue
  if (state/row['tenant_id']).exists() or db.execute('SELECT 1 FROM preparation_steps WHERE job_id=?',(row['id'],)).fetchone():raise RuntimeError('Allocated preparation requires explicit migration')
  snapshot=json.loads(row['snapshot']);reviewed_transition(snapshot['installation'],new_profile)
  snapshot['installation']=new_profile;result.append((snapshot,row['id']))
 return result

def stopped(service):
 return subprocess.run(['systemctl','is-active','--quiet',service]).returncode!=0

def main():
 from deployment.shared_adapter import SharedHostAdapter
 p=argparse.ArgumentParser();p.add_argument('--release',required=True);p.add_argument('--apply',action='store_true');p.add_argument('--finalize',action='store_true');args=p.parse_args()
 if not re.fullmatch('[a-z0-9-]{1,80}',args.release):raise ValueError('Invalid release ID')
 os.umask(0o077);adapter=SharedHostAdapter();db=sqlite3.connect(CONTROL);db.row_factory=sqlite3.Row
 directory=adapter.state.parent/'fleet-rollouts'/args.release;path=directory/'state.json'
 rows=active_tenants(db,time.time());plan=[{'tenant':r['tenant_id'],'current':r['fingerprint'],'target':installation_profile(json.loads(r['modules']))['fingerprint']} for r in rows]
 if not (args.apply or args.finalize):print(json.dumps({'release':args.release,'targets':plan,'source':str(ROOT),'native_odoo_touched':False}));return
 if not stopped('uno360x-saas-worker'):raise RuntimeError('Stop the preparation worker before a fleet rollout')
 if db.execute("SELECT 1 FROM preparation_jobs WHERE status='running'").fetchone():raise RuntimeError('Finish the current preparation before publishing')
 directory.mkdir(parents=True,mode=0o700,exist_ok=True)
 def save():
  tmp=path.with_suffix('.next');tmp.write_text(json.dumps(state));tmp.chmod(0o600);tmp.replace(path)
 if path.exists():
  state=json.loads(path.read_text())
  if state['source']!=str(ROOT):raise RuntimeError('Release ID belongs to another immutable source')
 else:
  state={'release':args.release,'source':str(ROOT),'started':time.time(),'phase':'preparing','targets':plan,'validated':[]}
  backup=sqlite3.connect(directory/'control-before.sqlite3');db.backup(backup);backup.close();save()
 if args.apply:
  for item in state['targets']:
   tid=item['tenant'];target=installation_profile(json.loads(db.execute('SELECT modules FROM tenants WHERE id=?',(tid,)).fetchone()[0]))
   if target['fingerprint']!=item['target']:raise RuntimeError('Candidate product changed during rollout')
   if item['current']==item['target']:continue
   pending=adapter.state/tid/'workspace-pending.json'
   if pending.exists():
    previous=json.loads(pending.read_text())
    if previous['snapshot']['installation']['fingerprint']!=item['target']:
     current=db.execute('SELECT fingerprint,snapshot FROM preparation_jobs WHERE tenant_id=?',(tid,)).fetchone()
     if previous['snapshot']!=json.loads(current['snapshot']) or previous['snapshot']['installation']['fingerprint']!=current['fingerprint']:
      raise RuntimeError('Unpublished pending tenant belongs to another release')
     adapter.validate_runtime(previous['snapshot']);adapter.check_modules(previous['snapshot'])
     archived=pending.with_name('workspace-published-'+current['fingerprint']+'.json')
     if archived.exists():raise RuntimeError('Published marker archive already exists; review required')
     pending.rename(archived)
   if not pending.exists():
    run=subprocess.run([sys.executable,str(ROOT/'deployment/workspace_release.py'),tid,'--apply','--defer-publish'],capture_output=True,text=True)
    (directory/(tid+'.log')).write_text(run.stdout+'\n'+run.stderr)
    if run.returncode:state['phase']='needs_review';state['failed_tenant']=tid;save();raise RuntimeError('Tenant rollout failed; inspect private backup and log')
   staged=json.loads(pending.read_text())
   if staged['snapshot']['installation']['fingerprint']!=item['target']:raise RuntimeError('Pending tenant belongs to another release')
   adapter.validate_runtime(staged['snapshot']);adapter.check_modules(staged['snapshot'])
   if tid not in state['validated']:state['validated'].append(tid)
   state['phase']='preparing';save();print(json.dumps({'tenant':tid,'runtime':'validated'}),flush=True)
  state['phase']='ready_to_publish';save();print(json.dumps({'release':args.release,'phase':state['phase'],'validated':len(state['validated'])}),flush=True)
 if args.finalize:
  if not stopped('uno360x-saas-pilot'):raise RuntimeError('Stop the gateway for atomic control publication')
  if state['phase'] not in ('ready_to_publish','publishing','published'):raise RuntimeError('All runtimes must be validated first')
  staged=[]
  for item in state['targets']:
   if item['current']==item['target']:continue
   pending=adapter.state/item['tenant']/'workspace-pending.json';data=json.loads(pending.read_text())
   row=db.execute('SELECT fingerprint,snapshot FROM preparation_jobs WHERE id=?',(data['job_id'],)).fetchone()
   if row['fingerprint'] not in (data['old_fingerprint'],item['target']):raise RuntimeError('Concurrent tenant release')
   if data['snapshot']['installation']['fingerprint']!=item['target']:raise RuntimeError('Pending product mismatch')
   assert dict(db.execute('SELECT started,expires FROM trial_workspaces WHERE tenant_id=?',(item['tenant'],)).fetchone())==data['trial']
   adapter.check_modules(data['snapshot']);staged.append(data)
  rebases=queued_rebases(db,adapter.state);state['phase']='publishing';save()
  with db:
   db.execute('BEGIN IMMEDIATE')
   db.execute('CREATE TABLE IF NOT EXISTS tenant_releases (tenant_id TEXT NOT NULL,fingerprint TEXT NOT NULL,previous_fingerprint TEXT NOT NULL,applied REAL NOT NULL,backup TEXT NOT NULL,PRIMARY KEY(tenant_id,fingerprint))')
   for data in staged:
    target=data['snapshot']['installation']['fingerprint']
    db.execute('INSERT OR REPLACE INTO tenant_releases VALUES (?,?,?,?,?)',(data['tenant_id'],target,data['old_fingerprint'],time.time(),data['backup']))
    db.execute('UPDATE preparation_jobs SET snapshot=?,fingerprint=? WHERE id=?',(json.dumps(data['snapshot'],sort_keys=True),target,data['job_id']))
   for snapshot,job in rebases:db.execute('UPDATE preparation_jobs SET snapshot=?,fingerprint=? WHERE id=?',(json.dumps(snapshot,sort_keys=True),snapshot['installation']['fingerprint'],job))
  for data in staged:
   marker=adapter.state/data['tenant_id']/'installed.json';marker.write_text(json.dumps({'fingerprint':data['snapshot']['installation']['fingerprint']}));marker.chmod(0o600)
  state.update(phase='published',published=time.time(),rebased_unallocated_jobs=len(rebases));save()
  print(json.dumps({'release':args.release,'phase':'published','tenant_count':len(staged),'rebased_queued':len(rebases),'native_odoo_touched':False}),flush=True)
if __name__=='__main__':main()
