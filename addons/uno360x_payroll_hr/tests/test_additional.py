from datetime import date

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestPayrollAdditional(TransactionCase):
    def test_weekend_approval_and_company_permissions(self):
        registrar = new_test_user(self.env, login='qa_additional_hr', groups='hr.group_hr_user')
        payroll = new_test_user(self.env, login='qa_additional_payroll', groups='uno360x_payroll_hr.group_payroll')
        unrelated = new_test_user(self.env, login='qa_additional_staff', groups='base.group_user')
        employee = self.env['hr.employee'].create({
            'name': 'Empleado ficticio', 'employee_type': 'employee', 'ux_weekend_eligible': True,
        })
        model = self.env['uno360x.payroll.additional']
        vals = {'employee_id': employee.id, 'work_date': date(2028, 2, 26), 'notes': 'Trabajo de prueba'}
        record = model.with_user(registrar).with_context(default_state='approved').create(vals)
        self.assertEqual(record.state, 'draft')
        self.assertEqual(record.payroll_date, date(2028, 2, 29))
        with self.assertRaises(AccessError):
            record.action_approve()
        with self.assertRaises(AccessError):
            record.write({'state': 'approved'})
        with self.assertRaises(AccessError):
            record.read(['approved_amount'])
        with self.assertRaises(AccessError):
            record.with_user(unrelated).read(['state'])
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            model.with_user(registrar).create(dict(vals, work_date=date(2028, 2, 25)))
        record.with_user(payroll).action_approve()
        self.assertEqual(record.with_user(payroll).approved_amount, 1500)
        workspace = self.env['uno360x.workspace'].with_user(registrar)
        register = self.env.ref('uno360x_payroll_hr.menu_additional_register')
        daypay = self.env.ref('uno360x_payroll_hr.menu_additional_daypay')
        report = self.env.ref('uno360x_payroll_hr.menu_additional_approved')
        self.assertTrue({register.id, daypay.id} <= workspace._workspace_context()['allowed_menus'])
        self.assertNotIn(report.id, workspace._workspace_context()['allowed_menus'])
        payroll_menus = workspace.with_user(payroll)._workspace_context()['allowed_menus']
        self.assertIn(report.id, payroll_menus)
        for name in ('menu_payroll_contracts', 'menu_payroll_receipts'):
            item = self.env.ref(f'uno360x_payroll_hr.{name}')
            self.assertIn(item.id, payroll_menus)
            self.assertNotIn(item.id, workspace._workspace_context()['allowed_menus'])
        html, _ = self.env['ir.actions.report'].with_user(payroll)._render_qweb_html(
            'uno360x_payroll_hr.additional_pdf', record.ids)
        self.assertIn(b'Trabajo de prueba', html)

        with self.assertRaises(AccessError):
            record.with_user(payroll).write({'notes': 'Cambiar aprobado'})
        record.with_user(payroll).action_cancel()
        self.assertEqual(record.with_user(payroll).approved_amount, 0)
        self.assertEqual(model.with_user(registrar).create(vals).state, 'draft')

    def test_contractor_requires_separate_eligibility_and_uses_agreed_net(self):
        contractor = self.env['hr.employee'].create({
            'name': 'Contratista ficticio', 'employee_type': 'contractor', 'ux_daypay_eligible': True,
            'ux_daypay_net': 2500, 'ux_daypay_rate': 3,
        })
        model = self.env['uno360x.payroll.additional']
        vals = {'employee_id': contractor.id, 'work_date': date(2028, 2, 25), 'notes': 'Instalación de prueba'}
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            model.create(vals)
        record = model.with_context(default_kind='day').create(vals)
        self.assertEqual(record.kind, 'day')
        approver = new_test_user(self.env, login='qa_daypay_approver', groups='uno360x_payroll_hr.group_payroll')
        record = record.with_user(approver)
        record.action_approve()
        self.assertEqual(record.approved_net, 2500)
        self.assertEqual(record.approved_retention, 77.32)
        self.assertEqual(record.approved_amount, 2577.32)
