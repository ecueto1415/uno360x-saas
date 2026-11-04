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
  self.assertTrue(any(node['href']=='/uno360x/area/pos' for node in commercial['nodes']))

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


 def test_search_result_targets_an_accessible_action_not_a_container(self):
  ctx=self.service._workspace_context()
  menu=self.service._search_menu('res.partner','contacts.menu_contacts',ctx['allowed_menus'])
  self.assertTrue(menu.action)
  self.assertEqual(menu.action.res_model,'res.partner')
  self.assertIn(menu.id,ctx['allowed_menus'])
  self.assertFalse(self.service._search_menu('res.partner','contacts.menu_contacts',set()))

 def test_approved_internal_views_render_without_operational_ids(self):
  import datetime
  from types import SimpleNamespace
  env=self.env(user=self.user)
  contact=self.env['res.partner'].create({'name':'Contact QA','company_id':self.env.company.id})
  specs=[('reference_contacts',{}),('reference_contact',{'id':str(contact.id)}),('reference_billing',{})]
  if 'project.project' in env.registry:
   project=self.env['project.project'].create({'name':'Project QA','company_id':self.env.company.id})
   specs.extend([('reference_projects',{}),('reference_project',{'id':str(project.id)})])
  if 'hr.employee' in env.registry:specs.append(('reference_employees',{}))
  for name,params in specs:
   values=self.service._workspace_context();values.update(csrf='qa-token',panel_env=env,datetime=datetime,request=SimpleNamespace(env=env,params=params,httprequest=SimpleNamespace(args=params)))
   with self.debug_mode():
    from odoo.http import request as active_request
    active_request.env=env;active_request.params=params;active_request.httprequest.args=params
    html=str(self.env['ir.ui.view']._render_template('uno360x_workspace.'+name,values))
   self.assertIn('UNO',html);self.assertNotIn('/odoo/action-303',html);self.assertNotIn('/odoo/action-379',html)

 def test_fourteen_areas_render_actual_user_scoped_data(self):
  from ..models.areas import AREAS
  self.assertEqual(len(AREAS),14)
  ctx=self.service._workspace_context()
  for key in AREAS:
   if key=='jenifer' or not self.service._area_available(key,ctx):continue
   values=self.service._area_values(key,q='no match QA',page='bad')
   values.update(csrf='test-csrf',area_back='/uno360x/area/'+key)
   html=str(self.env['ir.ui.view']._render_template('uno360x_workspace.area',values))
   self.assertIn('ua-area',html,key)
   self.assertNotIn('Empresa Alfa',html,key)
   self.assertNotIn('128',str(values['area_metrics']),key)
   self.assertFalse(self.user.has_group('base.group_system'))
 def test_area_records_and_totals_respect_company_and_search(self):
  partner=self.env['res.partner'].create({'name':'Area Unique QA','company_id':self.env.company.id})
  values=self.service._area_values('contacts',q='Area Unique QA')
  self.assertEqual(values['area_total'],1)
  self.assertEqual(values['area_rows'][0]['id'],partner.id)
  values=self.service._area_values('contacts',q='No Match Unique QA')
  self.assertEqual(values['area_total'],0)
  self.assertEqual(values['area_rows'],[])
 def test_area_options_are_enforced_before_queries(self):
  with patch.object(type(self.service),'_enabled_options',return_value=set()):
   for key in ('projects','leave','attendance','expenses','jenifer'):
    with self.assertRaises(AccessError):self.service._area_values(key)
  with self.assertRaises(AccessError):self.service._area_values('unknown')
 def test_area_tools_only_point_to_allowed_menu_actions(self):
  ctx=self.service._workspace_context()
  allowed={m.action.id for m in self.env['ir.ui.menu'].browse(list(ctx['allowed_menus'])) if m.action}
  for key in ('contacts','sales','billing','purchases','inventory'):
   values=self.service._area_values(key)
   for tool in values['area_tools']:
    self.assertIn(int(tool['href'].split('action-')[1].split('?')[0]),allowed)

 def test_project_card_does_not_require_optional_stage_field_permission(self):
  if 'project.project' not in self.env.registry:return
  project=self.env['project.project'].create({'name':'Restricted Stage Card QA','company_id':self.env.company.id,'user_id':self.user.id})
  values=self.service._area_values('projects',q='Restricted Stage Card QA')
  self.assertEqual(values['area_total'],1)
  self.assertEqual(values['area_rows'][0]['id'],project.id)
  self.assertIsNone(values['area_rows'][0]['stage_id'])
  values.update(csrf='qa-token',area_back='/uno360x/area/projects')
  html=str(self.env['ir.ui.view']._render_template('uno360x_workspace.area',values))
  self.assertIn('Restricted Stage Card QA',html)
  self.assertIn('ua-progress',html)
