"""Disposable lab benchmark with no public DNS and no customer/control records."""
import argparse,json,pathlib,sys,time,uuid,secrets,hashlib,os
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from control.container_adapter import ContainerAdapter
from control.catalog import installation_profile
from control.template_cache import CACHE,verified_cache
from deployment.pilot_adapter import PilotAdapter

class Benchmark(PilotAdapter):
 def __init__(self,images):
  ContainerAdapter.__init__(self,CACHE/'bench',images,ROOT,'template-benchmark','uno360x-bench-')
  self.startup_database_cpus='0.75';self.restore_database_cpus='1'
  self.database_limits=['--cpus','0.25','--memory','192m'];self.database_command=['postgres','-c','shared_buffers=32MB','-c','max_connections=25','-c','max_locks_per_transaction=256']
 lock=ContainerAdapter.lock
 def identity(self,s):
  if self.runtime_identity(s,lambda:self._shell_identity(s)):return
  self._shell_identity(s)
 def _shell_identity(self,s):
  with self.batch_shell(s):
   ContainerAdapter.identity(self,s)
   self.sync_user(s,{'tenant_id':s['tenant_id'],'account_id':s['qa_account'],'email':'benchmark@example.test','role':'owner','display_name':'Administrador ficticio QA'})
 def cleanup(self,s):
  n=self.names(s);proxy=n['prefix']+'-proxy'
  if self.exists('container',proxy):
   info=self.inspect(proxy)
   if not all(info['Config']['Labels'].get(k)==v for k,v in self.labels(s).items()):raise RuntimeError('Foreign QA proxy')
   self.run('rm','-f',proxy)
  for suffix in ('app','init','database'):
   name=n[suffix]
   if self.exists('container',name):self.check_container(name,s);self.run('rm','-f',name)
  for name in (n['pgvolume'],n['files']):
   if self.exists('volume',name):self.volume(name,s);self.run('volume','rm',name)
  if self.exists('network',n['network']):self.network(s);self.run('network','rm',n['network'])

def main():
 p=argparse.ArgumentParser();p.add_argument('--modules',nargs='*',default=[]);p.add_argument('--keep',action='store_true');p.add_argument('--cleanup',action='store_true');args=p.parse_args()
 os.umask(0o077);images=json.loads(pathlib.Path('/etc/uno360x-saas/images.json').read_text());a=Benchmark(images);state=CACHE/'qa-state.json'
 if args.cleanup:
  if state.exists():a.cleanup(json.loads(state.read_text()));state.unlink()
  print(json.dumps({'qa_resources_removed':True}));return
 if state.exists():raise RuntimeError('Clean up the previous disposable benchmark first')
 profile=installation_profile(args.modules)
 if verified_cache(profile,images) is None:raise RuntimeError('Build this profile before benchmarking; no cold fallback')
 s={'tenant_id':uuid.uuid4().hex,'qa_account':uuid.uuid4().hex,'hostname':'qa-benchmark.uno360x.com','slug':'benchmark','mode':'local_laboratory','installation':profile,'company_profile':{'name':'Empresa ficticia QA','country':'DO','currency':'DOP'}}
 n=a.names(s);timings=[];start=time.monotonic();state.write_text(json.dumps(s));state.chmod(0o600)
 try:
  with a.lock(s['tenant_id']):
   for step in ('network','database','installation','identity','validation'):
    t=time.monotonic();getattr(a,step)(s);timings.append({'step':step,'seconds':round(time.monotonic()-t,3)})
   result={'seconds':round(time.monotonic()-start,3),'modules':args.modules,'timings':timings,'template':json.loads((n['directory']/'installed.json').read_text()).get('template'),'tenant':s['tenant_id'],'database_uuid':a.sql(s,"SELECT value FROM ir_config_parameter WHERE key='database.uuid'"),'bridge_key_sha256':hashlib.sha256(a.bridge_key(s)).hexdigest()}
   (CACHE/('benchmark-'+('-'.join(args.modules) or 'base')+'.json')).write_text(json.dumps(result))
   if args.keep:
    origin=a.backend(s);password=secrets.token_urlsafe(24);login='saas_'+s['qa_account']
    a.shell(s,"user=env['res.users'].search([('login','=',%r)]);assert len(user)==1 and not user.has_group('base.group_system');user.with_context(no_reset_password=True).write({'password':%r});env.cr.commit();print('UNO360X_OK')"%(login,password))
    (CACHE/'qa-login.json').write_text(json.dumps({'origin':origin,'login':login,'password':password,'tenant':s['tenant_id']}));(CACHE/'qa-login.json').chmod(0o600)
    result['kept_for_visual_qa']=True
   print(json.dumps(result),flush=True)
 finally:
  if not args.keep:a.cleanup(s);state.unlink(missing_ok=True)
if __name__=='__main__':main()
