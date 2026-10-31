"""Company-scoped encrypted certificate custody. No DGII network or emission.

The company resolver is trusted backend code, never request-supplied tax data.
Only local key/certificate/identity checks are performed; state stays pending.
"""
import base64
from datetime import datetime,timezone
import hashlib
import json
import re
import secrets
import uuid
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID,ObjectIdentifier
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from .identity import IdentityError

def load_identity(p12,password):
    # Certificate checks do not depend on XML/lxml or import an Odoo addon.
    key,cert,_=pkcs12.load_key_and_certificates(p12,password)
    if not isinstance(key,rsa.RSAPrivateKey) or cert is None or key.key_size<2048:raise ValueError('Identidad inválida.')
    now=datetime.now(timezone.utc)
    start=cert.not_valid_before_utc if hasattr(cert,'not_valid_before_utc') else cert.not_valid_before.replace(tzinfo=timezone.utc)
    end=cert.not_valid_after_utc if hasattr(cert,'not_valid_after_utc') else cert.not_valid_after.replace(tzinfo=timezone.utc)
    if not start<=now<=end or not cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature:raise ValueError('Certificado no vigente o no apto para firma.')
    if key.public_key().public_numbers()!=cert.public_key().public_numbers():raise ValueError('Clave y certificado no corresponden.')
    return key,cert

class MemoryKeys:
    """Test fixture. Production must supply a separate durable key service."""
    def __init__(self):self.keys={}
    def create(self,scope):
        if scope in self.keys:raise ValueError('Clave ya existente.')
        self.keys[scope]=secrets.token_bytes(32)
        return self.keys[scope]
    def get(self,scope):return self.keys[scope]


class DirectoryKeys:
    """Protected WSL fixture, not a substitute for a commercial KMS/HSM."""
    def __init__(self,directory):
        if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise RuntimeError('Solo WSL root de laboratorio.')
        self.directory=Path(directory)
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(self.directory,0o700)
    def path(self,scope):return self.directory/(hashlib.sha256(scope.encode()).hexdigest()+'.key')
    def create(self,scope):
        key=secrets.token_bytes(32)
        fd=os.open(self.path(scope),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as handle:handle.write(key)
        return key
    def get(self,scope):
        fd=os.open(self.path(scope),os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as handle:key=handle.read()
        if len(key)!=32:raise ValueError('Clave no disponible.')
        return key


class FiscalVault:
    def __init__(self,identity,keys,resolve_company):
        self.identity=identity;self.db=identity.db;self.keys=keys;self.resolve_company=resolve_company
        self.db.executescript('''CREATE TABLE IF NOT EXISTS fiscal_certificates (
          id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),company_id INTEGER NOT NULL,
          cipher BLOB NOT NULL,nonce BLOB NOT NULL,expires REAL NOT NULL,thumbprint TEXT NOT NULL,
          created REAL NOT NULL,state TEXT NOT NULL CHECK(state='pending_validation')
        );''')

    def _authorize(self,session,tenant_id,company_id):
        account=self.identity._account(session)
        membership=self.identity._membership(account['id'],tenant_id)
        if membership['role'] not in ('owner','admin') or type(company_id) is not int or company_id<=0:
            raise IdentityError('Configuración fiscal no autorizada.')
        company=self.resolve_company(tenant_id,company_id)
        if not company or not re.fullmatch(r'[0-9]{9}|[0-9]{11}',company.get('tax_id','')):
            raise IdentityError('La empresa requiere identificación fiscal configurada.')
        return account,company

    def store(self,session,tenant_id,company_id,p12,password):
        account,company=self._authorize(session,tenant_id,company_id)
        if not isinstance(p12,bytes) or not 1<=len(p12)<=5_000_000 or not isinstance(password,str) or len(password)>1024:
            raise IdentityError('Material fiscal inválido.')
        try:
            key,cert=load_identity(p12,password.encode())
            identifiers=[]
            for oid in (NameOID.SERIAL_NUMBER,ObjectIdentifier('2.5.4.97')):
                identifiers += [a.value for a in cert.subject.get_attributes_for_oid(oid)]
            # Conservative exact identity match. Do not infer a tax ID from CN
            # or accept an arbitrary certificate merely because its key opens.
            if company['tax_id'] not in identifiers:raise ValueError()
            expires=(cert.not_valid_after_utc if hasattr(cert,'not_valid_after_utc') else cert.not_valid_after.replace(tzinfo=timezone.utc)).timestamp()
            from cryptography.hazmat.primitives import hashes
            thumb=cert.fingerprint(hashes.SHA256()).hex()
        except Exception:raise IdentityError('No se pudo validar certificado, contraseña e identidad fiscal de la empresa.') from None
        version=uuid.uuid4().hex;scope=tenant_id+':'+str(company_id)+':'+version
        encryption_key=self.keys.create(scope);nonce=secrets.token_bytes(12)
        payload=json.dumps({'p12':base64.b64encode(p12).decode(),'password':password}).encode()
        cipher=AESGCM(encryption_key).encrypt(nonce,payload,scope.encode())
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            # Recheck membership after parsing/encryption, before committing.
            self._authorize(session,tenant_id,company_id)
            self.db.execute("INSERT INTO fiscal_certificates VALUES (?,?,?,?,?,?,?,?, 'pending_validation')",
              (version,tenant_id,company_id,cipher,nonce,expires,thumb,self.identity.clock()))
            self.identity._audit('fiscal_certificate_stored',account['id'],tenant_id)
        return {'certificate_id':version,'state':'pending_validation','emission_enabled':False}

    def status(self,session,tenant_id,company_id):
        self._authorize(session,tenant_id,company_id)
        row=self.db.execute('SELECT id,expires,state FROM fiscal_certificates WHERE tenant_id=? AND company_id=? ORDER BY created DESC,rowid DESC LIMIT 1',(tenant_id,company_id)).fetchone()
        if not row:return {'state':'not_started','emission_enabled':False}
        return {'certificate_id':row['id'],'state':'expired' if row['expires']<=self.identity.clock() else row['state'],
                'expires':row['expires'],'renewal_due':row['expires']-self.identity.clock()<30*86400,'emission_enabled':False}

    def _load_for_worker(self,tenant_id,company_id,version):
        # Private internal method: no HTTP mapping, no owner download endpoint.
        row=self.db.execute('SELECT * FROM fiscal_certificates WHERE id=? AND tenant_id=? AND company_id=?',(version,tenant_id,company_id)).fetchone()
        if not row or row['expires']<=self.identity.clock():raise IdentityError('Certificado no disponible.')
        scope=tenant_id+':'+str(company_id)+':'+version
        try:
            payload=AESGCM(self.keys.get(scope)).decrypt(row['nonce'],row['cipher'],scope.encode())
            data=json.loads(payload)
            return base64.b64decode(data['p12'],validate=True),data['password']
        except Exception:raise IdentityError('No se pudo autenticar el material fiscal.') from None
