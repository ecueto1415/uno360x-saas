"""Optional shared PostgreSQL path; legacy per-company servers remain valid."""
import json,pathlib,re,secrets,sqlite3,uuid

class SharedDatabaseMixin:
 def shared_binding(self,s):
  if not getattr(self,'shared_pg_enabled',False):return None
  p=pathlib.Path('/var/lib/uno360x-saas/shared-postgres/inventory.sqlite3')
  if not p.exists():return None
  with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
   db.row_factory=sqlite3.Row;row=db.execute('SELECT * FROM reserve_bindings WHERE tenant_id=?',(s['tenant_id'],)).fetchone()
  if not row:return None
  data=dict(row)
  if not re.fullmatch('tenant_[a-f0-9]{32}',data['database_name']):raise RuntimeError('Invalid shared tenant database')
  if data['slot_id'] and not re.fullmatch('[a-f0-9]{32}',data['slot_id']):raise RuntimeError('Invalid shared slot')
  return data
 def names(self,s):
  n=super().names(s);binding=self.shared_binding(s)
  if binding:
   from deployment.reserve_pool import SERVER,PGVOLUME
   n.update(database=SERVER,pgvolume=PGVOLUME,role=binding['database_name'],files=binding['files_volume'])
  return n
 def check_container(self,name,s,info=None):
  from deployment.reserve_pool import SERVER,Pool
  if getattr(self,'shared_pg_enabled',False) and name==SERVER:
   with Pool(self) as pool:return pool.verify_server(info)
  return super().check_container(name,s,info)
 def volume(self,name,s):
  from deployment.reserve_pool import PGVOLUME,Pool
  binding=self.shared_binding(s)
  if binding and (name==PGVOLUME or (binding['slot_id'] and name==binding['files_volume'])):
   with Pool(self) as pool:
    row=pool.store.db.execute('SELECT fingerprint FROM reserve_slots WHERE id=?',(binding['slot_id'],)).fetchone() if name!=PGVOLUME else None
    return pool.verify_volume(name,{'uno360x.slot':binding['slot_id'],'uno360x.product':row['fingerprint']} if name!=PGVOLUME else None)
  return super().volume(name,s)
 def database(self,s):
  if getattr(self,'shared_pg_enabled',False):
   from deployment.reserve_pool import Pool,BASE
   legacy=super().names(s)
   binding=self.shared_binding(s)
   if not binding and not self.exists('container',legacy['database']):
    with Pool(self) as pool:
     pool.ensure();binding=pool.claim(s)
   if binding:
    with Pool(self) as pool:
     pool.attach(legacy['network'])
     if binding['slot_id']:
      password=(BASE/'slots'/binding['slot_id']/'database-password').read_text()
      self.protected(legacy['directory']/'database-password',password)
    result=super().database(s)
    config=legacy['directory']/'odoo.conf';text=config.read_text()
    if 'db_maxconn = 12' in text:config.write_text(text.replace('db_maxconn = 12','db_maxconn = 8'))
    return result
  return super().database(s)
 def installation(self,s):
  binding=self.shared_binding(s);n=self.names(s)
  if binding and binding['slot_id'] and not (n['directory']/'installed.json').exists():
   from deployment.reserve_pool import Pool
   with Pool(self) as pool:
    row=pool.store.db.execute('SELECT * FROM reserve_slots WHERE id=?',(binding['slot_id'],)).fetchone()
    if row['state']!='assigned' or row['tenant_id']!=s['tenant_id'] or row['fingerprint']!=s['installation']['fingerprint']:raise RuntimeError('Reserve assignment does not match tenant')
    pool.pristine(n['role'],s['installation'])
    pool.sql("INSERT INTO ir_config_parameter(key,value,create_uid,write_uid) VALUES ('database.uuid','%s',1,1),('database.secret','%s',1,1) ON CONFLICT(key) DO UPDATE SET value=excluded.value;"%(uuid.uuid4(),secrets.token_hex(32)),n['role'])
   p=n['directory']/'installed.json';p.write_text(json.dumps({'fingerprint':s['installation']['fingerprint'],'template':'shared-pg-reserve-'+binding['slot_id']}));p.chmod(0o600);return
  return super().installation(s)
 def stop_shared_expired(self,s):
  if not self.shared_binding(s):return False
  with self.lock(s['tenant_id']):
   n=self.names(s)
   for name in (n['app'],n['prefix']+'-proxy'):
    if not self.exists('container',name):continue
    info=self.inspect(name)
    if not all(info['Config']['Labels'].get(k)==v for k,v in self.labels(s).items()):raise RuntimeError('Foreign expired shared instance')
    if info['State']['Running']:self.run('stop',name)
  return True
