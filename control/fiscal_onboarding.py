"""Company-scoped DGII checklist; no browser automation, signing, or emission.

Checkers are trusted backend adapters. A user's checkbox, uploaded certificate,
or another taxpayer's certification cannot complete official verification.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from .identity import IdentityError

STEPS = (
    ('taxpayer','Datos y autorizacion de la empresa','dgii'),
    ('certificate_chain','Vigencia, cadena y revocacion del certificado','pki'),
    ('delegation','Representante autorizado para esta empresa','dgii'),
    ('precertification','Pruebas de datos y comprobantes','dgii'),
    ('reception','HTTPS, recepcion y aprobaciones comerciales','infrastructure'),
    ('declaration','Declaracion jurada confirmada y enviada','dgii'),
    ('certification','Certificacion aprobada por la DGII','dgii'),
    ('sequences','Secuencias e-NCF autorizadas y vigentes','dgii'),
)


@dataclass(frozen=True)
class FiscalContext:
    tenant_id: str
    company_id: int
    tax_id: str
    certificate_id: str
    certificate_sha256: str
    binding: str


@dataclass(frozen=True)
class CheckEvidence:
    binding: str
    source: str
    reference: str
    checked_at: float
    expires_at: float
    status: str = 'passed'


class FiscalOnboarding:
    def __init__(self, identity, vault, checkers=None):
        self.identity=identity;self.vault=vault;self.db=identity.db
        self.checkers=dict(checkers or {})
        if set(self.checkers)-{s[0] for s in STEPS}:
            raise ValueError('Verificador fiscal desconocido.')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS fiscal_setup_checks (
          tenant_id TEXT NOT NULL REFERENCES tenants(id),company_id INTEGER NOT NULL,
          step TEXT NOT NULL,binding TEXT NOT NULL,status TEXT NOT NULL,
          source TEXT NOT NULL,reference TEXT NOT NULL,checked REAL NOT NULL,expires REAL NOT NULL,
          PRIMARY KEY(tenant_id,company_id,step)
        );''')

    def _context(self,session,tenant_id,company_id):
        account,company=self.vault._authorize(session,tenant_id,company_id)
        certificate=self.db.execute('''SELECT id,thumbprint,expires FROM fiscal_certificates
          WHERE tenant_id=? AND company_id=? ORDER BY created DESC,rowid DESC LIMIT 1''',(tenant_id,company_id)).fetchone()
        data={'tenant_id':tenant_id,'company_id':company_id,'tax_id':company['tax_id'],
              'certificate_id':certificate['id'] if certificate else '',
              'certificate_sha256':certificate['thumbprint'] if certificate else ''}
        binding=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return account,FiscalContext(**data,binding=binding),certificate

    def status(self,session,tenant_id,company_id):
        _,context,certificate=self._context(session,tenant_id,company_id)
        now=self.identity.clock();certificate_current=bool(certificate and certificate['expires']>now)
        saved={r['step']:r for r in self.db.execute('SELECT * FROM fiscal_setup_checks WHERE tenant_id=? AND company_id=?',(tenant_id,company_id))}
        steps=[]
        for step,label,source in STEPS:
            row=saved.get(step);state='pending'
            if row and row['binding']==context.binding and row['expires']>now and certificate_current:
                state=row['status']
            steps.append({'id':step,'label':label,'state':state,
                          'requires_user_action':step=='declaration' and state!='passed'})
        missing=[s['id'] for s in steps if s['state']!='passed']
        next_action=('upload_certificate' if not certificate else 'renew_certificate' if not certificate_current
                     else missing[0] if missing else 'adapter_validation_pending')
        return {'tenant_id':tenant_id,'company_id':company_id,
                'certificate_state':'missing' if not certificate else 'current_local' if certificate_current else 'expired',
                'steps':steps,'next_action':next_action,
                'official_checks_passed':not missing and certificate_current,
                'emission_enabled':False,'legal_acceptance_automated':False,
                'message':'La emision requiere ademas un adaptador productivo validado por empresa.'}

    def run_checks(self,session,tenant_id,company_id,steps=None):
        account,context,certificate=self._context(session,tenant_id,company_id)
        if not certificate or certificate['expires']<=self.identity.clock():
            raise IdentityError('Cargue un certificado vigente antes de verificar la configuracion.')
        selected=[s[0] for s in STEPS] if steps is None else steps
        if not isinstance(selected,(list,tuple)) or not selected or len(selected)!=len(set(selected)) or set(selected)-{s[0] for s in STEPS}:
            raise ValueError('Seleccione verificaciones fiscales conocidas.')
        sources={s[0]:s[2] for s in STEPS};results=[]
        for step in selected:
            checker=self.checkers.get(step)
            if not callable(checker):continue
            try:
                evidence=checker(context)
                now=self.identity.clock()
                if (not isinstance(evidence,CheckEvidence) or evidence.binding!=context.binding
                    or evidence.source!=sources[step] or evidence.status not in ('passed','blocked','action_required')
                    or not 0<evidence.checked_at<=now or not now<evidence.expires_at<=certificate['expires']
                    or not re.fullmatch(r'[A-Za-z0-9_.:/ -]{1,200}',evidence.reference or '')):
                    raise ValueError('Evidencia no valida.')
                results.append((step,evidence))
            except Exception:
                # A failed recheck invalidates a prior pass; errors never include
                # adapter responses, signed seeds, certificate bytes, or tokens.
                now=self.identity.clock()
                results.append((step,CheckEvidence(context.binding,sources[step],'verification-failed',now,min(now+300,certificate['expires']),'blocked')))
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            _,current,_=self._context(session,tenant_id,company_id)
            if current.binding!=context.binding:
                raise IdentityError('La empresa o su certificado cambiaron; repita la verificacion.')
            for step,e in results:
                self.db.execute('''INSERT INTO fiscal_setup_checks VALUES(?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(tenant_id,company_id,step) DO UPDATE SET binding=excluded.binding,status=excluded.status,
                  source=excluded.source,reference=excluded.reference,checked=excluded.checked,expires=excluded.expires''',
                  (tenant_id,company_id,step,e.binding,e.status,e.source,e.reference,e.checked_at,e.expires_at))
            self.identity._audit('fiscal_checks_run',account['id'],tenant_id)
        return self.status(session,tenant_id,company_id)
