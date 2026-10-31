from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from control.identity import IdentityService,IdentityError
from control.onboarding import Onboarding,PreparationError,STEPS
from control.bridge_protocol import mint,verify

class FakeAdapter:
    def __init__(self,fail=None):self.fail=fail;self.resources=set()
    @contextmanager
    def lock(self,tenant):yield
    def __getattr__(self,step):
        if step not in STEPS:raise AttributeError(step)
        def ensure(snapshot):
            if self.fail==step:raise RuntimeError('fictional failure with sensitive details')
            self.resources.add((snapshot['tenant_id'],step))
        return ensure

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.messages=[];self.now=2000000000
        self.identity=IdentityService(Path(self.tmp.name)/'control.sqlite3',self.messages.append,clock=lambda:self.now)
        self.jobs=Onboarding(self.identity)
        self.owner=self.account('owner@example.test');self.worker=self.account('worker@example.test')
        self.tenant=self.identity.create_company(self.owner,'empresa-onboarding',['jenifer_ai'],'one')
    def tearDown(self):self.identity.close();self.tmp.cleanup()
    def account(self,email):
        self.identity.register(email);self.identity.complete_registration(self.messages[-1]['token'],'Clave ficticia onboarding 2026')
        return self.identity.login(email,'Clave ficticia onboarding 2026')['session']
    def ready(self):
        job=self.jobs.request(self.owner,self.tenant['id']);adapter=FakeAdapter()
        self.jobs.run(job['job_id'],adapter)
        return job,adapter
    def join(self):
        self.identity.invite(self.owner,self.tenant['id'],'worker@example.test')
        self.identity.accept_invitation(self.worker,self.messages[-1]['token'])

    def test_owner_request_is_idempotent_and_no_work_happens_in_request(self):
        first=self.jobs.request(self.owner,self.tenant['id'])
        self.assertEqual(first,self.jobs.request(self.owner,self.tenant['id']))
        self.assertEqual(first['status'],'queued');self.assertFalse(first['public_access'])
        self.assertFalse(first['completed_steps'])
        with self.assertRaises(IdentityError):self.jobs.request(self.worker,self.tenant['id'])
        self.join()
        with self.assertRaises(IdentityError):self.jobs.request(self.worker,self.tenant['id'])

    def test_each_failure_recovers_without_duplicate_resources(self):
        job=self.jobs.request(self.owner,self.tenant['id'])
        for step in STEPS:
            with self.subTest(step=step):
                adapter=FakeAdapter(fail=step)
                with self.assertRaises(PreparationError):self.jobs.run(job['job_id'],adapter)
                self.assertEqual(self.jobs.status(self.owner,self.tenant['id'])['status'],'failed')
                self.assertEqual(self.jobs.status(self.owner,self.tenant['id'])['current_step'],step)
                adapter.fail=None
                self.jobs.run(job['job_id'],adapter);self.jobs.run(job['job_id'],adapter)
                self.assertEqual(len(adapter.resources),5)
                self.assertEqual(self.jobs.status(self.owner,self.tenant['id'])['status'],'ready_local')

    def test_product_change_is_rejected_instead_of_silent_update(self):
        job=self.jobs.request(self.owner,self.tenant['id'])
        with patch('control.onboarding.installation_profile',return_value={'fingerprint':'different'}):
            with self.assertRaises(PreparationError):self.jobs.request(self.owner,self.tenant['id'])
            with self.assertRaises(PreparationError):self.jobs.run(job['job_id'],FakeAdapter())

    def test_handoff_requires_readiness_session_and_current_membership(self):
        with self.assertRaises(PreparationError):self.jobs.issue_handoff(self.owner,self.tenant['id'])
        self.ready();self.join()
        ticket=self.jobs.issue_handoff(self.worker,self.tenant['id'])['ticket']
        with self.assertRaises(IdentityError):self.jobs.consume_handoff(self.owner,ticket)
        self.identity.remove_member(self.owner,self.tenant['id'],self.identity._account(self.worker)['id'])
        with self.assertRaises(IdentityError):self.jobs.consume_handoff(self.worker,ticket)

    def test_ticket_is_single_use_expiring_and_hashed(self):
        self.ready();result=self.jobs.issue_handoff(self.owner,self.tenant['id']);ticket=result['ticket']
        self.assertNotIn(ticket,'\n'.join(self.identity.db.iterdump()))
        claims=self.jobs.consume_handoff(self.owner,ticket)
        self.assertEqual(claims['tenant_id'],self.tenant['id'])
        with self.assertRaises(IdentityError):self.jobs.consume_handoff(self.owner,ticket)
        ticket=self.jobs.issue_handoff(self.owner,self.tenant['id'])['ticket'];self.now+=60
        with self.assertRaises(IdentityError):self.jobs.consume_handoff(self.owner,ticket)

    def test_tickets_are_bound_to_original_session_even_for_same_account(self):
        self.ready();ticket=self.jobs.issue_handoff(self.owner,self.tenant['id'])['ticket']
        second=self.identity.login('owner@example.test','Clave ficticia onboarding 2026')['session']
        with self.assertRaises(IdentityError):self.jobs.consume_handoff(second,ticket)

    def test_assertion_protocol_rejects_cross_tenant_tamper_and_expiry(self):
        key=secrets.token_bytes(32);tenant='a'*32;account='b'*32
        token=mint(key,tenant,account,clock=lambda:self.now)
        self.assertEqual(verify(key,token,tenant,'saas_'+account,clock=lambda:self.now)['sub'],account)
        for wrong in [token+'x','not-a-token',token[:-2]+'00']:
            with self.assertRaises(ValueError):verify(key,wrong,tenant,'saas_'+account,clock=lambda:self.now)
        with self.assertRaises(ValueError):verify(key,token,'c'*32,'saas_'+account,clock=lambda:self.now)
        with self.assertRaises(ValueError):verify(secrets.token_bytes(32),token,tenant,'saas_'+account,clock=lambda:self.now)
        self.now+=30
        with self.assertRaises(ValueError):verify(key,token,tenant,'saas_'+account,clock=lambda:self.now)
