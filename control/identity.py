"""Local account/membership service. No SMTP, public HTTP, Odoo login or billing.

One connection/transaction covers accounts, memberships and tenant reservation.
Tokens and sessions are stored only as digests. Delivery is explicitly injected;
the lab supplies an in-memory sink and never prints links or credentials.
"""
from functools import lru_cache
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid

from .registry import Registry

GENERIC = {'message': 'Si corresponde, recibirás instrucciones en tu correo.'}
VERIFY_TTL = 3600
RESET_TTL = 1800
INVITE_TTL = 172800
SESSION_TTL = 30 * 86400
SESSION_RENEWAL_INTERVAL = 300
SESSION_COOKIE_TTL = 400 * 86400


class IdentityError(ValueError):
    pass


class LoginThrottled(IdentityError):
    pass



def email_key(value):
    if not isinstance(value, str) or not value.isascii():
        raise IdentityError('Correo inválido.')
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", value):
        raise IdentityError('Correo inválido.')
    local = value.split('@')[0]
    if local.startswith('.') or local.endswith('.') or '..' in local:
        raise IdentityError('Correo inválido.')
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise IdentityError('La contraseña debe tener de 12 a 128 caracteres.')
    salt = salt or secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
    return 'scrypt$16384$8$1$' + salt + '$' + result.hex()


def password_matches(password, encoded):
    if not isinstance(password, str) or len(password) > 128:
        return False
    try:
        algorithm,n,r,p,salt,expected = encoded.split('$')
        if (algorithm,n,r,p) != ('scrypt','16384','8','1'):
            return False
        value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()
        return hmac.compare_digest(value, expected)
    except (ValueError,TypeError):
        return False


@lru_cache(maxsize=1)
def dummy_password_hash():
    return password_hash(secrets.token_urlsafe(24))


class IdentityService:
    def __init__(self, path, deliver, clock=time.time):
        if not callable(deliver):
            raise TypeError('Se requiere un transporte explícito; no hay correo predeterminado.')
        self.registry = Registry(path)
        self.db = self.registry.db
        self.clock, self.deliver = clock, deliver
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            password_hash TEXT, verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1)),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
          );
          CREATE TABLE IF NOT EXISTS memberships (
            account_id TEXT NOT NULL REFERENCES accounts(id),
            tenant_id TEXT NOT NULL REFERENCES tenants(id),
            role TEXT NOT NULL CHECK(role IN ('owner','admin','member')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            PRIMARY KEY(account_id,tenant_id)
          );
          CREATE TABLE IF NOT EXISTS identity_tokens (
            digest TEXT PRIMARY KEY, purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset','invite')),
            email TEXT NOT NULL, account_id TEXT REFERENCES accounts(id),
            tenant_id TEXT REFERENCES tenants(id), role TEXT,
            issuer_id TEXT REFERENCES accounts(id),
            expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0 CHECK(used IN (0,1))
          );
          CREATE TABLE IF NOT EXISTS identity_sessions (
            digest TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
            expires REAL NOT NULL
          );
          CREATE TABLE IF NOT EXISTS identity_limits (
            bucket TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL
          );
          CREATE TABLE IF NOT EXISTS identity_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
            account_id TEXT, tenant_id TEXT, occurred REAL NOT NULL
          );
        ''')
        # Equal-cost work for nonexistent accounts. Never persisted or returned.
        self.dummy_hash = dummy_password_hash()

    def close(self):
        self.registry.close()

    def _audit(self, event, account=None, tenant=None):
        self.db.execute('INSERT INTO identity_audit(event,account_id,tenant_id,occurred) VALUES (?,?,?,?)',
                        (event,account,tenant,self.clock()))

    def _allow(self, category, key, maximum=5, window=900):
        bucket = digest(category + ':' + key)
        row = self.db.execute('SELECT * FROM identity_limits WHERE bucket=?',(bucket,)).fetchone()
        now = self.clock()
        if not row or now >= row['started'] + window:
            self.db.execute('INSERT INTO identity_limits VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET started=excluded.started,count=1',(bucket,now))
            return True
        self.db.execute('UPDATE identity_limits SET count=count+1 WHERE bucket=?',(bucket,))
        return row['count'] < maximum

    def _issue(self, purpose, email, account=None, tenant=None, role=None, issuer=None):
        self.db.execute('UPDATE identity_tokens SET used=1 WHERE purpose=? AND email=? AND tenant_id IS ? AND used=0',
                        (purpose,email,tenant))
        token = secrets.token_urlsafe(32)
        ttl = {'verify':VERIFY_TTL,'reset':RESET_TTL,'invite':INVITE_TTL}[purpose]
        self.db.execute('INSERT INTO identity_tokens VALUES (?,?,?,?,?,?,?,?,0)',
                        (digest(token),purpose,email,account,tenant,role,issuer,self.clock()+ttl))
        # The transport receives raw tokens only in memory, after transaction commit.
        return {'purpose':purpose,'email':email,'token':token,'expires_in':ttl}

    def _deliver(self, notification):
        if notification:
            try:
                self.deliver(notification)
            except Exception:
                # Do not expose addresses, tokens or delivery failure differences.
                with self.db:self._audit('delivery_failed')

    def register(self, email):
        email = email_key(email)
        notice = None
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self._allow('register',email):
                row = self.db.execute('SELECT * FROM accounts WHERE email=?',(email,)).fetchone()
                if not row:
                    account = uuid.uuid4().hex
                    self.db.execute('INSERT INTO accounts(id,email) VALUES (?,?)',(account,email))
                    row = self.db.execute('SELECT * FROM accounts WHERE id=?',(account,)).fetchone()
                if not row['verified'] and row['active']:
                    notice = self._issue('verify',email,row['id'])
                    self._audit('registration_requested',row['id'])
        self._deliver(notice)
        return dict(GENERIC)

    def request_verification(self, email):
        email = email_key(email)
        notice = None
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self._allow('register', email):
                row = self.db.execute('SELECT id FROM accounts WHERE email=? AND verified=0 AND active=1', (email,)).fetchone()
                if row:
                    notice = self._issue('verify', email, row['id'])
                    self._audit('verification_resent', row['id'])
        self._deliver(notice)
        return dict(GENERIC)

    def _token(self, token, purpose):
        if not isinstance(token,str) or not 32 <= len(token) <= 128:
            raise IdentityError('Enlace inválido o vencido.')
        row = self.db.execute('SELECT * FROM identity_tokens WHERE digest=? AND purpose=?',
                              (digest(token),purpose)).fetchone()
        if not row or row['used'] or row['expires'] <= self.clock():
            raise IdentityError('Enlace inválido o vencido.')
        return row

    def complete_registration(self, token, password):
        encoded = password_hash(password)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self._token(token,'verify')
            account = self.db.execute('SELECT * FROM accounts WHERE id=?',(row['account_id'],)).fetchone()
            if not account or account['verified'] or not account['active']:
                raise IdentityError('Enlace inválido o vencido.')
            self.db.execute('UPDATE accounts SET verified=1,password_hash=? WHERE id=?',(encoded,account['id']))
            self.db.execute('UPDATE identity_tokens SET used=1 WHERE digest=?',(row['digest'],))
            self._audit('email_verified',account['id'])
        return {'verified':True}

    def login(self, email, password, *, require_email_code=False, pending_email_code=None):
        email = email_key(email)
        session = None
        throttled = False
        # Scrypt is expensive: never hold SQLite's writer lock while hashing.
        row = self.db.execute('SELECT * FROM accounts WHERE email=?',(email,)).fetchone()
        encoded = row['password_hash'] if row and row['password_hash'] else self.dummy_hash
        matches = password_matches(password,encoded)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            allowed = self._allow('login',email)
            # A reset/disable may race with the hash check. Recheck atomically.
            row = self.db.execute('SELECT * FROM accounts WHERE email=?',(email,)).fetchone()
            if matches and row and row['active'] and row['verified'] and row['password_hash']==encoded:
                if require_email_code:
                    verified = {'id':row['id'],'email':row['email'],'password_hash':encoded}
                    if allowed and (pending_email_code == verified or self._allow('login-code-send', email, maximum=3, window=600)):
                        return verified
                    throttled = True
                elif allowed:
                    session = self._new_session(row['id'])
                    self.db.execute('DELETE FROM identity_limits WHERE bucket=?',(digest('login:'+email),))
        if throttled:
            raise LoginThrottled('Espera unos minutos antes de solicitar otro código.')
        if session is None:
            raise IdentityError('No se pudo iniciar sesión.')
        return {'session':session,'expires_in':SESSION_TTL}

    def _new_session(self, account_id):
        session = secrets.token_urlsafe(32)
        self.db.execute('INSERT INTO identity_sessions VALUES (?,?,?)',
                        (digest(session),account_id,self.clock()+SESSION_TTL))
        self._audit('login',account_id)
        return session

    def finish_email_login(self, account):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()
            if not row or not row['active'] or not row['verified'] or row['email']!=account['email'] or row['password_hash']!=account['password_hash']:
                raise IdentityError('Vuelve a iniciar sesión.')
            session = self._new_session(row['id'])
            self.db.execute('DELETE FROM identity_limits WHERE bucket=?',(digest('login:'+row['email']),))
        return {'session':session,'expires_in':SESSION_TTL}

    def _account(self, session, *, renew=False):
        if not isinstance(session,str) or len(session)>128:
            raise IdentityError('Sesión inválida o vencida.')
        now = self.clock()
        session_key = digest(session)
        row = self.db.execute('''SELECT a.*, s.expires AS session_expires FROM identity_sessions s JOIN accounts a ON a.id=s.account_id
          WHERE s.digest=? AND s.expires>? AND a.active=1 AND a.verified=1''',
                              (session_key,now)).fetchone()
        if not row:
            raise IdentityError('Sesión inválida o vencida.')
        if renew and row['session_expires'] <= now + SESSION_TTL - SESSION_RENEWAL_INTERVAL:
            # Keep an existing caller transaction intact. Never revive a deleted or expired session.
            already_in_transaction = self.db.in_transaction
            self.db.execute('UPDATE identity_sessions SET expires=? WHERE digest=? AND expires>? AND expires<?',
                            (now + SESSION_TTL,session_key,now,now + SESSION_TTL))
            if not already_in_transaction:
                self.db.commit()
        return row

    def logout(self, session):
        with self.db:self.db.execute('DELETE FROM identity_sessions WHERE digest=?',(digest(session),))
        return {'logged_out':True}

    def request_reset(self, email):
        email = email_key(email)
        notice = None
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if self._allow('reset',email):
                row = self.db.execute('SELECT * FROM accounts WHERE email=? AND verified=1 AND active=1',(email,)).fetchone()
                if row:
                    notice = self._issue('reset',email,row['id'])
        self._deliver(notice)
        return dict(GENERIC)

    def reset_password(self, token, password):
        encoded = password_hash(password)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self._token(token,'reset')
            account = self.db.execute('SELECT * FROM accounts WHERE id=? AND active=1 AND verified=1',(row['account_id'],)).fetchone()
            if not account:
                raise IdentityError('Enlace inválido o vencido.')
            self.db.execute('UPDATE accounts SET password_hash=? WHERE id=?',(encoded,account['id']))
            self.db.execute('DELETE FROM identity_sessions WHERE account_id=?',(account['id'],))
            self.db.execute("UPDATE identity_tokens SET used=1 WHERE account_id=? AND purpose='reset'",(account['id'],))
            self.db.execute('DELETE FROM identity_limits WHERE bucket=?',(digest('login:'+account['email']),))
            self._audit('password_reset',account['id'])
        return {'reset':True}

    def create_company(self, session, slug, modules, request_id):
        if not isinstance(request_id,str) or not 1 <= len(request_id) <= 128:
            raise IdentityError('Solicitud inválida.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self._account(session)
            key = 'identity:' + digest(account['id']+':'+request_id)
            tenant = self.registry._reserve_in_transaction(slug,modules,key)
            self.db.execute("INSERT OR IGNORE INTO memberships VALUES (?,?,'owner',1)",(account['id'],tenant['id']))
            self._audit('company_reserved',account['id'],tenant['id'])
        return {'id':tenant['id'],'hostname':tenant['hostname'],'role':'owner',
                'state':'reserved','access_enabled':False}

    def companies(self, session):
        account = self._account(session)
        rows = self.db.execute('''SELECT t.id,t.hostname,t.slug,t.state,m.role FROM memberships m
          JOIN tenants t ON t.id=m.tenant_id WHERE m.account_id=? AND m.active=1 ORDER BY t.slug''',(account['id'],)).fetchall()
        return [dict(row) for row in rows]

    def select_company(self, session, tenant_id):
        choices = self.companies(session)
        match = next((r for r in choices if r['id']==tenant_id),None)
        if not match:
            raise IdentityError('Empresa no disponible para tu usuario.')
        ready=False
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='preparation_jobs'").fetchone():
            from .onboarding import Onboarding
            try:ready=Onboarding(self).status(session,tenant_id)['local_ready']
            except ValueError:pass
        return dict(match,access_enabled=False,odoo_session_created=False,local_ready=ready,public_access=False)

    def _membership(self, account_id, tenant_id):
        row = self.db.execute('SELECT * FROM memberships WHERE account_id=? AND tenant_id=? AND active=1',
                              (account_id,tenant_id)).fetchone()
        if not row:
            raise IdentityError('Operación no autorizada.')
        return row

    def invite(self, session, tenant_id, email, role='member', *, employee_id=None, work_permissions=None, business=None):
        email = email_key(email)
        if role not in ('admin','member'):
            raise IdentityError('Rol inválido.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self._account(session)
            member = self._membership(account['id'],tenant_id)
            if member['role'] not in ('owner','admin') or (role=='admin' and member['role']!='owner'):
                raise IdentityError('Operación no autorizada.')
            if work_permissions is not None:
                if employee_id is None or member['role']!='owner' or len(work_permissions)!=2 or any(type(value) is not bool for value in work_permissions):
                    raise IdentityError('Solo el propietario puede asignar estos permisos.')
                plan = self.db.execute('SELECT modules FROM tenants WHERE id=?',(tenant_id,)).fetchone()
                if 'payroll_hr' not in json.loads(plan['modules']):
                    raise IdentityError('Este plan no incluye Recursos Humanos y Nómina.')
            elif employee_id is not None and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='invitation_work_permissions'").fetchone():
                previous = self.db.execute("""
                    SELECT p.hr,p.payroll FROM invitation_work_permissions p JOIN identity_tokens t ON t.digest=p.token_digest
                    JOIN employee_invites e ON e.token_digest=t.digest AND e.tenant_id=t.tenant_id
                    WHERE t.tenant_id=? AND t.email=? AND t.role=? AND t.used=0 AND e.employee_id=?
                    ORDER BY t.expires DESC LIMIT 1
                """,(tenant_id,email,role,employee_id)).fetchone()
                if previous:
                    if member['role']!='owner':
                        raise IdentityError('Solo el propietario puede reenviar esta invitación con permisos especiales.')
                    work_permissions = tuple(bool(value) for value in previous)
            if business is None and employee_id is not None and self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='invitation_business_permissions'").fetchone():
                previous = self.db.execute("""
                    SELECT p.areas FROM invitation_business_permissions p JOIN identity_tokens t ON t.digest=p.token_digest
                    JOIN employee_invites e ON e.token_digest=t.digest AND e.tenant_id=t.tenant_id
                    WHERE t.tenant_id=? AND t.email=? AND t.role=? AND t.used=0 AND e.employee_id=?
                    ORDER BY t.expires DESC LIMIT 1
                """,(tenant_id,email,role,employee_id)).fetchone()
                if previous:
                    business = json.loads(previous['areas'])
            if business is not None:
                if employee_id is None or role!='member':
                    raise IdentityError('Las areas comerciales se asignan a empleados.')
                business = self._checked_business_areas(business)
            if not self._allow('invite',account['id'],maximum=20,window=3600):
                raise IdentityError('Espera antes de enviar más invitaciones.')
            notice = self._issue('invite',email,tenant=tenant_id,role=role,issuer=account['id'])
            if employee_id is not None:
                self.db.execute("""CREATE TABLE IF NOT EXISTS employee_invites (
                    token_digest TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    employee_id INTEGER NOT NULL)""")
                self.db.execute('INSERT INTO employee_invites VALUES (?,?,?)',
                                (digest(notice['token']),tenant_id,employee_id))
                if work_permissions is not None:
                    self.db.execute("""CREATE TABLE IF NOT EXISTS invitation_work_permissions (
                        token_digest TEXT PRIMARY KEY REFERENCES identity_tokens(digest) ON DELETE CASCADE,
                        hr INTEGER NOT NULL CHECK(hr IN (0,1)), payroll INTEGER NOT NULL CHECK(payroll IN (0,1)))""")
                    self.db.execute('INSERT INTO invitation_work_permissions VALUES (?,?,?)',
                                    (digest(notice['token']),*work_permissions))
                if business is not None:
                    self.db.execute("""CREATE TABLE IF NOT EXISTS invitation_business_permissions (
                        token_digest TEXT PRIMARY KEY REFERENCES identity_tokens(digest) ON DELETE CASCADE,
                        areas TEXT NOT NULL)""")
                    self.db.execute('INSERT INTO invitation_business_permissions VALUES (?,?)',
                                    (digest(notice['token']),json.dumps(business)))
            self._audit('invitation_created',account['id'],tenant_id)
        if employee_id is None:
            self._deliver(notice)
        else:
            try:
                self.deliver(notice)
            except Exception:
                with self.db:
                    self.db.execute('UPDATE identity_tokens SET used=1 WHERE digest=?',(digest(notice['token']),))
                    self._audit('delivery_failed')
                raise IdentityError('No pudimos enviar la invitacion. Intenta de nuevo.') from None
        return {'invited':True}

    def accept_invitation(self, session, token):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self._account(session)
            self._accept_invitation(account, self._token(token,'invite'))
        return {'accepted':True}

    def activate_employee_invitation(self, token, password):
        self._token(token,'invite')
        encoded = password_hash(password)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self._token(token,'invite')
            if not self.db.execute("SELECT 1 FROM sqlite_master WHERE name='employee_invites'").fetchone() or not self.db.execute(
                    'SELECT 1 FROM employee_invites WHERE token_digest=? AND tenant_id=?',(row['digest'],row['tenant_id'])).fetchone():
                raise IdentityError('Invitacion no disponible.')
            account = self.db.execute('SELECT * FROM accounts WHERE email=?',(row['email'],)).fetchone()
            if account and account['verified'] and account['active']:
                return {'login_required':True}
            if account and not account['active']:
                raise IdentityError('Invitacion no disponible.')
            aid = account['id'] if account else uuid.uuid4().hex
            if not account:
                self.db.execute('INSERT INTO accounts(id,email) VALUES (?,?)',(aid,row['email']))
            self.db.execute('UPDATE accounts SET verified=1,password_hash=? WHERE id=?',(encoded,aid))
            self.db.execute("UPDATE identity_tokens SET used=1 WHERE account_id=? AND purpose='verify'",(aid,))
            self._accept_invitation({'id':aid,'email':row['email']},row)
        return {'accepted':True}

    def _accept_invitation(self, account, row):
        if row['email'] != account['email']:
            raise IdentityError('Invitación no disponible para tu usuario.')
        issuer = self._membership(row['issuer_id'],row['tenant_id'])
        if issuer['role'] not in ('owner','admin') or (row['role']=='admin' and issuer['role']!='owner'):
            raise IdentityError('Invitación no disponible para tu usuario.')
        # Never overwrite an existing membership or upgrade its role through
        # a delayed invitation. Role changes require a separate owner action.
        old = self.db.execute('SELECT * FROM memberships WHERE account_id=? AND tenant_id=?',
                              (account['id'],row['tenant_id'])).fetchone()
        if not old:
            self.db.execute('INSERT INTO memberships VALUES (?,?,?,1)',(account['id'],row['tenant_id'],row['role']))
        elif not old['active']:
            raise IdentityError('La membresía requiere revisión del administrador.')
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='employee_invites'").fetchone():
            employee = self.db.execute('SELECT employee_id FROM employee_invites WHERE token_digest=? AND tenant_id=?',
                                       (row['digest'],row['tenant_id'])).fetchone()
            if employee:
                self.db.execute("""CREATE TABLE IF NOT EXISTS employee_memberships (
                    tenant_id TEXT NOT NULL, account_id TEXT NOT NULL, employee_id INTEGER NOT NULL,
                    PRIMARY KEY(tenant_id,account_id), UNIQUE(tenant_id,employee_id))""")
                prior = self.db.execute('SELECT account_id,employee_id FROM employee_memberships WHERE tenant_id=? AND (account_id=? OR employee_id=?)',
                                        (row['tenant_id'],account['id'],employee['employee_id'])).fetchone()
                if prior and (prior['account_id']!=account['id'] or prior['employee_id']!=employee['employee_id']):
                    raise IdentityError('Este empleado ya tiene un acceso asignado.')
                self.db.execute('INSERT OR IGNORE INTO employee_memberships VALUES (?,?,?)',
                                (row['tenant_id'],account['id'],employee['employee_id']))
        if not old and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='invitation_work_permissions'").fetchone():
            permissions = self.db.execute('SELECT hr,payroll FROM invitation_work_permissions WHERE token_digest=?',
                                          (row['digest'],)).fetchone()
            if permissions:
                if issuer['role']!='owner':
                    raise IdentityError('La invitación requiere revisión del propietario.')
                self._save_work_permissions(row['tenant_id'],account['id'],*permissions)
        if not old and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='invitation_business_permissions'").fetchone():
            permissions = self.db.execute('SELECT areas FROM invitation_business_permissions WHERE token_digest=?',
                                          (row['digest'],)).fetchone()
            if permissions:
                if row['role']!='member':
                    raise IdentityError('La invitacion requiere revision del propietario.')
                self._save_business_permissions(row['tenant_id'],account['id'],json.loads(permissions['areas']))
        self.db.execute('UPDATE identity_tokens SET used=1 WHERE digest=?',(row['digest'],))
        self._audit('invitation_accepted',account['id'],row['tenant_id'])

    def revoke_invitation(self, session, tenant_id, email):
        email = email_key(email)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self._account(session)
            member = self._membership(account['id'],tenant_id)
            if member['role'] not in ('owner','admin'):
                raise IdentityError('Operación no autorizada.')
            # Admin cannot invalidate invitations granting another admin role.
            roles = ('member',) if member['role']=='admin' else ('admin','member')
            for role in roles:
                self.db.execute("UPDATE identity_tokens SET used=1 WHERE purpose='invite' AND tenant_id=? AND email=? AND role=?",
                                (tenant_id,email,role))
            self._audit('invitation_revoked',account['id'],tenant_id)
        return {'revoked':True}

    def members(self, session, tenant_id):
        account = self._account(session)
        actor = self._membership(account['id'],tenant_id)
        if actor['role'] not in ('owner','admin'):
            raise IdentityError('Operación no autorizada.')
        rows = self.db.execute('''SELECT a.id,a.email,m.role FROM memberships m JOIN accounts a ON a.id=m.account_id
          WHERE m.tenant_id=? AND m.active=1 AND a.active=1 AND a.verified=1 ORDER BY a.email''',(tenant_id,)).fetchall()
        return [dict(row) for row in rows]

    def change_role(self, session, tenant_id, target_id, role):
        if role not in ('admin','member'):
            raise IdentityError('Rol inválido.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self._account(session)
            actor = self._membership(account['id'],tenant_id)
            target = self._membership(target_id,tenant_id)
            if actor['role']!='owner' or target['role']=='owner':
                raise IdentityError('Operación no autorizada.')
            self.db.execute('UPDATE memberships SET role=? WHERE account_id=? AND tenant_id=?',(role,target_id,tenant_id))
            if role=='member':
                self.db.execute("UPDATE identity_tokens SET used=1 WHERE purpose='invite' AND tenant_id=? AND issuer_id=?",(tenant_id,target_id))
            self._audit('role_changed',account['id'],tenant_id)
        return {'changed':True}

    def remove_member(self, session, tenant_id, target_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self._account(session)
            actor = self._membership(account['id'],tenant_id)
            target = self._membership(target_id,tenant_id)
            if actor['role'] not in ('owner','admin') or target['role']=='owner' or (actor['role']=='admin' and target['role']!='member'):
                raise IdentityError('Operación no autorizada.')
            self.db.execute('UPDATE memberships SET active=0 WHERE account_id=? AND tenant_id=?',(target_id,tenant_id))
            email = self.db.execute('SELECT email FROM accounts WHERE id=?',(target_id,)).fetchone()['email']
            self.db.execute("UPDATE identity_tokens SET used=1 WHERE purpose='invite' AND tenant_id=? AND email=?",(tenant_id,email))
            self.db.execute("UPDATE identity_tokens SET used=1 WHERE purpose='invite' AND tenant_id=? AND issuer_id=?",(tenant_id,target_id))
            self._audit('member_removed',account['id'],tenant_id)
        return {'removed':True}


    def member_has_used_space(self, tenant_id, target_id):
        return bool(self.db.execute("""SELECT 1 FROM identity_audit
            WHERE tenant_id=? AND account_id=? AND event='handoff_consumed' LIMIT 1""",
            (tenant_id,target_id)).fetchone())

    def delete_unused_member(self, session, tenant_id, target_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            actor = self._account(session)
            membership = self._membership(actor['id'],tenant_id)
            target = self._membership(target_id,tenant_id)
            if actor['id']==target_id or membership['role'] not in ('owner','admin') or target['role']!='member':
                raise IdentityError('Este usuario tiene el acceso protegido.')
            if self.member_has_used_space(tenant_id,target_id):
                raise IdentityError('El usuario ya entró a la empresa. Usa Quitar acceso.')
            email = self.db.execute('SELECT email FROM accounts WHERE id=?',(target_id,)).fetchone()['email']
            self.db.execute("UPDATE identity_tokens SET used=1 WHERE tenant_id=? AND purpose='invite' AND (email=? OR issuer_id=?)",
                            (tenant_id,email,target_id))
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('employee_memberships','handoff_tickets','work_permissions','business_permissions'):
                if table in tables:
                    self.db.execute(f'DELETE FROM {table} WHERE tenant_id=? AND account_id=?',(tenant_id,target_id))
            self.db.execute('DELETE FROM memberships WHERE tenant_id=? AND account_id=?',(tenant_id,target_id))
            has_membership = self.db.execute('SELECT 1 FROM memberships WHERE account_id=?',(target_id,)).fetchone()
            has_draft = 'trial_signup_drafts' in tables and self.db.execute('SELECT 1 FROM trial_signup_drafts WHERE account_id=?',(target_id,)).fetchone()
            has_invites = self.db.execute("SELECT 1 FROM identity_tokens WHERE purpose='invite' AND email=? AND used=0 AND expires>?",
                                          (email,self.clock())).fetchone()
            has_other_use = self.db.execute("SELECT 1 FROM identity_audit WHERE account_id=? AND event='handoff_consumed' LIMIT 1",
                                            (target_id,)).fetchone()
            if not any((has_membership,has_draft,has_invites,has_other_use)):
                self.db.execute('DELETE FROM identity_tokens WHERE account_id=? OR issuer_id=?',(target_id,target_id))
                self.db.execute('DELETE FROM identity_sessions WHERE account_id=?',(target_id,))
                self.db.execute('DELETE FROM accounts WHERE id=?',(target_id,))
            self._audit('unused_member_deleted',actor['id'],tenant_id)
        return {'deleted':True}

    business_areas = ('pos','sales','inventory','billing')

    def work_permissions(self, tenant_id, account_id, role):
        company = self.db.execute('SELECT modules FROM tenants WHERE id=?',(tenant_id,)).fetchone()
        if not company:
            return ()
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE name IN ('work_permissions','business_permissions')")}
        result = ()
        if 'payroll_hr' in json.loads(company['modules']):
            if role=='owner':
                result = ('hr','payroll')
            else:
                row = self.db.execute('SELECT hr,payroll FROM work_permissions WHERE tenant_id=? AND account_id=?',
                                      (tenant_id,account_id)).fetchone() if 'work_permissions' in tables else None
                result = tuple(key for key in ('hr','payroll') if row[key]) if row is not None else ('hr',) if role=='admin' else ()
        if role=='member' and 'business_permissions' in tables:
            scoped = self.db.execute('SELECT areas FROM business_permissions WHERE tenant_id=? AND account_id=?',
                                     (tenant_id,account_id)).fetchone()
            if scoped is not None:
                result += ('scoped',*json.loads(scoped['areas']))
        return result

    def _checked_business_areas(self, business):
        if not isinstance(business,(list,tuple)) or any(key not in self.business_areas for key in business):
            raise ValueError('Las areas solicitadas no son validas.')
        return tuple(key for key in self.business_areas if key in business)

    def _save_business_permissions(self, tenant_id, target_id, business):
        self.db.execute("""CREATE TABLE IF NOT EXISTS business_permissions (
            tenant_id TEXT NOT NULL, account_id TEXT NOT NULL, areas TEXT NOT NULL,
            PRIMARY KEY(tenant_id,account_id))""")
        self.db.execute("""INSERT INTO business_permissions VALUES (?,?,?)
            ON CONFLICT(tenant_id,account_id) DO UPDATE SET areas=excluded.areas""",
            (tenant_id,target_id,json.dumps(self._checked_business_areas(business))))

    def set_work_permissions(self, session, tenant_id, target_id, *, hr=None, payroll=None, business=None):
        update_payroll = hr is not None or payroll is not None
        if update_payroll and (type(hr) is not bool or type(payroll) is not bool):
            raise ValueError('Permisos inválidos.')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            account = self._account(session)
            actor = self._membership(account['id'],tenant_id)
            target = self._membership(target_id,tenant_id)
            if target['role']=='owner' or (actor['role']!='owner' and (
                    actor['role']!='admin' or target['role']!='member' or update_payroll or business is None)):
                raise IdentityError('No tienes permiso para asignar estas areas.')
            plan = self.db.execute('SELECT modules FROM tenants WHERE id=?',(tenant_id,)).fetchone()
            if update_payroll and 'payroll_hr' in json.loads(plan['modules']):
                self._save_work_permissions(tenant_id,target_id,hr,payroll)
            elif hr or payroll:
                raise IdentityError('Este plan no incluye Recursos Humanos y Nómina.')
            if business is not None:
                if target['role']!='member':
                    raise IdentityError('Las areas de trabajo se asignan al nivel Empleado.')
                self._save_business_permissions(tenant_id,target_id,business)
            self._audit('work_permissions_changed',account['id'],tenant_id)
        return {'changed':True}

    def _save_work_permissions(self, tenant_id, target_id, hr, payroll):
        self.db.execute("""CREATE TABLE IF NOT EXISTS work_permissions (
            tenant_id TEXT NOT NULL, account_id TEXT NOT NULL,
            hr INTEGER NOT NULL CHECK(hr IN (0,1)), payroll INTEGER NOT NULL CHECK(payroll IN (0,1)),
            PRIMARY KEY(tenant_id,account_id))""")
        self.db.execute("""INSERT INTO work_permissions VALUES (?,?,?,?)
            ON CONFLICT(tenant_id,account_id) DO UPDATE SET hr=excluded.hr,payroll=excluded.payroll""",
            (tenant_id,target_id,hr,payroll))
