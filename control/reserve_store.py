"""Atomic, single-use prepared-space inventory. Contains no customer data."""
import json,pathlib,re,sqlite3,time,uuid
TARGET=50
LOW_WATER=40
REFILL_BATCH=5

def identifier(value):
 if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('Invalid reserve identity')
 return value

class ReserveStore:
 def __init__(self,path):
  self.path=pathlib.Path(path);self.path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
  if self.path.is_symlink():raise RuntimeError('Unexpected inventory symlink')
  self.db=sqlite3.connect(self.path,timeout=30);self.db.row_factory=sqlite3.Row
  self.db.executescript("""CREATE TABLE IF NOT EXISTS reserve_slots(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,modules TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('building','ready','assigned','retired','failed')),tenant_id TEXT UNIQUE,created REAL NOT NULL,assigned REAL);
   CREATE TABLE IF NOT EXISTS reserve_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
   INSERT OR IGNORE INTO reserve_meta VALUES ('refill','1');
   CREATE TABLE IF NOT EXISTS reserve_bindings(tenant_id TEXT PRIMARY KEY,database_name TEXT UNIQUE NOT NULL,slot_id TEXT UNIQUE,files_volume TEXT,legacy INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
   """);self.path.chmod(0o600)
 def close(self):self.db.close()
 def counts(self):return {r['state']:r['n'] for r in self.db.execute('SELECT state,count(*) n FROM reserve_slots GROUP BY state')}
 def trigger(self):
  ready=self.db.execute("SELECT count(*) FROM reserve_slots WHERE state='ready'").fetchone()[0]
  if ready<=LOW_WATER:self.db.execute("UPDATE reserve_meta SET value='1' WHERE key='refill'")
  return ready
 def refill_needed(self):
  with self.db:
   self.db.execute('BEGIN IMMEDIATE');ready=self.trigger();active=self.db.execute("SELECT value FROM reserve_meta WHERE key='refill'").fetchone()[0]=='1'
   if ready>=TARGET:self.db.execute("UPDATE reserve_meta SET value='0' WHERE key='refill'");return False
   return active
 def start_slot(self,profile,modules,slot_id=None):
  slot_id=identifier(slot_id or uuid.uuid4().hex)
  with self.db:self.db.execute("INSERT INTO reserve_slots VALUES (?,?,?,'building',NULL,?,NULL)",(slot_id,profile['fingerprint'],json.dumps(sorted(modules)),time.time()))
  return slot_id
 def mark_ready(self,slot_id):
  with self.db:
   self.db.execute("UPDATE reserve_slots SET state='ready' WHERE id=? AND state='building'",(identifier(slot_id),));self.trigger()
 def binding(self,tenant):
  row=self.db.execute('SELECT * FROM reserve_bindings WHERE tenant_id=?',(identifier(tenant),)).fetchone();return dict(row) if row else None
 def claim(self,tenant,fingerprint):
  tenant=identifier(tenant)
  with self.db:
   self.db.execute('BEGIN IMMEDIATE');old=self.binding(tenant)
   if old:return old
   row=self.db.execute("SELECT * FROM reserve_slots WHERE state='ready' AND fingerprint=? ORDER BY created,id LIMIT 1",(fingerprint,)).fetchone()
   if not row:return None
   slot=row['id'];database='tenant_'+slot;files='uno360x-reserve-'+slot+'-files'
   self.db.execute("UPDATE reserve_slots SET state='assigned',tenant_id=?,assigned=? WHERE id=? AND state='ready'",(tenant,time.time(),slot))
   self.db.execute('INSERT INTO reserve_bindings VALUES (?,?,?,?,0,?)',(tenant,database,slot,files,time.time()));self.trigger()
   return self.binding(tenant)
 def bind_import(self,tenant,files_volume):
  tenant=identifier(tenant)
  with self.db:
   self.db.execute('BEGIN IMMEDIATE');old=self.binding(tenant)
   if old:return old
   self.db.execute('INSERT INTO reserve_bindings VALUES (?,?,NULL,?,1,?)',(tenant,'tenant_'+tenant,files_volume,time.time()))
   return self.binding(tenant)
 def retire_old_ready(self,fingerprints):
  with self.db:
   for row in self.db.execute("SELECT id,fingerprint FROM reserve_slots WHERE state='ready'").fetchall():
    if row['fingerprint'] not in fingerprints:self.db.execute("UPDATE reserve_slots SET state='retired' WHERE id=?",(row['id'],))
   self.trigger()
