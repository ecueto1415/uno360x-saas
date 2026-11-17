"""Run the production queue for one provisioned SaaS tenant/company.

Run via the service manager with systemd credentials scope.json, identity.p12
and password. The scope contains tenant_id, company_id, rnc and environment.
Only environment ecf is allowed. Never run this worker in certification QA.
"""
import base64
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3

from certification.xmlsig import load_identity
from deployment.shared_adapter import SharedHostAdapter
from fiscal.trust import validate_certificate

DATABASE = Path('/var/lib/uno360x-saas/control/control.sqlite3')
TENANT_ROOT = Path('/var/lib/uno360x-saas/tenants')


def main():
    credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
    scope = json.loads((credentials / 'scope.json').read_bytes())
    tenant = scope['tenant_id']
    company = scope['company_id']
    issuer = scope['rnc']
    if (scope.get('environment') != 'ecf' or not re.fullmatch('[0-9a-f]{32}', tenant)
            or type(company) is not int or company < 1 or not re.fullmatch('[0-9]{9}|[0-9]{11}', issuer)):
        raise ValueError('Alcance fiscal productivo inválido.')
    with sqlite3.connect(f'file:{DATABASE}?mode=ro', uri=True) as db:
        record = db.execute(
            "SELECT snapshot FROM preparation_jobs WHERE tenant_id=? AND status='ready_local'", (tenant,),
        ).fetchone()
    if not record:
        raise ValueError('Empresa SaaS no preparada.')
    snapshot = json.loads(record[0])
    if snapshot['tenant_id'] != tenant:
        raise ValueError('El destino no corresponde a la credencial.')
    lock_file = TENANT_ROOT / tenant / 'fiscal-production-worker.lock'
    with lock_file.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        adapter = SharedHostAdapter()
        app = adapter.names(snapshot)['app']
        adapter.check_container(app, snapshot)
        p12 = (credentials/'identity.p12').read_bytes()
        password = (credentials/'password').read_bytes()
        _, certificate = load_identity(p12, password)
        validate_certificate(certificate, Path(os.environ['UNO360X_FISCAL_TRUST']))
        secret = {
            'tenant': tenant, 'company': company, 'issuer': issuer,
            'p12': base64.b64encode(p12).decode(),
            'password': base64.b64encode(password).decode(),
        }
        # No credentials in CLI args, configuration, Odoo DB, or command logs.
        code = 'scope = ' + repr(secret) + '\n' + '''
import base64
from odoo.addons.uno360x_ecf_core.builder import rnc
from odoo.addons.uno360x_ecf_core.dgii_client import DGIIError
from odoo.addons.uno360x_ecf_core.issuance import connect
identity=env['uno360x.tenant.identity'].search([])
company=env['res.company'].browse(scope['company']).exists()
assert len(identity)==1 and identity.tenant_id==scope['tenant'] and company
assert rnc(company.vat,'RNC')==scope['issuer'] and env.cr.dbname.startswith('tenant_')
if company.uno360x_ecf_enabled:
 p12=base64.b64decode(scope['p12'],validate=True)
 password=base64.b64decode(scope['password'],validate=True)
 model=env['uno360x.ecf.issue']
 domain=[('company_id','=',company.id),('issuer','=',scope['issuer'])]
 for document in model.search(domain+[('state','=','queued')],limit=5,order='id'):
  document._dispatch(p12,password,company)
 waiting=model.search(domain+[('state','in',['sent','uncertain'])],limit=5,order='write_date,id')
 if waiting:
  client=connect(p12,password)
  for document in waiting:
   if document.fingerprint==company.uno360x_ecf_fingerprint:
    try:
     document._consult(client)
    except DGIIError:
     continue
  env.cr.commit()
'''
        result = adapter.run('exec','-i',app,'odoo','shell','-c','/etc/odoo/odoo.conf','--no-http',
                             input=code,check=False)
        if result.returncode:
            raise RuntimeError('El trabajador fiscal no completó el ciclo. Revisar el estado en UNO360X.')


if __name__ == '__main__':
    main()
