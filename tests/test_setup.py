import tempfile,unittest
from pathlib import Path
from control.identity import IdentityService,IdentityError
from control.setup import Setup

class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.mail=[]
        self.identity=IdentityService(Path(self.tmp.name)/'control.sqlite3',self.mail.append)
        self.identity.register('owner@example.test');self.identity.complete_registration(self.mail[-1]['token'],'Clave ficticia setup 2026')
        self.session=self.identity.login('owner@example.test','Clave ficticia setup 2026')['session']
        self.tenant=self.identity.create_company(self.session,'setup-ficticio',[],'one')['id'];self.setup=Setup(self.identity)
    def tearDown(self):self.identity.close();self.tmp.cleanup()
    def test_saved_details_are_not_treated_as_fiscal_verification_or_applied_config(self):
        profile={'name':'Empresa ficticia','country':'DO','tax_id':'123456789','address':'Solo pruebas','currency':'DOP'}
        self.assertFalse(self.setup.status(self.session,self.tenant)['company_details_saved'])
        self.setup.save(self.session,self.tenant,profile)
        status=self.setup.status(self.session,self.tenant)
        self.assertTrue(status['company_details_saved']);self.assertFalse(status['workspace_ready_local'])
        self.assertFalse(status['tax_id_verified_external']);self.assertFalse(status['fiscal_emission_enabled'])
        with self.identity.db:
            self.identity.db.execute('CREATE TABLE trial_company_parameters (tenant_id TEXT PRIMARY KEY,applied REAL NOT NULL)')
            self.identity.db.execute('INSERT INTO trial_company_parameters VALUES (?,1)',(self.tenant,))
        status=self.setup.status(self.session,self.tenant)
        self.assertTrue(status['basic_company_parameters_applied_to_odoo'])
        self.assertFalse(status['configuration_applied_to_odoo']);self.assertFalse(status['fiscal_emission_enabled'])
    def test_missing_company_membership_and_invalid_profile_rejected(self):
        with self.assertRaises(IdentityError):self.setup.status(self.session,'unknown')
        with self.assertRaises(ValueError):self.setup.save(self.session,self.tenant,{'name':'missing'})
