"""Disposable end-to-end account demo with an in-memory fake mailbox."""
import json
from pathlib import Path
import secrets
import tempfile

from .identity import IdentityService,IdentityError
from .provisioning import build_plan


def main():
    messages=[]
    password=secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix='uno360x-identity-demo-') as directory:
        service=IdentityService(Path(directory)/'identity.sqlite3',messages.append)
        try:
            def account(email):
                service.register(email)
                service.complete_registration(messages[-1]['token'],password)
                return service.login(email,password)['session']
            owner=account('owner@example.test')
            worker=account('worker@example.test')
            alfa=service.create_company(owner,'demo-empresa-alfa',['jenifer_ai'],'alfa')
            beta=service.create_company(owner,'demo-empresa-beta',['projects_services'],'beta')
            assert not service.companies(worker)
            service.invite(owner,alfa['id'],'worker@example.test')
            service.accept_invitation(worker,messages[-1]['token'])
            assert len(service.companies(worker))==1
            try:service.select_company(worker,beta['id'])
            except IdentityError:blocked=True
            else:raise AssertionError('Aislamiento de membresías falló')
            service.request_reset('worker@example.test')
            service.reset_password(messages[-1]['token'],secrets.token_urlsafe(24))
            try:service.companies(worker)
            except IdentityError:revoked=True
            else:raise AssertionError('Sesión antigua no revocada')
            profile=build_plan(service.registry,alfa['hostname'])
            print(json.dumps({'mode':'disposable_local_demo','verified_owner':True,
              'owner_companies':len(service.companies(owner)),'invited_member_company_count':1,
              'other_company_blocked':blocked,'reset_revoked_old_session':revoked,
              'reserved_plan_addons':sorted(profile['installation']['addons']),
              'real_emails_sent':False,'real_instances_created':False,
              'odoo_single_sign_on':False},indent=2))
        finally:service.close()


if __name__=='__main__':main()
