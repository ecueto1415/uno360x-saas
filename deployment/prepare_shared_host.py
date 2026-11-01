"""Private staging on the explicitly authorized existing VM; no public runtime."""
import datetime,hashlib,json,os,pathlib,pwd,shutil,subprocess,tarfile
assert os.geteuid()==0
assert os.environ.get('UNO360X_ACK_SHARED_HOST_PREPARATION')=='140.82.47.80', 'Explicit authorized host acknowledgement required'
assert pathlib.Path('/etc/machine-id').exists()
assert pathlib.Path('/etc/odoo18.conf').exists()
os.umask(0o077)
def run(args,**kwargs):return subprocess.run(args,check=True,capture_output=True,text=True,**kwargs).stdout.strip()
def baseline():
 return {'configuration_hashes':{p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['/etc/odoo18.conf','/etc/nginx/sites-enabled/odoo']},'odoo_main_pid':run(['systemctl','show','odoo18','-p','MainPID','--value']),'services':{s:run(['systemctl','is-active',s]) for s in ['odoo18','postgresql@16-main','nginx']}}
before=baseline();assert all(v=='active' for v in before['services'].values())
backup=pathlib.Path('/opt/uno360x-saas/backups')/('shared-host-preparation-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
for database in ['Outsolutech_prueba','OUTSOLUTECH']:
 target=backup/(database+'.dump')
 with target.open('wb') as out:
  p=subprocess.run(['nice','-n','19','runuser','-u','postgres','--','pg_dump','-Fc','-d',database],stdout=out,stderr=subprocess.PIPE,check=True)
 run(['pg_restore','--list',str(target)])
with tarfile.open(backup/'filestores.tar.gz','w:gz',dereference=True) as archive:
 for database in ['Outsolutech_prueba','OUTSOLUTECH']:
  source=pathlib.Path('/opt/odoo18/.local/share/Odoo/filestore')/database
  assert source.is_dir();archive.add(source,arcname=database)
with tarfile.open(backup/'service-configuration.tar.gz','w:gz',dereference=True) as archive:
 for path in ['/etc/odoo18.conf','/etc/nginx/sites-enabled/odoo']:
  archive.add(path,arcname=path.lstrip('/'))
try:account=pwd.getpwnam('uno360x-saas')
except KeyError:
 run(['useradd','--system','--user-group','--create-home','--home-dir','/var/lib/uno360x-saas','--shell','/usr/sbin/nologin','uno360x-saas']);account=pwd.getpwnam('uno360x-saas')
assert account.pw_shell=='/usr/sbin/nologin' and account.pw_dir=='/var/lib/uno360x-saas'
assert account.pw_uid not in [0,pwd.getpwnam('odoo18').pw_uid]
for path,owner,group,mode in [('/srv/uno360x-saas',0,account.pw_gid,0o750),('/srv/uno360x-saas/releases',0,account.pw_gid,0o750),('/var/lib/uno360x-saas',account.pw_uid,account.pw_gid,0o700),('/etc/uno360x-saas',0,account.pw_gid,0o750)]:
 p=pathlib.Path(path);assert not p.is_symlink();p.mkdir(exist_ok=True,parents=True);os.chown(p,owner,group);p.chmod(mode)
policy={'deployment_mode':'shared_host_private_staging','public_signup_enabled':False,'operational_database':'Outsolutech_prueba','protected_services':['odoo18','postgresql@16-main','nginx'],'saas_user':'uno360x-saas','production_credentials_reused':False,'runtime_installed':False,'public_ports_added':False,'ubuntu_upgrade':'deferred_by_user','pending':['supported_host_operating_system','isolated_runtime_and_https_gateway','independent_verification_mail','external_backup_recovery']}
pathlib.Path('/etc/uno360x-saas/staging-policy.json').write_text(json.dumps(policy,indent=2));os.chown('/etc/uno360x-saas/staging-policy.json',0,account.pw_gid);os.chmod('/etc/uno360x-saas/staging-policy.json',0o640)
after=baseline();assert before==after,'Operational baseline changed; investigate before continuing'
files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()} for p in backup.iterdir() if p.is_file()}
report={'backup':str(backup),'online_backup':True,'restore_verified':False,'dump_catalogs_readable':True,'filestore_live_copy_not_atomic':True,'files':files,'baseline_before':before,'baseline_after':after,'separate_saas_account_created':True,'private_directories_prepared':True,'operational_configuration_and_odoo_pid_unchanged':True,'public_signup_enabled':False,'package_installation':False,'ubuntu_upgrade':False}
(backup/'report.json').write_text(json.dumps(report,indent=2))
print('SHARED_HOST_PREPARED '+json.dumps(report),flush=True)
