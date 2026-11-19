from odoo import fields, models


class FiscalRegistration(models.Model):
    _name = 'uno360x.fiscal.registration'
    _description = 'Registro fiscal de la empresa'

    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    tax_id = fields.Char(required=True)
    legal_name = fields.Char(required=True)
    fiscal_address = fields.Char(required=True)
    document = fields.Binary(required=True, attachment=False)
    confirmed_by = fields.Many2one('res.users', required=True)

    _sql_constraints = [
        ('unique_company', 'unique(company_id)', 'La empresa ya tiene un registro fiscal.'),
    ]
