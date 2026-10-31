from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_ux_refresh_expired_quote(self):
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(_('Solo se pueden actualizar presupuestos en borrador o enviados.'))
        now = fields.Datetime.now()
        today = fields.Date.context_today(self, timestamp=now)
        if not self.validity_date or self.validity_date >= today:
            raise UserError(_('Esta cotización no está vencida. No se han cambiado sus fechas.'))
        original_date = fields.Datetime.context_timestamp(self, self.date_order).date()
        days = (self.validity_date - original_date).days
        if days <= 0:
            raise UserError(_('La vigencia original no es válida. Corrija las fechas antes de actualizar.'))
        old_date, old_validity = self.date_order, self.validity_date
        self.write({'date_order': now, 'validity_date': today + timedelta(days=days)})
        self.message_post(body=_(
            'Cotización actualizada. Fecha anterior: %(old_date)s; vencimiento anterior: '
            '%(old_validity)s. Nueva fecha: %(today)s; nueva validez: %(validity)s '
            '(%(days)s días).',
            old_date=old_date, old_validity=old_validity,
            today=today, validity=self.validity_date, days=days,
        ))
        return {'type': 'ir.actions.client', 'tag': 'reload'}
