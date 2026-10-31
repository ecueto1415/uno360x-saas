"""Actual signup -> queued preparation -> separate Odoo -> central handoff.

Two fictional spaces, private WSL networks, no DNS/SMTP/payment/production.
May take a few minutes on first run; retries reuse the same identities/resources.
"""
import json
import os
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter,STATE
from tenants import protected
from control_state import control_database
from control.identity import IdentityService,IdentityError
from control.onboarding import Onboarding
from control.access_broker import open_space


def main():
    adapter=LocalAdapter()
    os.umask(0o077)
    mailbox=[]
    identity=IdentityService(control_database(),mailbox.append)
    jobs=Onboarding(identity)
    try:
        def account(email,filename):
            password=protected(STATE/filename,secrets.token_urlsafe(32)).read_text()
            row=identity.db.execute('SELECT verified FROM accounts WHERE email=?',(email,)).fetchone()
            if not row or not row['verified']:
                identity.register(email)
                identity.complete_registration(mailbox[-1]['token'],password)
            return identity.login(email,password)['session']
        owner=account('owner-auto@example.test','owner-password')
        member=account('member-auto@example.test','member-password')
        results=[];companies=[]
        for slug,modules in [('auto-empresa-alfa',['jenifer_ai']),('auto-empresa-beta',['payroll_hr','projects_services'])]:
            tenant=identity.create_company(owner,slug,modules,'automatic-'+slug)
            job=jobs.request(owner,tenant['id'])
            print('Preparando cliente ficticio:',slug,flush=True)
            jobs.run(job['job_id'],adapter)
            assert jobs.status(owner,tenant['id'])['local_ready']
            same=jobs.request(owner,tenant['id'])
            assert same['job_id']==job['job_id']
            companies.append(tenant)
            ticket=jobs.issue_handoff(owner,tenant['id'])['ticket']
            backend=open_space(jobs,owner,ticket,adapter)
            company=backend.rpc('res.company','search_read',[],{'fields':['name'],'limit':10})
            assert len(company)==1 and company[0]['name']==slug+' (LABORATORIO)'
            user=backend.rpc('res.users','read',[[backend.uid]],{'fields':['login']})
            assert user[0]['login']=='saas_'+identity._account(owner)['id']
            assert backend.uid not in (1,2)
            try:jobs.consume_handoff(owner,ticket)
            except IdentityError:pass
            else:raise AssertionError('Ticket reutilizado')
            results.append({'company':slug,'preparation':'ready_local','owner_odoo_login':True,
                            'technical_admin_used':False,'public_access':False})
        alfa,beta=companies
        identity.invite(owner,alfa['id'],'member-auto@example.test')
        member_id=identity._account(member)['id']
        existing=identity.db.execute('SELECT active FROM memberships WHERE account_id=? AND tenant_id=?',(member_id,alfa['id'])).fetchone()
        # Previous demo runs deliberately removed this membership; restore only
        # this fictional fixture through an explicit local setup transaction.
        if existing and not existing['active']:
            with identity.db:identity.db.execute('DELETE FROM memberships WHERE account_id=? AND tenant_id=?',(member_id,alfa['id']))
        identity.accept_invitation(member,mailbox[-1]['token'])
        member_backend=open_space(jobs,member,jobs.issue_handoff(member,alfa['id'])['ticket'],adapter)
        assert member_backend.rpc('res.users','read',[[member_backend.uid]],{'fields':['login']})[0]['login']=='saas_'+member_id
        try:member_backend.rpc('ir.config_parameter','search_read',[],{'fields':['key'],'limit':1})
        except IdentityError:settings_blocked=True
        else:raise AssertionError('Un miembro obtuvo acceso a configuración técnica')
        try:jobs.issue_handoff(member,beta['id'])
        except IdentityError:other_blocked=True
        else:raise AssertionError('Acceso cruzado no bloqueado')
        identity.remove_member(owner,alfa['id'],member_id)
        try:member_backend.rpc('res.company','search_read',[],{'fields':['name']})
        except IdentityError:revocation=True
        else:raise AssertionError('Retirada no aplicada')
        report={'mode':'real_local_lab','companies':results,'central_owner_company_count':len(identity.companies(owner)),
                'member_odoo_login':True,'other_company_blocked':other_blocked,'existing_broker_session_blocked_after_removal':revocation,
                'member_settings_access_blocked':settings_blocked,
                'real_emails_sent':False,'dns_created':False,'payments_enabled':False}
        (STATE/'verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:identity.close();mailbox.clear()


if __name__=='__main__':main()
