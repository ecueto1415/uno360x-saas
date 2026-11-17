import base64
from datetime import date
from hashlib import sha256
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .builder import SUPPORTED_TYPES, build_preview, rnc
from .dgii_client import DGIIError, SubmissionUnknown, validate_result
from .issuance import authorization_number, connect, prepare_signed
from .rfce import build_signed_summary, requires_summary, security_code
from lxml import etree

KIND_NAMES = {'31':'Crédito fiscal','32':'Consumo','33':'Nota de débito','34':'Nota de crédito','41':'Compras','43':'Gastos menores','44':'Regímenes especiales','45':'Gubernamental','46':'Exportaciones','47':'Pagos al exterior'}
KINDS = [(kind, 'E' + kind + ' · ' + KIND_NAMES[kind]) for kind in SUPPORTED_TYPES]


class FiscalCompany(models.Model):
    _inherit = 'res.company'

    uno360x_ecf_range_ids = fields.One2many('uno360x.ecf.range', 'company_id')
    uno360x_ecf_range_revision = fields.Integer(copy=False, groups='base.group_system')
    uno360x_ecf_enabled = fields.Boolean(groups='account.group_account_manager')
    uno360x_ecf_fingerprint = fields.Char(
        string='Huella SHA-256 del certificado', groups='account.group_account_manager', copy=False,
    )


class FiscalTax(models.Model):
    _inherit = 'account.tax'

    uno360x_ecf_export_zero = fields.Boolean(string='Tasa cero de exportación para e-CF')
    uno360x_ecf_retention = fields.Selection([('itbis','Retención de ITBIS'),('isr','Retención de ISR')])
    uno360x_ecf_exempt = fields.Boolean(string='Exento de ITBIS para e-CF')


class FiscalRange(models.Model):
    _name = 'uno360x.ecf.range'
    _description = 'Rango e-NCF autorizado por DGII'
    _order = 'expires, id'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    kind = fields.Selection(KINDS, required=True)
    authorization = fields.Char(required=True)
    first_number = fields.Char(required=True)
    last_number = fields.Char(required=True)
    cursor_number = fields.Char(readonly=True, copy=False)
    expires = fields.Date()
    active = fields.Boolean(default=True)

    def _lock_company(self):
        for company in self.mapped('company_id').sorted('id'):
            self.env.cr.execute('UPDATE res_company SET uno360x_ecf_range_revision=COALESCE(uno360x_ecf_range_revision,0)+1 WHERE id=%s', (company.id,))

    @api.constrains('kind','first_number','last_number','company_id','authorization','expires')
    def _check_bounds(self):
        self._lock_company()
        for row in self:
            if not row.expires and row.kind != '34':
                raise ValidationError(_('Indique el vencimiento autorizado por la DGII.'))
            if not re.fullmatch(r'[0-9]{1,10}', row.first_number or '') or not re.fullmatch(r'[0-9]{1,10}', row.last_number or ''):
                raise ValidationError(_('Indique los extremos numéricos del rango autorizado.'))
            start, end = int(row.first_number), int(row.last_number)
            if not 1 <= start <= end:
                raise ValidationError(_('El rango autorizado no es válido.'))
            others = self.with_context(active_test=False).sudo().search([
                ('id','!=',row.id), ('company_id','=',row.company_id.id), ('kind','=',row.kind),
            ])
            if any(start <= int(x.last_number) and end >= int(x.first_number) for x in others):
                raise ValidationError(_('El rango coincide con otra autorización de esta empresa.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any('cursor_number' in vals for vals in vals_list):
            raise ValidationError(_('El siguiente e-NCF se administra automáticamente.'))
        return super().create([dict(vals, cursor_number=False) for vals in vals_list])

    def write(self, vals):
        self._lock_company()
        self.invalidate_recordset(['cursor_number'])
        if 'cursor_number' in vals or (set(vals) - {'active'} and self.filtered('cursor_number')):
            raise ValidationError(_('Solo se puede archivar un rango que ya se utilizó.'))
        return super().write(vals)

    def unlink(self):
        self._lock_company()
        self.invalidate_recordset(['cursor_number'])
        if self.filtered('cursor_number'):
            raise ValidationError(_('No se puede eliminar un rango que ya se utilizó.'))
        return super().unlink()

    def _reserve(self, issued):
        self.ensure_one()
        self._lock_company()
        self.invalidate_recordset()
        if not self.active:
            raise ValueError('El rango autorizado está archivado.')
        start, end = int(self.first_number), int(self.last_number)
        number = int(self.cursor_number or start)
        encf = authorization_number(self.kind, number, start, end, self.expires or date.max, issued)
        super(FiscalRange, self).write({'cursor_number': str(number+1)})
        return encf


class FiscalDocument(models.Model):
    _name = 'uno360x.ecf.issue'
    _description = 'Emisión electrónica de cliente'
    _rec_name = 'encf'

    company_id = fields.Many2one('res.company', required=True)
    move_id = fields.Many2one('account.move', required=True, ondelete='restrict')
    range_id = fields.Many2one('uno360x.ecf.range', required=True, ondelete='restrict')
    encf = fields.Char(required=True)
    issuer = fields.Char(required=True)
    fingerprint = fields.Char(required=True, groups='base.group_system')
    payload = fields.Json(required=True, groups='base.group_system')
    signed_xml = fields.Binary(attachment=False, groups='base.group_system')
    signed_summary = fields.Binary(attachment=False, groups='base.group_system')
    signed_sha256 = fields.Char(groups='base.group_system')
    track_id = fields.Char()
    state = fields.Selection([
        ('queued','Pendiente de firma y envío'), ('blocked','Revisar configuración'),
        ('uncertain','En conciliación'), ('sent','Recibido por la DGII'),
        ('accepted','Aceptado'), ('conditional','Aceptado condicional'),
        ('rejected','Rechazado'),
    ], required=True, default='queued', index=True)
    _sql_constraints = [
        ('one_issue_per_move','unique(move_id)','Esta factura ya tiene un comprobante.'),
        ('issuer_encf_unique','unique(issuer, encf)','Este e-NCF ya está asignado al emisor.'),
    ]

    def _dispatch(self, p12, password, company, client_factory=connect):
        """Run from a dedicated worker transaction, never from an HTTP action."""
        self.ensure_one()
        assert self.env.su and self.company_id == company
        self.env.cr.execute('SELECT id FROM uno360x_ecf_issue WHERE id=%s FOR UPDATE SKIP LOCKED', (self.id,))
        if not self.env.cr.fetchone():
            return
        self.invalidate_recordset()
        if self.state != 'queued':
            return
        try:
            if not company.uno360x_ecf_enabled or company.uno360x_ecf_fingerprint != self.fingerprint:
                raise ValueError('Configuración fiscal cambió.')
            signed = prepare_signed(self.payload, self.encf, company.vat, self.fingerprint, p12, password)
            summary = build_signed_summary(signed, p12, password) if requires_summary(self.payload) else None
            client = client_factory(p12, password)
        except (ValueError, OSError, etree.LxmlError):
            self.state = 'blocked'
            self.env.cr.commit()
            return
        # Commit the idempotency marker before the first non-retryable network write.
        self.write({
            'state':'uncertain', 'signed_xml':base64.b64encode(signed),
            'signed_sha256':sha256(signed).hexdigest(),
            'signed_summary':base64.b64encode(summary) if summary else False,
        })
        self.env.cr.commit()
        try:
            if summary:
                result = {'state':client.submit_summary(summary, self.issuer, self.encf)}
            else:
                receipt = client.submit(signed, self.issuer, self.encf)
                result = {'state':'sent', 'track_id':receipt['trackId']}
        except SubmissionUnknown:
            return
        self.write(result)
        self.env.cr.commit()

    def _consult(self, client):
        self.ensure_one()
        if self.state not in ('uncertain','sent'):
            return
        if self.signed_summary:
            xml = base64.b64decode(self.signed_xml, validate=True)
            if sha256(xml).hexdigest() != self.signed_sha256:
                raise DGIIError('No se puede conciliar un RFCE con un XML alterado.')
            self.state = client.lookup_summary(self.issuer, self.encf, security_code(xml))
            return
        track = self.track_id
        if not track:
            rows = client.tracks(self.issuer, self.encf)
            tracks = {str(row['trackId']) for row in rows if row.get('trackId')}
            if len(tracks) != 1:
                return
            track = tracks.pop()
        state = validate_result(client.result(track), self.issuer, self.encf, track)
        if state:
            self.write({'state': state, 'track_id': track})


class FiscalMove(models.Model):
    _inherit = 'account.move'

    uno360x_ecf_issue_ids = fields.One2many('uno360x.ecf.issue','move_id')

    def action_uno360x_fiscal_open(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Solo Contabilidad puede preparar la emisión fiscal.'))
        if self.move_type not in ('out_invoice','out_refund','in_invoice') or self.state != 'draft':
            raise UserError(_('Abra una factura de cliente en borrador.'))
        kind = {'out_refund':'34','in_invoice':'43'}.get(self.move_type,'31')
        wizard = self.env['uno360x.ecf.issue.wizard'].create({'move_id': self.id,'kind':kind,'reference_move_id':self.reversed_entry_id.id})
        return {'type':'ir.actions.act_window','res_model':wizard._name,'res_id':wizard.id,
                'name': _('Emitir factura electrónica'), 'view_mode':'form','target':'new'}

    def write(self, vals):
        fiscal_fields = {'company_id','partner_id','currency_id','invoice_date',
                         'invoice_date_due','line_ids','invoice_line_ids','move_type'}
        if fiscal_fields.intersection(vals) and self.sudo().mapped('uno360x_ecf_issue_ids'):
            raise UserError(_('Los datos de una factura con e-NCF asignado quedan protegidos.'))
        return super().write(vals)

    def button_draft(self):
        if self.sudo().mapped('uno360x_ecf_issue_ids'):
            raise UserError(_('Una factura con e-NCF asignado requiere una corrección fiscal.'))
        return super().button_draft()

    def button_cancel(self):
        if self.sudo().mapped('uno360x_ecf_issue_ids'):
            raise UserError(_('Una factura con e-NCF asignado requiere una corrección fiscal.'))
        return super().button_cancel()


class FiscalWizard(models.TransientModel):
    _name = 'uno360x.ecf.issue.wizard'
    _description = 'Confirmar emisión de factura electrónica'

    move_id = fields.Many2one('account.move', required=True, readonly=True)
    partner_id = fields.Many2one(related='move_id.partner_id')
    currency_id = fields.Many2one(related='move_id.currency_id')
    amount_total = fields.Monetary(related='move_id.amount_total')
    kind = fields.Selection(KINDS, required=True, default='31')
    payment_type = fields.Selection([('1','Contado'),('2','Crédito')], required=True, default='2')
    income_type = fields.Selection([
        ('01','Ingresos de operaciones'), ('02','Ingresos financieros'), ('03','Extraordinarios'),
        ('04','Arrendamiento'), ('05','Venta de activo depreciable'), ('06','Otros ingresos'),
    ], required=True, default='01')

    reference_move_id = fields.Many2one('account.move', string='Factura original')
    modification = fields.Selection([('1','Anulación total'),('3','Corrección de monto')], default='3')

    def _reference(self):
        if self.kind not in ('33','34'):
            return {}
        move, original = self.move_id, self.reference_move_id
        if not original or original == move:
            raise UserError(_('Seleccione la factura original.'))
        original.check_access('read')
        if (
            original.move_type != 'out_invoice' or original.state != 'posted'
            or original.company_id != move.company_id
            or original.commercial_partner_id != move.commercial_partner_id
            or (self.kind=='34' and move.reversed_entry_id != original)
        ):
            raise UserError(_('La nota debe corresponder a la factura de origen de la misma empresa y cliente.'))
        source = original.uno360x_ecf_issue_ids.filtered(lambda d:d.state in ('accepted','conditional'))
        if len(source) != 1 or not original.invoice_date:
            raise UserError(_('La factura original requiere un comprobante aceptado.'))
        code = '3' if self.kind == '33' else self.modification
        if self.kind=='34' and (move.amount_total > original.amount_total or (code=='1' and move.amount_total != original.amount_total)):
            raise UserError(_('Revise el monto de la nota con respecto a la factura original.'))
        return {'ncf':source.encf,'date':str(original.invoice_date),'code':code}

    def _payload(self, expiry):
        move = self.move_id
        company = move.company_id
        lines = []
        for line in move.invoice_line_ids.filtered(lambda l:l.display_type=='product'):
            taxes = line.tax_ids.filtered(lambda tax:not tax.uno360x_ecf_retention)
            retained = line.tax_ids - taxes
            if len(taxes)!=1 or taxes.amount_type!='percent' or taxes.price_include:
                raise UserError(_('Use un impuesto porcentual explícito por partida, incluso si es exenta.'))
            if taxes.amount not in (0,16,18) or (not taxes.amount and not (taxes.uno360x_ecf_exempt or taxes.uno360x_ecf_export_zero)):
                raise UserError(_('Clasifique las partidas sin ITBIS como exentas o tasa cero de exportación.'))
            if taxes.uno360x_ecf_exempt and taxes.uno360x_ecf_export_zero:
                raise UserError(_('Un impuesto no puede ser exento y tasa cero de exportación a la vez.'))
            if retained and (self.kind not in ('41','47') or any(
                t.amount >= 0 or t.amount_type != 'percent' or t.price_include or t.include_base_amount for t in retained
            ) or taxes.include_base_amount):
                raise UserError(_('La tasa de ITBIS no está soportada por este comprobante.'))
            raw = line.price_unit * line.quantity * (1-line.discount/100)
            def retention(kind):
                return sum(move.currency_id.round(-raw*t.amount/100) for t in retained if t.uno360x_ecf_retention==kind)
            lines.append({
                'name': (line.product_id.name or line.name or '')[:80],
                'quantity':line.quantity, 'price_unit':line.price_unit,
                'discount':line.discount, 'subtotal':line.price_subtotal,
                'goods_service':'2' if line.product_id.type=='service' else '1', 'tax_rate':taxes.amount,
                'tax_category': '3' if taxes.uno360x_ecf_export_zero else {18:'1',16:'2',0:'4'}[taxes.amount],
                'retained_itbis':retention('itbis'),'retained_isr':retention('isr'),
            })
        buyer = move.partner_id.commercial_partner_id
        return {
            'currency':move.currency_id.name, 'move_type':move.move_type,
            'rounding_method':company.tax_calculation_rounding_method, 'document_type':self.kind,'reference':self._reference(),
            'payment_type':self.payment_type,'income_type':self.income_type,
            'invoice_date':str(move.invoice_date or fields.Date.context_today(self)),
            'due_date':str(move.invoice_date_due or ''),'test_expiry':str(expiry),
            'seller':{'rnc':company.vat,'name':company.name,'address':company.street},
            'buyer':{'rnc':buyer.vat,'name':buyer.name,'foreign_id':buyer.vat},'lines':lines,
            'amount_untaxed':move.amount_untaxed,'amount_tax':move.amount_tax,'amount_total':move.amount_total,
        }

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Solo Contabilidad puede confirmar la emisión.'))
        move = self.move_id
        move.check_access('write')
        self.env.cr.execute('SELECT id FROM account_move WHERE id=%s FOR UPDATE',(move.id,))
        move.invalidate_recordset()
        if move.company_id not in self.env.companies or move.move_type!={'34':'out_refund','41':'in_invoice','43':'in_invoice','47':'in_invoice'}.get(self.kind,'out_invoice'):
            raise UserError(_('La factura no corresponde a su empresa.'))
        docs = self.env['uno360x.ecf.issue']
        existing = docs.search([('move_id','=',move.id)],limit=1)
        if existing:
            return existing.get_formview_action()
        company=move.company_id
        if move.state!='draft' or not company.uno360x_ecf_enabled:
            raise UserError(_('La emisión está deshabilitada o la factura no está en borrador.'))
        fingerprint=company.uno360x_ecf_fingerprint or ''
        if not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
            raise UserError(_('Configure el certificado fiscal de esta empresa.'))
        issued=move.invoice_date or fields.Date.context_today(self)
        valid_on=max(issued, fields.Date.context_today(self))
        ranges=self.env['uno360x.ecf.range'].search([
            ('company_id','=',company.id),('kind','=',self.kind),'|',('expires','>=',valid_on),('expires','=',False),
        ])
        ranges._lock_company()
        ranges.invalidate_recordset()
        row = ranges.filtered(lambda x:x.active and int(x.cursor_number or x.first_number)<=int(x.last_number))[:1]
        if not row:
            raise UserError(_('Falta un rango e-NCF autorizado y vigente para el tipo seleccionado.'))
        try:
            payload=self._payload(row.expires)
            build_preview(payload)
            encf=row._reserve(issued)
        except ValueError as exc:
            raise UserError(str(exc)) from None
        move.action_post()
        if move.state!='posted' or self._payload(row.expires)!=payload:
            raise UserError(_('Contabilidad cambió los datos fiscales al confirmar. Revise la factura.'))
        issue=docs.sudo().create({'move_id':move.id,'company_id':company.id,'range_id':row.id,
            'encf':encf,'payload':payload,'issuer':rnc(company.vat,'RNC emisor'),'fingerprint':fingerprint})
        return issue.with_user(self.env.user).get_formview_action()
