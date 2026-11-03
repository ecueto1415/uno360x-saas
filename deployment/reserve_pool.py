"""Private shared PostgreSQL and unclaimed, independently owned databases."""
import contextlib,fcntl,itertools,json,os,pathlib,re,secrets,shutil,subprocess,time,uuid
from control.reserve_store import ReserveStore,identifier,TARGET
from control.catalog import installation_profile
from control.template_cache import verified_cache,custom_addons
BASE=pathlib.Path('/var/lib/uno360x-saas/shared-postgres')
SERVER='uno360x-shared-postgres-v1';PGVOLUME=SERVER+'-data';NETWORK=SERVER+'-net'
LABELS={'uno360x.environment':'shared-postgres-reserve','uno360x.managed':'uno360x-saas','uno360x.pool':'v1'}
OPTIONS=('jenifer_ai','payroll_hr','projects_services')

def ident(value):
 if not re.fullmatch('[a-z][a-z0-9_]{0,62}',value):raise ValueError('Invalid SQL identifier')
 return '"'+value+'"'
def literal(value):return "'"+str(value).replace("'","''")+"'"
def profiles():
 out=[]
 for n in range(4):
  for modules in itertools.combinations(OPTIONS,n):
   weight=4 if not modules or len(modules)==3 else 2 if modules==('payroll_hr',) else 1
   out.append((list(modules),installation_profile(modules),weight))
 return out

class Pool:
 def __init__(self,adapter):
  self.a=adapter;BASE.mkdir(mode=0o700,parents=True,exist_ok=True)
  if BASE.is_symlink() or BASE.stat().st_uid!=os.geteuid():raise RuntimeError('Unowned shared database state')
  self.store=ReserveStore(BASE/'inventory.sqlite3')
 def __enter__(self):return self
 def __exit__(self,*args):self.store.close()
 @contextlib.contextmanager
 def builder_lock(self,wait=True):
  with (BASE/'builder.lock').open('a') as f:
   fcntl.flock(f,fcntl.LOCK_EX|(0 if wait else fcntl.LOCK_NB))
   try:yield
   finally:fcntl.flock(f,fcntl.LOCK_UN)
 def labels(self,extra=None):return [v for k,x in dict(LABELS,**(extra or {})).items() for v in ('--label',k+'='+x)]
 def verify_volume(self,name,extra=None):
  info=json.loads(self.a.run('volume','inspect',name).stdout)[0];expected=dict(LABELS,**(extra or {}))
  if not all((info.get('Labels') or {}).get(k)==v for k,v in expected.items()):raise RuntimeError('Foreign shared volume')
  return info
 def verify_server(self,info=None):
  info=info or self.a.inspect(SERVER)
  if not all(info['Config']['Labels'].get(k)==v for k,v in LABELS.items()):raise RuntimeError('Foreign shared server')
  if info['Image'].removeprefix('sha256:')!=self.a.images['postgres:16'].removeprefix('sha256:'):raise RuntimeError('Shared PostgreSQL image drift')
  if any(info['NetworkSettings']['Ports'].values()):raise RuntimeError('Shared PostgreSQL must not publish a port')
  if NETWORK not in info['NetworkSettings']['Networks']:raise RuntimeError('Missing private shared management network')
  mounts={m['Destination']:m for m in info['Mounts']}
  if mounts.get('/var/lib/postgresql/data',{}).get('Name')!=PGVOLUME:raise RuntimeError('Unexpected PostgreSQL data mount')
  if mounts.get('/run/uno360x-pg-hba.conf',{}).get('Source')!=str(BASE/'pg_hba.conf') or mounts['/run/uno360x-pg-hba.conf']['RW']:raise RuntimeError('Unexpected PostgreSQL authentication mount')
  if info['HostConfig']['Memory']!=512*1024**2:raise RuntimeError('Unexpected shared PostgreSQL memory budget')
  for name in info['NetworkSettings']['Networks']:
   net=json.loads(self.a.run('network','inspect',name).stdout)[0]
   if not net['internal']:raise RuntimeError('Shared PostgreSQL network is not private')
   if name==NETWORK:
    if not all((net.get('labels') or {}).get(k)==v for k,v in LABELS.items()):raise RuntimeError('Foreign management network')
   elif not re.fullmatch(r'uno360x-pilot-[a-f0-9]{32}-net',name) or (net.get('labels') or {}).get('uno360x.environment')!='private-pilot':raise RuntimeError('Foreign tenant network')
  self.verify_volume(PGVOLUME);return info
 def sql(self,sql,database='postgres',check=True):
  ident(database)
  result=self.a.run('exec','-i',SERVER,'psql','-X','-q','-U','postgres','-d',database,'-v','ON_ERROR_STOP=1','-At',input=sql,check=False)
  if check and result.returncode:
   p=BASE/'last-error.log';p.write_text(result.stderr);p.chmod(0o600);raise RuntimeError('Shared PostgreSQL operation failed; inspect private log')
  return result.stdout.strip() if check else result
 def ensure(self):
  if not self.a.exists('network',NETWORK):self.a.run('network','create','--internal',*self.labels(),NETWORK)
  if not self.a.exists('volume',PGVOLUME):self.a.run('volume','create',*self.labels(),PGVOLUME)
  self.verify_volume(PGVOLUME)
  desired="local all postgres trust\nlocal all all reject\nhost all postgres 0.0.0.0/0 reject\nhost all postgres ::/0 reject\nhost postgres all 0.0.0.0/0 scram-sha-256\nhost postgres all ::/0 scram-sha-256\nhost sameuser all 0.0.0.0/0 scram-sha-256\nhost sameuser all ::/0 scram-sha-256\nhost all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n"
  hba=self.a.protected(BASE/'pg_hba.conf',desired)
  if hba.read_text()!=desired:hba.write_text(desired)
  hba.chmod(0o644)
  env=self.a.protected(BASE/'postgres.env','POSTGRES_PASSWORD='+secrets.token_hex(32)+'\n')
  if not self.a.exists('container',SERVER):
   self.a.run('run','-d','--name',SERVER,'--network',NETWORK,*self.labels(),'--cpus','0.75','--memory','512m','--pids-limit','160','--log-driver','k8s-file','--env-file',str(env),'-v',PGVOLUME+':/var/lib/postgresql/data','-v',str(hba)+':/run/uno360x-pg-hba.conf:ro',self.a.images['postgres:16'],'postgres','-c','hba_file=/run/uno360x-pg-hba.conf','-c','shared_buffers=64MB','-c','max_connections=80','-c','work_mem=2MB','-c','maintenance_work_mem=32MB','-c','max_locks_per_transaction=256')
  info=self.verify_server()
  if not info['State']['Running']:self.a.run('start',SERVER)
  for _ in range(60):
   p=self.a.run('exec',SERVER,'sh','-c',"test \"$(cat /proc/1/comm)\" = postgres && psql -X -U postgres -d postgres -Atc 'SELECT 1'",check=False)
   if p.returncode==0 and p.stdout.strip()=='1':break
   time.sleep(0.5)
  else:raise RuntimeError('Shared PostgreSQL did not start')
  self.sql("SELECT pg_reload_conf(); REVOKE ALL ON DATABASE postgres,template0,template1 FROM PUBLIC;")
  self.sql('REVOKE ALL ON SCHEMA public FROM PUBLIC;','postgres')
  self.sql("DO $$ DECLARE r text;BEGIN FOR r IN SELECT rolname FROM pg_roles WHERE rolname ~ '^tenant_[a-f0-9]{32}$' LOOP EXECUTE format('GRANT CONNECT ON DATABASE postgres TO %I',r);END LOOP;END $$;")
 def pristine(self,db,profile=None):
  if profile:
   names=self.sql("SELECT name FROM ir_module_module WHERE state='installed' AND name LIKE 'uno360x_%' ORDER BY name",db).splitlines()
   if names!=custom_addons(profile,self.a.root):raise RuntimeError('Reserve module mismatch')
  counts=self.sql("SELECT count(*) FROM uno360x_tenant_identity; SELECT count(*) FROM res_users WHERE coalesce(password,'')<>'' OR uno360x_account_id IS NOT NULL; SELECT count(*) FROM ir_mail_server; SELECT count(*) FROM ir_cron WHERE active; SELECT count(*) FROM account_move; SELECT count(*) FROM sale_order; SELECT count(*) FROM purchase_order; SELECT count(*) FROM pos_order;",db)
  if counts!='\n'.join(['0']*8):raise RuntimeError('Reserve is not pristine')
  self.sql("DO $$ DECLARE n bigint;t text;BEGIN FOREACH t IN ARRAY ARRAY['account_analytic_line','hr_contract','hr_leave','hr_expense','hr_expense_sheet','stock_picking','stock_move'] LOOP IF to_regclass('public.'||t) IS NOT NULL THEN EXECUTE format('SELECT count(*) FROM %I',t) INTO n;IF n<>0 THEN RAISE EXCEPTION 'Reserve contains business rows';END IF;END IF;END LOOP;END $$;",db)
  self.sql("DO $$ DECLARE n bigint;BEGIN IF to_regclass('public.hr_employee') IS NOT NULL THEN SELECT count(*) INTO n FROM hr_employee WHERE active OR id NOT IN (SELECT res_id FROM ir_model_data WHERE model='hr.employee' AND module='hr' AND name='employee_admin');IF n<>0 THEN RAISE EXCEPTION 'Reserve contains employee records';END IF;END IF;END $$;",db)
 def seed(self,profile):
  cache=verified_cache(profile,self.a.images)
  if cache is None:raise RuntimeError('Build the verified pristine template before replenishing')
  suffix=profile['fingerprint'][:24];db='uno_tpl_'+suffix;owner='uno_seed_'+suffix
  exists=self.sql('SELECT count(*) FROM pg_database WHERE datname='+literal(db))=='1'
  if exists and self.sql('SELECT datallowconn FROM pg_database WHERE datname='+literal(db))=='f':return db,owner,cache
  if not exists:
   self.sql('CREATE ROLE '+ident(owner)+' NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;\nCREATE DATABASE '+ident(db)+' OWNER '+ident(owner)+' TEMPLATE template0;')
  if self.sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'",db)=='0':
   with (cache/'database.dump').open('rb') as f:
    p=subprocess.run(['podman','exec','-i',SERVER,'pg_restore','-U','postgres','-d',db,'--role',owner,'--no-owner','--no-acl','--single-transaction','--exit-on-error'],stdin=f,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=240)
   if p.returncode:(BASE/'seed-error.log').write_bytes(p.stderr);raise RuntimeError('Pristine seed restore failed')
  self.pristine(db,profile)
  self.sql('ALTER SCHEMA public OWNER TO '+ident(owner),db)
  self.sql('ALTER DATABASE '+ident(db)+' OWNER TO postgres; ALTER DATABASE '+ident(db)+' ALLOW_CONNECTIONS false;')
  return db,owner,cache
 def create_slot(self,modules,profile):
  if shutil.disk_usage(BASE).free<10*1024**3:raise RuntimeError('Keep at least 10 GiB free before preparing reserves')
  seed,seed_owner,cache=self.seed(profile);slot=self.store.start_slot(profile,modules);role='tenant_'+slot
  folder=BASE/'slots'/slot;folder.mkdir(mode=0o700,parents=True);password=self.a.protected(folder/'database-password',secrets.token_hex(32)).read_text();volume='uno360x-reserve-'+slot+'-files'
  try:
   self.sql('CREATE ROLE '+ident(role)+' LOGIN PASSWORD '+literal(password)+' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8;\nCREATE DATABASE '+ident(role)+' OWNER '+ident(role)+' TEMPLATE '+ident(seed)+';')
   global_owned=self.sql('SELECT (SELECT count(*) FROM pg_database WHERE datdba=(SELECT oid FROM pg_roles WHERE rolname='+literal(seed_owner)+'))+(SELECT count(*) FROM pg_tablespace WHERE spcowner=(SELECT oid FROM pg_roles WHERE rolname='+literal(seed_owner)+'));')
   if global_owned!='0':raise RuntimeError('Template owner must not own global objects')
   self.sql('REASSIGN OWNED BY '+ident(seed_owner)+' TO '+ident(role)+'; REVOKE ALL ON SCHEMA public FROM PUBLIC;',role)
   self.sql('REVOKE ALL ON DATABASE '+ident(role)+' FROM PUBLIC; GRANT CONNECT,TEMPORARY ON DATABASE '+ident(role)+' TO '+ident(role)+';')
   self.pristine(role,profile)
   self.a.run('volume','create',*self.labels({'uno360x.slot':slot,'uno360x.product':profile['fingerprint']}),volume)
   self.verify_volume(volume,{'uno360x.slot':slot,'uno360x.product':profile['fingerprint']})
   code="""import pathlib,tarfile,pwd,os
root=pathlib.Path('/var/lib/odoo/filestore')/%r;root.mkdir(parents=True,exist_ok=True)
with tarfile.open('/seed.tar') as archive:
 for m in archive.getmembers():
  p=pathlib.PurePosixPath(m.name);assert not p.is_absolute() and '..' not in p.parts and (m.isfile() or m.isdir())
 archive.extractall(root)
u=pwd.getpwnam('odoo')
for p in [pathlib.Path('/var/lib/odoo'),root.parent,root,*root.rglob('*')]:os.chown(p,u.pw_uid,u.pw_gid)
"""%role
   self.a.run('run','--rm','--network','none','--cpus','0.25','--memory','96m','--user','0','--entrypoint','python3','-v',volume+':/var/lib/odoo','-v',str(cache/'files.tar')+':/seed.tar:ro',self.a.images['odoo:18.0'],'-c',code)
   self.store.mark_ready(slot);return slot
  except Exception:
   with self.store.db:self.store.db.execute("UPDATE reserve_slots SET state='failed' WHERE id=? AND state='building'",(slot,))
   raise
 def claim(self,s):
  binding=self.store.claim(s['tenant_id'],s['installation']['fingerprint'])
  if binding:return binding
  modules=[k for k,v in {'jenifer_ai':'uno360x_jenifer_core','payroll_hr':'uno360x_payroll_hr','projects_services':'uno360x_projects_services'}.items() if v in s['installation']['addons']]
  for _ in range(480):
   try:
    with self.builder_lock(wait=False):
     binding=self.store.claim(s['tenant_id'],s['installation']['fingerprint'])
     if not binding:self.create_slot(modules,s['installation']);binding=self.store.claim(s['tenant_id'],s['installation']['fingerprint'])
     if binding:return binding
   except BlockingIOError:pass
   binding=self.store.claim(s['tenant_id'],s['installation']['fingerprint'])
   if binding:return binding
   time.sleep(0.25)
  raise RuntimeError('Reserve assignment waits for replenishment')
 def attach(self,network):
  info=self.verify_server()
  if network not in info['NetworkSettings']['Networks']:self.a.run('network','connect','--alias',SERVER,network,SERVER)
  self.verify_server()
 def replenish(self):
  with self.builder_lock():
   self.ensure();all_profiles=profiles();self.store.retire_old_ready({p['fingerprint'] for _,p,_ in all_profiles})
   while self.store.refill_needed():
    if int(next(l.split()[1] for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024<2*1024**3:raise RuntimeError('Replenishment waits for host memory headroom')
    counts={r['fingerprint']:r['n'] for r in self.store.db.execute("SELECT fingerprint,count(*) n FROM reserve_slots WHERE state='ready' GROUP BY fingerprint")}
    modules,profile,weight=max(all_profiles,key=lambda item:item[2]-counts.get(item[1]['fingerprint'],0))
    slot=self.create_slot(modules,profile);print(json.dumps({'reserve_prepared':slot,'ready':self.store.counts().get('ready',0),'target':TARGET}),flush=True)
   print(json.dumps({'reserve_ready':self.store.counts().get('ready',0),'target':TARGET,'low_water':5}),flush=True)
   self.prune_retired()
 def prune_retired(self):
  for row in self.store.db.execute("SELECT * FROM reserve_slots WHERE state='retired' AND tenant_id IS NULL").fetchall():
   slot=row['id'];identifier(slot)
   if self.store.db.execute('SELECT 1 FROM reserve_bindings WHERE slot_id=?',(slot,)).fetchone():raise RuntimeError('Assigned reserve must never be pruned')
   role='tenant_'+slot;volume='uno360x-reserve-'+slot+'-files'
   if self.sql('SELECT count(*) FROM pg_database WHERE datname='+literal(role))=='1':
    self.pristine(role)
    self.sql('DROP DATABASE '+ident(role)+' WITH (FORCE); REVOKE CONNECT ON DATABASE postgres FROM '+ident(role)+'; DROP ROLE '+ident(role)+';')
   if self.a.exists('volume',volume):self.verify_volume(volume,{'uno360x.slot':slot,'uno360x.product':row['fingerprint']});self.a.run('volume','rm',volume)
