from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        # The stock move split and backorder both post to the receipt history.
        if not self.env.user.partner_id.email_formatted:
            receipts = self.with_context(uno360x_receipt_validation_log=True)
            return super(StockPicking, receipts)._action_done()
        return super()._action_done()

    def message_post(self, *, body='', **kwargs):
        if (
            self.env.context.get('uno360x_receipt_validation_log')
            and self.env.user.has_group('stock.group_stock_user')
            and len(self) == 1
            and self.picking_type_code == 'incoming'
            and not self.env.user.partner_id.email_formatted
            and self._uno360x_is_receipt_log(kwargs)
        ):
            self.check_access(self._mail_post_access)
            return self._message_log(body=body)
        return super().message_post(body=body, **kwargs)

    def _uno360x_is_receipt_log(self, values):
        if not values:
            return True
        return (
            values.keys() <= {'message_type', 'subtype_id'}
            and values.get('subtype_id') == self.env.ref('mail.mt_note').id
            and values.get('message_type') in ('notification', 'comment')
        )
