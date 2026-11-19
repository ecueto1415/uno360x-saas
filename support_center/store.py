"""No direct business DB access. User-scoped diagnostic snapshots come from the gateway."""
import contextlib
import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
from pathlib import Path

STATE = Path('/var/lib/uno360x-support/support.sqlite3')
TOPICS = ('access', 'billing', 'inventory', 'sales', 'payroll', 'performance', 'design', 'suggestion', 'other')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS cases (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, account TEXT NOT NULL,
 title TEXT NOT NULL, topic TEXT NOT NULL DEFAULT 'other', status TEXT NOT NULL DEFAULT 'open',
 human INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS case_scope ON cases(tenant,account,updated);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
 role TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL,
 request_id TEXT, state TEXT NOT NULL DEFAULT 'done', lease REAL, attempts INTEGER NOT NULL DEFAULT 0,
 UNIQUE(case_id,request_id));
CREATE INDEX IF NOT EXISTS pending ON messages(state,created);
CREATE TABLE IF NOT EXISTS message_context (
 message_id INTEGER PRIMARY KEY REFERENCES messages(id), tenant TEXT NOT NULL,
 account TEXT NOT NULL, captured REAL NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metrics (
 tenant TEXT NOT NULL, hour INTEGER NOT NULL, area TEXT NOT NULL,
 requests INTEGER NOT NULL, slow INTEGER NOT NULL, errors INTEGER NOT NULL,
 total_ms REAL NOT NULL, max_ms REAL NOT NULL, PRIMARY KEY(tenant,hour,area));
CREATE TABLE IF NOT EXISTS limits (scope TEXT NOT NULL, bucket INTEGER NOT NULL, n INTEGER NOT NULL,
 PRIMARY KEY(scope,bucket));
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, actor TEXT NOT NULL, case_id TEXT,
 event TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reports (day TEXT PRIMARY KEY, created REAL NOT NULL, body TEXT NOT NULL);
'''

class Invalid(ValueError):
    pass

class Limited(Invalid):
    pass

def submission(tenant, account, data):
    if not isinstance(data,dict) or set(data)-{'case_id','body','request_id','human'}:
        raise Invalid('Solicitud inválida.')
    body,key,case_id,human=data.get('body',''),data.get('request_id',''),data.get('case_id'),data.get('human',False)
    if (not isinstance(body,str) or not 1<=len(body.strip())<=3000 or not isinstance(key,str) or
        not re.fullmatch('[a-f0-9-]{32,36}',key) or type(human) is not bool or
        case_id is not None and (not isinstance(case_id,str) or not re.fullmatch('[a-f0-9]{32}',case_id))):
        raise Invalid('Escribe un mensaje de hasta 3,000 caracteres.')
    return body.strip(),key,case_id or hashlib.sha256((tenant+'\0'+account+'\0'+key).encode()).hexdigest()[:32],human

class Store:
    def __init__(self, path=STATE, clock=time.time, timeout=3):
        self.clock = clock
        self.db = sqlite3.connect(path, timeout=timeout)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=%d' % int(timeout*1000))

    def initialize(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def allow(self, scope, maximum=12):
        bucket = int(self.clock() // 60)
        row = self.db.execute('SELECT n FROM limits WHERE scope=? AND bucket=?', (scope,bucket)).fetchone()
        if row and row['n'] >= maximum:
            raise Limited('Hay varios mensajes seguidos. Espera un minuto e inténtalo otra vez.')
        self.db.execute('INSERT INTO limits VALUES (?,?,1) ON CONFLICT(scope,bucket) DO UPDATE SET n=n+1', (scope,bucket))

    def case(self, tenant, account, case_id):
        if not isinstance(case_id,str) or not re.fullmatch('[a-f0-9]{32}',case_id):
            raise Invalid('Conversación no disponible.')
        row = self.db.execute('SELECT * FROM cases WHERE id=? AND tenant=? AND account=?', (case_id,tenant,account)).fetchone()
        if not row:
            raise Invalid('Conversación no disponible.')
        return dict(row)

    def messages(self, case_id):
        return [dict(r) for r in self.db.execute('SELECT id,role,body,created,state FROM messages WHERE case_id=? ORDER BY id DESC LIMIT 80', (case_id,))][::-1]

    def listing(self, tenant, account, case_id=None):
        cases = [dict(r) for r in self.db.execute('SELECT * FROM cases WHERE tenant=? AND account=? ORDER BY updated DESC LIMIT 30',(tenant,account))]
        selected = self.case(tenant,account,case_id) if case_id else (cases[0] if cases else None)
        return {'cases':cases,'selected':selected,'messages':self.messages(selected['id']) if selected else []}

    def send(self, tenant, account, data, *, context=None):
        body,key,case_id,human=submission(tenant,account,data)
        now = self.clock()
        with self.transaction():
            existing = self.db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if existing:
                self.case(tenant,account,case_id)
            previous = self.db.execute('SELECT body FROM messages WHERE case_id=? AND request_id=?',(case_id,key)).fetchone()
            if previous:
                if previous['body'] != body:
                    raise Invalid('El identificador del mensaje ya fue utilizado.')
                return case_id
            self.allow('message:'+tenant+':'+account)
            self.allow('tenant:'+tenant,60)
            if not existing:
                self.db.execute('INSERT INTO cases (id,tenant,account,title,human,created,updated) VALUES (?,?,?,?,?,?,?)',(case_id,tenant,account,body[:100],int(human),now,now))
            else:
                if self.db.execute("SELECT 1 FROM messages WHERE case_id=? AND state IN ('pending','working')",(case_id,)).fetchone():
                    raise Invalid('Jenifer está preparando la respuesta anterior. Espera un momento.')
                self.db.execute("UPDATE cases SET human=MAX(human,?),status='open',updated=? WHERE id=?",(int(human),now,case_id))
            row = self.case(tenant,account,case_id)
            inserted=self.db.execute('INSERT INTO messages (case_id,role,body,created,request_id,state) VALUES (?,?,?,?,?,?)',
                            (case_id,'user',body,now,key,'done' if row['human'] else 'pending'))
            if context is not None:
                encoded=json.dumps(context,ensure_ascii=False)
                if len(encoded)>60000:
                    raise Invalid('El diagnóstico es demasiado extenso.')
                self.db.execute('INSERT INTO message_context VALUES (?,?,?,?,?)',
                    (inserted.lastrowid,tenant,account,now,encoded))
        return case_id

    def needs_context(self, tenant, account, data):
        body,key,case_id,human=submission(tenant,account,data)
        row=self.db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if row:
            self.case(tenant,account,case_id)
            previous=self.db.execute('SELECT body FROM messages WHERE case_id=? AND request_id=?',(case_id,key)).fetchone()
            if previous:
                if previous['body']!=body:raise Invalid('El identificador del mensaje ya fue utilizado.')
                return False
            if self.db.execute("SELECT 1 FROM messages WHERE case_id=? AND state IN ('pending','working')",(case_id,)).fetchone():
                raise Invalid('Jenifer está preparando la respuesta anterior. Espera un momento.')
        for scope,maximum in [('message:'+tenant+':'+account,12),('tenant:'+tenant,60)]:
            limit=self.db.execute('SELECT n FROM limits WHERE scope=? AND bucket=?',(scope,int(self.clock()//60))).fetchone()
            if limit and limit['n']>=maximum:raise Limited('Hay varios mensajes seguidos. Espera un minuto e inténtalo otra vez.')
        return not human and not (row and row['human'])

    def job_context(self, job):
        row=self.db.execute('''SELECT x.body,x.captured FROM message_context x
            JOIN messages m ON m.id=x.message_id JOIN cases c ON c.id=m.case_id
            WHERE m.id=? AND m.case_id=? AND x.tenant=c.tenant AND x.account=c.account''',
            (job['id'],job['case_id'])).fetchone()
        if not row or self.clock()-row['captured']>600:
            return {'verified':False,'reason':'No hay un diagnóstico reciente. No afirmar haber comprobado la configuración.'}
        return json.loads(row['body'])

    def handoff(self, tenant, account, case_id):
        with self.transaction():
            self.case(tenant,account,case_id)
            self.db.execute("UPDATE cases SET human=1,status='open',updated=? WHERE id=?",(self.clock(),case_id))
            self.db.execute("UPDATE messages SET state='done' WHERE case_id=? AND state IN ('pending','working')",(case_id,))

    def claim(self):
        now = self.clock()
        with self.transaction():
            # A crashed/ambiguous call goes to a human; never blindly resubmit to the provider.
            stale = self.db.execute("SELECT DISTINCT case_id FROM messages WHERE state='working' AND lease<?",(now-180,)).fetchall()
            for row in stale:
                self.db.execute('UPDATE cases SET human=1 WHERE id=?',(row['case_id'],))
            self.db.execute("UPDATE messages SET state='review' WHERE state='working' AND lease<?",(now-180,))
            row = self.db.execute("SELECT m.* FROM messages m JOIN cases c ON c.id=m.case_id WHERE m.state='pending' AND c.human=0 ORDER BY m.id LIMIT 1").fetchone()
            if not row:
                return None
            self.db.execute("UPDATE messages SET state='working',lease=?,attempts=attempts+1 WHERE id=?",(now,row['id']))
            return dict(row)

    def finish(self, job, reply, topic='other', failed=False):
        if topic not in TOPICS or not isinstance(reply,str) or not 1 <= len(reply.strip()) <= 6000:
            raise Invalid('Respuesta no válida.')
        with self.transaction():
            row = self.db.execute('SELECT state FROM messages WHERE id=? AND case_id=?',(job['id'],job['case_id'])).fetchone()
            if not row or row['state'] != 'working':
                return
            human = self.db.execute('SELECT human FROM cases WHERE id=?',(job['case_id'],)).fetchone()['human']
            self.db.execute('UPDATE messages SET state=? WHERE id=?',('review' if failed else 'done',job['id']))
            if not human:
                self.db.execute("INSERT INTO messages (case_id,role,body,created,request_id) VALUES (?,'assistant',?,?,?)",(job['case_id'],reply.strip(),self.clock(),'reply:'+str(job['id'])))
            self.db.execute('UPDATE cases SET topic=?,human=MAX(human,?),updated=? WHERE id=?',(topic,int(failed),self.clock(),job['case_id']))

    def record_metric(self, tenant, path, status, milliseconds):
        area = area_for(path)
        if area is None or not math.isfinite(milliseconds) or not 0 <= milliseconds <= 120000:
            return
        hour = int(self.clock()//3600)*3600
        with self.db:
            self.db.execute('''INSERT INTO metrics VALUES (?,?,?,1,?,?,?,?)
             ON CONFLICT(tenant,hour,area) DO UPDATE SET requests=requests+1,slow=slow+excluded.slow,
             errors=errors+excluded.errors,total_ms=total_ms+excluded.total_ms,max_ms=MAX(max_ms,excluded.max_ms)''',
             (tenant,hour,area,int(milliseconds>=2500),int(status>=500),milliseconds,milliseconds))

    def overview(self):
        return {'cases':[dict(r) for r in self.db.execute('SELECT * FROM cases ORDER BY updated DESC LIMIT 150')],
                'reports':[dict(r) for r in self.db.execute('SELECT day,created,body FROM reports ORDER BY day DESC LIMIT 14')]}

    def admin_case(self, case_id):
        if not isinstance(case_id,str) or not re.fullmatch('[a-f0-9]{32}',case_id):
            raise Invalid('Conversación no disponible.')
        row=self.db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if not row:
            raise Invalid('Conversación no disponible.')
        return {'selected':dict(row),'messages':self.messages(case_id)}

    def admin_action(self, actor, data):
        if set(data) != {'case_id','action','body','request_id'} or data['action'] not in ('reply','resolve'):
            raise Invalid('Solicitud inválida.')
        case_id,body,key=data['case_id'],data['body'],data['request_id']
        if (not isinstance(case_id,str) or not isinstance(body,str) or len(body)>3000 or
            not isinstance(key,str) or not re.fullmatch('[a-f0-9-]{32,36}',key) or
            data['action']=='reply' and not body.strip()):
            raise Invalid('Escribe una respuesta de hasta 3,000 caracteres.')
        with self.transaction():
            self.admin_case(case_id)
            if self.db.execute('SELECT 1 FROM messages WHERE case_id=? AND request_id=?',(case_id,'admin:'+key)).fetchone():
                return
            self.db.execute("UPDATE cases SET human=1,status=?,updated=? WHERE id=?",('resolved' if data['action']=='resolve' else 'open',self.clock(),case_id))
            self.db.execute("UPDATE messages SET state='done' WHERE case_id=? AND state='pending'",(case_id,))
            self.db.execute("INSERT INTO messages (case_id,role,body,created,request_id) VALUES (?,'team',?,?,?)",(case_id,body.strip() or 'El equipo marcó esta conversación como resuelta.',self.clock(),'admin:'+key))
            self.db.execute('INSERT INTO audit(actor,case_id,event,created) VALUES (?,?,?,?)',(actor,case_id,data['action'],self.clock()))

    def daily_report(self, day):
        now=self.clock()
        metrics=[dict(r) for r in self.db.execute('''SELECT area,SUM(requests) AS requests,SUM(slow) AS slow,
          SUM(errors) AS errors,SUM(total_ms)/SUM(requests) AS average_ms,MAX(max_ms) AS max_ms,
          COUNT(DISTINCT tenant) AS companies FROM metrics WHERE hour>=? GROUP BY area''',(int((now-86400)//3600)*3600,))]
        topics=[dict(r) for r in self.db.execute('''SELECT topic,COUNT(*) AS conversations,COUNT(DISTINCT tenant) AS companies,
          SUM(human) AS escalated FROM cases WHERE updated>=? GROUP BY topic''',(now-86400,))]
        changes=[]
        for m in metrics:
            if m['errors'] or m['slow']:
                changes.append({'priority':'Alta' if m['errors'] else 'Media','area':m['area'],
                    'proposal':'Investigar errores del servicio' if m['errors'] else 'Revisar la carga y consultas de esta sección',
                    'evidence':m,'effort':'Por estimar tras diagnóstico','risk':'Validar en pruebas antes de publicar'})
        for t in topics:
            changes.append({'priority':'Media' if t['topic'] in ('access','billing','performance') else 'Por revisar',
                'area':t['topic'],'proposal':'Revisar conversaciones y acordar una mejora; no implica que exista un fallo confirmado',
                'evidence':dict(t,case_ids=[r['id'] for r in self.db.execute('SELECT id FROM cases WHERE topic=? AND updated>=? ORDER BY updated DESC LIMIT 10',(t['topic'],now-86400))]),
                'effort':'Por estimar','risk':'Aprobar el alcance antes de modificar el sistema'})
        report={'day':day,'generated':now,'period_hours':24,'metrics':metrics,'topics':topics,'proposals':changes,
                'open_cases':self.db.execute("SELECT COUNT(*) FROM cases WHERE status='open'").fetchone()[0],
                'limitations':['Métricas del tiempo del servidor al entregar páginas; no incluyen toda la red o el dispositivo del cliente.',
                    'Los tiempos se agrupan por hora: la primera hora del período puede incluir mediciones anteriores al límite exacto de 24 horas.',
                    'No se registran pulsaciones, campos, documentos, contraseñas ni URLs con identificadores.',
                    'Las sugerencias se agrupan por tema; confirmar coincidencias antes de unir solicitudes.',
                    'Los cambios requieren aprobación de Ericsson. No hay despliegues automáticos.']}
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO reports VALUES (?,?,?)',(day,now,json.dumps(report,ensure_ascii=False)))
        return json.loads(self.db.execute('SELECT body FROM reports WHERE day=?',(day,)).fetchone()[0])

    def prune(self):
        with self.db:
            self.db.execute('DELETE FROM limits WHERE bucket<?',(int(self.clock()//60)-1440,))
            self.db.execute('DELETE FROM metrics WHERE hour<?',(int(self.clock())-30*86400,))
            self.db.execute('DELETE FROM reports WHERE created<?',(self.clock()-90*86400,))

def area_for(path):
    # Categorize only known page routes; never persist paths, record IDs or query strings.
    route=path.split('?',1)[0]
    for name,starts in (('billing',('/uno360x-factur','/odoo/customer-invoices','/odoo/vendor-bills')),
                       ('inventory',('/uno360x-invent','/uno360x-product')),
                       ('sales',('/uno360x-venta','/uno360x-cotiza','/uno360x-crm')),
                       ('payroll',('/uno360x-nomina','/uno360x-equipo'))):
        if route.startswith(starts):
            return name
    return 'workspace' if route.startswith('/uno360x-') or route in ('/odoo','/web') or route.startswith('/odoo/') else None
