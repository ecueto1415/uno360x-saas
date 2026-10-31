import secrets
from unittest.mock import patch
from odoo import Command
from odoo.exceptions import AccessDenied
from odoo.tests.common import TransactionCase,tagged
from ..protocol import mint

@tagged('post_install','-at_install')
class TestAuthBridge(TransactionCase):
    def setUp(self):
        super().setUp()
        self.key=secrets.token_bytes(32)
        self.identity=self.env['uno360x.tenant.identity'].search([],limit=1)
        if not self.identity:
            self.identity=self.env['uno360x.tenant.identity'].create({'tenant_id':'a'*32,'hostname':'bridge-ficticio.uno360x.com'})
        self.account='b'*32
        self.user=self.env['res.users'].with_context(no_reset_password=True).create({
          'name':'Cuenta ficticia bridge','login':'saas_'+self.account,
          'uno360x_account_id':self.account,'password':'Clave ficticia independiente 2026',
          'groups_id':[Command.set(self.env.ref('base.group_user').ids)],
          'company_id':self.env.company.id,'company_ids':[Command.set(self.env.company.ids)]})

    def check(self,token):
        with patch('pathlib.Path.read_bytes',return_value=self.key):
            return self.user.with_user(self.user)._check_credentials({'type':'uno360x_bridge','password':token}, {'interactive':True})

    def test_assertion_authenticates_correct_user_once(self):
        token=mint(self.key,self.identity.tenant_id,self.account)
        self.assertEqual(self.check(token)['uid'],self.user.id)
        with self.assertRaises(AccessDenied):self.check(token)

    def test_other_tenant_and_other_key_are_rejected(self):
        for token in [mint(self.key,'c'*32,self.account),mint(secrets.token_bytes(32),self.identity.tenant_id,self.account),
                      mint(self.key,self.identity.tenant_id,'d'*32)]:
            with self.assertRaises(AccessDenied):self.check(token)

    def test_native_login_remains_available_without_settings_privileges(self):
        result=self.user.with_user(self.user)._check_credentials({'type':'password','password':'Clave ficticia independiente 2026'},{'interactive':True})
        self.assertEqual(result['uid'],self.user.id)
        self.assertFalse(self.user.has_group('base.group_system'))
