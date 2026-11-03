"""Control-plane preparation jobs and single-use handoff tickets.

Request handlers only queue jobs. A separate trusted local adapter performs
privileged work. No production adapter, billing bypass or public activation.
"""
import json
import secrets
import uuid

from .catalog import installation_profile
from .identity import IdentityError,digest

STEPS=('network','database','installation','identity','validation')


class PreparationError(ValueError):
    pass


class Onboarding:
    def __init__(self, identity):
        self.identity=identity
        self.db=identity.db
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS preparation_jobs (
            id TEXT PRIMARY KEY, tenant_id TEXT UNIQUE NOT NULL REFERENCES tenants(id),
            requested_by TEXT NOT NULL REFERENCES accounts(id), snapshot TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','running','failed','ready_local')),
            current_step TEXT, updated REAL NOT NULL
          );
          CREATE TABLE IF NOT EXISTS preparation_steps (
            job_id TEXT NOT NULL REFERENCES preparation_jobs(id), step TEXT NOT NULL,
            PRIMARY KEY(job_id,step)
          );
          CREATE TABLE IF NOT EXISTS handoff_tickets (
            digest TEXT PRIMARY KEY, session_digest TEXT NOT NULL,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            tenant_id TEXT NOT NULL REFERENCES tenants(id), job_id TEXT NOT NULL REFERENCES preparation_jobs(id),
            expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0
          );
        ''')

    def request(self, session, tenant_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account=self.identity._account(session)
            membership=self.identity._membership(account['id'],tenant_id)
            if membership['role']!='owner':raise IdentityError('Operación no autorizada.')
            tenant=self.db.execute('SELECT * FROM tenants WHERE id=?',(tenant_id,)).fetchone()
            profile=installation_profile(json.loads(tenant['modules']))
            old=self.db.execute('SELECT * FROM preparation_jobs WHERE tenant_id=?',(tenant_id,)).fetchone()
            if old:
                if old['fingerprint']!=profile['fingerprint']:
                    raise PreparationError('El producto cambió; requiere migración explícita.')
                return self.status(session,tenant_id)
            snapshot={'tenant_id':tenant_id,'slug':tenant['slug'],'hostname':tenant['hostname'],
                      'installation':profile,'mode':'local_laboratory','public_access':False}
            job=uuid.uuid4().hex
            self.db.execute("INSERT INTO preparation_jobs VALUES (?,?,?,?,?,'queued',NULL,?)",
                            (job,tenant_id,account['id'],json.dumps(snapshot,sort_keys=True),profile['fingerprint'],self.identity.clock()))
            self.identity._audit('preparation_queued',account['id'],tenant_id)
        return self.status(session,tenant_id)

    def status(self, session, tenant_id):
        account=self.identity._account(session)
        self.identity._membership(account['id'],tenant_id)
        row=self.db.execute('SELECT * FROM preparation_jobs WHERE tenant_id=?',(tenant_id,)).fetchone()
        if not row:raise PreparationError('No existe preparación para esta empresa.')
        tenant=self.db.execute('SELECT modules FROM tenants WHERE id=?',(tenant_id,)).fetchone()
        changed=installation_profile(json.loads(tenant['modules']))['fingerprint']!=row['fingerprint']
        done={r[0] for r in self.db.execute('SELECT step FROM preparation_steps WHERE job_id=?',(row['id'],))}
        return {'job_id':row['id'],'tenant_id':tenant_id,'status':row['status'],
                'current_step':row['current_step'],'completed_steps':[s for s in STEPS if s in done],
                'public_access':False,'local_ready':row['status']=='ready_local' and not changed,
                'requires_migration':changed}

    def run(self, job_id, adapter):
        """Worker-only entry. Adapter must lock across processes and be idempotent."""
        row=self.db.execute('SELECT * FROM preparation_jobs WHERE id=?',(job_id,)).fetchone()
        if not row:raise PreparationError('Preparación desconocida.')
        snapshot=json.loads(row['snapshot'])
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
            basic=self.db.execute('SELECT name,country,currency FROM trial_workspaces WHERE tenant_id=?',(snapshot['tenant_id'],)).fetchone()
            if basic:snapshot['company_profile']=dict(basic)
        with adapter.lock(snapshot['tenant_id']):
            tenant=self.db.execute('SELECT * FROM tenants WHERE id=?',(snapshot['tenant_id'],)).fetchone()
            expected=installation_profile(json.loads(tenant['modules']))
            if expected['fingerprint']!=row['fingerprint']:
                raise PreparationError('El producto cambió; requiere migración explícita.')
            with self.db:
                self.db.execute("UPDATE preparation_jobs SET status='running',updated=? WHERE id=?",(self.identity.clock(),job_id))
                self.db.execute('DELETE FROM preparation_steps WHERE job_id=?',(job_id,))
            import time as duration_clock
            resource_names=adapter.names(snapshot) if hasattr(adapter,'names') else None
            timing_path=resource_names['directory']/'preparation-timing.json' if isinstance(resource_names,dict) and resource_names.get('directory') else None
            timings=[]
            for step in STEPS:
                with self.db:
                    self.db.execute('UPDATE preparation_jobs SET current_step=?,updated=? WHERE id=?',(step,self.identity.clock(),job_id))
                try:
                    # Reconcile every step. A recorded success cannot hide a
                    # missing/stopped resource after a process or host crash.
                    step_started=duration_clock.monotonic()
                    getattr(adapter,step)(snapshot)
                    timings.append({'step':step,'seconds':round(duration_clock.monotonic()-step_started,3)})
                    if timing_path:
                        timing_path.write_text(json.dumps({'steps':timings,'seconds':round(sum(x['seconds'] for x in timings),3)}));timing_path.chmod(0o600)
                except Exception:
                    with self.db:
                        self.db.execute("UPDATE preparation_jobs SET status='failed',updated=? WHERE id=?",(self.identity.clock(),job_id))
                        self.identity._audit('preparation_failed',tenant=snapshot['tenant_id'])
                    raise PreparationError('Falló la preparación local en '+step+'.') from None
                with self.db:
                    self.db.execute('INSERT OR IGNORE INTO preparation_steps VALUES (?,?)',(job_id,step))
            with self.db:
                self.db.execute("UPDATE preparation_jobs SET status='ready_local',current_step=NULL,updated=? WHERE id=?",(self.identity.clock(),job_id))
                if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
                    from .trials import TRIAL_SECONDS
                    now = self.identity.clock()
                    self.db.execute('UPDATE trial_workspaces SET started=?,expires=? WHERE tenant_id=? AND started IS NULL',
                                    (now, now + TRIAL_SECONDS, snapshot['tenant_id']))
                self.identity._audit('preparation_ready_local',tenant=snapshot['tenant_id'])
        return {'job_id':job_id,'status':'ready_local','public_access':False}

    def issue_handoff(self, session, tenant_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account=self.identity._account(session)
            self.identity._membership(account['id'],tenant_id)
            job=self.db.execute("SELECT * FROM preparation_jobs WHERE tenant_id=? AND status='ready_local'",(tenant_id,)).fetchone()
            if not job:raise PreparationError('El espacio todavía no está listo.')
            if not self.status(session,tenant_id)['local_ready']:
                raise PreparationError('El espacio requiere una migración.')
            from .trials import check_trial_access
            check_trial_access(self.identity, tenant_id)
            if not self.identity._allow('handoff',account['id'],maximum=20,window=60):
                raise IdentityError('Espera antes de volver a intentarlo.')
            ticket=secrets.token_urlsafe(32)
            self.db.execute('INSERT INTO handoff_tickets VALUES (?,?,?,?,?,?,0)',
                            (digest(ticket),digest(session),account['id'],tenant_id,job['id'],self.identity.clock()+60))
        return {'ticket':ticket,'expires_in':60,'public_access':False}

    def consume_handoff(self, session, ticket):
        """Broker-only operation; returns claims, never an Odoo password."""
        if not isinstance(ticket,str) or len(ticket)>128:raise IdentityError('Acceso inválido.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account=self.identity._account(session)
            row=self.db.execute('SELECT * FROM handoff_tickets WHERE digest=?',(digest(ticket),)).fetchone()
            if not row or row['used'] or row['expires']<=self.identity.clock() or row['account_id']!=account['id'] or row['session_digest']!=digest(session):
                raise IdentityError('Acceso inválido o vencido.')
            member=self.identity._membership(account['id'],row['tenant_id'])
            from .trials import check_trial_access
            check_trial_access(self.identity, row['tenant_id'])
            job=self.db.execute("SELECT * FROM preparation_jobs WHERE id=? AND status='ready_local'",(row['job_id'],)).fetchone()
            if not job:raise PreparationError('El espacio no está disponible.')
            if not self.status(session,row['tenant_id'])['local_ready']:
                raise PreparationError('El espacio requiere una migración.')
            self.db.execute('UPDATE handoff_tickets SET used=1 WHERE digest=?',(row['digest'],))
            self.identity._audit('handoff_consumed',account['id'],row['tenant_id'])
        return {'tenant_id':row['tenant_id'],'account_id':account['id'],'email':account['email'],
                'role':member['role'],'job_id':job['id']}
