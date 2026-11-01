"""Approved trial signup flow. Local only; never grants public Odoo access."""
import json
import math
import uuid

from .identity import IdentityError, email_key
from .registry import OPTIONAL_MODULES
from .onboarding import Onboarding

TRIAL_SECONDS = 15 * 24 * 60 * 60


class Trials:
    def __init__(self, identity):
        self.identity = identity
        self.db = identity.db
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS trial_signup_drafts (
            account_id TEXT PRIMARY KEY REFERENCES accounts(id),
            name TEXT NOT NULL, modules TEXT NOT NULL, consent_version TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS trial_workspaces (
            account_id TEXT UNIQUE NOT NULL REFERENCES accounts(id),
            tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), name TEXT NOT NULL,
            country TEXT NOT NULL, currency TEXT NOT NULL, created REAL NOT NULL,
            started REAL, expires REAL
          );
        ''')

    def register(self, email, name, modules, consent):
        email = email_key(email)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 150:
            raise ValueError('Indica tu nombre.')
        if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules) or not set(modules) <= OPTIONAL_MODULES:
            raise ValueError('Selección inválida.')
        if consent is not True:
            raise ValueError('Revisa las condiciones de la prueba.')
        # Register remains generic and rate limited; no account enumeration.
        result = self.identity.register(email)
        with self.db:
            row = self.db.execute('SELECT id FROM accounts WHERE email=? AND verified=0 AND active=1', (email,)).fetchone()
            if row:
                self.db.execute('INSERT OR IGNORE INTO trial_signup_drafts VALUES (?,?,?,?)',
                                (row['id'], name.strip(), json.dumps(sorted(set(modules))), 'lab-review-v1'))
        return result

    def draft(self, session):
        account = self.identity._account(session)
        row = self.db.execute('SELECT name,modules FROM trial_signup_drafts WHERE account_id=?', (account['id'],)).fetchone()
        return {'name': row['name'] if row else '', 'modules': json.loads(row['modules']) if row else []}

    def companies(self, session):
        choices = self.identity.companies(session)
        for choice in choices:
            row = self.db.execute('SELECT name FROM trial_workspaces WHERE tenant_id=?', (choice['id'],)).fetchone()
            choice['name'] = row['name'] if row else choice['slug']
        return {'companies': choices}

    def create(self, session, name, country, currency, modules):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 150 or country != 'DO' or currency not in ('DOP', 'USD'):
            raise ValueError('Revisa los datos básicos de la empresa.')
        if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules) or not set(modules) <= OPTIONAL_MODULES:
            raise ValueError('Selección inválida.')
        modules = sorted(set(modules))
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self.identity._account(session)
            old = self.db.execute('SELECT * FROM trial_workspaces WHERE account_id=?', (account['id'],)).fetchone()
            if old:
                tenant_id = old['tenant_id']
                existing = self.db.execute('SELECT modules FROM tenants WHERE id=?', (tenant_id,)).fetchone()
                if (old['name'], old['country'], old['currency'], json.loads(existing['modules'])) != (name.strip(), country, currency, modules):
                    raise ValueError('Ya existe tu empresa de prueba. Continúa con ella.')
            else:
                # No technical hostname is requested from the user or accepted as input.
                tenant = self.identity.registry._reserve_in_transaction('empresa-' + uuid.uuid4().hex[:16], modules, 'trial:' + account['id'])
                tenant_id = tenant['id']
                self.db.execute("INSERT INTO memberships VALUES (?,?,'owner',1)", (account['id'], tenant_id))
                self.db.execute('INSERT INTO trial_workspaces VALUES (?,?,?,?,?,?,NULL,NULL)',
                                (account['id'], tenant_id, name.strip(), country, currency, self.identity.clock()))
                self.identity._audit('trial_company_created', account['id'], tenant_id)
        # Queueing is separately idempotent, so a retry recovers after interruption.
        Onboarding(self.identity).request(session, tenant_id)
        return self.status(session, tenant_id)

    def status(self, session, tenant_id):
        account = self.identity._account(session)
        self.identity._membership(account['id'], tenant_id)
        row = self.db.execute('SELECT * FROM trial_workspaces WHERE tenant_id=?', (tenant_id,)).fetchone()
        if not row:
            return {'tenant_id': tenant_id, 'is_trial': False, 'public_access': False}
        job = Onboarding(self.identity).status(session, tenant_id)
        if job['local_ready'] and row['started'] is None:
            # Also reconcile older worker versions; the worker records this at first readiness.
            ready_at = self.db.execute('SELECT updated FROM preparation_jobs WHERE tenant_id=?', (tenant_id,)).fetchone()[0]
            with self.db:
                self.db.execute('UPDATE trial_workspaces SET started=?,expires=? WHERE tenant_id=? AND started IS NULL',
                                (ready_at, ready_at + TRIAL_SECONDS, tenant_id))
            row = self.db.execute('SELECT * FROM trial_workspaces WHERE tenant_id=?', (tenant_id,)).fetchone()
        remaining = max(0, math.ceil((row['expires'] - self.identity.clock()) / 86400)) if row['expires'] else None
        tenant = self.db.execute('SELECT modules FROM tenants WHERE id=?', (tenant_id,)).fetchone()
        return dict(job, is_trial=True, name=row['name'], country=row['country'], currency=row['currency'],
                    modules=json.loads(tenant['modules']), started=row['started'], expires=row['expires'],
                    days_remaining=remaining, trial_active=remaining is not None and remaining > 0,
                    card_required=False, automatic_charge=False)


def check_trial_access(identity, tenant_id):
    """Existing non-trial fixtures and production are outside this policy."""
    if not identity.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
        return
    row = identity.db.execute('SELECT started,expires FROM trial_workspaces WHERE tenant_id=?', (tenant_id,)).fetchone()
    if row and (row['started'] is None or row['expires'] <= identity.clock()):
        raise IdentityError('La prueba no está activa. Los datos se conservan.')
