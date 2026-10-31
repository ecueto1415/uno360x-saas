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
