from odoo import api, fields, models
from odoo.exceptions import ValidationError, AccessError

class Tender(models.Model):
    _inherit = 'jenifer.tender'
    discarded_by_id = fields.Many2one('res.users', string='Descartada por', readonly=True, copy=False, tracking=True)
    discarded_at = fields.Datetime(string='Fecha de descarte', readonly=True, copy=False, tracking=True)

    def _discard_values(self, vals):
        vals = dict(vals)
        if {'discarded_by_id', 'discarded_at'} & vals.keys():
            raise AccessError('El usuario y la fecha de descarte se registran automáticamente.')
        stage = self.env.ref('jenifer_outsolutech.stage_descartada')
        entering = vals.get('stage_id') == stage.id or vals.get('decision') == 'discard'
        if entering:
            reason = vals.get('discard_reason', self.discard_reason if self else '')
            if not reason or not reason.strip():
                raise ValidationError('Para descartar la licitación, abra su ficha y escriba el motivo de descarte antes de guardar. Quedará registrado quién la descartó y cuándo.')
            vals.update(stage_id=stage.id, decision='discard', discard_reason=reason.strip())
            if not self or self.stage_id != stage or self.decision != 'discard':
                vals.update(discarded_by_id=self.env.uid, discarded_at=fields.Datetime.now())
        elif self and vals.get('stage_id') and self.stage_id == stage and 'decision' not in vals:
            vals['decision'] = 'pending'
        if self and 'discard_reason' in vals and (vals.get('stage_id', self.stage_id.id) == stage.id or vals.get('decision', self.decision) == 'discard'):
            if not (vals['discard_reason'] or '').strip():
                raise ValidationError('Una licitación descartada debe conservar su motivo de descarte.')
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self.browse()._discard_values(vals) for vals in vals_list])

    def write(self, vals):
        for record in self:
            prepared = record._discard_values(vals)
            previous = record.discard_reason
            result = super(Tender, record).write(prepared)
            if 'discarded_at' in prepared:
                record.message_post(body='Licitación descartada. Motivo: %s' % prepared['discard_reason'], subtype_xmlid='mail.mt_note')
            elif 'discard_reason' in prepared and previous != record.discard_reason:
                record.message_post(body='Motivo de descarte actualizado: %s' % record.discard_reason, subtype_xmlid='mail.mt_note')
        return True
