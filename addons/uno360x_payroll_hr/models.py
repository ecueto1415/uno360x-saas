from odoo import fields, models


class Contract(models.Model):
    _inherit = 'hr.contract'

    wage = fields.Monetary(groups='uno360x_payroll_hr.group_payroll')


class PayrollReceipt(models.Model):
    _name = 'uno360x.payroll.receipt'
    _description = 'Recibo de nómina UNO360X'
    _order = 'date desc, id desc'

    name = fields.Char(string='Referencia', required=True)
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company)
    employee_id = fields.Many2one('hr.employee.public', string='Empleado',
                                  required=True, check_company=True, ondelete='restrict')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    filename = fields.Char(string='Nombre del archivo')
    document = fields.Binary(string='Recibo', required=True, attachment=False,
                             groups='uno360x_payroll_hr.group_payroll')

