from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInvoiceTemplates(TransactionCase):
    def test_edit_template_and_create_draft(self):
        company = self.env.company
        partner = self.env['res.partner'].create({'name': 'Cliente ficticio QA'})
        product = self.env['product.product'].create({
            'name': 'Procedimiento ficticio QA',
            'type': 'service',
        })
        templates = self.env['uno360x.invoice.template']
        original = templates.create({
            'name': 'Cirugía de cataratas QA',
            'company_id': company.id,
            'line_ids': [Command.create({
                'product_id': product.id, 'name': 'Procedimiento',
                'quantity': 2, 'price_unit': 115,
            })],
        })
        with self.assertRaises(UserError):
            original.copy()
        original.line_ids.quantity = 3
        wizard = self.env['uno360x.invoice.template.wizard'].create({
            'template_id': original.id, 'partner_id': partner.id,
        })
        invoice = self.env['account.move'].browse(wizard.action_create_invoice()['res_id'])
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, partner)
        self.assertEqual(invoice.invoice_line_ids.product_id, product)
        self.assertEqual(invoice.invoice_line_ids.quantity, 3)
        self.assertEqual(invoice.invoice_line_ids.price_unit, 115)
        self.assertFalse(invoice._ux_accepted_ecf_number())

        original.unlink()
        self.assertFalse(original.exists())
        self.assertTrue(invoice.exists())
        self.assertEqual(invoice.invoice_line_ids.quantity, 3)
