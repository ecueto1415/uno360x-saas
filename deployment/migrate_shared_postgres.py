"""Reviewed per-tenant PostgreSQL migration with a retained legacy rollback.

Never touches native Odoo/PostgreSQL. Pause the SaaS preparation worker before
--apply. The gateway must run this release so maintenance blocks tenant writes.
"""
import argparse,datetime,hashlib,json,pathlib,shutil,sqlite3,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.pilot_adapter import PilotAdapter
from deployment.reserve_pool import Pool,SERVER,ident,literal,BASE
CONTROL=pathlib.Path('/var/lib/uno360x-saas/control/control.sqlite3')

def digest(adapter,s):
 sql="SELECT json_agg(x ORDER BY x.id) FROM (SELECT id,login,password,uno360x_account_id,active FROM res_users) x; SELECT json_agg(x ORDER BY x.uid,x.gid) FROM res_groups_users_rel x; SELECT json_agg(x ORDER BY x.id) FROM res_company x; SELECT count(*) FROM account_move; SELECT count(*) FROM sale_order; SELECT count(*) FROM purchase_order; SELECT count(*) FROM pos_order;"
 return hashlib.sha256(adapter.sql(s,sql).encode()).hexdigest()

def migrate(tenant,apply=False):
 db=sqlite3.connect(CONTROL);db.row_factory=sqlite3.Row
 row=db.execute("SELECT p.*,t.modules FROM preparation_jobs p JOIN tenants t ON t.id=p.tenant_id WHERE p.tenant_id=? AND p.status='ready_local'",(tenant,)).fetchone()
 if not row:raise RuntimeError('Ready SaaS tenant required')
 s=json.loads(row['snapshot']);old=PilotAdapter();old.shared_pg_enabled=False;new=PilotAdapter();new.shared_pg_enabled=True
 if new.shared_binding(s):print(json.dumps({'tenant':tenant,'status':'already_shared'}));return
 n=old.names(s);old.check_container(n['database'],s);old.check_container(n['app'],s)
 if not apply:print(json.dumps({'tenant':tenant,'action':'migrate_database_only','credentials':'preserve','native_odoo_touched':False}));return
 backup=BASE/'migrations'/tenant/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup.mkdir(mode=0o700,parents=True)
 db.execute('CREATE TABLE IF NOT EXISTS tenant_maintenance(tenant_id TEXT PRIMARY KEY,reason TEXT NOT NULL,started REAL NOT NULL)')
 with old.lock(tenant),Pool(new) as pool,pool.builder_lock():
  pool.ensure()
  if pool.sql('SELECT count(*) FROM pg_database WHERE datname='+literal(n['role']))!='0':raise RuntimeError('Target database already exists without a binding; review before retry')
  prior=dict(db.execute('SELECT started,expires FROM trial_workspaces WHERE tenant_id=?',(tenant,)).fetchone())
  control_backup=sqlite3.connect(backup/'control-before.sqlite3');db.backup(control_backup);control_backup.close()
  shutil.copytree(n['directory'],backup/'tenant-state')
  original_config=(n['directory']/'odoo.conf').read_text();password=(n['directory']/'database-password').read_text();created=False;bound=False
  (backup/'migration.json').write_text(json.dumps({'tenant':tenant,'source':str(ROOT),'legacy_database':n['database'],'role':n['role'],'files_volume':n['files'],'trial':prior,'phase':'preparing'}))
  with db:db.execute('INSERT OR REPLACE INTO tenant_maintenance VALUES (?,?,?)',(tenant,'Actualizando el almacenamiento de tu empresa',time.time()))
  try:
   old.run('stop',n['app']);before=digest(old,s)
   with (backup/'database.dump').open('wb') as out:
    result=subprocess.run(['podman','exec',n['database'],'pg_dump','-Fc','--no-owner','--no-acl','-U','postgres','-d',n['role']],stdout=out,stderr=subprocess.PIPE,timeout=240)
   if result.returncode:raise RuntimeError('Source database backup failed')
   old.volume(n['files'],s);old.run('volume','export','--output',str(backup/'files.tar'),n['files'])
   pool.sql('CREATE ROLE '+ident(n['role'])+' LOGIN PASSWORD '+literal(password)+' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8;\nCREATE DATABASE '+ident(n['role'])+' OWNER '+ident(n['role'])+' TEMPLATE template0;');created=True
   pool.sql('REVOKE ALL ON DATABASE '+ident(n['role'])+' FROM PUBLIC; GRANT CONNECT,TEMPORARY ON DATABASE '+ident(n['role'])+' TO '+ident(n['role'])+'; GRANT CONNECT ON DATABASE postgres TO '+ident(n['role'])+';')
   with (backup/'database.dump').open('rb') as incoming:
    result=subprocess.run(['podman','exec','-i',SERVER,'pg_restore','-U','postgres','-d',n['role'],'--role',n['role'],'--no-owner','--no-acl','--single-transaction','--exit-on-error'],stdin=incoming,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
   if result.returncode:(backup/'restore-error.log').write_bytes(result.stderr);raise RuntimeError('Target database restore failed')
   pool.attach(n['network']);pool.store.bind_import(tenant,n['files']);bound=True
   if digest(new,s)!=before:raise RuntimeError('User, company or business-row verification failed')
   text=original_config.replace('db_host = '+n['database'],'db_host = '+SERVER).replace('db_maxconn = 12','db_maxconn = 8')
   if text==original_config or 'db_host = '+SERVER not in text:raise RuntimeError('Unexpected source configuration')
   (n['directory']/'odoo.conf').write_text(text)
   new.validation(s);new.access_backend(s)
   assert dict(db.execute('SELECT started,expires FROM trial_workspaces WHERE tenant_id=?',(tenant,)).fetchone())==prior
   assert (n['directory']/'database-password').read_text()==password
   old.run('stop',n['database'])
   record={'tenant':tenant,'source':str(ROOT),'backup':str(backup),'phase':'shared','credentials_unchanged':True,'users_groups_company_and_business_counts_verified':True,'trial_dates_unchanged':True,'legacy_database_retained_stopped':True,'completed':time.time()}
   (backup/'migration.json').write_text(json.dumps(record));(n['directory']/'shared-migration.json').write_text(json.dumps(record))
   with db:db.execute('DELETE FROM tenant_maintenance WHERE tenant_id=?',(tenant,))
   print(json.dumps(record),flush=True)
  except Exception:
   if new.exists('container',n['app']) and new.inspect(n['app'])['State']['Running']:new.run('stop',n['app'])
   if bound:
    with pool.store.db:pool.store.db.execute('DELETE FROM reserve_bindings WHERE tenant_id=? AND legacy=1',(tenant,))
   (n['directory']/'odoo.conf').write_text(original_config)
   old.run('start',n['database']);old.validation(s)
   if created:
    pool.sql('DROP DATABASE '+ident(n['role'])+' WITH (FORCE); REVOKE CONNECT ON DATABASE postgres FROM '+ident(n['role'])+'; DROP ROLE '+ident(n['role'])+';')
   with db:db.execute('DELETE FROM tenant_maintenance WHERE tenant_id=?',(tenant,))
   (backup/'rollback.json').write_text(json.dumps({'tenant':tenant,'legacy_restored':True,'time':time.time()}))
   raise

def main():
 p=argparse.ArgumentParser();p.add_argument('tenant');p.add_argument('--apply',action='store_true');a=p.parse_args()
 if a.apply and subprocess.run(['systemctl','is-active','--quiet','uno360x-saas-worker']).returncode==0:raise RuntimeError('Pause preparation worker before database migration')
 migrate(a.tenant,a.apply)
if __name__=='__main__':main()
