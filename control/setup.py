"""Company setup drafts and evidence-based checklist. No Odoo configuration writes."""
import json
import re
from .identity import IdentityError

class Setup:
    def __init__(self,identity):
        self.identity=identity;self.db=identity.db
        self.db.executescript('''CREATE TABLE IF NOT EXISTS company_setup_drafts (
          tenant_id TEXT PRIMARY KEY REFERENCES tenants(id),profile TEXT NOT NULL,updated REAL NOT NULL
        );''')
    def save(self,session,tenant_id,profile):
        account=self.identity._account(session);member=self.identity._membership(account['id'],tenant_id)
        if member['role'] not in ('owner','admin'):raise IdentityError('Configuración no autorizada.')
        if not isinstance(profile,dict) or set(profile)!={'name','country','tax_id','address','currency'}:raise ValueError('Datos de empresa incompletos.')
        if not all(isinstance(v,str) for v in profile.values()):raise ValueError('Datos inválidos.')
        clean={k:v.strip() for k,v in profile.items()}
        if not 1<=len(clean['name'])<=150 or not 1<=len(clean['address'])<=255 or clean['country']!='DO' or clean['currency'] not in ('DOP','USD') or not re.fullmatch('[0-9]{9}|[0-9]{11}',clean['tax_id']):raise ValueError('Revise los datos de empresa.')
        with self.db:
            self.db.execute('INSERT INTO company_setup_drafts VALUES (?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET profile=excluded.profile,updated=excluded.updated',(tenant_id,json.dumps(clean),self.identity.clock()))
            self.identity._audit('setup_draft_saved',account['id'],tenant_id)
        return {'saved':True,'applied_to_odoo':False,'tax_id_verified_external':False}
    def status(self,session,tenant_id):
        account=self.identity._account(session);self.identity._membership(account['id'],tenant_id)
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        profile=self.db.execute('SELECT 1 FROM company_setup_drafts WHERE tenant_id=?',(tenant_id,)).fetchone()
        ready=False
        if 'preparation_jobs' in tables:
            from .onboarding import Onboarding
            ready=Onboarding(self.identity).status(session,tenant_id)['local_ready'] if self.db.execute('SELECT 1 FROM preparation_jobs WHERE tenant_id=?',(tenant_id,)).fetchone() else False
        members=self.db.execute('SELECT count(*) FROM memberships WHERE tenant_id=? AND active=1',(tenant_id,)).fetchone()[0]
        applied=bool('trial_company_parameters' in tables and self.db.execute('SELECT 1 FROM trial_company_parameters WHERE tenant_id=?',(tenant_id,)).fetchone())
        return {'account_verified':True,'workspace_ready_local':ready,'company_details_saved':bool(profile),
                'team_invited_and_joined':members>1,'configuration_applied_to_odoo':False,
                'basic_company_parameters_applied_to_odoo':applied,
                'tax_id_verified_external':False,'fiscal_emission_enabled':False}
