from markupsafe import Markup
from odoo import _, Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import email_normalize

from .calculations import cutoff


class Employee(models.Model):
    _inherit = 'hr.employee'

    ux_payroll_enabled = fields.Boolean(string='Incluir en nómina quincenal', groups='uno360x_payroll_hr.group_payroll')
    ux_payroll_base = fields.Monetary(string='Sueldo base por quincena', currency_field='ux_daypay_currency_id',
                                     groups='uno360x_payroll_hr.group_payroll')
    ux_payroll_deductions = fields.Monetary(string='Descuentos habituales', currency_field='ux_daypay_currency_id',
                                           groups='uno360x_payroll_hr.group_payroll')
    ux_payroll_email = fields.Char(string='Correo individual de nómina', groups='uno360x_payroll_hr.group_payroll')
    ux_payroll_email_verified = fields.Boolean(string='Correo verificado', groups='uno360x_payroll_hr.group_payroll')

    @api.constrains('ux_payroll_enabled', 'employee_type', 'ux_payroll_base', 'ux_payroll_deductions')
    def _check_payroll_profile(self):
        for employee in self.sudo().filtered('ux_payroll_enabled'):
            if employee.employee_type != 'employee' or employee.ux_payroll_base <= 0 or employee.ux_payroll_deductions < 0:
                raise ValidationError(_('Habilite solo empleados fijos con sueldo base positivo y descuentos válidos.'))

    def write(self, vals):
        if 'ux_payroll_email' in vals:
            vals = dict(vals, ux_payroll_email_verified=False)
        return super().write(vals)

    @api.constrains('ux_payroll_email', 'ux_payroll_email_verified')
    def _check_payroll_email(self):
        for employee in self.sudo().filtered('ux_payroll_email_verified'):
            if not email_normalize(employee.ux_payroll_email or '', strict=True):
                raise ValidationError(_('Indique un correo individual válido antes de verificarlo.'))


class Company(models.Model):
    _inherit = 'res.company'

    ux_payroll_mail_server_id = fields.Many2one(
        'ir.mail_server', string='Servidor de correo para nómina', groups='base.group_system',
    )
    ux_payroll_sender = fields.Char(string='Remitente de nómina', groups='base.group_system')


class PayrollBatch(models.Model):
    _name = 'uno360x.payroll.batch'
    _description = 'Nómina quincenal UNO360X'
    _rec_name = 'payroll_date'
    _order = 'payroll_date desc, id desc'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', string='Empresa', default=lambda self: self.env.company,
                                 required=True, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    payroll_date = fields.Date(string='Corte de pago', required=True, default=lambda self: cutoff(fields.Date.context_today(self)))
    state = fields.Selection([('draft', 'Pendiente'), ('approved', 'Aprobada'), ('cancelled', 'Cancelada')],
                             string='Estado', default='draft', required=True, readonly=True, copy=False)
    line_ids = fields.One2many('uno360x.payroll.line', 'batch_id', string='Comprobantes', readonly=True)
    total = fields.Monetary(string='Total neto', compute='_compute_total')
    approved_by = fields.Many2one('res.users', string='Aprobada por', readonly=True, copy=False)
    approved_at = fields.Datetime(string='Fecha de aprobación', readonly=True, copy=False)

    _sql_constraints = [('company_cutoff_unique', 'UNIQUE(company_id, payroll_date)', 'Ya existe una nómina para ese corte.')]

    @api.depends('line_ids.net')
    def _compute_total(self):
        for batch in self:
            batch.total = sum(batch.line_ids.mapped('net'))

    @api.constrains('payroll_date', 'company_id')
    def _check_cutoff(self):
        for batch in self:
            if batch.company_id not in self.env.companies or cutoff(batch.payroll_date) != batch.payroll_date:
                raise ValidationError(_('Seleccione un corte válido de la empresa: 15, 30 o último día de febrero.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any(set(values) - {'payroll_date'} for values in vals_list):
            raise AccessError(_('La empresa y el estado de la nómina se asignan automáticamente.'))
        defaults = {k: v for k, v in self.env.context.items()
                    if not k.startswith('default_') or k == 'default_payroll_date'}
        return super(PayrollBatch, self.with_context(defaults)).create(vals_list)

    def _lock_draft(self):
        self.check_access('write')
        if self.ids:
            self.env.cr.execute('SELECT id FROM uno360x_payroll_batch WHERE id IN %s ORDER BY id FOR UPDATE', (tuple(self.ids),))
            self.invalidate_recordset()
        if any(batch.state != 'draft' for batch in self):
            raise UserError(_('La nómina ya está cerrada.'))

    def write(self, vals):
        self._lock_draft()
        if set(vals) - {'payroll_date'} or self.line_ids:
            raise AccessError(_('Solo puede cambiar el corte antes de preparar los comprobantes.'))
        return super().write(vals)

    def _profiles(self):
        self.ensure_one()
        return self.env['hr.employee'].sudo().search([
            ('company_id', '=', self.company_id.id), ('ux_payroll_enabled', '=', True), ('employee_type', '=', 'employee'),
        ])

    def _approved_weekends(self, employee):
        return self.env['uno360x.payroll.additional'].search([
            ('company_id', '=', self.company_id.id), ('payroll_date', '=', self.payroll_date),
            ('employee_id', '=', employee.id), ('kind', '=', 'weekend'), ('state', '=', 'approved'),
            ('payroll_line_id', '=', False),
        ])

    def action_prepare(self):
        self.ensure_one()
        self._lock_draft()
        profiles = self._profiles()
        if not profiles:
            raise UserError(_('Habilite al menos un empleado fijo con sueldo base por quincena.'))
        by_employee = {line.employee_id.id: line for line in self.line_ids}
        for employee in profiles:
            line = by_employee.get(employee.id)
            if not line:
                line = self.env['uno360x.payroll.line']._prepare(self, employee)
            line._update_weekends(self._approved_weekends(employee))

    def action_approve(self):
        self.ensure_one()
        self._lock_draft()
        self.env.cr.execute('SELECT id FROM res_company WHERE id=%s FOR UPDATE', (self.company_id.id,))
        profiles = self._profiles()
        if not self.line_ids or set(self.line_ids.employee_id.ids) != set(profiles.ids):
            raise UserError(_('Prepare todos los empleados vigentes antes de aprobar.'))
        for line in self.line_ids:
            if not line.reviewed or line.net < 0:
                raise UserError(_('Revise importes y descuentos de todos los comprobantes antes de aprobar.'))
            approved = self._approved_weekends(line.employee_id)
            if set(approved.ids) != set(line.additional_ids.ids) or self.currency_id.compare_amounts(sum(approved.mapped('approved_amount')), line.weekend_total):
                raise UserError(_('Cambió un adicional. Prepare de nuevo el corte y revise los importes.'))
            approved._attach_to_payroll(line)
        return super().write({'state': 'approved', 'approved_by': self.env.uid, 'approved_at': fields.Datetime.now()})

    def action_send_receipts(self):
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM uno360x_payroll_batch WHERE id=%s FOR UPDATE', (self.id,))
        self.invalidate_recordset()
        if self.state != 'approved':
            raise UserError(_('Apruebe la nómina antes de enviar los comprobantes.'))
        company = self.company_id.sudo()
        server = company.ux_payroll_mail_server_id
        sender = email_normalize(company.ux_payroll_sender or '', strict=True)
        if not server or not server.active or not sender:
            raise UserError(_('Configure el servidor y remitente de nómina de esta empresa.'))
        deliveries = []
        for line in self.line_ids:
            employee = self.env['hr.employee'].sudo().browse(line.employee_id.id)
            address = email_normalize(employee.ux_payroll_email or '', strict=True)
            if employee.company_id != self.company_id or not employee.ux_payroll_email_verified or not address:
                raise UserError(_('Verifique el correo individual de todos los empleados del corte.'))
            deliveries.append((line, address))
        if len({address.casefold() for _, address in deliveries}) != len(deliveries):
            raise UserError(_('Dos empleados comparten el mismo correo de nómina.'))
        report = self.env['ir.actions.report']
        for line, address in deliveries:
            if line.sudo().mail_id:
                continue
            pdf, _fmt = report._render_qweb_pdf('uno360x_payroll_hr.biweekly_receipt_pdf', res_ids=line.ids)
            attachment = self.env['ir.attachment'].sudo().create({
                'name': f'Comprobante_{self.payroll_date}.pdf', 'raw': pdf, 'mimetype': 'application/pdf',
                'res_model': line._name, 'res_id': line.id, 'public': False, 'company_id': self.company_id.id,
            })
            mail = self.env['mail.mail'].sudo().create({
                'subject': _('Comprobante de nómina del %s', self.payroll_date),
                'body_html': Markup('<p>{}</p>').format(_('Adjuntamos su comprobante individual de nómina.')),
                'email_from': sender, 'email_to': address, 'mail_server_id': server.id,
                'attachment_ids': [Command.link(attachment.id)], 'auto_delete': False,
            })
            line._record_delivery(mail)
            mail.send_after_commit()

    def action_cancel(self):
        self._lock_draft()
        return super().write({'state': 'cancelled'})


class PayrollLine(models.Model):
    _name = 'uno360x.payroll.line'
    _description = 'Comprobante individual de nómina'
    _rec_name = 'employee_id'
    _check_company_auto = True

    batch_id = fields.Many2one('uno360x.payroll.batch', string='Nómina', required=True, ondelete='restrict', check_company=True)
    employee_id = fields.Many2one('hr.employee.public', string='Empleado', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    payroll_date = fields.Date(related='batch_id.payroll_date', string='Corte')
    state = fields.Selection(related='batch_id.state')
    salary_base = fields.Monetary(string='Sueldo base', required=True)
    deductions = fields.Monetary(string='Descuentos revisados')
    other = fields.Monetary(string='Otros ingresos')
    incentive = fields.Monetary(string='Incentivo por proyecto')
    incentive_reason = fields.Char(string='Proyecto y motivo del incentivo')
    additional_ids = fields.Many2many('uno360x.payroll.additional', string='Días de fin de semana', readonly=True)
    weekend_total = fields.Monetary(string='Adicionales de fin de semana', readonly=True)
    net = fields.Monetary(string='Neto a cobrar', compute='_compute_net', store=True)
    reviewed = fields.Boolean(string='Importes y descuentos revisados')
    mail_id = fields.Many2one('mail.mail', readonly=True, copy=False, groups='base.group_system')
    delivery_state = fields.Selection(related='mail_id.state', string='Estado del correo',
                                      groups='uno360x_payroll_hr.group_payroll')


    _sql_constraints = [
        ('batch_employee_unique', 'UNIQUE(batch_id, employee_id)', 'Ya existe un comprobante para ese empleado y corte.'),
        ('valid_amounts', 'CHECK(salary_base > 0 AND deductions >= 0 AND other >= 0 AND incentive >= 0)',
         'El sueldo debe ser positivo y los demás importes no pueden ser negativos.'),
    ]

    @api.depends('salary_base', 'deductions', 'other', 'incentive', 'weekend_total', 'currency_id')
    def _compute_net(self):
        for line in self:
            value = line.salary_base + line.other + line.incentive + line.weekend_total - line.deductions
            line.net = line.currency_id.round(value) if line.currency_id else value

    @api.constrains('incentive', 'incentive_reason')
    def _check_incentive(self):
        if any(line.incentive and not (line.incentive_reason or '').strip() for line in self):
            raise ValidationError(_('Indique el proyecto y el motivo del incentivo.'))

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Prepare los comprobantes desde la nómina quincenal.'))

    @api.model
    def _prepare(self, batch, employee):
        defaults = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        return super(PayrollLine, self.with_context(defaults)).create({
            'batch_id': batch.id, 'employee_id': employee.id,
            'salary_base': employee.ux_payroll_base, 'deductions': employee.ux_payroll_deductions,
        })

    def _update_weekends(self, days):
        self.ensure_one()
        amount = sum(days.mapped('approved_amount'))
        if set(days.ids) != set(self.additional_ids.ids) or self.currency_id.compare_amounts(amount, self.weekend_total):
            super().write({'additional_ids': [Command.set(days.ids)], 'weekend_total': amount, 'reviewed': False})

    def _record_delivery(self, mail):
        super(PayrollLine, self.sudo()).write({'mail_id': mail.id})

    def write(self, vals):
        self.check_access('write')
        self.batch_id._lock_draft()
        editable = {'salary_base', 'deductions', 'other', 'incentive', 'incentive_reason'}
        if set(vals) - (editable | {'reviewed'}):
            raise AccessError(_('No se pueden cambiar el empleado, el corte ni los días aprobados desde el comprobante.'))
        if editable.intersection(vals):
            vals = dict(vals, reviewed=False)
        return super().write(vals)
