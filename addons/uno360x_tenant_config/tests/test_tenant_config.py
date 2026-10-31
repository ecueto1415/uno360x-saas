from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTenantConfig(TransactionCase):
    def test_identity_validation(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['uno360x.tenant.identity'].sudo().create({
                'tenant_id': 'invalid', 'hostname': 'example.evil.com',
            })

    def test_operator_cannot_create_identity(self):
        user = new_test_user(self.env, login='saas_test_operator', groups='base.group_user')
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['uno360x.tenant.identity'].with_user(user).create({
                'tenant_id': 'a' * 32, 'hostname': 'empresa-alfa.uno360x.com',
            })

    def test_company_setup_is_not_shared(self):
        a = self.env['res.company'].sudo().create({'name': 'Ficticia A'})
        b = self.env['res.company'].sudo().create({'name': 'Ficticia B'})
        a.uno360x_ecf_setup_state = 'pending_validation'
        self.assertEqual(b.uno360x_ecf_setup_state, 'not_started')
        self.assertNotIn('active', dict(a._fields['uno360x_ecf_setup_state'].selection))
