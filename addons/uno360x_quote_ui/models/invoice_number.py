from odoo import api, fields, models
from odoo.exceptions import UserError


class InvoiceNumber(models.Model):
    _inherit='account.move'

    ux_invoice_number=fields.Char(string='Comprobante',compute='_compute_ux_invoice_number',search='_search_ux_invoice_number')

    def _ux_accepted_ecf_number(self):
        """Override in the validated tenant fiscal adapter; never infer from FAC."""
        self.ensure_one()
        return False

    @api.depends('name')
    def _compute_ux_invoice_number(self):
        for move in self:
            move.ux_invoice_number=move._ux_accepted_ecf_number() or move.name or 'Borrador'

    def _search_ux_invoice_number(self,operator,value):
        # Fiscal adapter must extend search along with its accepted-number hook.
        return [('name',operator,value)]

    def action_ux_discard_invoice_draft(self):
        self.ensure_one()
        self.check_access('unlink')
        self.env.cr.execute('SELECT id FROM account_move WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        if (self.state != 'draft' or self.move_type not in ('out_invoice', 'out_refund')
                or self.posted_before or self._ux_accepted_ecf_number()):
            raise UserError('Solo se puede descartar un borrador de cliente que nunca se confirmó.')
        action = ('account.action_move_out_refund_type' if self.move_type == 'out_refund'
                  else 'account.action_move_out_invoice_type')
        self.unlink()
        return self.env['ir.actions.actions']._for_xml_id(action)
