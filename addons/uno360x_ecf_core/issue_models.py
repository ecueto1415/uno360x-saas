import json
import base64
from datetime import date
from hashlib import sha256
import re
import logging
from pathlib import Path

from psycopg2.errors import SequenceGeneratorLimitExceeded
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config

from .builder import SUPPORTED_TYPES, build_preview, rnc
from .dgii_client import DGIIError, SubmissionUnknown, validate_result
from .issuance import authorization_number, connect, prepare_signed
from .rfce import build_signed_summary, requires_summary, security_code
from lxml import etree

KIND_NAMES = {'31':'Crédito fiscal','32':'Consumo','33':'Nota de débito','34':'Nota de crédito','41':'Compras','43':'Gastos menores','44':'Regímenes especiales','45':'Gubernamental','46':'Exportaciones','47':'Pagos al exterior'}
KINDS = [(kind, 'E' + kind + ' · ' + KIND_NAMES[kind]) for kind in SUPPORTED_TYPES]


def _wake_fiscal_worker(signal):
    try:
        with signal.open('r+b') as flag:
            flag.write(b'1')
    except FileNotFoundError:
        return  # The timer covers issuers without a path trigger.
    except OSError:
        logging.getLogger(__name__).warning('Fiscal wakeup unavailable; the timer will process the queue.')


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
    cursor_number = fields.Char(compute='_compute_cursor_number', readonly=True)
    expires = fields.Date()
    active = fields.Boolean(default=True)

    def _number_sequence_name(self):
        self.ensure_one()
        return 'uno360x_ecf_range_number_%s' % int(self.id)

    def _create_number_sequence(self):
        for row in self:
            name = row._number_sequence_name()
            self.env.cr.execute('SELECT to_regclass(%s)', (name,))
            if self.env.cr.fetchone()[0]:
                continue
            self.env.cr.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() "
                "AND table_name='uno360x_ecf_range' AND column_name='cursor_number'"
            )
            legacy = None
            if self.env.cr.fetchone():
                self.env.cr.execute(
                    'SELECT cursor_number FROM uno360x_ecf_range WHERE id=%s', (row.id,)
                )
                legacy = self.env.cr.fetchone()
            first, last = int(row.first_number), int(row.last_number)
            next_number = int(legacy[0] or first) if legacy else first
            # The identifier comes only from an integer primary key.
            self.env.cr.execute(
                'CREATE SEQUENCE "%s" AS bigint MINVALUE %s MAXVALUE %s START WITH %s CACHE 1 NO CYCLE'
                % (name, first, last, min(next_number, last))
            )
            if next_number > last:
                self.env.cr.execute('SELECT setval(%s, %s, true)', (name, last))

    def init(self):
        super().init()
        self.with_context(active_test=False).search([])._create_number_sequence()

    @api.depends('first_number', 'last_number')
    def _compute_cursor_number(self):
        for row in self:
            if not isinstance(row.id, int):
                row.cursor_number = False
                continue
            name = row._number_sequence_name()
            self.env.cr.execute('SELECT to_regclass(%s)', (name,))
            if not self.env.cr.fetchone()[0]:
                row.cursor_number = False
                continue
            self.env.cr.execute('SELECT last_value, is_called FROM "%s"' % name)
            value, used = self.env.cr.fetchone()
            row.cursor_number = str(value + 1 if used else value)

    def _number_sequence_used(self):
        return self.filtered(lambda row: int(row.cursor_number or row.first_number) > int(row.first_number))

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
        rows = super().create(vals_list)
        rows._create_number_sequence()
        return rows

    def write(self, vals):
        self._lock_company()
        self.invalidate_recordset(['cursor_number'])
        if 'cursor_number' in vals or (set(vals) - {'active'} and self._number_sequence_used()):
            raise ValidationError(_('Solo se puede archivar un rango que ya se utilizó.'))
        result = super().write(vals)
        if {'first_number', 'last_number'}.intersection(vals):
            for row in self:
                self.env.cr.execute(
                    'ALTER SEQUENCE "%s" MINVALUE %s MAXVALUE %s START WITH %s RESTART WITH %s' %
                    (row._number_sequence_name(), int(row.first_number),
                     int(row.last_number), int(row.first_number), int(row.first_number))
                )
            self.invalidate_recordset(['cursor_number'])
        return result

    def unlink(self):
        self._lock_company()
        self.invalidate_recordset(['cursor_number'])
        if self._number_sequence_used():
            raise ValidationError(_('No se puede eliminar un rango que ya se utilizó.'))
        names = [row._number_sequence_name() for row in self]
        result = super().unlink()
        for name in names:
            self.env.cr.execute('DROP SEQUENCE IF EXISTS "%s"' % name)
        return result

    def _reserve(self, issued):
        self.ensure_one()
        self.invalidate_recordset()
        if not self.active:
            raise ValueError('El rango autorizado está archivado.')
        first, last = int(self.first_number), int(self.last_number)
        current = int(self.cursor_number or self.first_number)
        authorization_number(self.kind, current, first, last, self.expires or date.max, issued)
        # PostgreSQL sequences do not roll back. A failed transaction can
        # leave an unused number, but must never make that number available
        # again to a different invoice. Reserve after accounting validations.
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute('SELECT nextval(%s)', (self._number_sequence_name(),))
                number = self.env.cr.fetchone()[0]
        except SequenceGeneratorLimitExceeded:
            raise ValueError('El rango autorizado está agotado.') from None
        self.invalidate_recordset(['cursor_number'])
        return authorization_number(self.kind, number, first, last, self.expires or date.max, issued)


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

    uno360x_credit_original_encf = fields.Char(compute='_compute_uno360x_credit_display')
    uno360x_credit_state = fields.Char(compute='_compute_uno360x_credit_display')
    uno360x_credit_no_payment = fields.Boolean(compute='_compute_uno360x_credit_display')

    @api.depends('move_type', 'uno360x_ecf_issue_ids.state', 'uno360x_ecf_issue_ids.payload',
                 'reversed_entry_id', 'reversed_entry_id.amount_residual', 'amount_residual',
                 'line_ids.matched_debit_ids')
    def _compute_uno360x_credit_display(self):
        for move in self:
            issue = move.sudo().uno360x_ecf_issue_ids.filtered(
                lambda record: record.encf.startswith('E34')
            )[:1] if move.move_type == 'out_refund' else self.env['uno360x.ecf.issue']
            move.uno360x_credit_state = False
            move.uno360x_credit_original_encf = False
            move.uno360x_credit_no_payment = False
            if not issue:
                continue
            move.uno360x_credit_state = dict(issue._fields['state']._description_selection(self.env)).get(issue.state)
            reference = (issue.payload or {}).get('reference') or {}
            move.uno360x_credit_original_encf = reference.get('ncf')
            original = move.reversed_entry_id
            receivable = move.sudo().line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')
            debit_moves = receivable.matched_debit_ids.debit_move_id.move_id
            covers_original = (
                original and debit_moves == original and
                move.currency_id.is_zero(move.amount_residual) and
                move.currency_id.is_zero(original.amount_residual) and
                not move.currency_id.compare_amounts(move.amount_total, original.amount_total)
            )
            move.uno360x_credit_no_payment = reference.get('code') == '1' or bool(covers_original)

    @api.depends('uno360x_ecf_issue_ids.encf', 'move_type')
    def _compute_display_name(self):
        super()._compute_display_name()
        for move in self.filtered(lambda record: record.move_type in ('out_invoice', 'out_refund')):
            issue = move.sudo().uno360x_ecf_issue_ids.filtered('encf')[:1]
            if issue:
                move.display_name = issue.encf

    uno360x_credit_eligible = fields.Boolean(compute='_compute_uno360x_credit_eligible')

    @api.depends('move_type', 'uno360x_ecf_issue_ids.state')
    def _compute_uno360x_credit_eligible(self):
        for move in self:
            move.uno360x_credit_eligible = move.move_type == 'out_invoice' and any(
                issue.state in ('accepted', 'conditional') for issue in move.sudo().uno360x_ecf_issue_ids
            )

    def _uno360x_check_credit_eligibility(self):
        if self.filtered(lambda move: move.move_type == 'out_invoice' and not move.uno360x_credit_eligible):
            raise UserError(_('La factura debe tener un comprobante electrónico aceptado por la DGII para emitir una nota de crédito.'))

    uno360x_full_credit_encf = fields.Char(compute='_compute_uno360x_full_credit_encf')

    def _uno360x_applied_full_credit(self):
        self.ensure_one()
        if self.move_type != 'out_invoice' or not self.sudo().uno360x_ecf_issue_ids:
            return self.env['uno360x.ecf.issue']
        notes = self.sudo().reversal_move_ids.filtered(
            lambda note: note.state == 'posted' and note.uno360x_credit_no_payment
        )
        return notes.uno360x_ecf_issue_ids.filtered(
            lambda issue: issue.encf.startswith('E34') and issue.state in ('accepted', 'conditional')
        )[:1]

    @api.depends('move_type', 'uno360x_ecf_issue_ids.encf', 'payment_state',
                 'reversal_move_ids.state', 'reversal_move_ids.amount_residual',
                 'reversal_move_ids.uno360x_ecf_issue_ids.state')
    def _compute_uno360x_full_credit_encf(self):
        for move in self:
            move.uno360x_full_credit_encf = move._uno360x_applied_full_credit().encf

    def action_uno360x_applied_credit(self):
        self.ensure_one()
        self.check_access('read')
        note = self._uno360x_applied_full_credit().move_id.with_env(self.env)
        if not note:
            raise UserError(_('No se encontró una nota de crédito electrónica aplicada.'))
        note.check_access('read')
        return note.get_formview_action()

    def uno360x_credit_progress(self, issue_id):
        self.ensure_one()
        self.check_access('read')
        issue = self.env['uno360x.ecf.issue'].browse(issue_id).exists()
        issue.check_access('read')
        if not issue or issue.move_id.reversed_entry_id != self:
            raise UserError(_('La nota no corresponde a esta factura.'))
        success = issue.state in ('accepted', 'conditional')
        done = success or issue.state in ('rejected', 'blocked')
        return {
            'done': done, 'success': success,
            'message': (_('Nota de crédito %s aceptada por la DGII.') % issue.encf) if success
                       else _('La nota requiere revisión. Consulte su estado desde la factura.'),
            'action': self.get_formview_action(),
        }

    @api.depends('ref', 'move_type', 'partner_id', 'invoice_date', 'tax_totals',
                 'invoice_line_ids.product_id', 'invoice_line_ids.quantity',
                 'invoice_line_ids.product_uom_id', 'invoice_line_ids.name',
                 'uno360x_full_credit_encf')
    def _compute_duplicated_ref_ids(self):
        super()._compute_duplicated_ref_ids()

    def _uno360x_duplicate_products(self):
        self.ensure_one()
        return sorted(
            (line.product_id.id or 0,
             '' if line.product_id else ' '.join((line.name or '').split()).casefold(),
             line.product_uom_id.id or 0, line.quantity)
            for line in self.invoice_line_ids
            if line.display_type == 'product'
        )

    def _fetch_duplicate_reference(self, matching_states=('draft', 'posted')):
        result = super()._fetch_duplicate_reference(matching_states=matching_states)
        for move in self.filtered(lambda record: record.move_type == 'out_invoice'):
            origin = move._origin
            if origin not in result:
                continue
            if move.uno360x_full_credit_encf:
                result[origin] = self.env['account.move']
                continue
            products = move._uno360x_duplicate_products()
            result[origin] = result[origin].filtered(
                lambda other: not other.uno360x_full_credit_encf and
                products == other._uno360x_duplicate_products()
            )
        return result


    uno360x_fiscal_live_token = fields.Char(compute='_compute_uno360x_fiscal_live')
    uno360x_fiscal_live_status = fields.Char(compute='_compute_uno360x_fiscal_live')

    def _uno360x_fiscal_progress_data(self):
        self.ensure_one()
        issues = (self.sudo().uno360x_ecf_issue_ids |
                  self.sudo().reversal_move_ids.filtered(lambda move: move.state != 'cancel').uno360x_ecf_issue_ids)
        rows = sorted((issue.id, issue.encf or '', issue.state) for issue in issues)
        pending = any(row[2] in ('queued', 'sent', 'uncertain') for row in rows)
        labels = dict(self.env['uno360x.ecf.issue']._fields['state']._description_selection(self.env))
        return {
            'token': json.dumps(rows),
            'pending': pending,
            'status': ' · '.join('%s — %s' % (encf, labels.get(state, state)) for _, encf, state in rows),
        }

    @api.depends('uno360x_ecf_issue_ids.state', 'uno360x_ecf_issue_ids.encf',
                 'reversal_move_ids.state', 'reversal_move_ids.uno360x_ecf_issue_ids.state')
    def _compute_uno360x_fiscal_live(self):
        for move in self:
            progress = move._uno360x_fiscal_progress_data()
            move.uno360x_fiscal_live_token = progress['token']
            move.uno360x_fiscal_live_status = progress['status']

    def uno360x_fiscal_progress(self):
        self.ensure_one()
        self.check_access('read')
        return self._uno360x_fiscal_progress_data()

    def action_uno360x_credit_original(self):
        self.ensure_one()
        self.check_access('read')
        original = self.reversed_entry_id
        if not original or not self.uno360x_credit_original_encf:
            raise UserError(_('No se encontró la factura original.'))
        original.check_access('read')
        return original.get_formview_action()

    def action_register_payment(self):
        if self.filtered('uno360x_credit_no_payment'):
            raise UserError(_('Esta nota de crédito se aplica a la factura original y no requiere registrar un pago.'))
        return super().action_register_payment()


    def _uno360x_check_credit_origin(self):
        if any(move.move_type == 'out_refund' for move in self):
            raise UserError(_('Abra la factura original para crear una nota de crédito. Una nota de crédito no puede ser el origen de otra.'))

    def action_reverse(self):
        self.check_access('read')
        self._uno360x_check_credit_origin()
        self._uno360x_check_credit_eligibility()
        if self.filtered('uno360x_full_credit_encf'):
            raise UserError(_('La factura ya tiene una nota de crédito electrónica por el total.'))
        return super().action_reverse()

    def _reverse_moves(self, default_values_list=None, cancel=False):
        self._uno360x_check_credit_origin()
        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)

    def action_uno360x_fiscal_open(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Solo Contabilidad puede preparar la emisión fiscal.'))
        existing = self.env['uno360x.ecf.issue'].search([('move_id', '=', self.id)], limit=1)
        if existing:
            return existing.get_formview_action()
        if self.move_type not in ('out_invoice','out_refund','in_invoice') or self.state not in ('draft','posted'):
            raise UserError(_('Abra una factura de cliente en borrador.'))
        kind = {'out_refund':'34','in_invoice':'43'}.get(self.move_type,'31')
        wizard = self.env['uno360x.ecf.issue.wizard'].create({'move_id': self.id,'kind':kind,'reference_move_id':self.reversed_entry_id.id})
        return {'type':'ir.actions.act_window','res_model':wizard._name,'res_id':wizard.id,
                'name': _('Emitir factura electrónica'), 'view_mode':'form','target':'new'}

    def _uno360x_check_fiscal_edit(self):
        ids = sorted(move.id for move in self if isinstance(move.id, int))
        if ids:
            self.env.cr.execute('SELECT id FROM account_move WHERE id = ANY(%s) ORDER BY id FOR UPDATE', (ids,))
            if self.env['uno360x.ecf.issue'].sudo().search_count([('move_id', 'in', ids)], limit=1):
                raise UserError(_('Este comprobante tiene un e-NCF asignado. Sus datos fiscales no se pueden modificar. Para corregirlo, utilice el documento fiscal que corresponda.'))

    def write(self, vals):
        fiscal_fields = {'name', 'state', 'company_id', 'partner_id', 'currency_id', 'date',
                         'invoice_date', 'invoice_date_due', 'invoice_payment_term_id', 'journal_id',
                         'line_ids', 'invoice_line_ids', 'move_type', 'fiscal_position_id', 'ref',
                         'reversed_entry_id', 'narration', 'invoice_origin'}
        if fiscal_fields.intersection(vals):
            self.check_access('write')
            self._uno360x_check_fiscal_edit()
        return super().write(vals)

    def unlink(self):
        self.check_access('unlink')
        self._uno360x_check_fiscal_edit()
        return super().unlink()

    @api.depends('restrict_mode_hash_table', 'state', 'inalterable_hash', 'uno360x_ecf_issue_ids')
    def _compute_show_reset_to_draft_button(self):
        super()._compute_show_reset_to_draft_button()
        for move in self:
            if move.show_reset_to_draft_button and move.sudo().uno360x_ecf_issue_ids:
                move.show_reset_to_draft_button = False

    def button_draft(self):
        if self.sudo().mapped('uno360x_ecf_issue_ids'):
            raise UserError(_('Una factura con e-NCF asignado requiere una corrección fiscal.'))
        return super().button_draft()

    def button_cancel(self):
        if self.sudo().mapped('uno360x_ecf_issue_ids'):
            raise UserError(_('Una factura con e-NCF asignado requiere una corrección fiscal.'))
        return super().button_cancel()


class FiscalCreditReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    uno360x_has_fiscal_issue = fields.Boolean(compute='_compute_uno360x_fiscal_credit')
    uno360x_fiscal_credit = fields.Boolean(compute='_compute_uno360x_fiscal_credit')

    @api.depends('move_ids', 'move_ids.uno360x_ecf_issue_ids.state')
    def _compute_uno360x_fiscal_credit(self):
        for wizard in self:
            move = wizard.move_ids
            wizard.uno360x_has_fiscal_issue = bool(move.sudo().mapped('uno360x_ecf_issue_ids'))
            wizard.uno360x_fiscal_credit = (
                len(move) == 1 and move.move_type == 'out_invoice' and bool(
                    move.sudo().uno360x_ecf_issue_ids.filtered(lambda d: d.state in ('accepted','conditional'))
                )
            )

    def reverse_moves(self, is_modify=False):
        self.ensure_one()
        self.move_ids._uno360x_check_credit_eligibility()
        fiscal = self.move_ids.sudo().mapped('uno360x_ecf_issue_ids')
        if fiscal:
            if is_modify or not self.uno360x_fiscal_credit:
                raise UserError(_('Abra una sola factura fiscal y use Confirmar nota de crédito electrónica.'))
            return self.action_uno360x_confirm_credit()
        return super().reverse_moves(is_modify=is_modify)

    def action_uno360x_confirm_credit(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager') or not self.uno360x_fiscal_credit:
            raise UserError(_('Seleccione una factura fiscal aceptada con acceso de Contabilidad.'))
        original = self.move_ids
        original.check_access('read')
        reason = (self.reason or '').strip()
        if not reason or len(reason) > 90:
            raise UserError(_('Escriba el motivo de la nota de crédito, con un máximo de 90 caracteres.'))
        if self.date > fields.Date.context_today(self):
            raise UserError(_('Seleccione una fecha que no sea futura.'))
        self.env.cr.execute('SELECT id FROM account_move WHERE id=%s FOR UPDATE', (original.id,))
        moves = self.env['account.move']
        notes = moves.search([('reversed_entry_id','=',original.id),('move_type','=','out_refund'),('state','!=','cancel')])
        if len(notes)>1:
            raise UserError(_('Ya existen notas asociadas. Revise las notas existentes desde la factura original.'))
        if notes:
            note = notes
            if note.uno360x_ecf_issue_ids:
                issue = note.uno360x_ecf_issue_ids[:1]
                return self._uno360x_wait_credit(original, issue)
            if original.currency_id.compare_amounts(note.amount_total,original.amount_total):
                return note.get_formview_action()
        else:
            super().reverse_moves(is_modify=False)
            note = self.new_move_ids
        note.ensure_one()
        note.write({'ref':reason})
        action = note.action_uno360x_fiscal_open()
        wizard = self.env[action['res_model']].browse(action['res_id'])
        wizard.write({'kind':'34','reference_move_id':original.id,'modification':'1'})
        wizard.action_confirm()
        issue = note.sudo().uno360x_ecf_issue_ids[:1]
        return self._uno360x_wait_credit(original, issue)

    def _uno360x_wait_credit(self, original, issue):
        action = original.get_formview_action()
        action['target'] = 'current'
        return action


class FiscalMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        move_ids = {v.get('move_id') or self.env.context.get('default_move_id') for v in vals_list}
        self.env['account.move'].browse(sorted(i for i in move_ids if isinstance(i, int) and i))._uno360x_check_fiscal_edit()
        return super().create(vals_list)

    def write(self, vals):
        fiscal_fields = {'move_id', 'name', 'display_type', 'partner_id', 'account_id', 'product_id',
                         'product_uom_id', 'quantity', 'price_unit', 'discount', 'tax_ids',
                         'tax_line_id', 'tax_repartition_line_id', 'date_maturity',
                         'currency_id', 'amount_currency', 'debit', 'credit', 'balance'}
        if fiscal_fields.intersection(vals):
            self.check_access('write')
            self.flush_recordset(['move_id'])
            self.env.cr.execute('SELECT DISTINCT move_id FROM account_move_line WHERE id = ANY(%s)', (self.ids,))
            moves = self.env['account.move'].browse([row[0] for row in self.env.cr.fetchall()])
            if vals.get('move_id'):
                moves |= self.env['account.move'].browse(vals['move_id'])
            moves._uno360x_check_fiscal_edit()
        return super().write(vals)

    def unlink(self):
        self.check_access('unlink')
        self.move_id._uno360x_check_fiscal_edit()
        return super().unlink()


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
        return dict(ncf=source.encf, date=str(original.invoice_date), code=code,
                    reason=(move.ref or '')[:90] if self.kind=='34' else '')

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
            return dict(move.get_formview_action(), target='current')
        company=move.company_id
        if move.state not in ('draft','posted') or not company.uno360x_ecf_enabled:
            raise UserError(_('La emisión está deshabilitada o la factura no está en borrador.'))
        fingerprint=company.uno360x_ecf_fingerprint or ''
        if not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
            raise UserError(_('Configure el certificado fiscal de esta empresa.'))
        issued=move.invoice_date or fields.Date.context_today(self)
        valid_on=max(issued, fields.Date.context_today(self))
        ranges=self.env['uno360x.ecf.range'].search([
            ('company_id','=',company.id),('kind','=',self.kind),'|',('expires','>=',valid_on),('expires','=',False),
        ])
        ranges.invalidate_recordset()
        row = ranges.filtered(lambda x:x.active and int(x.cursor_number or x.first_number)<=int(x.last_number))[:1]
        if not row:
            raise UserError(_('Falta un rango e-NCF autorizado y vigente para el tipo seleccionado.'))
        try:
            payload=self._payload(row.expires)
            build_preview(payload)
        except ValueError as exc:
            raise UserError(str(exc)) from None
        if move.state == 'draft':
            move.action_post()
        if move.state!='posted' or self._payload(row.expires)!=payload:
            raise UserError(_('Contabilidad cambió los datos fiscales al confirmar. Revise la factura.'))
        try:
            encf = row._reserve(issued)
        except ValueError as exc:
            raise UserError(str(exc)) from None
        issue=docs.sudo().create({'move_id':move.id,'company_id':company.id,'range_id':row.id,
            'encf':encf,'payload':payload,'issuer':rnc(company.vat,'RNC emisor'),'fingerprint':fingerprint})
        signal = Path(config['data_dir']) / '.uno360x-fiscal-wakeup'
        self.env.cr.postcommit.add(lambda: _wake_fiscal_worker(signal))
        return dict(move.get_formview_action(), target='current')
