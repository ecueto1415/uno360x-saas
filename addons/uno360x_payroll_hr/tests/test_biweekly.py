from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestBiweeklyPayroll(TransactionCase):
    def test_cutoff_review_approval_and_individual_receipt(self):
        approver = new_test_user(self.env, login='qa_biweekly_approver', groups='uno360x_payroll_hr.group_payroll')
        hr = new_test_user(self.env, login='qa_biweekly_hr', groups='hr.group_hr_user')
        employee = self.env['hr.employee'].create({
            'name': 'Empleado quincenal ficticio', 'employee_type': 'employee',
            'ux_weekend_eligible': True, 'ux_payroll_enabled': True,
            'ux_payroll_base': 12000, 'ux_payroll_deductions': 500,
            'ux_payroll_email': 'nomina-ficticia@example.invalid', 'ux_payroll_email_verified': True,
        })
        day = self.env['uno360x.payroll.additional'].with_user(approver).create({
            'employee_id': employee.id, 'work_date': date(2028, 2, 26), 'notes': 'Trabajo de fin de semana ficticio',
        })
        day.action_approve()
        batch = self.env['uno360x.payroll.batch'].with_user(approver).create({'payroll_date': date(2028, 2, 29)})
        batch.action_prepare()
        line = batch.line_ids
        self.assertEqual(line.net, 13000)
        with self.assertRaises(AccessError):
            line.with_user(hr).read(['net'])
        with self.assertRaises(UserError):
            batch.action_approve()
        line.write({'incentive': 300, 'incentive_reason': 'Proyecto de prueba', 'reviewed': True})
        self.assertFalse(line.reviewed)
        line.write({'reviewed': True})
        batch.action_approve()
        self.assertEqual(line.net, 13300)
        self.assertEqual(day.payroll_line_id.id, line.id)
        with self.assertRaises(UserError):
            day.action_cancel()
        with self.assertRaises(UserError):
            line.write({'deductions': 0})
        reports = self.env['ir.actions.report'].with_user(approver)
        html, _ = reports._render_qweb_html('uno360x_payroll_hr.biweekly_receipt_pdf', line.ids)
        self.assertIn(b'Trabajo de fin de semana ficticio', html)
        summary, _ = reports._render_qweb_html('uno360x_payroll_hr.biweekly_summary_pdf', batch.ids)
        self.assertIn(b'Empleado quincenal ficticio', summary)
        with self.assertRaises(UserError):
            batch.action_send_receipts()
        server = self.env['ir.mail_server'].create({'name': 'Solo pruebas', 'smtp_host': 'smtp.example.invalid'})
        self.env.company.write({'ux_payroll_mail_server_id': server.id, 'ux_payroll_sender': 'nomina@example.invalid'})
        with patch.object(type(reports), '_render_qweb_pdf', return_value=(b'%PDF-test', 'pdf')), \
             patch.object(type(self.env['mail.mail']), 'send_after_commit', autospec=True) as queued:
            batch.action_send_receipts()
            batch.action_send_receipts()
        self.assertEqual(queued.call_count, 1)
        mail = line.sudo().mail_id
        self.assertEqual(mail.email_to, 'nomina-ficticia@example.invalid')
        self.assertEqual(mail.attachment_ids.res_id, line.id)
        self.assertFalse(mail.attachment_ids.public)
