"""Restore pristine templates only into newly created, owned tenant resources."""
import json,pathlib,subprocess,secrets,uuid,time
from control.template_cache import verified_cache,custom_addons
class TemplateInstallMixin:
 def installation(self,s):
  n=self.names(s);marker=n['directory']/'installed.json'
  if marker.exists() or self.exists('container',n['init']):return super().installation(s)
  cache=verified_cache(s['installation'],self.images)
  if cache is None:return super().installation(s)
  started=time.monotonic();self.check_container(n['database'],s);self.volume(n['files'],s)
  journal=n['directory']/'template-restore.json';fingerprint=s['installation']['fingerprint']
  exists=int(self.sql(s,"SELECT count(*) FROM pg_tables WHERE schemaname='public'"))
  if exists:
   if not journal.exists() or json.loads(journal.read_text()).get('fingerprint')!=fingerprint:raise RuntimeError('Nonempty tenant database cannot receive a template')
  else:
   journal.write_text(json.dumps({'fingerprint':fingerprint,'cache':cache.name,'started':time.time()}));journal.chmod(0o600)
   original_cpus='0.25'
   self.run('update','--cpus',getattr(self,'restore_database_cpus','0.75'),n['database'])
   try:
    with (cache/'database.dump').open('rb') as incoming:
     result=subprocess.run(['podman','exec','-i',n['database'],'pg_restore','-U','postgres','-d',n['role'],'--role',n['role'],'--no-owner','--no-acl','--single-transaction','--exit-on-error'],stdin=incoming,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=180)
   finally:self.run('update','--cpus',original_cpus,n['database'])
   if result.returncode:
    (n['directory']/'restore-error.log').write_bytes(result.stderr);(n['directory']/'restore-error.log').chmod(0o600);raise RuntimeError('Atomic template restore failed')
  self.check_modules(s)
  actual=self.sql(s,"SELECT name FROM ir_module_module WHERE state='installed' AND name LIKE 'uno360x_%' ORDER BY name")
  if actual.splitlines()!=custom_addons(s['installation'],self.root):raise RuntimeError('Unexpected template capabilities')
  safe=self.sql(s,"SELECT count(*) FROM uno360x_tenant_identity; SELECT count(*) FROM res_users WHERE password IS NOT NULL AND password<>''; SELECT count(*) FROM res_users WHERE uno360x_account_id IS NOT NULL; SELECT count(*) FROM ir_mail_server; SELECT count(*) FROM ir_cron WHERE active; SELECT count(*) FROM account_move; SELECT count(*) FROM sale_order; SELECT count(*) FROM purchase_order; SELECT count(*) FROM pos_order;")
  if safe!='\n'.join(['0']*9):raise RuntimeError('Template contains identity, credentials, business data or automation')
  self.sql(s,"DO $$ DECLARE n bigint; t text; BEGIN FOREACH t IN ARRAY ARRAY['account_analytic_line','hr_contract','hr_leave','hr_expense','hr_expense_sheet','stock_picking','stock_move'] LOOP IF to_regclass('public.'||t) IS NOT NULL THEN EXECUTE format('SELECT count(*) FROM %I',t) INTO n; IF n<>0 THEN RAISE EXCEPTION 'Pristine template business record check failed'; END IF; END IF; END LOOP; END $$;")
  self.sql(s,"DO $$ DECLARE n bigint; BEGIN IF to_regclass('public.hr_employee') IS NOT NULL THEN SELECT count(*) INTO n FROM hr_employee WHERE active; IF n<>0 THEN RAISE EXCEPTION 'Template contains active employee records'; END IF; END IF; END $$;")
  role=n['role'];code="""import pathlib,tarfile,pwd,os
root=pathlib.Path('/var/lib/odoo/filestore')/%r
root.mkdir(parents=True,exist_ok=True)
with tarfile.open('/run/uno360x/template-files.tar') as archive:
 for member in archive.getmembers():
  path=pathlib.PurePosixPath(member.name)
  assert not path.is_absolute() and '..' not in path.parts and (member.isfile() or member.isdir())
 archive.extractall(root)
u=pwd.getpwnam('odoo')
for p in [pathlib.Path('/var/lib/odoo'),root.parent,root,*root.rglob('*')]:os.chown(p,u.pw_uid,u.pw_gid)
print('UNO360X_FILES_OK')
"""%role
  result=self.run('run','--rm','--user','0','--entrypoint','python3',*self.common(s),'-v',str(cache/'files.tar')+':/run/uno360x/template-files.tar:ro',self.images['odoo:18.0'],'-c',code)
  if 'UNO360X_FILES_OK' not in result.stdout:raise RuntimeError('Template files were not restored')
  # Every actual tenant receives fresh database secrets in addition to fresh
  # DB login, admin password and bridge key created by database().
  self.sql(s,"INSERT INTO ir_config_parameter(key,value,create_uid,write_uid) VALUES ('database.uuid','%s',1,1),('database.secret','%s',1,1) ON CONFLICT(key) DO UPDATE SET value=excluded.value;"%(uuid.uuid4(),secrets.token_hex(32)))
  marker.write_text(json.dumps({'fingerprint':fingerprint,'template':cache.name,'restore_seconds':round(time.monotonic()-started,3)}));marker.chmod(0o600)
