from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control.identity import IdentityService,IdentityError
from control.onboarding import Onboarding
from control.access_broker import BackendSession

class Prepared:
    def lock(self,tenant):return nullcontext()
    def __getattr__(self,name):return lambda snapshot:None

class AccessBrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.messages=[]
        self.identity=IdentityService(Path(self.tmp.name)/'control.sqlite3',self.messages.append)
        def account(email):
            self.identity.register(email);self.identity.complete_registration(self.messages[-1]['token'],'Clave ficticia broker 2026')
            return self.identity.login(email,'Clave ficticia broker 2026')['session']
        self.owner=account('owner@example.test');self.member=account('member@example.test')
        self.tenant=self.identity.create_company(self.owner,'empresa-broker',[],'one')
        self.jobs=Onboarding(self.identity);job=self.jobs.request(self.owner,self.tenant['id'])
        self.jobs.run(job['job_id'],Prepared())
        self.identity.invite(self.owner,self.tenant['id'],'member@example.test')
        self.identity.accept_invitation(self.member,self.messages[-1]['token'])
        self.claims=self.jobs.consume_handoff(self.member,self.jobs.issue_handoff(self.member,self.tenant['id'])['ticket'])
        self.backend=BackendSession(self.jobs,self.member,self.claims,{},None,'http://127.0.0.1:1',7)
    def tearDown(self):self.identity.close();self.tmp.cleanup()

    def test_existing_backend_session_stops_on_membership_removal(self):
        with patch('control.access_broker._rpc',return_value='ok') as remote:
            self.assertEqual('ok',self.backend.rpc('res.company','search_read'))
            self.identity.remove_member(self.owner,self.tenant['id'],self.claims['account_id'])
            with self.assertRaises(IdentityError):self.backend.rpc('res.company','search_read')
            self.assertEqual(remote.call_count,1)

    def test_role_change_and_logout_require_new_entry(self):
        self.identity.change_role(self.owner,self.tenant['id'],self.claims['account_id'],'admin')
        with patch('control.access_broker._rpc') as remote:
            with self.assertRaises(IdentityError):self.backend.rpc('res.company','search_read')
            remote.assert_not_called()
        self.identity.logout(self.member)
        with self.assertRaises(IdentityError):self.backend.rpc('res.company','search_read')

    def test_private_methods_and_path_injection_never_reach_backend(self):
        with patch('control.access_broker._rpc') as remote:
            for model,method in [('res.users','_check_credentials'),('../web','read'),('res.company','read?x=1')]:
                with self.assertRaises(IdentityError):self.backend.rpc(model,method)
            remote.assert_not_called()
