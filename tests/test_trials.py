import tempfile
import unittest
from pathlib import Path

from control.identity import IdentityService, IdentityError
from control.onboarding import Onboarding
from control.trials import Trials, TrialCompanyExists, TRIAL_SECONDS, check_trial_access
from tests.test_onboarding import FakeAdapter


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.mail = [];self.now = 2000000000
        self.identity = IdentityService(Path(self.tmp.name)/'control.sqlite3', self.mail.append, clock=lambda:self.now)
        self.trials = Trials(self.identity)
        self.trials.register('trial@example.test', 'Persona ficticia', ['payroll_hr'], True)
        self.identity.complete_registration(self.mail[-1]['token'], 'Contraseña ficticia trials 2026')
        self.session = self.identity.login('trial@example.test', 'Contraseña ficticia trials 2026')['session']
    def tearDown(self):
        self.identity.close();self.tmp.cleanup()
    def create(self):
        return self.trials.create(self.session, 'Mi Empresa SRL', 'DO', 'DOP', ['payroll_hr'])
    def test_draft_survives_verification_and_repeat_signup_does_not_replace_it(self):
        self.assertEqual(self.trials.draft(self.session)['modules'], ['payroll_hr'])
        self.trials.register('trial@example.test','Otro nombre',[],True)
        self.assertEqual(self.trials.draft(self.session)['name'], 'Persona ficticia')
    def test_existing_email_is_explicit_without_new_account_or_verification_mail(self):
        before=self.identity.db.execute('SELECT count(*) FROM accounts').fetchone()[0];mail_count=len(self.mail)
        result=self.trials.register('TRIAL@example.test','Another name',[],True)
        self.assertTrue(result['account_exists']);self.assertFalse(result['verification_required'])
        self.assertEqual(self.identity.db.execute('SELECT count(*) FROM accounts').fetchone()[0],before)
        self.assertEqual(len(self.mail),mail_count)
        self.trials.register('pending@example.test','Pending',[],True);token=self.mail[-1]['token'];mail_count=len(self.mail)
        result=self.trials.register('pending@example.test','Pending again',[],True)
        self.assertTrue(result['account_exists']);self.assertTrue(result['verification_required']);self.assertEqual(len(self.mail),mail_count)
        self.identity.complete_registration(token,'Pending fictional password 2026!')
    def test_existing_owner_cannot_create_another_trial_through_history_or_api(self):
        self.identity.create_company(self.session,'existing-owner',[],'existing-owner-request')
        before=self.identity.db.execute('SELECT count(*) FROM tenants').fetchone()[0]
        with self.assertRaises(TrialCompanyExists):self.create()
        self.assertEqual(self.identity.db.execute('SELECT count(*) FROM tenants').fetchone()[0],before)
    def test_create_retries_are_idempotent_and_one_trial_per_account(self):
        first=self.create();second=self.create()
        self.assertEqual(first['tenant_id'], second['tenant_id'])
        self.assertEqual(self.identity.db.execute('SELECT count(*) FROM tenants').fetchone()[0],1)
        with self.assertRaises(ValueError):self.trials.create(self.session,'Otra empresa','DO','DOP',[])
    def test_fifteen_days_start_only_at_readiness_and_never_restart(self):
        state=self.create();tid=state['tenant_id'];self.assertIsNone(state['started']);self.assertFalse(state['trial_active'])
        with self.assertRaises(IdentityError):check_trial_access(self.identity,tid)
        self.now+=3600;Onboarding(self.identity).run(state['job_id'],FakeAdapter())
        state=self.trials.status(self.session,tid);self.assertEqual(state['started'],self.now)
        self.assertEqual(state['expires'],self.now+TRIAL_SECONDS);self.assertEqual(state['days_remaining'],15)
        check_trial_access(self.identity,tid);started=self.now
        self.now+=60;Onboarding(self.identity).run(state['job_id'],FakeAdapter())
        self.assertEqual(self.trials.status(self.session,tid)['started'],started)
        self.now=started+TRIAL_SECONDS
        self.session=self.identity.login('trial@example.test','Contraseña ficticia trials 2026')['session']
        self.assertEqual(self.trials.status(self.session,tid)['days_remaining'],0)
        with self.assertRaises(IdentityError):check_trial_access(self.identity,tid)
        # Session expires earlier, so use a fresh one to verify the handoff gate.
        session=self.identity.login('trial@example.test','Contraseña ficticia trials 2026')['session']
        with self.assertRaises(IdentityError):Onboarding(self.identity).issue_handoff(session,tid)
        self.assertEqual(self.identity.db.execute('SELECT count(*) FROM tenants').fetchone()[0],1)
    def test_invalid_modules_country_consent_and_foreign_membership_are_rejected(self):
        for args in [('a@example.test','Name', ['unknown'],True),('a@example.test','Name',[],False)]:
            with self.assertRaises(ValueError):self.trials.register(*args)
        with self.assertRaises(ValueError):self.trials.create(self.session,'X','US','DOP',[])
        state=self.create()
        self.identity.register('other@example.test');self.identity.complete_registration(self.mail[-1]['token'],'Contraseña ficticia other 2026')
        other=self.identity.login('other@example.test','Contraseña ficticia other 2026')['session']
        with self.assertRaises(IdentityError):self.trials.status(other,state['tenant_id'])
    def test_non_trial_companies_remain_outside_policy(self):
        tid=self.identity.create_company(self.session,'fixture-antiguo',[],'fixture')['id']
        check_trial_access(self.identity,tid)
        self.assertFalse(self.trials.status(self.session,tid)['is_trial'])
