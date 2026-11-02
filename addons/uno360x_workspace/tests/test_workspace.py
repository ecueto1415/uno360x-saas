from unittest.mock import patch
from odoo.tests import TransactionCase,tagged
from odoo.exceptions import AccessError

@tagged('post_install','-at_install')
class TestWorkspace(TransactionCase):
 def setUp(self):
  super().setUp()
  groups=['base.group_user','sales_team.group_sale_manager','account.group_account_manager','purchase.group_purchase_manager','stock.group_stock_manager','point_of_sale.group_pos_manager']
  for group in ['hr.group_hr_manager','hr_attendance.group_hr_attendance_manager','hr_holidays.group_hr_holidays_manager','project.group_project_manager']:
   if self.env.ref(group,raise_if_not_found=False):groups.append(group)
  self.user=self.env['res.users'].with_context(no_reset_password=True).create({'name':'Workspace QA','login':'workspace-qa','company_id':self.env.company.id,'company_ids':[(6,0,self.env.company.ids)],'groups_id':[(6,0,[self.env.ref(g).id for g in groups])]})
  self.service=self.env['uno360x.workspace'].with_user(self.user)
 def test_four_scenarios_keep_the_current_groups(self):
  for options in [set(),{'payroll_hr'},{'jenifer_ai'},{'projects_services'}]:
   with patch.object(type(self.service),'_enabled_options',return_value=options):
    ctx=self.service._workspace_context();names=[g['name'] for g in ctx['groups']]
    self.assertIn('Comercial',names);self.assertIn('Finanzas',names);self.assertIn('Operaciones',names)
    self.assertEqual('Jenifer IA' in names,'jenifer_ai' in options)
    if 'hr.employee' in self.env.registry.models:self.assertEqual('Equipo' in names,'payroll_hr' in options)
    projects=[n['name'] for g in ctx['groups'] if g['name']=='Operaciones' for n in g['nodes']]
    if 'project.project' in self.env.registry.models:self.assertEqual('Proyecto' in projects,'projects_services' in options)
    forbidden={self.env.ref('base.menu_management').id,self.env.ref('base.menu_administration').id}
    self.assertFalse(forbidden & ctx['allowed_menus'])
 def test_public_user_cannot_read_workspace(self):
  with self.assertRaises(AccessError):self.service.with_user(self.env.ref('base.public_user'))._workspace_context()
 def test_summary_uses_live_data_and_does_not_grant_permissions(self):
  values=self.service._dashboard('invalid');self.assertEqual(values['company'],self.env.company)
  self.assertFalse(self.user.has_group('base.group_system'))
  self.assertIsInstance(values['money'](0),str)
  self.assertEqual(len(values['series']),6)
 def test_templates_render_with_user_context(self):
  values=self.service._dashboard();values['csrf']='qa-token'
  for template in ['dashboard','apps','help']:
   html=str(self.env['ir.ui.view']._render_template('uno360x_workspace.'+template,values))
   self.assertIn('UNO',html);self.assertIn('Comercial',html);self.assertNotIn('OUTSOLUTECH',html)

 def test_basic_user_does_not_gain_financial_access(self):
  user=self.env['res.users'].with_context(no_reset_password=True).create({'name':'Restricted QA','login':'restricted-workspace-qa','company_id':self.env.company.id,'company_ids':[(6,0,self.env.company.ids)],'groups_id':[(6,0,[self.env.ref('base.group_user').id])]})
  data=self.service.with_user(user)._dashboard()
  self.assertFalse(data['can_finance']);self.assertEqual(data['series'],[])
  self.assertEqual(data['pending_total'],0)

 def test_pos_entry_has_setup_and_return_without_creating_a_session(self):
  before=self.env['pos.session'].search_count([])
  values=self.service._workspace_context();values.update(csrf='qa-csrf',pos_configs=self.env['pos.config'].browse(),can_manage_pos=True,pos_error='')
  html=str(self.env['ir.ui.view']._render_template('uno360x_workspace.pos_home',values))
  self.assertIn('/uno360x/pos/create',html);self.assertIn('Crear mi primera caja',html);self.assertIn('Volver a UNO360X',html)
  self.assertEqual(self.env['pos.session'].search_count([]),before)
  commercial=next(g for g in values['groups'] if g['name']=='Comercial')
  self.assertTrue(any(node['href']=='/uno360x-pos' for node in commercial['nodes']))

 def test_pos_dashboard_menu_also_uses_the_safe_entry(self):
  action=self.env.ref('point_of_sale.action_pos_config_kanban')
  menu_ids=set(self.env['ir.ui.menu'].search([('action','=','%s,%s'%(action._name,action.id))]).ids)
  def flatten(nodes):
   for node in nodes:
    yield node
    yield from flatten(node['children'])
  nodes=list(flatten([node for group in self.service._workspace_context()['groups'] for node in group['nodes']]))
  dashboards=[node for node in nodes if node['id'] in menu_ids]
  self.assertTrue(dashboards)
  self.assertTrue(all(node['href']=='/uno360x-pos' for node in dashboards))
