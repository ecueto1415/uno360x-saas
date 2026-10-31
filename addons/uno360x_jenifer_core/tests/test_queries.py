from odoo.tests.common import TransactionCase,tagged,new_test_user
from ..models.query_parser import parse_query

@tagged('post_install','-at_install')
class TestPortableJenifer(TransactionCase):
    def test_read_intents_reject_writes(self):
        self.assertEqual(parse_query('CxC: Empresa ficticia'),('receivable','Empresa ficticia'))
        self.assertEqual(parse_query('Paga las cuentas por pagar'),('readonly',''))
        self.assertEqual(parse_query('Cuentas por pagar'),('payable',''))

    def test_permission_denied_without_elevation(self):
        user=new_test_user(self.env['res.users'].with_context(no_reset_password=True).env,login='jenifer_limited_ficticio',groups='base.group_user')
        self.assertFalse(self.env['account.move'].with_user(user).has_access('read'))
        response=self.env['uno360x.jenifer.query'].with_user(user)._respond('CxC')
        self.assertIn('no tiene permiso',response)

    def test_queries_do_not_send_mail_or_write_accounts(self):
        before=(self.env['mail.mail'].search_count([]),self.env['account.move'].search_count([]))
        service=self.env['uno360x.jenifer.query']
        for query in ['CxC: INEXISTENTE_FICTICIO_992','CxP: INEXISTENTE_FICTICIO_992','Cotizaciones pendientes: INEXISTENTE_FICTICIO_992','Paga las cuentas por pagar']:
            self.assertTrue(service._respond(query))
        self.assertEqual(before,(self.env['mail.mail'].search_count([]),self.env['account.move'].search_count([])))

    def test_quotes_exclude_unselected_companies(self):
        other=self.env['res.company'].create({'name':'OTRA_FICTICIA_992'})
        partner=self.env['res.partner'].create({'name':'Cliente ficticio'})
        order=self.env['sale.order'].with_company(other).create({'partner_id':partner.id,'company_id':other.id})
        reply=self.env['uno360x.jenifer.query'].with_context(allowed_company_ids=self.env.company.ids)._respond('Cotizaciones pendientes')
        self.assertNotIn('OTRA_FICTICIA_992',reply)
