from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .calculations import cutoff, totals


class Employee(models.Model):
    _inherit = 'hr.employee'

    ux_weekend_eligible = fields.Boolean(string='Habilitado para adicionales de fin de semana')
    ux_daypay_eligible = fields.Boolean(string='Habilitado para trabajar por jornada')
    ux_daypay_net = fields.Monetary(
        string='Neto acordado por jornada', currency_field='ux_daypay_currency_id',
        groups='uno360x_payroll_hr.group_payroll',
    )
    ux_daypay_currency_id = fields.Many2one(related='company_id.currency_id')
    ux_daypay_rate = fields.Float(
        string='RetenciÃ³n asumida (%)', groups='uno360x_payroll_hr.group_payroll',
    )

    @api.constrains('ux_daypay_eligible', 'employee_type')
    def _check_daypay_eligibility(self):
        if any(employee.ux_daypay_eligible and employee.employee_type != 'contractor' for employee in self):
            raise ValidationError(_('Solo los contratistas se habilitan para trabajo por jornada.'))



class Company(models.Model):
    _inherit = 'res.company'

    ux_weekend_rate = fields.Monetary(
        string='Tarifa por dÃ­a de fin de semana', currency_field='currency_id',
        default=1500, groups='uno360x_payroll_hr.group_payroll',
    )

    _sql_constraints = [
        ('ux_weekend_rate_positive', 'CHECK(ux_weekend_rate >= 0)', 'La tarifa no puede ser negativa.'),
    ]


class WeekendAdditional(models.Model):
    _name = 'uno360x.payroll.additional'
    _description = 'Adicional de nÃ³mina por fin de semana'
    _rec_name = 'employee_id'
    _order = 'payroll_date desc, work_date desc, id desc'
    _check_company_auto = True

    kind = fields.Selection([('weekend', 'Fin de semana'), ('day', 'Por jornada')],
                            string='Modalidad', required=True, default='weekend')
    employee_id = fields.Many2one('hr.employee.public', string='Empleado o contratista', required=True,
                                  check_company=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', string='Empresa', related='employee_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    work_date = fields.Date(string='Fecha de trabajo', required=True)
    payroll_date = fields.Date(string='Corte de pago', compute='_compute_dates', store=True)
    active_work_date = fields.Date(compute='_compute_dates', store=True)
    notes = fields.Text(string='Lugar, cliente o proyecto y trabajo realizado', required=True)
    state = fields.Selection(
        [('draft', 'Pendiente de aprobaciÃ³n'), ('approved', 'Aprobado'), ('cancelled', 'Cancelado')],
        string='Estado', required=True, readonly=True, default='draft', copy=False,
    )
    approved_amount = fields.Monetary(
        string='Aprobado para nÃ³mina', readonly=True, copy=False, groups='uno360x_payroll_hr.group_payroll',
    )
    approved_net = fields.Monetary(string='Neto aprobado', readonly=True, copy=False,
                                   groups='uno360x_payroll_hr.group_payroll')
    approved_retention = fields.Monetary(string='RetenciÃ³n calculada', readonly=True, copy=False,
                                         groups='uno360x_payroll_hr.group_payroll')
    approved_by = fields.Many2one('res.users', string='Aprobado por', readonly=True, copy=False)
    payroll_line_id = fields.Many2one('uno360x.payroll.line', string='Comprobante de nómina',
                                      readonly=True, ondelete='restrict', copy=False,
                                      groups='uno360x_payroll_hr.group_payroll')


    _sql_constraints = [
        ('employee_active_date_unique', 'UNIQUE(employee_id, active_work_date)',
         'Ya existe un registro vigente para este empleado y esta fecha.'),
    ]

    @api.depends('work_date', 'state')
    def _compute_dates(self):
        for record in self:
            record.payroll_date = cutoff(record.work_date) if record.work_date else False
            record.active_work_date = record.work_date if record.state != 'cancelled' else False

    @api.constrains('employee_id', 'work_date', 'notes', 'state', 'kind')
    def _check_weekend(self):
        for record in self.filtered(lambda r: r.state != 'cancelled'):
            employee = self.env['hr.employee'].sudo().browse(record.employee_id.id)
            if not employee.active or employee.company_id not in self.env.companies:
                raise ValidationError(_('Seleccione un empleado activo de una empresa autorizada.'))
            if record.kind == 'weekend':
                if not employee.ux_weekend_eligible or employee.employee_type != 'employee':
                    raise ValidationError(_('Habilite primero al empleado fijo en su ficha de Empleados.'))
                if not record.work_date or record.work_date.weekday() not in (5, 6):
                    raise ValidationError(_('La fecha debe ser sÃ¡bado o domingo.'))
            elif not employee.ux_daypay_eligible or employee.employee_type != 'contractor':
                raise ValidationError(_('Habilite primero al contratista por jornada en su ficha de Empleados.'))
            if not (record.notes or '').strip():
                raise ValidationError(_('Indique dÃ³nde se trabajÃ³ y quÃ© se hizo.'))

    @api.model_create_multi
    def create(self, vals_list):
        # Ignore caller-provided defaults for fields managed by the workflow.
        protected = self._fields.keys() - {'kind', 'employee_id', 'work_date', 'notes'}
        if any(protected.intersection(vals) for vals in vals_list):
            raise AccessError(_('El estado, el corte y el importe se asignan automÃ¡ticamente.'))
        clean_context = {key: value for key, value in self.env.context.items()
                         if not (key.startswith('default_') and key[8:] in protected)}
        return super(WeekendAdditional, self.with_context(clean_context)).create(vals_list)

    def _lock(self):
        self.check_access('write')
        if self.ids:
            self.env.cr.execute(
                'SELECT id FROM uno360x_payroll_additional WHERE id IN %s ORDER BY id FOR UPDATE',
                (tuple(self.ids),),
            )
            self.invalidate_recordset()

    def write(self, vals):
        self._lock()
        if set(vals) - {'kind', 'employee_id', 'work_date', 'notes'} or any(r.state != 'draft' for r in self):
            raise AccessError(_('Solo se pueden editar los datos de un adicional pendiente.'))
        return super().write(vals)

    def _change_state(self, state, allowed):
        if not self.env.user.has_group('uno360x_payroll_hr.group_payroll'):
            raise AccessError(_('Esta acciÃ³n requiere el permiso de NÃ³mina.'))
        if self.company_id:
            self.env.cr.execute('SELECT id FROM res_company WHERE id IN %s ORDER BY id FOR UPDATE',
                                (tuple(self.company_id.ids),))
        self._lock()
        if self.payroll_line_id:
            raise UserError(_('El adicional ya está incluido en una nómina aprobada.'))
        if any(record.state not in allowed for record in self):
            raise UserError(_('El estado del adicional cambiÃ³. Vuelva a cargar el registro.'))
        for record in self:
            net = retention = gross = 0
            if state == 'approved':
                if record.kind == 'day':
                    employee = self.env['hr.employee'].sudo().browse(record.employee_id.id)
                    try:
                        net, retention, gross = totals(employee.ux_daypay_net, employee.ux_daypay_rate)
                    except ValueError as error:
                        raise UserError(_('Revise el neto y la retenciÃ³n configurados en la ficha del contratista.')) from error
                else:
                    net = gross = record.company_id.ux_weekend_rate
                    if gross <= 0:
                        raise UserError(_('Configure una tarifa de fin de semana mayor que cero para esta empresa.'))
            super(WeekendAdditional, record).write({
                'state': state, 'approved_amount': gross, 'approved_net': net, 'approved_retention': retention,
                'approved_by': self.env.uid if state == 'approved' else False,
            })

    def _attach_to_payroll(self, line):
        self._lock()
        if any(day.payroll_line_id or day.state != 'approved' or day.kind != 'weekend'
               or day.company_id != line.company_id or day.employee_id != line.employee_id for day in self):
            raise UserError(_('El adicional cambió o ya está incluido en otro comprobante.'))
        if self:
            super().write({'payroll_line_id': line.id})

    def action_approve(self):
        self._change_state('approved', ('draft',))

    def action_reset(self):
        self._change_state('draft', ('approved',))

    def action_cancel(self):
        self._change_state('cancelled', ('draft', 'approved'))


class Workspace(models.AbstractModel):
    _inherit = 'uno360x.workspace'

    @api.model
    def _workspace_context(self):
        context = super()._workspace_context()
        if 'payroll_hr' not in context['options']:
            return context
        visible = self.env['ir.ui.menu']._visible_menu_ids()
        roots = [
            self.env.ref(f'uno360x_payroll_hr.{xmlid}')
            for xmlid in ('menu_payroll_root', 'menu_additionals')
        ]
        nodes = []
        for root in roots:
            if root.id not in visible:
                continue
            menus = self.env['ir.ui.menu'].sudo().search(
                [('parent_id', '=', root.id), ('id', 'in', list(visible)), ('active', '=', True)],
                order='sequence,id',
            )
            children = [
                {'id': menu.id, 'name': menu.name, 'href': f'/uno360x/open/{menu.id}', 'children': []}
                for menu in menus
            ]
            if children:
                nodes.append({'id': root.id, 'name': root.name, 'href': '', 'children': children})
                context['allowed_menus'].update([root.id, *menus.ids])
        if nodes:
            team = next((group for group in context['groups'] if group['name'] == 'Equipo'), None)
            if team is None:
                team = {'name': 'Equipo', 'icon': 'team', 'nodes': []}
                context['groups'].append(team)
            team['nodes'].extend(nodes)
        return context
