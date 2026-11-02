"""Common workspace. Business queries always use the requesting user's env."""
import calendar,datetime
from odoo import api,models,fields
from odoo.exceptions import AccessError
from odoo.tools.misc import format_amount

MENU_GROUPS=[
 ('Comercial','sales',[('contacts.menu_contacts','Contactos'),('crm.crm_menu_root','CRM'),('sale.sale_menu_root','Ventas'),('point_of_sale.menu_point_root','Punto de venta')]),
 ('Finanzas','finance',[('account.menu_finance','Facturación / Contabilidad'),('hr_expense.menu_hr_expense_root','Gastos')]),
 ('Operaciones','operations',[('project.menu_main_pm','Proyecto'),('purchase.menu_purchase_root','Compra'),('stock.menu_stock_root','Inventario')]),
 ('Equipo','team',[('hr.menu_hr_root','Empleados'),('hr_attendance.menu_hr_attendance_root','Asistencias'),('hr_holidays.menu_hr_holidays_root','Ausencias')]),
 ('Jenifer IA','ai',[]),
 ('Reportes','reports',[('spreadsheet_dashboard.spreadsheet_dashboard_menu_root','Dashboards')])]
OPTIONS={'payroll_hr':'uno360x_payroll_hr','jenifer_ai':'uno360x_jenifer_core','projects_services':'uno360x_projects_services'}

class Workspace(models.AbstractModel):
 _name='uno360x.workspace'
 _description='Entorno común de UNO360X'
 @api.model
 def _enabled_options(self):
  installed=set(self.env['ir.module.module'].sudo().search([('name','in',list(OPTIONS.values())),('state','=','installed')]).mapped('name'))
  return {key for key,name in OPTIONS.items() if name in installed}
 @api.model
 def _can_read(self,name):
  return name in self.env.registry.models and self.env[name].check_access_rights('read',raise_exception=False)
 @api.model
 def _workspace_context(self):
  if not self.env.user.has_group('base.group_user'):raise AccessError('Acceso de empresa requerido.')
  visible=self.env['ir.ui.menu']._visible_menu_ids();options=self._enabled_options();allowed=set();pos_root=self.env.ref('point_of_sale.menu_point_root',raise_if_not_found=False);pos_actions=tuple(self.env.ref(xmlid,raise_if_not_found=False) for xmlid in ('point_of_sale.action_pos_config_kanban','point_of_sale.action_client_pos_menu'))
  def node(m,label=None):
   allowed.add(m.id)
   return {'id':m.id,'name':label or m.name,'href':'/uno360x-pos' if m==pos_root or m.action in pos_actions else ('/uno360x/open/%s'%m.id if m.action else ''),
           'children':[node(c) for c in m.child_id.sorted('sequence') if c.active and c.id in visible]}
  groups=[]
  for title,icon,specs in MENU_GROUPS:
   if title=='Equipo' and 'payroll_hr' not in options:continue
   if title=='Jenifer IA':
    if 'jenifer_ai' in options:groups.append({'name':title,'icon':icon,'nodes':[{'id':0,'name':'Jenifer','href':'/uno360x-jenifer','children':[]}]})
    continue
   nodes=[]
   for xmlid,label in specs:
    if xmlid.startswith('project.') and 'projects_services' not in options:continue
    m=self.env.ref(xmlid,raise_if_not_found=False)
    if m and m.active and m.id in visible:nodes.append(node(m,label))
   if nodes:groups.append({'name':title,'icon':icon,'nodes':nodes})
  user=self.env.user
  return {'company':self.env.company,'u':user,'en':(user.lang or '').startswith('en'),'groups':groups,
          'allowed_menus':allowed,'options':options,'page_key':'overview','csrf':None}
 @api.model
 def _dashboard(self,period=None):
  ctx=self._workspace_context();today=fields.Date.context_today(self)
  try:first=datetime.date.fromisoformat(str(period)+'-01') if period else today.replace(day=1)
  except (ValueError,TypeError):first=today.replace(day=1)
  if not 2020<=first.year<=today.year+1:first=today.replace(day=1)
  def shift(day,months):
   m=day.year*12+day.month-1+months
   return day.replace(year=m//12,month=m%12+1,day=1)
  ctx.update(today=today,month_start=first,month_end=shift(first,1),can_finance=self._can_read('account.move'),can_sales=self._can_read('sale.order'))
  company=[('company_id','=',self.env.company.id)];series=[]
  def amount(model,domain,field):
   return model.read_group(domain,[field+':sum'],[])[0].get(field,0.0) or 0.0
  if ctx['can_finance']:
   model=self.env['account.move']
   for i in range(-5,1):
    day=shift(first,i);domain=company+[('state','=','posted'),('move_type','in',['out_invoice','out_refund']),('invoice_date','>=',day),('invoice_date','<',shift(day,1))]
    series.append({'date':day,'value':amount(model,domain,'amount_total_signed')})
   pending=company+[('state','=','posted'),('move_type','=','out_invoice'),('amount_residual','>',0)]
   ctx.update(pending_total=amount(model,pending,'amount_residual_signed'),open_count=model.search_count(pending),overdue_count=model.search_count(pending+[('invoice_date_due','<',today)]))
   period_domain=company+[('state','=','posted'),('move_type','in',['out_invoice','out_refund']),('invoice_date','>=',first),('invoice_date','<',shift(first,1))]
   ctx['period_pending']=amount(model,period_domain,'amount_residual_signed')
  else:ctx.update(pending_total=0,open_count=0,overdue_count=0,period_pending=0)
  billed=series[-1]['value'] if series else 0;prev=series[-2]['value'] if len(series)>1 else 0
  ctx.update(series=series,billed=billed,variation=(billed-prev)/abs(prev)*100 if prev else None,period_settled=billed-ctx['period_pending'],ring_percent=max(0,min(100,(billed-ctx['period_pending'])/billed*100)) if billed>0 else 0)
  ctx['chart_max']=max([x['value'] for x in series]+[1]);ctx['chart_min']=min([x['value'] for x in series]+[0]);ctx['chart_span']=ctx['chart_max']-ctx['chart_min']
  ctx['stale_quotes']=self.env['sale.order'].search_count(company+[('state','=','sent'),('write_date','<=',today-datetime.timedelta(days=7))]) if ctx['can_sales'] else 0
  ctx['opportunities']=self.env['crm.lead'].search_count(company+[('type','=','opportunity'),('active','=',True)]) if self._can_read('crm.lead') else None
  ctx['projects']=self.env['project.project'].search(company,limit=3,order='write_date desc') if 'projects_services' in ctx['options'] and self._can_read('project.project') else []
  ctx['project_count']=self.env['project.project'].search_count(company) if 'projects_services' in ctx['options'] and self._can_read('project.project') else None
  ctx['employee_count']=self.env['hr.employee'].search_count(company) if 'payroll_hr' in ctx['options'] and self._can_read('hr.employee') else None
  ctx['money']=lambda value:format_amount(self.env,value,self.env.company.currency_id)
  return ctx
