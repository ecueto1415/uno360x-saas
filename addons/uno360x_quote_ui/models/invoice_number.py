from odoo import api,fields,models


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
