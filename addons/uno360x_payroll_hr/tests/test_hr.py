import json
from datetime import date
from odoo.tests.common import TransactionCase, tagged, new_test_user
from odoo.exceptions import AccessError
from ..calculations import totals,cutoff,statement_totals,cedula_digits,csv_safe

@tagged('post_install','-at_install')
class TestPortableHR(TransactionCase):
    def test_calculations_and_rounding(self):
        net,tax,gross=totals(2500,3)
        self.assertEqual((net,tax,gross),(2500,77.32,2577.32))
        current=statement_totals(2500,3,2500)
        self.assertAlmostEqual(totals(2500,3)[2]+current[2],totals(5000,3)[2],places=2)
        for n,r in [(0,3),(-1,3),(100,100),(float('nan'),3)]:
            with self.assertRaises(ValueError):totals(n,r)

    def test_calendar_handles_february_and_leap_year(self):
        self.assertEqual(cutoff(date(2026,2,26)),date(2026,2,28))
        self.assertEqual(cutoff(date(2028,2,26)),date(2028,2,29))
        self.assertEqual(cutoff(date(2026,12,31)),date(2027,1,15))
        with self.assertRaises(ValueError):cutoff(date.today(),30,15)

    def test_private_employee_data_and_company_isolation(self):
        other=self.env['res.company'].create({'name':'Otra empresa ficticia'})
        employee=self.env['hr.employee'].create({'name':'Persona ficticia','company_id':other.id})
        user=new_test_user(self.env['res.users'].with_context(no_reset_password=True).env,login='hr_ficticio',groups='hr.group_hr_user',company_id=self.env.company.id,
          company_ids=[(6,0,self.env.company.ids)])
        self.assertFalse(self.env['hr.employee'].with_user(user).search([('id','=',employee.id)]))
        with self.assertRaises(AccessError):employee.with_user(user).read(['name'])
        self.assertEqual(csv_safe('=2+2'),"'=2+2")
        with self.assertRaises(ValueError):cedula_digits('00000000000')

from odoo.tests import HttpCase


@tagged('post_install','-at_install')
class TestPayrollAccess(HttpCase):
    def test_hr_cannot_read_wages_or_download_receipts(self):
        password = 'Only for the payroll security test 2026!'
        hr = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, login='uno_hr_security_test', password=password,
                           groups='hr.group_hr_user,hr_contract.group_hr_contract_employee_manager')
        payroll = new_test_user(self.env['res.users'].with_context(no_reset_password=True).env, login='uno_payroll_security_test', password=password,
                                groups='uno360x_payroll_hr.group_payroll')
        employee = self.env['hr.employee'].create({'name':'Fictional employee'})
        contract = self.env['hr.contract'].create({
            'name':'Fictional contract','employee_id':employee.id,
            'date_start':date(2026,1,1),'wage':47321,
        })
        receipt = self.env['uno360x.payroll.receipt'].create({
            'name':'Fictional receipt','employee_id':employee.id,
            'filename':'receipt.txt','document':'VU5PMzYwWF9TRUNVUkVfUkVDRUlQVA==',
        })
        self.assertEqual(employee.with_user(hr).read(['name'])[0]['name'],'Fictional employee')
        for record, fields in ((contract,['name','wage']),(receipt,['document'])):
            with self.assertRaises(AccessError):
                record.with_user(hr).read(fields)
        self.assertNotIn('wage',self.env['hr.contract'].with_user(hr).fields_get())
        self.assertEqual(contract.with_user(payroll).read(['wage'])[0]['wage'],47321)
        download = f'/web/content/uno360x.payroll.receipt/{receipt.id}/document?download=1'
        self.authenticate(hr.login,password)
        response = self.url_open(download)
        self.assertIn(response.status_code,(403,404))
        self.assertNotIn(b'UNO360X_SECURE_RECEIPT',response.content)
        request = {'jsonrpc':'2.0','id':1,'method':'call','params':{
            'model':'hr.contract','method':'read','args':[[contract.id],['wage']],'kwargs':{}}}
        response = self.url_open('/web/dataset/call_kw/hr.contract/read',data=json.dumps(request),headers={'Content-Type':'application/json'})
        self.assertIn('error',response.json())
        self.assertNotIn('47321',response.text)
        self.authenticate(payroll.login,password)
        response = self.url_open(download)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'UNO360X_SECURE_RECEIPT')
