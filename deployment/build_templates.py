"""Build all eight module combinations from EMPTY databases, never customer DBs."""
import sys,pathlib,json,os,pwd,time,itertools,secrets,subprocess,shutil,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from control.container_adapter import ContainerAdapter
from control.template_install import TemplateInstallMixin
from control.catalog import installation_profile
from control.template_cache import CACHE,RECIPE,cache_key,checksum,verified_cache,custom_addons
OPTIONS=['jenifer_ai','payroll_hr','projects_services']
class Builder(TemplateInstallMixin,ContainerAdapter):
 def shell(self,s,code):
  result=self.run('run','--rm','-i',*self.common(s),self.images['odoo:18.0'],'odoo','shell','-c','/etc/odoo/odoo.conf','--no-http',input=code,check=False)
  if result.returncode or 'UNO360X_OK' not in result.stdout:
   p=self.names(s)['directory']/'sanitizer-error.log';p.write_text(result.stderr);p.chmod(0o600);o=p.with_name('sanitizer-output.log');o.write_text(result.stdout);o.chmod(0o600);raise RuntimeError('Template sanitization failed; private log retained')
  return result.stdout
 def common(self,s):
  args=super().common(s);args[args.index('--cpus')+1]='0.65';args[args.index('--memory')+1]='640m';return [*args,'--oom-score-adj','500']
 def run(self,*args,**kw):
  if '--stop-after-init' in args:
   args=tuple('/uno360x_auth_bridge,/uno360x_workspace' if x=='/uno360x_auth_bridge' else x for x in args)
   args=(*args,'--load-language','es_DO','-u','uno360x_auth_bridge,uno360x_workspace')
  return super().run(*args,**kw)

def build(modules,images):
 profile=installation_profile(modules);key=cache_key(profile,images)
 if verified_cache(profile,images):return {'modules':modules,'cached':True}
 # Do not compete with a customer creation job or start under low memory.
 mem={k:int(v.split()[0]) for k,v in [l.split(':',1) for l in pathlib.Path('/proc/meminfo').read_text().splitlines()]}
 if mem['MemAvailable']<3*1024*1024:raise RuntimeError('Insufficient safe build memory')
 group=pathlib.Path('/sys/fs/cgroup/user.slice/user-996.slice');maximum=(group/'memory.max').read_text().strip();used=int((group/'memory.current').read_text())
 if maximum=='max' or int(maximum)-used<896*1024**2:raise RuntimeError('Insufficient reserved SaaS build headroom')
 import sqlite3
 c=sqlite3.connect('file:/var/lib/uno360x-saas/control/control.sqlite3?mode=ro',uri=True)
 pending=c.execute("SELECT count(*) FROM preparation_jobs WHERE status='running' OR (status='queued' AND COALESCE(current_step,'')!='capacity')").fetchone()[0];c.close()
 if pending:raise RuntimeError('Customer provisioning has priority')
 stage=CACHE/'ready'/('.building-'+key);stage.mkdir(mode=0o700,parents=True,exist_ok=True);resume=stage/'builder.json'
 tid=json.loads(resume.read_text())['tenant_id'] if resume.exists() else secrets.token_hex(16)
 resume.write_text(json.dumps({'tenant_id':tid}));resume.chmod(0o600)
 s={'tenant_id':tid,'slug':'pristine-template','hostname':'template.invalid','mode':'local_laboratory','installation':profile}
 a=Builder(CACHE/'build',images,ROOT,'template-builder','uno360x-template-');a.database_limits=['--cpus','0.25','--memory','192m'];a.database_command=['postgres','-c','shared_buffers=32MB','-c','max_connections=25','-c','maintenance_work_mem=32MB','-c','max_locks_per_transaction=256']
 started=time.monotonic();n=a.names(s)
 try:
  with a.lock(tid):
   a.network(s);a.database(s)
   base=installation_profile([]);seed_profile=base if modules and verified_cache(base,images) else None
   if seed_profile is None:
    for manifest in sorted((CACHE/'ready').glob('*/manifest.json'),key=lambda p:p.stat().st_mtime,reverse=True):
     meta=json.loads(manifest.read_text());candidate=meta.get('installation')
     if not candidate or set(candidate['addons'])!=set(base['addons']):continue
     if any(candidate['addons'][k]!=base['addons'][k] for k in base['addons'] if k!='uno360x_workspace'):continue
     if verified_cache(candidate,images):seed_profile=candidate;break
   if not (n['directory']/'installed.json').exists() and seed_profile and seed_profile['fingerprint']!=profile['fingerprint']:
    seed=dict(s,installation=seed_profile,resource_fingerprint=profile['fingerprint']);a.installation(seed)
    # Builder-only transition from the empty Base seed to this exact profile.
    (n['directory']/'installed.json').unlink()
   a.installation(s)
   a.shell(s,"""import secrets,json
print('FACTORY_DEFAULTS '+json.dumps({model:[{'id':x.id,'name':x.display_name,'xmlid':x.get_external_id().get(x.id)} for x in env[model].with_context(active_test=False).search([],limit=8)] for model in ('project.task','account.analytic.line','hr.employee') if model in env.registry}))
assert not env['uno360x.tenant.identity'].search_count([])
assert env['res.company'].search_count([])==1
assert env['res.users'].search([('share','=',False),('active','=',True)]).ids==env.ref('base.user_admin').ids
assert not env['res.users'].with_context(active_test=False).search_count([('uno360x_account_id','!=',False)])
# Keep standard Internal/Time Off configuration, but no sample time entries
# or active Administrator employee. This database has never accepted customers.
for model in ('account.move','sale.order','purchase.order','pos.order','stock.picking','stock.move','hr.contract','hr.leave','hr.expense','hr.expense.sheet'):
 if model in env.registry:assert not env[model].sudo().search_count([]),model
if 'account.analytic.line' in env.registry:env['account.analytic.line'].sudo().search([]).unlink()
if 'project.project' in env.registry:
 projects=env['project.project'].with_context(active_test=False).search([])
 assert all(p.name in ('Internal','Interno','Internal Project','Proyecto interno','Time Off') for p in projects),projects.mapped('name')
if 'project.task' in env.registry:
 tasks=env['project.task'].with_context(active_test=False).search([])
 assert len(tasks)<=3 and all(t.name in ('Time Off','Training','Meeting','Capacitación','Reunión') for t in tasks)
if 'hr.employee' in env.registry:
 employees=env['hr.employee'].with_context(active_test=False).search([])
 admin=env.ref('hr.employee_admin',raise_if_not_found=False)
 assert not (employees-admin) if admin else not employees
 if employees:employees.write({'active':False,'name':'Administrador del sistema','work_email':False,'work_phone':False})
assert not env['ir.mail_server'].sudo().search_count([])
env['ir.cron'].sudo().search([]).write({'active':False})
env.cr.execute('UPDATE res_users SET password=NULL')
for model in ('res.users.apikeys','uno360x.auth.nonce','mail.mail'):
 if model in env.registry:env[model].sudo().search([]).unlink()
company=env.ref('base.main_company');company.write({'name':'UNO360X Plantilla','country_id':env.ref('base.do').id,'currency_id':env.ref('base.DOP').id})
company.partner_id.write({'email':False,'phone':False,'vat':False})
assert env['res.lang'].search([('code','=','es_DO')]).active
params=env['ir.config_parameter'].sudo()
for name in ('database.uuid','database.secret'):params.set_param(name,'template-not-an-active-company')
params.set_param('web.base.url','https://uno360x.com')
env.cr.commit();print('UNO360X_OK')
""")
   actual=a.sql(s,"SELECT name FROM ir_module_module WHERE state='installed' AND name LIKE 'uno360x_%' ORDER BY name")
   if actual.splitlines()!=custom_addons(profile,ROOT):raise RuntimeError('Unexpected template modules')
   with (stage/'database.dump').open('wb') as out:
    result=subprocess.run(['podman','exec',n['database'],'pg_dump','-U','postgres','-d',n['role'],'-Fc','--no-owner','--no-acl'],stdout=out,stderr=subprocess.PIPE,timeout=120)
   if result.returncode:raise RuntimeError('Template dump failed')
   files=json.loads(a.run('volume','inspect',n['files']).stdout)[0]['Mountpoint'];filestore=pathlib.Path(files)/'filestore'/n['role']
   # Namespace root can read rootless Odoo files without making them public.
   result=subprocess.run(['podman','unshare','tar','-C',str(filestore),'--owner=0','--group=0','-cf',str(stage/'files.tar'),'.'],capture_output=True,timeout=120)
   if result.returncode:raise RuntimeError('Template filestore export failed')
   for p in stage.iterdir():p.chmod(0o600)
   meta={'key':key,'recipe':RECIPE,'fingerprint':profile['fingerprint'],'images':images,'pristine':True,'installation':profile,'modules':modules,'created':time.time(),'build_seconds':round(time.monotonic()-started,2),'sha256':{name:checksum(stage/name) for name in ('database.dump','files.tar')}}
   (stage/'manifest.json').write_text(json.dumps(meta));(stage/'manifest.json').chmod(0o600)
   resume.unlink(missing_ok=True)
   target=CACHE/'ready'/key;stage.rename(target);verified_cache(profile,images)
   return {'modules':modules,'build_seconds':meta['build_seconds'],'cached':False}
 finally:
  ready=(CACHE/'ready'/key).exists()
  # Failed factory jobs keep their PRIVATE synthetic state for diagnostics and
  # retry, but all compute is stopped. Ready templates drop all builder resources.
  for suffix in ('app','init','database'):
   name=n[suffix]
   if a.exists('container',name):
    info=a.check_container(name,s)
    if ready:a.run('rm','-f',name)
    elif info['State']['Running']:a.run('stop',name)
  if ready:
   for name in (n['pgvolume'],n['files']):
    if a.exists('volume',name):a.volume(name,s);a.run('volume','rm',name)
   if a.exists('network',n['network']):a.network(s);a.run('network','rm',n['network'])

def main():
 if os.geteuid()==0 or pwd.getpwuid(os.geteuid()).pw_name!='uno360x-saas':raise RuntimeError('Exclusive rootless account required')
 os.umask(0o077);CACHE.mkdir(mode=0o700,exist_ok=True);images=json.loads(pathlib.Path('/etc/uno360x-saas/images.json').read_text())
 combinations=[list(x) for n in range(4) for x in itertools.combinations(OPTIONS,n)]
 # Prioritize Base, full suite, then individual plans and combinations.
 combinations=[[],OPTIONS]+[x for x in combinations if x and x!=OPTIONS]
 journal=[]
 for modules in combinations:
  (CACHE/'progress.json').write_text(json.dumps({'current':modules,'completed':journal,'updated':time.time()}))
  try:result=build(modules,images)
  except Exception as error:
   (CACHE/'progress.json').write_text(json.dumps({'current':modules,'completed':journal,'failed':type(error).__name__,'updated':time.time()}));raise
  journal.append(result);print(json.dumps(result),flush=True)
 (CACHE/'progress.json').write_text(json.dumps({'completed':journal,'ready':True,'updated':time.time()}))
if __name__=='__main__':main()
