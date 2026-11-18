from datetime import timedelta
import re

from odoo import _, fields, models
from odoo.exceptions import UserError

from .builder import PreparationError, build_preview


class AccountMove(models.Model):
    _inherit = 'account.move'

    uno360x_certification_state = fields.Selection(
        selection=lambda self: self.env['uno360x.ecf.certification.request']._fields['state'].selection,
        compute='_compute_uno360x_certification',
        string='Estado en certificación',
    )
    uno360x_certification_encf = fields.Char(
        compute='_compute_uno360x_certification', string='e-NCF de prueba',
    )

    def _compute_uno360x_certification(self):
        requests = self.env['uno360x.ecf.certification.request'].sudo().search([
            ('move_id', 'in', self.ids), ('company_id', 'in', self.env.companies.ids),
        ])
        by_move = {request.move_id.id: request for request in requests}
        for move in self:
            request = by_move.get(move.id)
            move.uno360x_certification_state = request.state if request else False
            move.uno360x_certification_encf = request.encf if request else False

    def action_uno360x_review_ecf(self):
        self.ensure_one()
        self.check_access('write')
        if self.state != 'draft' or self.move_type != 'out_invoice':
            raise UserError(_('Seleccione una factura de cliente en borrador.'))
        wizard = self.env['uno360x.ecf.review'].with_context({}).create({'move_id': self.id})
        return {
            'type': 'ir.actions.act_window', 'name': _('Revisar factura electrónica'),
            'res_model': wizard._name, 'res_id': wizard.id, 'view_mode': 'form', 'target': 'new',
        }


class AccountTax(models.Model):
    _inherit = 'account.tax'

    uno360x_ecf_exempt = fields.Boolean(string='Exento de ITBIS para e-CF')


class FiscalReview(models.TransientModel):
    _name = 'uno360x.ecf.review'
    _description = 'Revisión local de factura electrónica'

    move_id = fields.Many2one('account.move', required=True, readonly=True, ondelete='cascade')
    partner_id = fields.Many2one(related='move_id.partner_id', readonly=True)
    currency_id = fields.Many2one(related='move_id.currency_id', readonly=True)
    amount_total = fields.Monetary(related='move_id.amount_total', readonly=True)
    document_type = fields.Selection([('31', 'Crédito fiscal · E31'), ('44', 'Regímenes especiales · E44'), ('45', 'Gubernamental · E45')], required=True, default='31')
    certification_ready = fields.Boolean(compute='_compute_certification_ready')
    test_encf = fields.Char(string='e-NCF de prueba')

    def _compute_certification_ready(self):
        configured = self.env['ir.config_parameter'].sudo().get_param('uno360x.ecf.certification.company')
        for row in self:
            row.certification_ready = bool(configured and configured == str(row.move_id.company_id.id))

    payment_type = fields.Selection([('1', 'Contado'), ('2', 'Crédito')], required=True, default='2')
    income_type = fields.Selection([
        ('01', 'Ingresos de operaciones'), ('02', 'Ingresos financieros'),
        ('03', 'Ingresos extraordinarios'), ('04', 'Ingresos por arrendamiento'),
        ('05', 'Ingresos por venta de activo depreciable'), ('06', 'Otros ingresos'),
    ], required=True, default='01')

    def _invoice_data(self):
        self.ensure_one()
        self.check_access('write')
        move = self.move_id
        move.check_access('write')
        if move.company_id not in self.env.companies or move.state != 'draft' or move.move_type != 'out_invoice':
            raise UserError(_('Abra una factura de cliente en borrador de su empresa.'))
        seller = move.company_id.partner_id
        buyer = move.partner_id.commercial_partner_id
        issue_date = move.invoice_date or fields.Date.context_today(self)
        lines = []
        for line in move.invoice_line_ids.filtered(lambda item: item.display_type == 'product'):
            tax = line.tax_ids
            if len(tax) != 1 or tax.amount_type != 'percent' or tax.price_include:
                raise UserError(_('Asigne un impuesto porcentual por separado a la partida «%s».') % line.name)
            category = {16: '2', 18: '1'}.get(tax.amount)
            if tax.amount == 0 and tax.uno360x_ecf_exempt:
                category = '4'
            if not category or (self.document_type == '44' and category != '4'):
                raise UserError(_('Revise el impuesto de la partida «%s». El E44 requiere un impuesto configurado como exento.') % line.name)
            name = line.product_id.name or line.name
            lines.append({
                'name': name[:80], 'quantity': line.quantity, 'price_unit': line.price_unit,
                'discount': line.discount, 'subtotal': line.price_subtotal,
                'goods_service': '2' if line.product_id.type == 'service' else '1',
                'tax_rate': tax.amount, 'tax_category': category,
            })
        return {
            'currency': move.currency_id.name, 'move_type': move.move_type,
            'rounding_method': move.company_id.tax_calculation_rounding_method,
            'document_type': self.document_type, 'payment_type': self.payment_type,
            'income_type': self.income_type, 'invoice_date': str(issue_date),
            'due_date': str(move.invoice_date_due or ''), 'test_expiry': str(issue_date + timedelta(days=1)),
            'seller': {'rnc': seller.vat, 'name': move.company_id.uno360x_fiscal_legal_name or seller.name, 'address': seller.street},
            'buyer': {'rnc': buyer.vat, 'name': buyer.name}, 'lines': lines,
            'amount_untaxed': move.amount_untaxed, 'amount_tax': move.amount_tax, 'amount_total': move.amount_total,
        }

    def _validate_invoice(self):
        data = self._invoice_data()
        try:
            build_preview(data)
        except PreparationError as error:
            raise UserError(str(error)) from None
        return data

    def action_review(self):
        self._validate_invoice()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Validación local completada'),
                       'message': _('Los datos y totales pasaron la revisión. La firma y el envío a la DGII requieren habilitación fiscal.'),
                       'type': 'success', 'next': {'type': 'ir.actions.act_window_close'}},
        }


    def action_emit_certification(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Solo un administrador de contabilidad puede preparar un envío de certificación.'))
        if not self.certification_ready:
            raise UserError(_('El envío de certificación no está habilitado para esta empresa.'))
        encf = (self.test_encf or '').strip().upper()
        if not re.fullmatch(r'E' + self.document_type + r'[0-9]{10}', encf) or int(encf[3:]) == 0:
            raise UserError(_('Indique un e-NCF de prueba válido para el tipo seleccionado.'))
        data = self._validate_invoice()
        move = self.move_id
        requests = self.env['uno360x.ecf.certification.request'].sudo()
        request = requests.search([('move_id', '=', move.id)], limit=1)
        if request and (request.payload != data or request.encf != encf):
            raise UserError(_('Esta factura ya tiene una solicitud de certificación con datos diferentes.'))
        if not request:
            requests.create({
                'move_id': move.id, 'company_id': move.company_id.id,
                'requested_by_id': self.env.uid, 'payload': data, 'encf': encf,
            })
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Solicitud de certificación registrada'),
                'message': _('Pendiente de firma y envío al ambiente de certificación de la DGII.'),
                'type': 'info', 'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class FiscalCertificationRequest(models.Model):
    _name = 'uno360x.ecf.certification.request'
    _description = 'Solicitud pendiente de certificación e-CF'
    _check_company_auto = True
    _sql_constraints = [
        ('move_unique', 'unique(move_id)', 'La factura ya tiene una solicitud de certificación.'),
        ('encf_unique', 'unique(company_id, encf)', 'El e-NCF de prueba ya está reservado para esta empresa.'),
    ]

    move_id = fields.Many2one('account.move', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one('res.company', required=True, ondelete='restrict')
    requested_by_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    payload = fields.Json(required=True)

    encf = fields.Char(readonly=True, copy=False)
    track_id = fields.Char(readonly=True, copy=False)
    signed_xml = fields.Binary(readonly=True, copy=False, attachment=False)
    state = fields.Selection([
        ('queued', 'Pendiente de envío'),
        ('sending', 'Enviando'),
        ('submitted', 'Recibido por la DGII'),
        ('accepted', 'Aceptado'),
        ('conditional', 'Aceptado condicional'),
        ('rejected', 'Rechazado'),
        ('uncertain', 'Pendiente de conciliar'),
    ], required=True, default='queued', readonly=True, copy=False)

    def _claim_certification(self, encf, rnc, expected, signed_xml):
        """Called by the trusted sender in a separate transaction before transmission."""
        self.ensure_one()
        if not self.env.su:
            raise UserError(_('Esta operación requiere el servicio de certificación.'))
        self.env.cr.execute(
            'SELECT id FROM uno360x_ecf_certification_request WHERE id = %s FOR UPDATE', (self.id,),
        )
        self.invalidate_recordset()
        kind = self.payload.get('document_type')
        if self.state != 'queued' or (self.encf and self.encf != encf) or not re.fullmatch(r'E' + re.escape(kind or '') + r'[0-9]{10}', encf):
            raise UserError(_('La solicitud ya se procesó o el e-NCF de prueba es inválido.'))
        if self.payload != expected:
            raise UserError(_('Los datos de la solicitud cambiaron antes del envío.'))
        issuer = self.payload.get('seller', {}).get('rnc')
        if not rnc or issuer != rnc or self.company_id.vat != rnc:
            raise UserError(_('El RNC no corresponde a la solicitud de esta empresa.'))
        if not signed_xml:
            raise UserError(_('Se requiere el XML firmado antes de reservar el envío.'))
        self.write({'state': 'sending', 'encf': encf, 'signed_xml': signed_xml})
        return self.payload

    def _record_certification_result(self, encf, state, track_id=None):
        self.ensure_one()
        if not self.env.su:
            raise UserError(_('Esta operación requiere el servicio de certificación.'))
        self.env.cr.execute(
            'SELECT id FROM uno360x_ecf_certification_request WHERE id = %s FOR UPDATE', (self.id,),
        )
        self.invalidate_recordset()
        transitions = {
            'sending': {'submitted', 'uncertain'},
            'uncertain': {'submitted'},
            'submitted': {'accepted', 'conditional', 'rejected'},
        }
        if self.encf != encf or state not in transitions.get(self.state, set()):
            raise UserError(_('El estado fiscal no corresponde a la solicitud.'))
        if state == 'submitted' and not track_id:
            raise UserError(_('La DGII debe devolver un TrackId.'))
        if self.state == 'submitted' and track_id != self.track_id:
            raise UserError(_('El TrackId no corresponde a la solicitud.'))
        self.write({'state': state, 'track_id': track_id or False})
