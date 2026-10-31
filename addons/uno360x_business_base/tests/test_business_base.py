from odoo import Command, fields
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBusinessBase(AccountTestInvoicingCommon):
    chart_template = 'do'
    country_code = 'DO'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.goods = cls.env['product.product'].create({
            'name': 'Artículo ficticio UNO360X', 'type': 'consu',
            'is_storable': True, 'invoice_policy': 'order',
            'list_price': 100, 'standard_price': 40,
            'taxes_id': [Command.clear()], 'supplier_taxes_id': [Command.clear()],
            'property_account_income_id': cls.company_data['default_account_revenue'].id,
            'property_account_expense_id': cls.company_data['default_account_expense'].id,
        })

    def test_quotation_to_invoice_and_payment(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'order_line': [Command.create({'product_id': self.goods.id,
                'product_uom_qty': 2, 'price_unit': 100, 'tax_id': [Command.clear()]})],
        })
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.amount_total, 200)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertTrue(order.picking_ids)
        invoice = order._create_invoices()
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.amount_residual, 200)
        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({
                'journal_id': self.company_data['default_journal_bank'].id,
                'payment_date': fields.Date.today(),
            })
        payment._create_payments()
        self.assertEqual(invoice.amount_residual, 0)
        self.assertIn(invoice.payment_state, ('in_payment', 'paid'))

    def test_purchase_receipt_and_vendor_bill(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner_a.id,
            'order_line': [Command.create({'product_id': self.goods.id,
                'product_qty': 3, 'price_unit': 40, 'date_planned': fields.Datetime.now(),
                'taxes_id': [Command.clear()]})],
        })
        order.button_confirm()
        receipt = order.picking_ids
        self.assertEqual(len(receipt), 1)
        receipt.move_ids.write({'quantity': 3, 'picked': True})
        receipt.button_validate()
        self.assertEqual(receipt.state, 'done')
        self.assertEqual(self.goods.qty_available, 3)
        order.action_create_invoice()
        bill = order.invoice_ids
        bill.invoice_date = fields.Date.today()
        bill.action_post()
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.amount_total, 120)
        self.assertEqual(bill.amount_residual, 120)

    def test_fiscal_activation_remains_unavailable(self):
        self.assertEqual(self.env.company.uno360x_ecf_setup_state, 'not_started')
        choices = dict(self.env.company._fields['uno360x_ecf_setup_state'].selection)
        self.assertNotIn('active', choices)
        self.assertNotIn('enabled', choices)
        self.assertTrue(self.env['account.account'].search_count([
            ('company_ids', 'in', self.env.company.ids)]))
