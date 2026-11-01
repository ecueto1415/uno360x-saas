"""Rootless adapter limited to one private VM pilot tenant; never native Odoo."""
from contextlib import contextmanager
import json,os,pwd,re,sqlite3,time
from pathlib import Path
from control.container_adapter import ContainerAdapter
ROOT=Path(__file__).resolve().parents[1]
STATE=Path('/var/lib/uno360x-saas/tenants')
class SharedHostAdapter(ContainerAdapter):
 def __init__(self):
  if os.name!='posix' or os.geteuid()==0 or pwd.getpwuid(os.geteuid()).pw_name!='uno360x-saas':
   raise RuntimeError('Exclusive unprivileged SaaS account required')
  images=json.loads(Path('/etc/uno360x-saas/images.json').read_text())
  super().__init__(STATE,images,ROOT,'private-pilot','uno360x-pilot-')
  info=json.loads(self.run('info','--format','json').stdout)
  if not info['host']['security']['rootless']:raise RuntimeError('Rootless runtime required')
 @contextmanager
 def lock(self,tid):
  import fcntl
  if not re.fullmatch('[a-f0-9]{32}',tid):raise ValueError('Invalid tenant')
  with (self.state/'capacity.lock').open('a') as capacity:
   fcntl.flock(capacity,fcntl.LOCK_EX|fcntl.LOCK_NB)
   others=[p for p in self.state.iterdir() if p.is_dir() and re.fullmatch('[a-f0-9]{32}',p.name) and p.name!=tid]
   if others:raise RuntimeError('Private pilot capacity is one tenant')
   with super().lock(tid):yield
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
