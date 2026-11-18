"""Process one explicitly provisioned SaaS issuer without network in Odoo."""
import base64
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import fcntl
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from types import ModuleType

from certification.xmlsig import load_identity
from deployment.shared_adapter import SharedHostAdapter
from fiscal.trust import validate_certificate
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
DATABASE = Path('/var/lib/uno360x-saas/control/control.sqlite3')
TENANT_ROOT = Path('/var/lib/uno360x-saas/tenants')


def load_fiscal():
    # Host worker uses the same fiscal code without importing the Odoo ORM.
    package = ModuleType('_uno360x_worker_fiscal')
    package.__path__ = [str(ROOT/'addons/uno360x_ecf_core')]
    sys.modules[package.__name__] = package
    return [importlib.import_module(package.__name__+'.'+module)
            for module in ('issuance','dgii_client','rfce')]


def sql_text(value):
    return "convert_from(decode('%s','hex'),'UTF8')" % str(value).encode().hex()


class Queue:
    def __init__(self, sql, tenant, company, issuer):
        self.sql = sql
        self.scope = f"""q.company_id={int(company)} AND q.issuer={sql_text(issuer)}
            AND EXISTS (SELECT 1 FROM uno360x_tenant_identity i WHERE i.tenant_id={sql_text(tenant)})
            AND EXISTS (SELECT 1 FROM res_company c JOIN res_partner p ON p.id=c.partner_id
                 WHERE c.id=q.company_id AND regexp_replace(p.vat,'[[:space:]-]','','g')=q.issuer
                 AND c.uno360x_ecf_enabled AND c.uno360x_ecf_fingerprint=q.fingerprint)"""

    def pending(self):
        return json.loads(self.sql(f"""
            SELECT COALESCE(json_agg(pending),'[]'::json)::text FROM (
                SELECT q.id,q.encf,q.issuer,q.fingerprint,q.payload,q.state,q.track_id,
                       convert_from(q.signed_xml,'UTF8') AS signed_xml,q.signed_sha256,
                       q.signed_summary IS NOT NULL AS is_summary
                FROM uno360x_ecf_issue q WHERE ({self.scope}) AND (
                    q.state='queued' OR (
                        q.state='sent' AND q.track_id IS NOT NULL
                        AND q.write_date <= (now() AT TIME ZONE 'UTC') - interval '8 seconds'
                    ) OR (
                        (q.state='uncertain' OR (q.state='sent' AND q.track_id IS NULL))
                        AND q.write_date <= (now() AT TIME ZONE 'UTC') - interval '2 minutes'
                    ))
                ORDER BY (q.state='queued') DESC,q.write_date,q.id LIMIT 5
            ) pending;"""))

    def change(self, doc, assignments):
        write = ', '.join(assignments + ["write_date=(now() AT TIME ZONE 'UTC')"])
        result = self.sql(f"""
            WITH change AS (
                UPDATE uno360x_ecf_issue q SET {write}
                WHERE q.id={int(doc['id'])} AND q.state={sql_text(doc['state'])}
                 AND q.encf={sql_text(doc['encf'])} AND ({self.scope}) RETURNING q.id
            ) SELECT count(*) FROM change;""")
        return result == '1'


def dispatch(queue, doc, client, issuance, api, rfce, p12, password):
    try:
        xml = issuance.prepare_signed(doc['payload'], doc['encf'], doc['issuer'],
                                      doc['fingerprint'], p12, password)
        summary = rfce.build_signed_summary(xml,p12,password) if rfce.requires_summary(doc['payload']) else None
    except (ValueError, etree.LxmlError):
        queue.change(doc, ["state='blocked'"])
        return
    changes = ["state='uncertain'", "signed_xml=decode('%s','hex')" % base64.b64encode(xml).hex(),
               "signed_sha256="+sql_text(sha256(xml).hexdigest())]
    if summary:
        changes.append("signed_summary=decode('%s','hex')" % base64.b64encode(summary).hex())
    if not queue.change(doc, changes):
        return
    # The uncertain state is committed before the only non-idempotent request.
    doc['state'] = 'uncertain'
    try:
        if summary:
            result = ["state="+sql_text(client.submit_summary(summary,doc['issuer'],doc['encf']))]
        else:
            track = client.submit(xml,doc['issuer'],doc['encf'])['trackId']
            result = ["state='sent'","track_id="+sql_text(track)]
    except api.SubmissionUnknown:
        return
    if queue.change(doc, result) and not summary:
        consult(queue, dict(doc, state='sent', track_id=track), client, api, rfce)


def consult(queue, doc, client, api, rfce):
    try:
        if doc['is_summary']:
            signed=base64.b64decode(doc['signed_xml'],validate=True)
            if sha256(signed).hexdigest()!=doc['signed_sha256']:
                raise api.DGIIError('XML de conciliación alterado.')
            state=client.lookup_summary(doc['issuer'],doc['encf'],rfce.security_code(signed))
            queue.change(doc, ['state='+sql_text(state)])
            return
        track=doc['track_id']
        if not track:
            tracks={str(row['trackId']) for row in client.tracks(doc['issuer'],doc['encf']) if row.get('trackId')}
            if len(tracks)!=1:
                queue.change(doc, [])
                return
            track=tracks.pop()
        state=api.validate_result(client.result(track),doc['issuer'],doc['encf'],track)
        queue.change(doc, ['state='+sql_text(state),'track_id='+sql_text(track)] if state else [])
    except ValueError:
        queue.change(doc, [])


def process_document(queue, doc, issuance, api, rfce, p12, password):
    # Each task owns its authenticated client. Never share a token/session
    # between concurrent requests or across companies.
    client = issuance.connect(p12, password)
    if doc['state'] == 'queued':
        dispatch(queue, doc, client, issuance, api, rfce, p12, password)
    else:
        consult(queue, doc, client, api, rfce)


def process_pending(queue, documents, issuance, api, rfce, p12, password):
    """Fill five issuer slots, including arrivals while other sends are active."""
    deadline = time.monotonic() + 60
    processed = set()
    failures = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        running = {}
        while documents or running:
            for doc in documents:
                if len(running) == 5:
                    break
                if doc['id'] in processed:
                    continue
                processed.add(doc['id'])
                future = executor.submit(
                    process_document, queue, doc, issuance, api, rfce, p12, password
                )
                running[future] = doc['id']
            if not running:
                break
            done, _ = wait(running, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in done:
                running.pop(future)
                try:
                    future.result()
                except Exception as error:
                    failures.append(type(error).__name__)
            # Bound each activation so a busy business cannot keep the
            # oneshot service running beyond its normal timeout.
            documents = queue.pending() if time.monotonic() < deadline else []
    if failures:
        raise RuntimeError('Fiscal worker tasks failed: ' + ', '.join(failures))


def main():
    credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
    scope = json.loads((credentials/'scope.json').read_bytes())
    tenant, company, issuer = scope['tenant_id'], scope['company_id'], scope['rnc']
    if (len(sys.argv)!=2 or sys.argv[1]!=tenant or scope.get('environment')!='ecf'
            or not re.fullmatch('[0-9a-f]{32}',tenant) or type(company) is not int
            or company<1 or not re.fullmatch('[0-9]{9}|[0-9]{11}',issuer)):
        raise ValueError('Alcance fiscal productivo inválido.')
    with sqlite3.connect(f'file:{DATABASE}?mode=ro',uri=True) as db:
        record=db.execute("SELECT snapshot FROM preparation_jobs WHERE tenant_id=? AND status='ready_local'",(tenant,)).fetchone()
    if not record:
        raise ValueError('Empresa SaaS no preparada.')
    snapshot=json.loads(record[0])
    if snapshot['tenant_id']!=tenant:
        raise ValueError('El destino no corresponde a la credencial.')
    with (TENANT_ROOT/tenant/'fiscal-production-worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        adapter=SharedHostAdapter()
        name=adapter.names(snapshot)['role']
        if not re.fullmatch(r'tenant_[0-9a-f]{32}',name):
            raise ValueError('La base no pertenece al SaaS.')
        queue=Queue(lambda query:adapter.sql(snapshot,query),tenant,company,issuer)
        documents=queue.pending()
        if not documents:
            return
        p12=(credentials/'identity.p12').read_bytes()
        password=(credentials/'password').read_bytes()
        _,cert=load_identity(p12,password)
        validate_certificate(cert,Path(os.environ['UNO360X_FISCAL_TRUST']))
        issuance,api,rfce=load_fiscal()
        process_pending(queue,documents,issuance,api,rfce,p12,password)


if __name__=='__main__':
    main()
