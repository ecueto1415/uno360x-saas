from odoo.tests.common import TransactionCase,tagged,new_test_user
from odoo.exceptions import AccessError

@tagged('post_install','-at_install')
class TestPortableProjects(TransactionCase):
    def test_task_subtask_and_hours(self):
        project=self.env['project.project'].create({'name':'Proyecto ficticio','allow_timesheets':True})
        task=self.env['project.task'].create({'name':'Tarea ficticia','project_id':project.id})
        sub=self.env['project.task'].create({'name':'Subtarea ficticia','project_id':project.id,'parent_id':task.id})
        employee=self.env['hr.employee'].create({'name':'Técnico ficticio','user_id':self.env.user.id,'hourly_cost':25})
        line=self.env['account.analytic.line'].create({'name':'Trabajo ficticio','project_id':project.id,
          'task_id':sub.id,'employee_id':employee.id,'unit_amount':2,'company_id':self.env.company.id})
        self.assertEqual(line.unit_amount,2)
        self.assertAlmostEqual(line.amount,-50)
        self.assertEqual(sub.parent_id,task)

    def test_employee_cannot_read_other_company_project(self):
        other=self.env['res.company'].create({'name':'Otra empresa de proyectos'})
        project=self.env['project.project'].with_company(other).create({'name':'Privado ficticio',
          'company_id':other.id,'privacy_visibility':'employees'})
        user=new_test_user(self.env['res.users'].with_context(no_reset_password=True).env,login='project_ficticio',groups='project.group_project_user',
          company_id=self.env.company.id,company_ids=[(6,0,self.env.company.ids)])
        self.assertFalse(self.env['project.project'].with_user(user).search([('id','=',project.id)]))
        with self.assertRaises(AccessError):project.with_user(user).read(['name'])
