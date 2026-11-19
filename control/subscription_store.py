"""SaaS billing ledger; tenant admins may set preferences and report a transfer only.

The workspace cannot create invoices, mark payments paid, change prices or grant access.
No card numbers, CVV, payment credentials or sandbox events belong in this ledger.
"""
import hashlib
import json
import re
import uuid

SCHEMA='''
CREATE TABLE IF NOT EXISTS subscription_preferences (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), method TEXT NOT NULL, email TEXT NOT NULL,
 updated REAL NOT NULL, actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscription_terms (
 tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), amount_minor INTEGER NOT NULL CHECK(amount_minor>=0),
 currency TEXT NOT NULL CHECK(currency IN ('USD','DOP')), next_due REAL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS subscription_invoices (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),number TEXT NOT NULL,
 issued REAL NOT NULL,due REAL,total_minor INTEGER NOT NULL CHECK(total_minor>=0),
 currency TEXT NOT NULL CHECK(currency IN ('USD','DOP')),state TEXT NOT NULL CHECK(state IN ('pending','paid','void')),
 pdf BLOB NOT NULL, UNIQUE(tenant_id,number));
CREATE INDEX IF NOT EXISTS subscription_invoice_scope ON subscription_invoices(tenant_id,issued,id);
CREATE TABLE IF NOT EXISTS subscription_transfer_reports (
 id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),invoice_id TEXT NOT NULL REFERENCES subscription_invoices(id),
 reference TEXT NOT NULL,mime TEXT NOT NULL,proof BLOB NOT NULL,sha256 TEXT NOT NULL,
 created REAL NOT NULL,actor TEXT NOT NULL,request_id TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'review' CHECK(state IN ('review','verified','rejected')),
 UNIQUE(tenant_id,request_id),UNIQUE(tenant_id,invoice_id,sha256));
CREATE TABLE IF NOT EXISTS subscription_audit (
 id INTEGER PRIMARY KEY,tenant_id TEXT NOT NULL,actor TEXT NOT NULL,event TEXT NOT NULL,created REAL NOT NULL);
'''
MAX_PROOF=3*1024*1024

class BillingInvalid(ValueError):pass

class Subscription:
    def __init__(self,identity):
        self.identity=identity;self.db=identity.db

    def initialize(self):
        self.db.executescript(SCHEMA)

    def authorize(self,session,tenant):
        account=self.identity._account(session)
        role=self.identity._membership(account['id'],tenant)['role']
        if role not in ('owner','admin'):raise PermissionError('Solo el administrador puede gestionar la suscripción.')
        return account

    def overview(self,session,tenant):
        actor=self.authorize(session,tenant)
        row=self.db.execute('SELECT modules FROM tenants WHERE id=?',(tenant,)).fetchone()
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        trial=self.db.execute('SELECT name,expires FROM trial_workspaces WHERE tenant_id=?',(tenant,)).fetchone() if 'trial_workspaces' in tables else None
        pref=self.db.execute('SELECT method,email,updated FROM subscription_preferences WHERE tenant_id=?',(tenant,)).fetchone()
        terms=self.db.execute('SELECT amount_minor,currency,next_due FROM subscription_terms WHERE tenant_id=?',(tenant,)).fetchone()
        return {'name':trial['name'] if trial else 'Mi empresa','modules':json.loads(row['modules']),
                'trial_expires':trial['expires'] if trial else None,
                'preferences':dict(pref) if pref else {'method':'','email':dict(actor).get('email','')},'terms':dict(terms) if terms else None,
                'automatic_charge':False,'card_available':False}

    def invoices(self,session,tenant,year='',state='',query=''):
        self.authorize(session,tenant)
        if year and not re.fullmatch(r'20\d{2}',year):raise BillingInvalid('Año no válido.')
        if state not in ('','pending','paid','void') or not isinstance(query,str) or len(query)>80:raise BillingInvalid('Filtro no válido.')
        rows=[dict(r) for r in self.db.execute('''SELECT i.id,i.number,i.issued,i.due,i.total_minor,i.currency,i.state,
             (SELECT COUNT(*) FROM subscription_transfer_reports p WHERE p.invoice_id=i.id AND p.tenant_id=i.tenant_id AND p.state='review') AS awaiting_review
             FROM subscription_invoices i WHERE i.tenant_id=? ORDER BY issued DESC,id DESC''',(tenant,))]
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return [r for r in rows if (not year or datetime.fromtimestamp(r['issued'],ZoneInfo('America/Santo_Domingo')).strftime('%Y')==year)
                and (not state or r['state']==state) and (not query or query.casefold() in r['number'].casefold())]

    def invoice(self,session,tenant,invoice):
        self.authorize(session,tenant)
        if not isinstance(invoice,str) or not re.fullmatch('[a-f0-9]{32}',invoice):raise BillingInvalid('Factura no disponible.')
        row=self.db.execute('SELECT * FROM subscription_invoices WHERE id=? AND tenant_id=?',(invoice,tenant)).fetchone()
        if not row:raise BillingInvalid('Factura no disponible.')
        return dict(row)

    def preferences(self,session,tenant,method,email):
        actor=self.authorize(session,tenant)
        from .identity import email_key,IdentityError
        try:email=email_key(email)
        except IdentityError:raise BillingInvalid('Correo de facturación no válido.') from None
        if method!='transfer':raise BillingInvalid('Las tarjetas todavía no están habilitadas. Selecciona transferencia.')
        with self.db:
            self.db.execute('''INSERT INTO subscription_preferences VALUES (?,?,?,?,?) ON CONFLICT(tenant_id)
                DO UPDATE SET method=excluded.method,email=excluded.email,updated=excluded.updated,actor=excluded.actor''',
                (tenant,method,email,self.identity.clock(),actor['id']))
            self.db.execute('INSERT INTO subscription_audit(tenant_id,actor,event,created) VALUES (?,?,?,?)',
                (tenant,actor['id'],'preferences_saved',self.identity.clock()))

    def report_transfer(self,session,tenant,invoice,reference,proof,request_id):
        actor=self.authorize(session,tenant)
        if not isinstance(reference,str) or not 1<=len(reference.strip())<=100 or any(ord(ch)<32 for ch in reference):raise BillingInvalid('Indica una referencia de hasta 100 caracteres.')
        if not isinstance(proof,bytes) or not 1<=len(proof)<=MAX_PROOF:raise BillingInvalid('Adjunta un PDF, JPG o PNG de hasta 3 MB.')
        if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):raise BillingInvalid('Solicitud no válida.')
        mime='application/pdf' if proof.startswith(b'%PDF-') else 'image/png' if proof.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if proof.startswith(b'\xff\xd8\xff') else None
        if not mime:raise BillingInvalid('El comprobante debe ser PDF, JPG o PNG.')
        fingerprint=hashlib.sha256(proof).hexdigest()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row=self.invoice(session,tenant,invoice)
            prior=self.db.execute('SELECT * FROM subscription_transfer_reports WHERE tenant_id=? AND request_id=?',(tenant,request_id)).fetchone()
            if prior:
                if (prior['invoice_id'],prior['reference'],prior['sha256'])!=(invoice,reference.strip(),fingerprint):raise BillingInvalid('La solicitud ya se utilizó con otros datos.')
                return prior['id']
            if row['state']!='pending':raise BillingInvalid('Solo se puede reportar un pago para una factura pendiente.')
            previous=self.db.execute('SELECT id FROM subscription_transfer_reports WHERE tenant_id=? AND invoice_id=? AND sha256=?',(tenant,invoice,fingerprint)).fetchone()
            if previous:return previous['id']
            if self.db.execute('SELECT COUNT(*) FROM subscription_transfer_reports WHERE tenant_id=? AND invoice_id=?',(tenant,invoice)).fetchone()[0]>=5:raise BillingInvalid('Este pago ya tiene comprobantes registrados. Contacta al equipo.')
            rid=uuid.uuid4().hex
            self.db.execute('''INSERT INTO subscription_transfer_reports(id,tenant_id,invoice_id,reference,mime,proof,sha256,created,actor,request_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',(rid,tenant,invoice,reference.strip(),mime,proof,fingerprint,self.identity.clock(),actor['id'],request_id))
            self.db.execute('INSERT INTO subscription_audit(tenant_id,actor,event,created) VALUES (?,?,?,?)',
                (tenant,actor['id'],'transfer_reported',self.identity.clock()))
        return rid

    def proof(self,session,tenant,report):
        self.authorize(session,tenant)
        if not isinstance(report,str) or not re.fullmatch('[a-f0-9]{32}',report):raise BillingInvalid('Comprobante no disponible.')
        row=self.db.execute('SELECT mime,proof FROM subscription_transfer_reports WHERE id=? AND tenant_id=?',(report,tenant)).fetchone()
        if not row:raise BillingInvalid('Comprobante no disponible.')
        return dict(row)
