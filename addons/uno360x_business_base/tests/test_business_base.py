from uuid import uuid4

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import new_test_user
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


    def test_scoped_billing_user_cannot_read_sales_through_account_group(self):
        sales=self.env['sale.order'].create({'partner_id':self.partner_a.id})
        lead=self.env['crm.lead'].create({'name':'Fictional lead'})
        scoped='uno360x_business_base.group_scoped_employee'
        billing=new_test_user(self.env['res.users'].with_context(no_reset_password=True).env,
            login='scope_bill_test',groups=scoped+',uno360x_business_base.group_area_billing',
            company_id=self.env.company.id,company_ids=[Command.set(self.env.company.ids)])
        self.assertTrue(billing.has_group('account.group_account_invoice'))
        self.assertFalse(sales.with_user(billing).search([('id','=',sales.id)]))
        self.assertFalse(lead.with_user(billing).has_access('read'))

    def test_scoped_inventory_user_cannot_read_pos_orders(self):
        scoped='uno360x_business_base.group_scoped_employee'
        inventory=new_test_user(self.env['res.users'].with_context(no_reset_password=True).env,
            login='scope_inventory_test',groups=scoped+',uno360x_business_base.group_area_inventory',
            company_id=self.env.company.id,company_ids=[Command.set(self.env.company.ids)])
        domain=self.env['ir.rule'].with_user(inventory)._compute_domain('pos.order','read')
        self.assertIn(('id','=',False),domain)


    def _area_user(self, area):
        return new_test_user(self.env,login='uno_area_'+area,
            groups='base.group_user,uno360x_business_base.group_scoped_employee,uno360x_business_base.group_area_'+area,
            company_id=self.env.company.id,company_ids=[Command.set(self.env.company.ids)])

    def test_sales_employee_can_confirm_quotation(self):
        sales=self._area_user('sales')
        order=self.env['sale.order'].with_user(sales).create({
            'partner_id':self.partner_a.id,
            'order_line':[Command.create({'product_id':self.goods.id,'product_uom_qty':1})],
        })
        order.action_confirm()
        self.assertEqual(order.state,'sale')
        self.assertTrue(order.sudo().picking_ids)

    def test_billing_employee_can_post_invoice(self):
        billing=self._area_user('billing')
        invoice=self.env['account.move'].with_user(billing).create({
            'move_type':'out_invoice','partner_id':self.partner_a.id,
            'invoice_date':fields.Date.today(),
            'invoice_line_ids':[Command.create({'product_id':self.goods.id,'price_unit':100})],
        })
        invoice.action_post()
        self.assertEqual(invoice.state,'posted')

    def test_pos_employee_can_open_box(self):
        pos=self._area_user('pos')
        config=self.env['pos.config'].create({'name':'Caja UNO360X de prueba'})
        action=config.with_user(pos).open_ui()
        self.assertIn('/pos/ui',action['url'])
        session=config.current_session_id
        self.assertTrue(session)
        self.assertTrue(session.with_user(pos).has_access('read'))
        self.assertFalse(session.with_user(self._area_user('inventory')).has_access('read'))
        session = session.with_user(pos)
        session.set_opening_control(0, '')
        method=config.payment_method_ids.filtered('is_cash_count')[:1] or config.payment_method_ids[:1]
        self.assertTrue(method)
        data={
            'uuid':str(uuid4()),'name':'Order test','user_id':pos.id,'session_id':session.id,
            'amount_total':100,'amount_paid':100,'amount_tax':0,'amount_return':0,
            'state':'paid','date_order':fields.Datetime.to_string(fields.Datetime.now()),
            'lines':[(0,0,{'product_id':self.goods.id,'qty':1,'price_unit':100,
                            'price_subtotal':100,'price_subtotal_incl':100,'tax_ids':[(6,0,[])]})],
            'payment_ids':[(0,0,{'amount':100,'payment_method_id':method.id})],
        }
        result=self.env['pos.order'].with_user(pos).sync_from_ui([data])
        order=self.env['pos.order'].with_user(pos).browse(result['pos.order'][0]['id'])
        self.assertEqual(order.state,'paid')
        if session.update_stock_at_closing:
            self.assertFalse(order.picking_ids)
        else:
            self.assertTrue(order.picking_ids)
        session.post_closing_cash_details(100 if method.is_cash_count else 0)
        closed=session.close_session_from_ui()
        self.assertTrue(closed['successful'],closed)
        self.assertEqual(session.state,'closed')
