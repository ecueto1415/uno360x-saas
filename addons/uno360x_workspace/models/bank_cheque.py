import re
from decimal import Decimal
from math import isfinite

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class BankCheque(models.Model):
    _name = 'uno360x.bank.cheque'
    _description = 'Cheque bancario'
    _order = 'id desc'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    journal_id = fields.Many2one('account.journal', required=True, ondelete='restrict', check_company=True)
    currency_id = fields.Many2one(related='journal_id.uno_cheque_currency_id')
    beneficiary = fields.Char(required=True, size=120)
    date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(required=True)
    memo = fields.Char(size=150)
    bill_id = fields.Many2one('account.move', ondelete='restrict', check_company=True)
    number = fields.Char(readonly=True, copy=False)
    state = fields.Selection([('draft', 'Borrador'), ('issued', 'Emitido'), ('void', 'Anulado')], default='draft', required=True, copy=False)
    issued_by = fields.Many2one('res.users', readonly=True, copy=False)
    void_reason = fields.Char(readonly=True, copy=False)

    _sql_constraints = [('number_unique', 'unique(journal_id, number)', 'Ese número de cheque ya fue utilizado en esta cuenta.')]

    @api.constrains('journal_id', 'company_id', 'amount', 'beneficiary', 'bill_id')
    def _check_details(self):
        for cheque in self:
            if cheque.journal_id.type != 'bank' or cheque.journal_id.company_id != cheque.company_id:
                raise ValidationError(_('Selecciona una cuenta bancaria de esta empresa.'))
            if not (cheque.beneficiary or '').strip() or not isfinite(cheque.amount) or not cheque.amount > 0 or cheque.amount >= 10**12:
                raise ValidationError(_('Indica un beneficiario y un monto válido.'))
            bill = cheque.bill_id
            if bill and (bill.move_type != 'in_invoice' or bill.state != 'posted' or bill.currency_id != cheque.currency_id):
                raise ValidationError(_('Vincula una factura de proveedor confirmada en la misma moneda.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if set(vals) - {'company_id', 'journal_id', 'beneficiary', 'date', 'amount', 'memo', 'bill_id'}:
                raise AccessError(_('Usa el formulario de cheques.'))
            if vals.get('company_id', self.env.company.id) != self.env.company.id:
                raise AccessError(_('Selecciona la empresa activa.'))
            vals.update(state='draft', number=False, issued_by=False, void_reason=False)
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - {'journal_id', 'beneficiary', 'date', 'amount', 'memo', 'bill_id'}:
            raise AccessError(_('Usa las acciones de Cheques para cambiar el estado.'))
        for cheque in self:
            cheque._lock()
            if cheque.state != 'draft':
                raise UserError(_('Solo puedes editar un borrador.'))
        return super().write(vals)

    def _lock(self):
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM uno360x_bank_cheque WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def _issue(self, number):
        self._lock()
        if self.state == 'issued' and self.number == number:
            return
        if self.state != 'draft' or not re.fullmatch(r'[0-9]{1,16}', number or ''):
            raise UserError(_('Introduce el número impreso en la hoja de la chequera.'))
        self.env.cr.execute('SELECT id FROM account_journal WHERE id = %s FOR UPDATE', [self.journal_id.id])
        if self.search_count([('journal_id', '=', self.journal_id.id), ('number', '=', number)]):
            raise UserError(_('Ese número de cheque ya fue utilizado.'))
        super(BankCheque, self).write({'number': number, 'state': 'issued', 'issued_by': self.env.uid})

    def _void(self, reason):
        self._lock()
        if self.state != 'issued' or not reason.strip():
            raise UserError(_('Indica el motivo para anular el cheque emitido.'))
        super(BankCheque, self).write({'state': 'void', 'void_reason': reason.strip()[:250]})

    def _amount_words(self):
        self.ensure_one()
        from num2words import num2words
        rounded = Decimal(str(self.currency_id.round(self.amount)))
        whole = int(rounded)
        cents = int((rounded - whole).scaleb(2).quantize(Decimal('1')))
        labels = {'DOP': ('peso dominicano', 'pesos dominicanos'), 'USD': ('dólar estadounidense', 'dólares estadounidenses')}
        singular, plural = labels.get(self.currency_id.name, (self.currency_id.name, self.currency_id.name))
        words = num2words(whole, lang='es')
        words = re.sub(r'(?:uno|ún)$', 'un', words)
        currency = singular if whole == 1 else plural
        if whole and whole % 1000000 == 0:
            currency = 'de ' + currency
        return f'{words.capitalize()} {currency} con {cents:02d}/100'


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    uno_cheque_currency_id = fields.Many2one('res.currency', compute='_compute_cheque_currency')
    uno_cheque_x = fields.Float(string='Ajuste horizontal del cheque (mm)', default=0)
    uno_cheque_y = fields.Float(string='Ajuste vertical del cheque (mm)', default=0)

    @api.depends('currency_id', 'company_id.currency_id')
    def _compute_cheque_currency(self):
        for journal in self:
            journal.uno_cheque_currency_id = journal.currency_id or journal.company_id.currency_id

    uno_cheque_width = fields.Float(default=216)
    uno_cheque_height = fields.Float(default=279)
    uno_cheque_date_x = fields.Float(default=183)
    uno_cheque_date_y = fields.Float(default=18)
    uno_cheque_beneficiary_x = fields.Float(default=27)
    uno_cheque_beneficiary_y = fields.Float(default=31)
    uno_cheque_amount_x = fields.Float(default=190)
    uno_cheque_amount_y = fields.Float(default=31)
    uno_cheque_words_x = fields.Float(default=18)
    uno_cheque_words_y = fields.Float(default=44)

    @api.constrains('uno_cheque_width', 'uno_cheque_height', 'uno_cheque_date_x', 'uno_cheque_date_y', 'uno_cheque_beneficiary_x', 'uno_cheque_beneficiary_y', 'uno_cheque_amount_x', 'uno_cheque_amount_y', 'uno_cheque_words_x', 'uno_cheque_words_y', 'uno_cheque_x', 'uno_cheque_y')
    def _check_cheque_layout(self):
        for journal in self:
            width = journal.uno_cheque_width or 216
            height = journal.uno_cheque_height or 279
            if not (80 <= width <= 500 and 60 <= height <= 500):
                raise ValidationError(_('Revisa el ancho y el alto del papel.'))
            for key, right in [('date', True), ('beneficiary', False), ('amount', True), ('words', False)]:
                x = journal['uno_cheque_' + key + '_x'] + journal.uno_cheque_x
                y = journal['uno_cheque_' + key + '_y'] + journal.uno_cheque_y
                if not (0 <= x <= width and 5 <= y <= height and (x >= 15 if right else width - x >= 15)):
                    raise ValidationError(_('Los campos deben quedar dentro del papel.'))
