from datetime import date, datetime
import re
from zoneinfo import ZoneInfo

from odoo import fields, models
from odoo.exceptions import UserError

DOCUMENT_TYPES = [
    ('31', 'E31 · Crédito fiscal'),
    ('44', 'E44 · Regímenes especiales'),
    ('45', 'E45 · Gubernamental'),
]


class FiscalSequenceRequest(models.Model):
    _name = 'uno360x.fiscal.sequence.request'
    _description = 'Rango fiscal presentado por la empresa'
    _order = 'id desc'

    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    tax_id = fields.Char(required=True)
    document_type = fields.Selection(DOCUMENT_TYPES, required=True)
    authorization = fields.Char(required=True)
    first_encf = fields.Char(required=True)
    last_encf = fields.Char(required=True)
    next_encf = fields.Char(required=True)
    expires = fields.Date(required=True)
    submitted_by = fields.Many2one('res.users', required=True)

    _sql_constraints = [
        ('unique_authorization', 'unique(company_id, tax_id, document_type, authorization)',
         'Esa autorización ya está registrada para el tipo de comprobante.'),
    ]

    def _submit_range(self, company, user, form):
        tax_id = re.sub(r'[\s-]', '', company.vat or '')
        if not re.fullmatch(r'(?:[0-9]{9}|[0-9]{11})', tax_id) or not int(tax_id):
            raise UserError('Guarda el RNC o la cédula en Datos de la empresa antes de agregar una secuencia.')
        kind = form['document_type']
        if kind not in dict(DOCUMENT_TYPES):
            raise UserError('Selecciona un tipo de comprobante.')
        authorization = form['authorization'].strip().upper()
        if not re.fullmatch(r'[A-Z0-9-]{1,60}', authorization):
            raise UserError('Ingresa el número de autorización de la DGII.')
        first, last, next_number = (
            form[key].strip().upper() for key in ('first_encf', 'last_encf', 'next_encf')
        )
        next_number = next_number or first
        if not all(re.fullmatch(fr'E{kind}[0-9]{{10}}', value) and int(value[3:])
                   for value in (first, last, next_number)):
            raise UserError(f'Los números deben empezar por E{kind} y tener diez dígitos adicionales.')
        if not first <= next_number <= last:
            raise UserError('El próximo e-NCF debe estar entre el inicial y el final.')
        try:
            expires = date.fromisoformat(form['expires'])
        except ValueError:
            raise UserError('Ingresa una fecha de vencimiento válida.') from None
        today = datetime.now(ZoneInfo('America/Santo_Domingo')).date()
        if expires < today:
            raise UserError('La fecha de vencimiento ya pasó.')

        # Touch the company row so concurrent submissions retry with a fresh snapshot.
        self.env.cr.execute('UPDATE res_company SET id = id WHERE id = %s', [company.id])
        domain = [('company_id', '=', company.id), ('tax_id', '=', tax_id), ('document_type', '=', kind)]
        existing = self.search(domain + [('authorization', '=', authorization)], limit=1)
        if existing:
            if (existing.first_encf, existing.last_encf, existing.next_encf, existing.expires) == (
                first, last, next_number, expires
            ):
                return existing
            raise UserError('Esa autorización ya está registrada con otros datos.')
        if self.search_count(domain + [('first_encf', '<=', last), ('last_encf', '>=', first)], limit=1):
            raise UserError('Este rango se superpone con una secuencia ya registrada.')
        return self.create({
            'company_id': company.id, 'tax_id': tax_id, 'document_type': kind,
            'authorization': authorization, 'first_encf': first, 'last_encf': last,
            'next_encf': next_number, 'expires': expires, 'submitted_by': user.id,
        })
