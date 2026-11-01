"""Rootless adapter limited to one private VM pilot tenant; never native Odoo."""
from contextlib import contextmanager
import json,os,pwd,re,sqlite3,time
from pathlib import Path
from control.container_adapter import ContainerAdapter
ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/uno360x-saas/tenants')
class CapacityUnavailable(RuntimeError):pass

class SharedHostAdapter(ContainerAdapter):
 def __init__(self):
  if os.name!='posix' or os.geteuid()==0 or pwd.getpwuid(os.geteuid()).pw_name!='uno360x-saas':
   raise RuntimeError('Exclusive unprivileged SaaS account required')
  images=json.loads(Path('/etc/uno360x-saas/images.json').read_text())
  super().__init__(STATE,images,ROOT,'private-pilot','uno360x-pilot-')
  policy=Path('/etc/uno360x-saas/resource-policy.json')
  self.max_active=int(json.loads(policy.read_text()).get('max_active_tenants',1)) if policy.exists() else 1
  if self.max_active not in (1,2):raise RuntimeError('Resource admission policy exceeds this VM budget')
  self.database_limits=['--cpus','0.25','--memory','192m']
  self.database_command=['postgres','-c','shared_buffers=32MB','-c','max_connections=40','-c','maintenance_work_mem=32MB']
  info=json.loads(self.run('info','--format','json').stdout)
  if not info['host']['security']['rootless']:raise RuntimeError('Rootless runtime required')
 def common(self,s):
  args=super().common(s);args[args.index('--memory')+1]='640m';args[args.index('--cpus')+1]='0.5';return args
 def _allocated(self,except_tid):
  directories=[p.name for p in self.state.iterdir() if p.is_dir() and re.fullmatch('[a-f0-9]{32}',p.name) and p.name!=except_tid]
  control=Path('/var/lib/uno360x-saas/control/control.sqlite3')
  if not control.exists():return len(directories)
  db=sqlite3.connect('file:'+str(control)+'?mode=ro',uri=True)
  try:
   if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():return len(directories)
   count=0
   for tid in directories:
    row=db.execute('SELECT expires FROM trial_workspaces WHERE tenant_id=?',(tid,)).fetchone()
    if row and row[0] and row[0]<=time.time():
     # Expiration frees a slot only after owned compute is actually stopped.
     names=[self.prefix+tid+'-'+suffix for suffix in ('db','app','proxy')]
     if not any(self.exists('container',name) and self.inspect(name)['State']['Running'] for name in names):continue
    count+=1
   return count
  finally:db.close()
 @contextmanager
 def lock(self,tid):
  import fcntl
  if not re.fullmatch('[a-f0-9]{32}',tid):raise ValueError('Invalid tenant')
  with (self.state/'capacity.lock').open('a') as capacity:
   fcntl.flock(capacity,fcntl.LOCK_EX)
   directory=self.state/tid
   if directory.is_symlink():raise RuntimeError('Unexpected tenant path')
   if not directory.exists() and self._allocated(tid)>=getattr(self,'max_active',1):raise CapacityUnavailable('Compute capacity is queued')
   directory.mkdir(mode=0o700,exist_ok=True)
  # Do not hold the global admission lock during another tenant's installation.
  with super().lock(tid):yield
 def stop_expired(self,s):
  with self.lock(s['tenant_id']):
   names=self.names(s)
   for suffix in ('app','db','proxy'):
    name=names['prefix']+'-'+suffix
    if not self.exists('container',name):continue
    info=self.inspect(name)
    if not all(info['Config']['Labels'].get(k)==v for k,v in self.labels(s).items()):raise RuntimeError('Foreign expired resource')
    if info['State']['Running']:self.run('stop',name)
 def identity(self,s):
  super().identity(s)
  db=sqlite3.connect('file:/var/lib/uno360x-saas/control/control.sqlite3?mode=ro',uri=True)
  try:
   row=db.execute("SELECT a.id,a.email FROM preparation_jobs p JOIN accounts a ON a.id=p.requested_by JOIN memberships m ON m.account_id=a.id AND m.tenant_id=p.tenant_id WHERE p.tenant_id=? AND a.verified=1 AND a.active=1 AND m.active=1 AND m.role='owner'",(s['tenant_id'],)).fetchone()
  finally:db.close()
  if not row:raise RuntimeError('Verified owner required before readiness')
  self.sync_user(s,{'tenant_id':s['tenant_id'],'account_id':row[0],'email':row[1],'role':'owner'})
 def validation(self,s):
  n=self.names(s)
  if not self.exists('container',n['app']):
   self.run('run','-d','--name',n['app'],*self.common(s),self.images['odoo:18.0'],'odoo','-c','/etc/odoo/odoo.conf')
  else:
   self.check_container(n['app'],s);self.run('start',n['app'])
  self.check_container(n['app'],s);self.check_container(n['database'],s);self.check_modules(s)
  expected=s['tenant_id']+'|'+s['hostname']+'\n0\n0\nf|f|f|f'
  actual=self.sql(s,"SELECT tenant_id,hostname FROM uno360x_tenant_identity; SELECT count(*) FROM ir_cron WHERE active; SELECT count(*) FROM ir_mail_server; SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname='%s';"%n['role'])
  if actual!=expected:raise RuntimeError('Tenant isolation validation failed')
  probe="import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8069/web/login',timeout=3).status==200"
  for _ in range(45):
   if self.run('exec',n['app'],'python3','-c',probe,check=False).returncode==0:return
   time.sleep(1)
  raise RuntimeError('Private application is unavailable')
 def backend(self,s):
  raise RuntimeError('Public gateway not deployed; do not expose tenant ports')
