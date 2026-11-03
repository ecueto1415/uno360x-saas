"""Rootless adapter limited to one private VM pilot tenant; never native Odoo."""
from contextlib import contextmanager
import json,os,pwd,re,sqlite3,time
from pathlib import Path
from control.container_adapter import ContainerAdapter
from control.template_install import TemplateInstallMixin
ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/uno360x-saas/tenants')
class CapacityUnavailable(RuntimeError):pass

class SharedHostAdapter(TemplateInstallMixin,ContainerAdapter):
 def __init__(self):
  if os.name!='posix' or os.geteuid()==0 or pwd.getpwuid(os.geteuid()).pw_name!='uno360x-saas':
   raise RuntimeError('Exclusive unprivileged SaaS account required')
  images=json.loads(Path('/etc/uno360x-saas/images.json').read_text())
  super().__init__(STATE,images,ROOT,'private-pilot','uno360x-pilot-')
  policy=Path('/etc/uno360x-saas/resource-policy.json')
  settings=json.loads(policy.read_text()) if policy.exists() else {'max_active_tenants':1}
  cap=settings.get('max_active_tenants',1);self.max_active=None if cap is None else int(cap)
  if self.max_active is not None and self.max_active not in (1,2,3):raise RuntimeError('Invalid explicit pilot admission policy')
  self.startup_database_cpus='0.75';self.restore_database_cpus='1'
  self.database_limits=['--cpus','0.25','--memory','192m']
  self.database_command=['postgres','-c','shared_buffers=32MB','-c','max_connections=40','-c','maintenance_work_mem=32MB','-c','max_locks_per_transaction=256']
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
 def has_headroom(self,except_tid):
  # Open registration, bounded admission. Never stop an existing tenant to
  # create another one and never treat an unbounded cgroup as safe capacity.
  group=Path('/sys/fs/cgroup/user.slice/user-996.slice')
  maximum=(group/'memory.max').read_text().strip();used=int((group/'memory.current').read_text());quota,period=(group/'cpu.max').read_text().split()
  mem={k:int(v.split()[0])*1024 for k,v in [l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines()]}
  if maximum=='max' or quota=='max':return False
  if int(maximum)>mem['MemTotal']//2 or int(quota)/int(period)>max(1,os.cpu_count()/2):return False
  committed=self._allocated(except_tid)*832*1024**2
  return int(maximum)-max(used,committed)>=1088*1024**2 and mem['MemAvailable']>=2*1024**3
 @contextmanager
 def lock(self,tid):
  import fcntl
  if not re.fullmatch('[a-f0-9]{32}',tid):raise ValueError('Invalid tenant')
  with (self.state/'capacity.lock').open('a') as capacity:
   fcntl.flock(capacity,fcntl.LOCK_EX)
   directory=self.state/tid
   if directory.is_symlink():raise RuntimeError('Unexpected tenant path')
   if not directory.exists():
    cap=getattr(self,'max_active',1)
    if cap is None:
     if not self.has_headroom(tid):raise CapacityUnavailable('Protected resource headroom is queued')
    elif self._allocated(tid)>=cap:raise CapacityUnavailable('Compute capacity is queued')
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
  if self.runtime_identity(s,lambda:self._shell_identity(s)):return
  self._shell_identity(s)
 def _shell_identity(self,s):
  with self.batch_shell(s):
   super().identity(s)
   db=sqlite3.connect('file:/var/lib/uno360x-saas/control/control.sqlite3?mode=ro',uri=True)
   try:
    row=db.execute("SELECT a.id,a.email,d.name FROM preparation_jobs p JOIN accounts a ON a.id=p.requested_by LEFT JOIN trial_signup_drafts d ON d.account_id=a.id JOIN memberships m ON m.account_id=a.id AND m.tenant_id=p.tenant_id WHERE p.tenant_id=? AND a.verified=1 AND a.active=1 AND m.active=1 AND m.role='owner'",(s['tenant_id'],)).fetchone()
   finally:db.close()
   if not row:raise RuntimeError('Verified owner required before readiness')
   self.sync_user(s,{'tenant_id':s['tenant_id'],'account_id':row[0],'email':row[1],'role':'owner','display_name':row[2]})
 def validate_runtime(self,s,inspected=None):
  inspected=inspected or {}
  n=self.names(s)
  if n['app'] not in inspected and not self.exists('container',n['app']):
   self.run('run','-d','--name',n['app'],*self.common(s),self.images['odoo:18.0'],'odoo','-c','/etc/odoo/odoo.conf')
   self.check_container(n['app'],s)
  else:
   info=self.check_container(n['app'],s,info=inspected.get(n['app']))
   if not info['State']['Running']:self.run('start',n['app'])
  self.check_container(n['database'],s,info=inspected.get(n['database']))
  wanted=sorted(s['installation']['addons'])
  modules="SELECT name FROM ir_module_module WHERE state='installed' AND name IN (%s) ORDER BY name; "%','.join("'%s'"%name for name in wanted)
  expected='\n'.join(wanted)+'\n'+s['tenant_id']+'|'+s['hostname']+'\n0\n0\nf|f|f|f'
  actual=self.sql(s,modules+"SELECT tenant_id,hostname FROM uno360x_tenant_identity; SELECT count(*) FROM ir_cron WHERE active; SELECT count(*) FROM ir_mail_server; SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname='%s';"%n['role'])
  if actual!=expected:raise RuntimeError('Tenant modules, isolation or identity validation failed')
 def validation(self,s):
  self.validate_runtime(s)
  n=self.names(s)
  probe="import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8069/web/login',timeout=3).status==200"
  for _ in range(45):
   if self.run('exec',n['app'],'python3','-c',probe,check=False).returncode==0:return
   time.sleep(1)
  raise RuntimeError('Private application is unavailable')
 def backend(self,s):
  raise RuntimeError('Public gateway not deployed; do not expose tenant ports')
