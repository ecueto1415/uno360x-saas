"""Approved 14-area workspace: user-scoped reads and existing native actions."""
import calendar,datetime,math
from urllib.parse import urlencode
from ..billing_assets import billing_asset_urls
from zoneinfo import ZoneInfo
from odoo import api,models,fields
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare, float_round
from odoo.tools.misc import format_amount,format_date,format_datetime

AREAS={
 'contacts':('Contactos','Comercial','res.partner','contacts.menu_contacts','Contacto','cards',None),
 'crm':('CRM','Comercial','crm.lead','crm.crm_menu_root','Oportunidad','board',None),
 'sales':('Ventas','Comercial','sale.order','sale.sale_menu_root','Cotización','list',None),
 'pos':('Punto de venta','Comercial','pos.config','point_of_sale.menu_point_root','Caja','pos',None),
 'billing':('Facturación / Contabilidad','Finanzas','account.move','account.menu_finance','Factura','list',None),
 'expenses':('Gastos','Finanzas','hr.expense','hr_expense.menu_hr_expense_root','Gasto','list','projects_services'),
 'projects':('Proyectos','Operaciones','project.project','project.menu_main_pm','Proyecto','cards','projects_services'),
 'purchases':('Compras','Operaciones','purchase.order','purchase.menu_purchase_root','Solicitud','list',None),
 'inventory':('Inventario','Operaciones','product.product','stock.menu_stock_root','Producto','list',None),
 'maintenance':('Mantenimiento','Operaciones','maintenance.request','maintenance.menu_maintenance_title','Solicitud','board',None),
 'attendance':('Asistencias','Equipo','hr.attendance','hr_attendance.menu_hr_attendance_root','Registro','list','payroll_hr'),
 'leave':('Ausencias','Equipo','hr.leave','hr_holidays.menu_hr_holidays_root','Solicitud','calendar','payroll_hr'),
 'jenifer':('Jenifer','Jenifer IA','uno360x.jenifer.query',None,None,'assistant','jenifer_ai'),
 'reports':('Tableros','Reportes','spreadsheet.dashboard','spreadsheet_dashboard.spreadsheet_dashboard_menu_root','Tablero','reports',None),
}
FILTERS={
 'contacts':[('all','Directorio',[]),('customers','Clientes',[('customer_rank','>',0)]),('vendors','Proveedores',[('supplier_rank','>',0)])],
 'crm':[('all','Oportunidades',[('type','=','opportunity')]),('leads','Leads',[('type','=','lead')])],
 'sales':[('all','Cotizaciones',[('state','in',['draft','sent'])]),('draft','Borrador',[('state','=','draft')]),('sent','Enviadas',[('state','=','sent')]),('orders','Pedidos',[('state','=','sale')]),('invoice','A facturar',[('invoice_status','=','to invoice')])],
 'billing':[('all','Clientes',[('move_type','in',['out_invoice','out_refund'])]),('vendors','Proveedores',[('move_type','in',['in_invoice','in_refund'])]),('unpaid','Pendientes',[('move_type','=','out_invoice'),('state','=','posted'),('payment_state','!=','paid')]),('paid','Pagadas',[('move_type','=','out_invoice'),('state','=','posted'),('payment_state','=','paid')])],
 'purchases':[('all','Solicitudes',[('state','in',['draft','sent','to approve'])]),('orders','Pedidos',[('state','in',['purchase','done'])])],
 'attendance':[('all','Hoy',[]),('open','Sin salida',[('check_out','=',False)])],
 'leave':[('all','Calendario',[]),('mine','Mis solicitudes',[]),('pending','Por aprobar',[('state','in',['confirm','validate1'])]),('approved','Aprobadas',[('state','=','validate')])],
 'expenses':[('all','Mis gastos',[]),('review','Por aprobar',[('state','in',['submitted','reported'])]),('paid','Reembolsados',[('state','=','done')])],
}

class WorkspaceAreas(models.AbstractModel):
 _inherit='uno360x.workspace'
 @api.model
 def _area_spec(self,key):
  if key not in AREAS:raise AccessError('Área no disponible.')
  return AREAS[key]
 @api.model
 def _area_action(self,key,ctx):
  title,group,model,xmlid,create,kind,option=self._area_spec(key)
  if option and option not in ctx['options']:return self.env['ir.actions.act_window']
  if key=='billing':
   action=self.env.ref('account.action_move_out_invoice_type',raise_if_not_found=False)
   menus=self.env['ir.ui.menu'].browse(list(ctx['allowed_menus']))
   if action and any(m.action==action for m in menus):return action
  menu=self._search_menu(model,xmlid,ctx['allowed_menus']) if xmlid else False
  return menu.action if menu else self.env['ir.actions.act_window']
 @api.model
 def _area_navigation(self,ctx):
  """Only existing permitted menu roots get a new landing destination."""
  by_xml={v[3]:k for k,v in AREAS.items() if v[3]}
  menu_ids=[]
  def collect(nodes):
   for entry in nodes:
    if entry['id']:menu_ids.append(entry['id'])
    collect(entry['children'])
  for group in ctx['groups']:collect(group['nodes'])
  external_ids=self.env['ir.ui.menu'].browse(menu_ids).get_external_id()
  def visit(node):
   external=external_ids.get(node['id'])
   if external in by_xml:
    key=by_xml[external]
    if self._area_available(key,ctx):node['href']='/uno360x/area/'+key
   for child in node['children']:visit(child)
  for group in ctx['groups']:
   if group['icon']=='reports':
    group['nodes']=[{'id':0,'name':'Tableros','href':'/uno360x/area/reports','children':[]}]
    continue
   for node in group['nodes']:
    if node['id']:visit(node)
    elif group['name']=='Jenifer IA':node['href']='/uno360x-jenifer'
  return ctx
 @api.model
 def _workspace_context(self):
  ctx=super()._workspace_context()
  ctx['billing_assets']=False
  ctx['asset_revision']=self.env['ir.config_parameter'].sudo().get_param('uno360x.workspace.release','18.0.2.0.0')
  return self._area_navigation(ctx)
 @api.model
 def _area_available(self,key,ctx):
  spec=self._area_spec(key)
  return (not spec[6] or spec[6] in ctx['options']) and (key=='reports' or self._can_read(spec[2]))
 @api.model
 def _inventory_replenishment_summary(self, products, all_locations=False):
  if not products or not self._can_read('stock.warehouse.orderpoint') or not self._can_read('stock.move'):
   return {}
  company = self.env.company
  rules = self.env['stock.warehouse.orderpoint'].search([
   ('company_id', '=', company.id), ('product_id', 'in', products.ids),
   ('active', '=', True), ('product_id.is_storable', '=', True),
  ], order='warehouse_id, location_id, id')
  primary = self.env['stock.warehouse'].search([('company_id', '=', company.id)], order='sequence, id', limit=1)
  rules = rules.sorted(lambda rule: (
   0 if primary and rule.warehouse_id == primary else 1,
   rule.location_id != rule.warehouse_id.lot_stock_id, rule.id,
  ))
  moves = self.env['stock.move'].search([
   ('company_id', '=', company.id),
   ('product_id', 'in', rules.product_id.ids),
   ('state', 'in', ('waiting', 'confirmed', 'partially_available', 'assigned')),
   ('purchase_line_id', '!=', False),
   ('purchase_line_id.order_id.state', 'in', ('purchase', 'done')),
   ('picking_type_id.code', '=', 'incoming'),
   ('picking_type_id.warehouse_id', 'in', rules.warehouse_id.ids),
   ('location_id.usage', '=', 'supplier'),
  ])
  incoming = moves.grouped(lambda move: (move.product_id.id, move.picking_type_id.warehouse_id.id))
  summary = {}
  for location, location_rules in rules.grouped('location_id').items():
   quantities = {
    product.id: product.qty_available
    for product in location_rules.product_id.with_company(company).with_context(
     allowed_company_ids=[company.id], location=location.id)
   }
   for rule in location_rules:
    product = rule.product_id
    key = rule.id if all_locations else product.id
    if key in summary:
     continue
    rounding = product.uom_id.rounding
    current = quantities[product.id]
    low = float_compare(current, rule.product_min_qty, precision_rounding=rounding) <= 0
    pending = 0.0
    for move in incoming.get((product.id, rule.warehouse_id.id), ()):
     destination = move.location_final_id or move.location_dest_id
     if destination == location or destination.parent_path.startswith(location.parent_path):
      pending += move.product_uom._compute_quantity(
       move.product_uom_qty, product.uom_id, round=False)
    target = max(rule.product_min_qty, rule.product_max_qty)
    suggestion = float_round(max(0.0, target - current - pending), precision_rounding=rounding) if low else 0.0
    summary[key] = {
     'rule': rule, 'current': current, 'low': low, 'pending': pending,
     'suggestion': suggestion,
    }
  return summary

 @api.model
 def _inventory_shortage_rows(self):
  company = self.env.company
  product_ids = self.env['stock.warehouse.orderpoint'].search([
   ('company_id', '=', company.id), ('active', '=', True),
  ]).product_id.ids
  products = self.env['product.product'].search([
   ('id', 'in', product_ids), ('is_storable', '=', True),
   ('company_id', 'in', [False, company.id]),
  ])
  stock = self._inventory_replenishment_summary(products, all_locations=True)
  return sorted(
   (item for item in stock.values() if item['suggestion'] > 0),
   key=lambda item: (item['rule'].warehouse_id.name, item['rule'].product_id.display_name),
  )

 @api.model
 def _area_values(self,key,q='',page=1,selection='all',period=None,detail=None):
  ctx=self._workspace_context();title,group,model,xmlid,create,kind,option=self._area_spec(key)
  if not self._area_available(key,ctx):raise AccessError('Esta opción no está disponible con tu plan o permisos.')
  try:page=max(1,min(10000,int(page)))
  except (TypeError,ValueError):page=1
  q=str(q or '').strip()[:100];today=fields.Date.context_today(self)
  ctx.update(area_key=key,area_title=title,area_group=group,page_key=key,query=q,selection=selection,area_kind=kind,area_rows=[],area_columns=[],area_metrics=[],area_tabs=[],area_tools=[],area_boards=[],area_calendar=[],area_can_create=False,area_create='',area_action='',area_total=0,area_pages=1,area_page=page,area_previous='',area_next='',area_month='',area_notice='',area_updated=format_datetime(self.env,fields.Datetime.now()),area_currency=self.env.company.currency_id.name)
  base='/uno360x/area/'+key
  action=self._area_action(key,ctx)
  ctx['area_action']='/odoo/action-%s'%action.id if action else ''
  if key == 'billing' and self.env.user.has_group('account.group_account_manager'):
   finance_shortcuts = []
   for model_name, create_id, list_id, label, list_label in (
    ('account.account', 'finance_simple_account_action', 'account.action_account_form',
     'Nueva cuenta contable', 'Plan de cuentas'),
    ('account.journal', 'finance_simple_bank_action', 'account.action_account_journal_form',
     'Agregar banco', 'Ver diarios'),
   ):
    if self.env[model_name].has_access('create'):
     create_action = self.env.ref('uno360x_workspace.' + create_id)
     list_action = self.env.ref(list_id)
     finance_shortcuts.append({
      'name': label, 'create': '/odoo/action-%s/new' % create_action.id,
      'list_name': list_label, 'list': '/odoo/action-%s' % list_action.id,
     })
   ctx['area_finance_shortcuts'] = finance_shortcuts
  product_template_action = False
  if key == 'inventory':
   product_menu = self.env.ref('stock.menu_product_variant_config_stock', raise_if_not_found=False)
   if (product_menu and product_menu.id in ctx['allowed_menus'] and product_menu.action
       and product_menu.action.res_model == 'product.template'
       and self._can_read('product.template')):
    product_template_action = product_menu.action
    if self.env['product.template'].check_access_rights('create', raise_exception=False):
     ctx.update(area_can_create=True, area_create='/odoo/action-%s/new' % product_template_action.id,
                area_create_label='Nuevo producto')
  elif action and self.env[model].check_access_rights('create',raise_exception=False) and key != 'reports':
   ctx.update(area_can_create=True,area_create=ctx['area_action']+'/new',area_create_label=create)
  menus=self.env['ir.ui.menu'].browse(list(ctx['allowed_menus']))
  root=self.env.ref(xmlid,raise_if_not_found=False) if xmlid else False
  if root:
   for m in menus.filtered(lambda m:m.action and (m.parent_id==root or m.parent_id.parent_id==root)).sorted('sequence'):
    href='/odoo/action-%s?menu_id=%s'%(m.action.id,m.id)
    if m.get_external_id().get(m.id)=='sale.menu_sale_order_invoice':
     href='/uno360x/area/sales?selection=invoice'
    ctx['area_tools'].append({'name':m.name,'href':href})
  if key=='reports':
   dashboard=self._dashboard(period)
   ctx.update(area_action='',area_tools=[],area_tabs=[])
   ctx.update(self._board_values(dashboard,selection,detail))
   return ctx
  filters=FILTERS.get(key,[('all',{'projects':'Proyectos','pos':'Cajas','inventory':'Productos','maintenance':'Solicitudes'}.get(key,'General'),[])])
  selected=next((f for f in filters if f[0]==selection),filters[0]);selection=selected[0];ctx['selection']=selection
  def url(**extra):return base+'?'+urlencode(dict(q=q,selection=selection,**extra))
  if key=='sales' and selection=='invoice':
   menu=self.env.ref('sale.menu_sale_order_invoice',raise_if_not_found=False)
   ctx.update(area_can_create=False,area_action='/odoo/action-%s'%menu.action.id if menu and menu.id in ctx['allowed_menus'] else '')
  ctx['can_invoice_templates'] = key == 'sales' and self.env.user.has_group('account.group_account_invoice')
  ctx['area_tabs']=[{'name':name,'href':base+'?'+urlencode({'q':q,'selection':value}),'active':value==selection} for value,name,domain in filters]
  obj=self.env[model];company=[]
  if 'company_id' in obj._fields:
   company=['|',('company_id','=',False),('company_id','=',self.env.company.id)] if key in ('contacts','inventory','crm','maintenance') else [('company_id','=',self.env.company.id)]
  domain=company+list(selected[2]);base_domain=list(company)
  if key=='contacts':base_domain+=[('active','=',True)];domain+=[('active','=',True)]
  if key=='attendance' and selection=='all':
   tz=ZoneInfo(self.env.user.tz or 'UTC');local=datetime.datetime.combine(today,datetime.time.min).replace(tzinfo=tz);start=fields.Datetime.to_string(local.astimezone(datetime.timezone.utc).replace(tzinfo=None));end=fields.Datetime.to_string((local+datetime.timedelta(days=1)).astimezone(datetime.timezone.utc).replace(tzinfo=None));domain+=[('check_in','>=',start),('check_in','<',end)]
  if key=='leave' and selection=='mine':domain+=[('employee_id.user_id','=',self.env.uid)]
  if key=='expenses' and selection=='all':domain+=[('employee_id.user_id','=',self.env.uid)]
  search='name'
  if key in ('attendance','leave'):search='employee_id.name'
  if q:
   if key == 'billing' and 'uno360x_ecf_issue_ids' in obj._fields and self.env.user.has_group('account.group_account_invoice'):
    domain+=['|','|',('uno360x_ecf_issue_ids.encf','ilike',q),('name','ilike',q),('partner_id.name','ilike',q)]
   elif key in ('sales','purchases','billing','crm'):domain+=['|',('name','ilike',q),('partner_id.name','ilike',q)]
   else:domain+=[(search,'ilike',q)]
  count=lambda d:obj.search_count(base_domain+d)
  money=lambda value,currency=None:format_amount(self.env,value,currency or self.env.company.currency_id)
  if key=='contacts':ctx['area_metrics']=[('Contactos activos',count([('active','=',True)])),('Clientes',count([('customer_rank','>',0),('active','=',True)])),('Proveedores',count([('supplier_rank','>',0),('active','=',True)]))]
  elif key=='sales':ctx['area_metrics']=[('Cotizaciones abiertas',count([('state','in',['draft','sent'])])),('Enviadas',count([('state','=','sent')])),('Pedidos por facturar',count([('invoice_status','=','to invoice')]))]
  elif key=='billing':ctx['area_metrics']=[('Facturas de clientes',count([('move_type','=','out_invoice')])),('Pendientes',count([('move_type','=','out_invoice'),('state','=','posted'),('payment_state','!=','paid')])),('Pagadas',count([('move_type','=','out_invoice'),('state','=','posted'),('payment_state','=','paid')]))]
  elif key=='crm':ctx['area_metrics']=[('Oportunidades abiertas',count([('type','=','opportunity'),('active','=',True),('probability','<',100)])),('Sin próxima actividad',count([('type','=','opportunity'),('activity_ids','=',False)])),('Ganadas',count([('type','=','opportunity'),('probability','=',100)]))]
  elif key=='pos':
   sessions=self.env['pos.session'] if self._can_read('pos.session') else None
   opened=sessions.search_count([('company_id','=',self.env.company.id),('state','in',['opening_control','opened','closing_control'])]) if sessions is not None else 'Sin acceso'
   ctx['area_metrics']=[('Cajas disponibles',count([('active','=',True)])),('Turnos abiertos',opened),('Empresa',self.env.company.name)]
  elif key=='projects':ctx['area_metrics']=[('Proyectos activos',count([('active','=',True)])),('Con responsable',count([('user_id','!=',False),('active','=',True)])),('Resultados filtrados',obj.search_count(domain))]
  elif key=='purchases':ctx['area_metrics']=[('Solicitudes abiertas',count([('state','in',['draft','sent','to approve'])])),('Pedidos confirmados',count([('state','=','purchase')])),('Por facturar',count([('invoice_status','=','to invoice')]))]
  elif key=='maintenance':ctx['area_metrics']=[('Solicitudes abiertas',count([('stage_id.done','=',False)])),('Programadas',count([('schedule_date','!=',False),('stage_id.done','=',False)])),('Alta prioridad',count([('priority','=','3'),('stage_id.done','=',False)]))]
  elif key=='attendance':ctx['area_metrics']=[('Registros visibles',obj.search_count(domain)),('Sin salida',count([('check_out','=',False)])),('Empleado',self.env.user.name)]
  elif key=='leave':ctx['area_metrics']=[('Solicitudes visibles',obj.search_count(domain)),('Por aprobar',count([('state','in',['confirm','validate1'])])),('Aprobadas',count([('state','=','validate')]))]
  elif key=='expenses':ctx['area_metrics']=[('Mis gastos',count([('employee_id.user_id','=',self.env.uid)])),('Por aprobar',count([('state','in',['submitted','reported'])])),('Reembolsados',count([('state','=','done')]))]
  elif key=='inventory':ctx['area_metrics']=[('Productos activos',count([('active','=',True)])),('Disponibles',count([('qty_available','>',0)])),('Sin existencias',count([('qty_available','<=',0)]))]
  total=obj.search_count(domain);pages=max(1,math.ceil(total/24));page=min(page,pages)
  order='name,id' if key in ('contacts','inventory','pos') else 'id desc'
  records=obj.search(domain,limit=24,offset=(page-1)*24,order=order)
  ctx.update(area_total=total,area_page=page,area_pages=pages,area_previous=url(page=page-1) if page>1 else '',area_next=url(page=page+1) if page<pages else '')
  def label(rec,name):
   val=rec[name]
   if not val:return '—'
   field=rec._fields[name]
   if field.type=='many2one':return val.display_name
   if field.type=='selection':return dict(field._description_selection(self.env)).get(val,val)
   if field.type=='datetime':return format_datetime(self.env,val)
   if field.type=='date':return format_date(self.env,val)
   if field.type=='float':return '{:,.2f}'.format(val)
   return str(val)
  columns={
   'contacts':[('name','Nombre'),('city','Ciudad'),('email','Correo')],
   'sales':[('name','Documento'),('partner_id','Cliente'),('date_order','Fecha'),('validity_date','Vigencia'),('amount_total','Total'),('state','Estado')],
   'billing':[('name','Número de factura / e-NCF'),('partner_id','Cliente'),('invoice_date','Fecha'),('invoice_date_due','Vencimiento'),('amount_total','Total'),('payment_state','Pago'),('state','Estado')],
   'expenses':[('name','Concepto'),('employee_id','Empleado'),('date','Fecha'),('total_amount','Importe'),('state','Estado')],
   'purchases':[('name','Documento'),('partner_id','Proveedor'),('date_planned','Entrega'),('amount_total','Total'),('state','Estado')],
   'inventory':[('name','Producto'),('default_code','Referencia'),('qty_available','Stock actual'),('uom_id','Unidad')],
   'attendance':[('employee_id','Empleado'),('check_in','Entrada'),('check_out','Salida'),('worked_hours','Horas registradas')],
   'leave':[('employee_id','Empleado'),('holiday_status_id','Tipo'),('request_date_from','Desde'),('request_date_to','Hasta'),('number_of_days','Días'),('state','Estado')],
   'projects':[('name','Proyecto'),('partner_id','Cliente'),('user_id','Responsable')],
   'crm':[('name','Oportunidad'),('partner_id','Cliente'),('expected_revenue','Importe'),('stage_id','Etapa')],
   'maintenance':[('name','Solicitud'),('equipment_id','Equipo'),('user_id','Técnico'),('schedule_date','Programada'),('stage_id','Etapa')],
   'pos':[('name','Caja'),('current_session_state','Estado'),('current_user_id','Responsable')],
  }.get(key,[])
  readable_fields=obj.fields_get([f for f,l in columns if f in obj._fields])
  columns=[(f,l) for f,l in columns if f in readable_fields]
  if key == 'billing':ctx['billing_assets']=billing_asset_urls()
  ctx['area_columns']=[l for f,l in columns]
  stock_summary = self._inventory_replenishment_summary(records) if key == 'inventory' else {}
  if key == 'inventory':
   ctx['inventory_shortage_report'] = self.env.user.has_group('stock.group_stock_user')
   ctx['area_columns'].extend(['Almacén', 'Mínimo', 'Objetivo', 'Por recibir', 'Sugerido'])
  for rec in records:
   native=ctx['area_action']+'/'+str(rec.id) if action else ''
   if product_template_action:
    template = rec.product_tmpl_id
    if template.has_access('read') and template.product_variant_count == 1:
     native = '/odoo/action-%s/%s' % (product_template_action.id, template.id)
   if key=='contacts':native='/uno360x-contacto?id='+str(rec.id)
   if key=='projects':native='/uno360x-proyecto?id='+str(rec.id)
   vals=[]
   stock = stock_summary.get(rec.id)
   stock_low = bool(stock and stock['low'])
   for f,l in columns:
    v=money(rec[f],rec.currency_id if 'currency_id' in rec._fields else None) if f in ('amount_total','total_amount','expected_revenue') else label(rec,f)
    if key == 'inventory' and f == 'qty_available' and rec.is_storable:
     v = '{:,.2f}'.format(stock['current'] if stock else rec[f])
    if key == 'billing' and f == 'name' and rec.move_type in ('out_invoice', 'out_refund'):
     v = rec.display_name if 'uno360x_ecf_issue_ids' in rec._fields and rec.sudo().uno360x_ecf_issue_ids else v
    credited = key == 'billing' and f == 'payment_state' and rec.currency_id.is_zero(rec.amount_residual) and (
     (rec.move_type == 'out_invoice' and 'uno360x_full_credit_encf' in rec._fields and rec.uno360x_full_credit_encf) or
     (rec.move_type == 'out_refund' and rec.payment_state == 'paid' and
      'uno360x_credit_no_payment' in rec._fields and rec.uno360x_credit_no_payment)
    )
    fiscal_payment_badge = None
    if credited:
     fiscal_payment_badge = 'credit' if rec.move_type == 'out_refund' else 'reversed'
     v = 'Nota de crédito' if fiscal_payment_badge == 'credit' else 'Revertido'
    vals.append({'text':v,'paid':f=='payment_state' and rec[f]=='paid' and not credited,
                 'fiscal_payment_badge':fiscal_payment_badge,
                 'stock_low':f=='qty_available' and stock_low})
   if key == 'inventory':
    if stock:
     rule = stock['rule']
     location_name = rule.warehouse_id.name if rule.location_id == rule.warehouse_id.lot_stock_id else rule.location_id.display_name
     amounts = (rule.product_min_qty, rule.product_max_qty, stock['pending'], stock['suggestion'])
     extra = [location_name, *('{:,.2f}'.format(amount) for amount in amounts)]
    else:
     extra = ['—'] * 5
    vals.extend({'text': value, 'paid': False} for value in extra)
   item={'id':rec.id,'name':rec.display_name,'href':native,'cells':vals,'subtitle':' · '.join(v['text'] for v in vals[1:3]),'initials':rec.display_name[:2].upper(),'progress':None,'stage_id':rec.stage_id.id if kind=='board' and 'stage_id' in obj.fields_get(['stage_id']) else None,'stage':rec.stage_id.display_name if kind=='board' and 'stage_id' in obj.fields_get(['stage_id']) else '', 'pos_open':False}
   if key=='projects' and self._can_read('project.task'):
    tasks=self.env['project.task'];all_tasks=tasks.search_count([('project_id','=',rec.id)]);done=tasks.search_count([('project_id','=',rec.id),('state','in',['1_done','1_canceled'])]);item['progress']=round(done/all_tasks*100) if all_tasks else 0;item['subtitle']=str(done)+' / '+str(all_tasks)+' tareas cerradas'
   if key=='pos':item['pos_open']=rec.current_session_state in ('opening_control','opened','closing_control')
   ctx['area_rows'].append(item)
  if kind=='board':
   boards={}
   for item in ctx['area_rows']:
    board=boards.setdefault(item['stage_id'],{'name':item['stage'] or 'Sin etapa','items':[]});board['items'].append(item)
   ctx['area_boards']=list(boards.values())
  if kind=='calendar':
   try:month=datetime.date.fromisoformat(str(period)+'-01') if period else today.replace(day=1)
   except (TypeError,ValueError):month=today.replace(day=1)
   if not 2020<=month.year<=today.year+2:month=today.replace(day=1)
   ctx['area_month']=month.strftime('%Y-%m')
   last=month.replace(day=calendar.monthrange(month.year,month.month)[1])
   leaves=obj.search(company+[('request_date_from','<=',last),('request_date_to','>=',month),('state','not in',['cancel','refuse'])],limit=100)
   weeks=[]
   for week in calendar.Calendar().monthdatescalendar(month.year,month.month):
    weeks.append([{'day':d.day,'current':d.month==month.month,'events':[l.employee_id.name for l in leaves if l.request_date_from<=d<=l.request_date_to]} for d in week])
   ctx['area_calendar']=weeks
  return ctx
