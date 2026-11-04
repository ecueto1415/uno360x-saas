import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control.identity import IdentityService,IdentityError,GENERIC,VERIFY_TTL,RESET_TTL,SESSION_TTL,INVITE_TTL,email_key

PASSWORD='Clave ficticia de prueba 2026'
NEW_PASSWORD='Otra clave ficticia de prueba 2026'


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'identity.sqlite3'
        self.messages=[]
        self.now=2000000000
        self.service=IdentityService(self.path,self.messages.append,clock=lambda:self.now)

    def tearDown(self):
        self.service.close();self.tmp.cleanup()

    def account(self,email):
        self.assertEqual(self.service.register(email),GENERIC)
        self.service.complete_registration(self.messages[-1]['token'],PASSWORD)
        return self.service.login(email,PASSWORD)['session']

    def company(self,session,slug='empresa-alfa'):
        return self.service.create_company(session,slug,[],'create-'+slug)

    def test_registration_requires_verified_email_and_no_secret_in_database(self):
        self.service.register('Owner@Example.test')
        token=self.messages[-1]['token']
        with self.assertRaises(IdentityError):self.service.login('owner@example.test',PASSWORD)
        self.assertEqual(self.service.complete_registration(token,PASSWORD),{'verified':True})
        session=self.service.login('owner@example.test',PASSWORD)['session']
        dump='\n'.join(self.service.db.iterdump())
        for value in (PASSWORD,token,session):self.assertNotIn(value,dump)
        with self.assertRaises(IdentityError):self.service.complete_registration(token,PASSWORD)

    def test_resend_does_not_allow_pre_registration_password_takeover(self):
        self.service.register('owner@example.test');old=self.messages[-1]['token']
        self.service.register('owner@example.test');current=self.messages[-1]['token']
        with self.assertRaises(IdentityError):self.service.complete_registration(old,PASSWORD)
        self.service.complete_registration(current,NEW_PASSWORD)
        with self.assertRaises(IdentityError):self.service.login('owner@example.test',PASSWORD)
        self.assertTrue(self.service.login('owner@example.test',NEW_PASSWORD)['session'])

    def test_registration_and_reset_responses_do_not_reveal_accounts(self):
        self.account('known@example.test');before=len(self.messages)
        self.assertEqual(self.service.register('known@example.test'),GENERIC)
        self.assertEqual(len(self.messages),before)
        self.assertEqual(self.service.request_reset('known@example.test'),self.service.request_reset('absent@example.test'))

    def test_expired_verification_and_invalid_password(self):
        self.service.register('owner@example.test');token=self.messages[-1]['token']
        with self.assertRaises(IdentityError):self.service.complete_registration(token,'short')
        self.now+=VERIFY_TTL
        with self.assertRaises(IdentityError):self.service.complete_registration(token,PASSWORD)

    def test_login_rate_limit_survives_reopen(self):
        self.account('owner@example.test')
        for _ in range(5):
            with self.assertRaises(IdentityError):self.service.login('owner@example.test','wrong password long')
        self.service.close();self.service=IdentityService(self.path,self.messages.append,clock=lambda:self.now)
        with self.assertRaises(IdentityError):self.service.login('owner@example.test',PASSWORD)
        self.now+=901
        self.assertTrue(self.service.login('owner@example.test',PASSWORD)['session'])

    def test_reset_revokes_sessions_and_other_reset_links(self):
        session=self.account('owner@example.test')
        self.service.request_reset('owner@example.test');old=self.messages[-1]['token']
        self.service.request_reset('owner@example.test');token=self.messages[-1]['token']
        with self.assertRaises(IdentityError):self.service.reset_password(old,NEW_PASSWORD)
        self.service.reset_password(token,NEW_PASSWORD)
        with self.assertRaises(IdentityError):self.service.companies(session)
        with self.assertRaises(IdentityError):self.service.login('owner@example.test',PASSWORD)
        self.assertTrue(self.service.login('owner@example.test',NEW_PASSWORD)['session'])
        with self.assertRaises(IdentityError):self.service.reset_password(token,PASSWORD)

    def test_expired_reset_cannot_change_password(self):
        self.account('owner@example.test');self.service.request_reset('owner@example.test')
        token=self.messages[-1]['token'];self.now+=RESET_TTL
        with self.assertRaises(IdentityError):self.service.reset_password(token,NEW_PASSWORD)
        self.assertTrue(self.service.login('owner@example.test',PASSWORD)['session'])

    def test_sessions_expire_and_logout_revokes(self):
        session=self.account('owner@example.test');self.service.logout(session)
        with self.assertRaises(IdentityError):self.service.companies(session)
        session=self.service.login('owner@example.test',PASSWORD)['session'];self.now+=SESSION_TTL
        with self.assertRaises(IdentityError):self.service.companies(session)

    def test_only_verified_account_reserves_company_and_retry_is_idempotent(self):
        with self.assertRaises(IdentityError):self.company('forged')
        session=self.account('owner@example.test');company=self.company(session)
        self.assertEqual(company,self.company(session))
        self.assertFalse(company['access_enabled'])
        self.assertEqual(1,self.service.db.execute('SELECT count(*) FROM tenants').fetchone()[0])
        self.assertEqual(1,self.service.db.execute('SELECT count(*) FROM memberships').fetchone()[0])
        self.assertEqual('owner',self.service.companies(session)[0]['role'])

    def test_company_creation_is_atomic_when_membership_fails(self):
        session=self.account('owner@example.test')
        self.service.db.executescript("CREATE TRIGGER fail_membership BEFORE INSERT ON memberships BEGIN SELECT RAISE(ABORT,'test failure'); END;")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):self.company(session)
        self.assertEqual(0,self.service.db.execute('SELECT count(*) FROM tenants').fetchone()[0])
        self.assertEqual(0,self.service.db.execute('SELECT count(*) FROM memberships').fetchone()[0])

    def test_accounts_with_same_email_domain_do_not_share_memberships(self):
        owner=self.account('owner@example.test');outsider=self.account('outsider@example.test')
        company=self.company(owner)
        self.assertEqual([],self.service.companies(outsider))
        with self.assertRaises(IdentityError):self.service.select_company(outsider,company['id'])
        with self.assertRaises(IdentityError):self.service.invite(outsider,company['id'],'new@example.test')

    def test_invitation_is_bound_to_verified_recipient_and_single_use(self):
        owner=self.account('owner@example.test');worker=self.account('worker@example.test');other=self.account('other@example.test')
        company=self.company(owner);self.service.invite(owner,company['id'],'Worker@Example.test')
        token=self.messages[-1]['token']
        with self.assertRaises(IdentityError):self.service.accept_invitation(other,token)
        self.service.accept_invitation(worker,token)
        self.assertEqual('member',self.service.companies(worker)[0]['role'])
        with self.assertRaises(IdentityError):self.service.accept_invitation(worker,token)
        with self.assertRaises(IdentityError):self.service.invite(worker,company['id'],'third@example.test')

    def test_one_account_can_choose_between_multiple_authorized_companies(self):
        owner=self.account('owner@example.test');second=self.account('second@example.test')
        alfa=self.company(owner);beta=self.company(second,'empresa-beta')
        self.service.invite(second,beta['id'],'owner@example.test')
        self.service.accept_invitation(owner,self.messages[-1]['token'])
        self.assertEqual({alfa['id'],beta['id']},{r['id'] for r in self.service.companies(owner)})
        self.assertFalse(self.service.select_company(owner,beta['id'])['odoo_session_created'])

    def test_invitation_expiration_and_revocation(self):
        owner=self.account('owner@example.test');worker=self.account('worker@example.test');company=self.company(owner)
        self.service.invite(owner,company['id'],'worker@example.test');token=self.messages[-1]['token']
        self.service.revoke_invitation(owner,company['id'],'worker@example.test')
        with self.assertRaises(IdentityError):self.service.accept_invitation(worker,token)
        self.service.invite(owner,company['id'],'worker@example.test');token=self.messages[-1]['token']
        self.now+=INVITE_TTL
        worker=self.service.login('worker@example.test',PASSWORD)['session']
        with self.assertRaises(IdentityError):self.service.accept_invitation(worker,token)

    def test_removing_member_blocks_access_and_stale_invitations(self):
        owner=self.account('owner@example.test');worker=self.account('worker@example.test');company=self.company(owner)
        self.service.invite(owner,company['id'],'worker@example.test')
        self.service.accept_invitation(worker,self.messages[-1]['token'])
        target=self.service._account(worker)['id']
        self.service.invite(owner,company['id'],'worker@example.test');stale=self.messages[-1]['token']
        self.service.remove_member(owner,company['id'],target)
        with self.assertRaises(IdentityError):self.service.select_company(worker,company['id'])
        with self.assertRaises(IdentityError):self.service.accept_invitation(worker,stale)
        with self.assertRaises(IdentityError):self.service.remove_member(owner,company['id'],self.service._account(owner)['id'])

    def test_admin_cannot_create_admin_and_removed_admin_invites_are_invalid(self):
        owner=self.account('owner@example.test');admin=self.account('admin@example.test');worker=self.account('worker@example.test');company=self.company(owner)
        self.service.invite(owner,company['id'],'admin@example.test','admin')
        self.service.accept_invitation(admin,self.messages[-1]['token'])
        with self.assertRaises(IdentityError):self.service.invite(admin,company['id'],'new@example.test','admin')
        self.service.invite(admin,company['id'],'worker@example.test');pending=self.messages[-1]['token']
        self.service.remove_member(owner,company['id'],self.service._account(admin)['id'])
        with self.assertRaises(IdentityError):self.service.accept_invitation(worker,pending)

    def test_password_storage_is_salted_and_audit_contains_no_tokens(self):
        self.account('first@example.test');self.account('second@example.test')
        rows=self.service.db.execute('SELECT password_hash FROM accounts').fetchall()
        self.assertNotEqual(rows[0][0],rows[1][0])
        self.assertTrue(rows[0][0].startswith('scrypt$'))
        audit=json.dumps([tuple(r) for r in self.service.db.execute('SELECT * FROM identity_audit')])
        for message in self.messages:self.assertNotIn(message['token'],audit)

    def test_delivery_failure_has_same_response_and_no_secret_exception(self):
        self.service.deliver=lambda notice:(_ for _ in ()).throw(RuntimeError(notice['token']))
        self.assertEqual(self.service.register('delivery@example.test'),GENERIC)
        self.assertEqual('delivery_failed',self.service.db.execute('SELECT event FROM identity_audit ORDER BY id DESC').fetchone()[0])

    def test_email_validation_and_password_limits(self):
        for email in ['bad','a@b','a..b@example.test','a@example.test\nInjected: x','ñ@example.test']:
            with self.assertRaises(IdentityError):email_key(email)
        self.assertEqual('name+tag@example.test',email_key(' Name+tag@Example.test '))
        self.service.register('owner@example.test')
        with self.assertRaises(IdentityError):self.service.complete_registration(self.messages[-1]['token'],'x'*129)

    def test_role_changes_take_effect_without_changing_other_companies(self):
        owner=self.account('owner@example.test');worker=self.account('worker@example.test');company=self.company(owner)
        self.service.invite(owner,company['id'],'worker@example.test')
        self.service.accept_invitation(worker,self.messages[-1]['token'])
        target=self.service._account(worker)['id']
        with self.assertRaises(IdentityError):self.service.members(worker,company['id'])
        self.service.change_role(owner,company['id'],target,'admin')
        self.assertEqual(2,len(self.service.members(worker,company['id'])))
        self.service.invite(worker,company['id'],'new@example.test');pending=self.messages[-1]['token']
        self.service.change_role(owner,company['id'],target,'member')
        with self.assertRaises(IdentityError):self.service.invite(worker,company['id'],'third@example.test')
        with self.assertRaises(IdentityError):self.service.change_role(worker,company['id'],self.service._account(owner)['id'],'member')
        new=self.account('new@example.test')
        with self.assertRaises(IdentityError):self.service.accept_invitation(new,pending)

    def test_concurrent_confirmation_consumes_token_exactly_once(self):
        self.service.register('owner@example.test');token=self.messages[-1]['token']
        def verify(_):
            service=IdentityService(self.path,lambda notice:None,clock=lambda:self.now)
            try:
                service.complete_registration(token,PASSWORD)
                return True
            except IdentityError:return False
            finally:service.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual([False,True],sorted(pool.map(verify,range(2))))

    def test_login_hash_runs_outside_writer_transaction_and_rechecks_reset(self):
        import sqlite3
        from control.identity import password_hash
        self.account('hash-race@example.test')
        replacement=password_hash(NEW_PASSWORD)
        def race(password,encoded):
            self.assertFalse(self.service.db.in_transaction)
            with sqlite3.connect(self.path) as other:
                other.execute('UPDATE accounts SET password_hash=? WHERE email=?',(replacement,'hash-race@example.test'))
            return True
        before=self.service.db.execute('SELECT count(*) FROM identity_sessions').fetchone()[0]
        with patch('control.identity.password_matches',side_effect=race):
            with self.assertRaises(IdentityError):self.service.login('hash-race@example.test',PASSWORD)
        self.assertEqual(self.service.db.execute('SELECT count(*) FROM identity_sessions').fetchone()[0],before)

    def test_twenty_concurrent_account_registrations_do_not_lock_database(self):
        import threading
        barrier=threading.Barrier(20)
        def one(i):
            messages=[];service=IdentityService(self.path,messages.append,clock=lambda:self.now)
            try:
                barrier.wait(timeout=30)
                email='parallel20-%02d@example.test'%i
                service.register(email)
                service.complete_registration(messages[-1]['token'],PASSWORD)
                session=service.login(email,PASSWORD)['session']
                service.logout(session)
                return True
            finally:service.close()
        with ThreadPoolExecutor(max_workers=20) as pool:
            self.assertEqual(list(pool.map(one,range(20))),[True]*20)
        self.assertEqual(self.service.db.execute('SELECT count(*) FROM accounts WHERE verified=1').fetchone()[0],20)
