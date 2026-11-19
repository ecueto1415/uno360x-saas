from odoo import _, models
from odoo.exceptions import AccessError, UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def action_new_quotation(self):
        action = super().action_new_quotation()
        action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
        return action

    def action_uno360x_new_quotation(self):
        self.ensure_one()
        self.check_access('read')
        self.env['sale.order'].check_access('create')
        if self.company_id != self.env.company:
            raise AccessError(_('La oportunidad pertenece a otra empresa.'))
        if self.type != 'opportunity':
            raise UserError(_('Abre una oportunidad del CRM para cotizar.'))
        return self.action_new_quotation()
