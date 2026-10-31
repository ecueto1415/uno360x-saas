from datetime import timedelta
from unittest.mock import patch
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

@tagged('post_install','-at_install')
class TestPortableQuotes(TransactionCase):
    def make_order(self):
        today=fields.Date.context_today(self.env.user)
        return self.env['sale.order'].create({'partner_id':self.env['res.partner'].create({'name':'Cliente ficticio'}).id,
          'date_order':fields.Datetime.now()-timedelta(days=40),'validity_date':today-timedelta(days=10)})

    def test_expired_quote_renews_preserving_original_duration(self):
        order=self.make_order();old=order.validity_date
        days=(old-fields.Datetime.context_timestamp(order,order.date_order).date()).days
        order.action_ux_refresh_expired_quote()
        self.assertEqual(order.validity_date,fields.Date.context_today(order)+timedelta(days=days))
        self.assertTrue(order.message_ids)

    def test_current_quote_not_changed(self):
        order=self.make_order();order.validity_date=fields.Date.today()+timedelta(days=5)
        before=(order.date_order,order.validity_date)
        with self.assertRaises(UserError):order.action_ux_refresh_expired_quote()
        self.assertEqual(before,(order.date_order,order.validity_date))

    def test_pdf_versions_and_copy_are_independent(self):
        order=self.make_order();report=self.env['ir.actions.report']
        action=self.env.ref('uno360x_quote_ui.action_save_pdf_version')
        with patch.object(type(report),'_render_qweb_pdf',return_value=(b'%PDF-1.4 fictional test','pdf')):
            for _ in range(2):
                action.with_context(active_model='sale.order',active_id=order.id,active_ids=order.ids).run()
        self.assertEqual(len(order.x_ux_quote_pdf_version_ids),2)
        self.assertEqual(len(set(order.x_ux_quote_pdf_version_ids.mapped('name'))),2)
        self.assertFalse(order.copy().x_ux_quote_pdf_version_ids)
        self.assertTrue(all(a.res_model=='sale.order' and a.res_id==order.id for a in order.x_ux_quote_pdf_version_ids))
