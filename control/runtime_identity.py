"""One process for first identity setup and the running application."""
import json,time

class RuntimeIdentityMixin:
 def runtime_identity(self,s,configure):
  n=self.names(s);payload_file=n['directory']/'initial-owner.json'
  if not payload_file.exists():
   marker=n['directory']/'installed.json'
   if not marker.exists() or not json.loads(marker.read_text()).get('template'):return False
   if self.exists('container',n['app']):return False
   if self.sql(s,'SELECT count(*) FROM uno360x_tenant_identity')!='0':raise RuntimeError('Runtime bootstrap requires an unclaimed pristine instance')
   if hasattr(self,'_startup_scripts'):raise RuntimeError('Nested runtime bootstrap')
   self._startup_scripts=[]
   try:
    configure();script='\n'.join(self._startup_scripts)
   finally:del self._startup_scripts
   if not script:raise RuntimeError('Missing initial owner setup')
   self.protected(payload_file,json.dumps({'tenant_id':s['tenant_id'],'hostname':s['hostname'],'fingerprint':s['installation']['fingerprint'],'script':script}))
   # Same isolation as odoo.conf: private 0700 parent, read-only file mount.
   payload_file.chmod(0o644)
  payload=json.loads(payload_file.read_text())
  if payload['tenant_id']!=s['tenant_id'] or payload['hostname']!=s['hostname'] or payload['fingerprint']!=s['installation']['fingerprint']:raise RuntimeError('Bootstrap identity or release mismatch')
  if not self.exists('container',n['app']):
   args=self.common(s);args[args.index('--cpus')+1]='1'
   self.run('run','-d','--name',n['app'],'--log-driver','k8s-file','--oom-score-adj','500',*args,
    '-v',str(self.root/'deployment/runtime_bootstrap.py')+':/run/uno360x/runtime_bootstrap.py:ro',
    '-v',str(payload_file)+':/run/uno360x/initial-owner.json:ro','--entrypoint','python3',
    self.images['odoo:18.0'],'/run/uno360x/runtime_bootstrap.py')
  else:
   info=self.check_container(n['app'],s)
   if not info['State']['Running']:self.run('start',n['app'])
  self.check_container(n['app'],s)
  try:
   for _ in range(90):
    value=self.sql(s,"SELECT value FROM ir_config_parameter WHERE key='uno360x.initial_owner.completed'")
    if value==s['installation']['fingerprint']:return True
    info=self.inspect(n['app'])
    if not info['State']['Running']:raise RuntimeError('Initial owner setup failed; private container log retained')
    time.sleep(0.25)
   raise RuntimeError('Initial owner setup timed out')
  finally:
   if self.inspect(n['app'])['State']['Running']:self.run('update','--cpus','0.5',n['app'])
