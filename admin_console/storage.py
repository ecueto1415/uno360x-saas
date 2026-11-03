"""Persistent storage assignments. Never allocates disks or stops tenant services."""
import re,time
GB=1_000_000_000
RESERVE=10*GB
class QuotaError(ValueError):pass
class Conflict(QuotaError):pass

def schema(db):
 db.executescript('CREATE TABLE IF NOT EXISTS storage_assignments(tenant TEXT PRIMARY KEY,quota_bytes INTEGER NOT NULL,updated REAL NOT NULL); CREATE TABLE IF NOT EXISTS storage_changes(request_id TEXT PRIMARY KEY,tenant TEXT NOT NULL,previous_bytes INTEGER NOT NULL,quota_bytes INTEGER NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,occurred REAL NOT NULL);')

def overlay(db,snapshot):
 schema(db);assigned=dict(db.execute('SELECT tenant,quota_bytes FROM storage_assignments'))
 for c in snapshot['clients']:
  c['quota_bytes']=assigned.get(c['id'],c.get('quota_bytes',5*GB));c['quota_enforced']=False
  c['quota_history']=[dict(row) for row in db.execute('SELECT previous_bytes,quota_bytes,actor,reason,occurred FROM storage_changes WHERE tenant=? ORDER BY occurred DESC LIMIT 10',(c['id'],))]
 return snapshot

def increase(db,snapshot,data,actor,now=None):
 now=time.time() if now is None else now;schema(db)
 if now-snapshot.get('generated',0)>180:raise QuotaError('Actualiza las mediciones antes de ampliar el espacio.')
 tenant=data.get('tenant_id');gb=data.get('quota_gb');expected=data.get('expected_bytes');request=data.get('request_id');reason=data.get('reason','')
 if not isinstance(tenant,str) or not re.fullmatch('[a-f0-9]{32}',tenant):raise QuotaError('Empresa inválida.')
 if type(gb) is not int or not 5<=gb<=1000:raise QuotaError('Introduce una capacidad entera entre 5 y 1000 GB.')
 if type(expected) is not int or expected<5*GB:raise QuotaError('Capacidad actual inválida.')
 if not isinstance(request,str) or not re.fullmatch('[a-f0-9]{32}',request):raise QuotaError('Solicitud inválida.')
 if not isinstance(reason,str) or not 3<=len(reason.strip())<=200:raise QuotaError('Escribe un motivo de 3 a 200 caracteres.')
 reason=reason.strip();target=gb*GB
 with db:
  db.execute('BEGIN IMMEDIATE')
  # Read assignments inside the same transaction to serialize simultaneous increases.
  assigned=dict(db.execute('SELECT tenant,quota_bytes FROM storage_assignments'))
  client=next((c for c in snapshot['clients'] if c['id']==tenant),None)
  if not client:raise QuotaError('Empresa SaaS no disponible.')
  prior=db.execute('SELECT * FROM storage_changes WHERE request_id=?',(request,)).fetchone()
  if prior:
   if prior['tenant']!=tenant or prior['quota_bytes']!=target or prior['previous_bytes']!=expected or prior['reason']!=reason:raise Conflict('La solicitud ya se utilizó para otro cambio.')
   return {'tenant_id':tenant,'quota_bytes':assigned.get(tenant,prior['quota_bytes']),'duplicate':True}
  current=assigned.get(tenant,client.get('quota_bytes',5*GB))
  if expected!=current:raise Conflict('La capacidad cambió. Actualiza la ficha y vuelve a intentarlo.')
  if target<=current:raise QuotaError('La nueva capacidad debe ser mayor que la actual.')
  used=client.get('storage_bytes')
  if used is not None and target<used:raise QuotaError('La capacidad no puede ser inferior al consumo actual.')
  free=snapshot.get('server',{}).get('disk_available')
  if not isinstance(free,(float,int)):raise QuotaError('La capacidad física del servidor no está disponible.')
  committed=sum(max(0,assigned.get(c['id'],c.get('quota_bytes',5*GB))-(c.get('storage_bytes') or 0)) for c in snapshot['clients'])
  if target-current>free-RESERVE-committed:raise QuotaError('No hay margen físico suficiente. Amplía primero el disco del servidor.')
  db.execute('INSERT OR REPLACE INTO storage_assignments VALUES (?,?,?)',(tenant,target,now))
  db.execute('INSERT INTO storage_changes VALUES (?,?,?,?,?,?,?)',(request,tenant,current,target,actor,reason,now))
 return {'tenant_id':tenant,'quota_bytes':target,'duplicate':False}
