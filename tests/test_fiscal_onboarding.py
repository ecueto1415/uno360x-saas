from dataclasses import replace
from control.fiscal_onboarding import FiscalOnboarding,CheckEvidence,STEPS
from control.identity import IdentityError
import test_fiscal_vault as vault_fixtures


class OnboardingTests(vault_fixtures.VaultTests):
    def stored(self):
        return self.vault.store(self.session,self.a,1,self.p12,'fiscal-ficticio')

    def checkers(self):
        return {step:(lambda context,source=source:CheckEvidence(context.binding,source,'fixture-evidence',self.identity.clock(),self.identity.clock()+3600)) for step,_,source in STEPS}

    def test_missing_certificate_guides_customer_without_enabling(self):
        flow=FiscalOnboarding(self.identity,self.vault)
        status=flow.status(self.session,self.a,1)
        self.assertEqual(status['next_action'],'upload_certificate')
        self.assertFalse(status['emission_enabled'])
        with self.assertRaises(IdentityError):flow.run_checks(self.session,self.a,1)

    def test_upload_does_not_mean_official_approval(self):
        self.stored();flow=FiscalOnboarding(self.identity,self.vault)
        status=flow.run_checks(self.session,self.a,1)
        self.assertEqual(status['next_action'],'taxpayer')
        self.assertTrue(all(s['state']=='pending' for s in status['steps']))
        self.assertFalse(status['official_checks_passed'])

    def test_verified_checks_never_implicitly_enable_transmission(self):
        self.stored();flow=FiscalOnboarding(self.identity,self.vault,self.checkers())
        status=flow.run_checks(self.session,self.a,1)
        self.assertTrue(status['official_checks_passed'])
        self.assertFalse(status['emission_enabled']);self.assertFalse(status['legal_acceptance_automated'])
        self.assertEqual(status['next_action'],'adapter_validation_pending')

    def test_company_and_certificate_rotation_invalidate_evidence(self):
        self.stored();flow=FiscalOnboarding(self.identity,self.vault,self.checkers());flow.run_checks(self.session,self.a,1)
        self.stored()
        self.assertFalse(flow.status(self.session,self.a,1)['official_checks_passed'])
        flow.run_checks(self.session,self.a,1)
        self.vault.resolve_company=lambda tenant,company:{'tax_id':'987654321'}
        self.assertFalse(flow.status(self.session,self.a,1)['official_checks_passed'])

    def test_checks_are_not_shared_between_tenants_even_same_rnc(self):
        self.stored();flow=FiscalOnboarding(self.identity,self.vault,self.checkers());flow.run_checks(self.session,self.a,1)
        self.vault.resolve_company=lambda tenant,company:{'tax_id':'123456789'}
        self.vault.store(self.session,self.b,1,self.p12,'fiscal-ficticio')
        status=flow.status(self.session,self.b,1)
        self.assertFalse(status['official_checks_passed']);self.assertTrue(all(s['state']=='pending' for s in status['steps']))

    def test_wrong_binding_wrong_source_and_owner_dict_rejected(self):
        self.stored()
        for callback in (
            lambda context:{'status':'passed'},
            lambda context:CheckEvidence('another-company','dgii','fixture',self.identity.clock(),self.identity.clock()+60),
            lambda context:CheckEvidence(context.binding,'browser','fixture',self.identity.clock(),self.identity.clock()+60),
        ):
            flow=FiscalOnboarding(self.identity,self.vault,{'taxpayer':callback})
            status=flow.run_checks(self.session,self.a,1,['taxpayer'])
            self.assertEqual(status['steps'][0]['state'],'blocked')

    def test_failed_recheck_invalidates_previous_pass(self):
        self.stored();flow=FiscalOnboarding(self.identity,self.vault,self.checkers());flow.run_checks(self.session,self.a,1)
        def fails(context):raise RuntimeError('PRIVATE TOKEN MUST NOT BE SAVED')
        flow.checkers['taxpayer']=fails
        status=flow.run_checks(self.session,self.a,1,['taxpayer'])
        self.assertFalse(status['official_checks_passed'])
        self.assertNotIn('PRIVATE TOKEN','\n'.join(self.identity.db.iterdump()))

    def test_expired_checks_return_to_pending(self):
        self.stored();flow=FiscalOnboarding(self.identity,self.vault,self.checkers());flow.run_checks(self.session,self.a,1)
        with self.identity.db:self.identity.db.execute('UPDATE fiscal_setup_checks SET expires=?',(self.identity.clock()-1,))
        self.assertFalse(flow.status(self.session,self.a,1)['official_checks_passed'])

    def test_unknown_company_and_logged_out_owner_denied(self):
        self.stored();flow=FiscalOnboarding(self.identity,self.vault,self.checkers())
        with self.assertRaises(IdentityError):flow.status(self.session,self.a,2)
        with self.assertRaises(IdentityError):flow.status('not-a-session',self.a,1)

    def test_changed_profile_during_check_cannot_save_stale_pass(self):
        self.stored()
        def race(context):
            self.vault.resolve_company=lambda tenant,company:{'tax_id':'987654321'}
            return CheckEvidence(context.binding,'dgii','fixture',self.identity.clock(),self.identity.clock()+60)
        flow=FiscalOnboarding(self.identity,self.vault,{'taxpayer':race})
        with self.assertRaises(IdentityError):flow.run_checks(self.session,self.a,1,['taxpayer'])
        self.assertEqual(self.identity.db.execute('SELECT count(*) FROM fiscal_setup_checks').fetchone()[0],0)
