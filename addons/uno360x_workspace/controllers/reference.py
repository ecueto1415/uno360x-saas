"""Approved appearance with current tenant ACLs; never operational record IDs."""
import datetime
from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden,NotFound
from .workspace import WorkspaceController

class ReferenceWorkspace(WorkspaceController):
 def _reference(self,key,model,option=None):
  service=self._service();ctx=service._workspace_context()
  if option and option not in ctx['options']:raise NotFound()
  if model not in request.env.registry or not service._can_read(model):raise Forbidden()
  ctx.update(panel_env=request.env,datetime=datetime)
  return self._render('uno360x_workspace.reference_'+key,ctx)
 @http.route('/uno360x-contactos',type='http',auth='user',methods=['GET'])
 def contacts(self,**kw):return self._reference('contacts','res.partner')
 @http.route('/uno360x-contacto',type='http',auth='user',methods=['GET'])
 def contact(self,**kw):return self._reference('contact','res.partner')
 @http.route('/uno360x-proyectos',type='http',auth='user',methods=['GET'])
 def projects(self,**kw):return self._reference('projects','project.project','projects_services')
 @http.route('/uno360x-proyecto',type='http',auth='user',methods=['GET'])
 def project(self,**kw):return self._reference('project','project.project','projects_services')
 @http.route('/uno360x-facturacion',type='http',auth='user',methods=['GET'])
 def billing(self,**kw):return self._reference('billing','account.move')
 @http.route('/uno360x/invoice/new',type='http',auth='user',methods=['GET'])
 def invoice_new(self,**kw):
  self._service()
  request.env['account.move'].check_access_rights('create')
  action=request.env.ref('account.action_move_out_invoice_type',raise_if_not_found=False)
  if not action:raise NotFound()
  return request.redirect('/odoo/action-%s/new'%action.id,code=303)
 @http.route('/uno360x-empleados',type='http',auth='user',methods=['GET'])
 def employees(self,**kw):return self._reference('employees','hr.employee','payroll_hr')
 @http.route('/uno360x/native/<string:model>',type='http',auth='user',methods=['GET'])
 def native_model(self,model,**kw):
  allowed={'res.partner','project.project','project.task','sale.order','purchase.order','account.payment','hr.employee','account.move','account.journal'}
  if model not in allowed:raise NotFound()
  ctx=self._service()._workspace_context()
  if model.startswith('project.') and 'projects_services' not in ctx['options']:raise NotFound()
  if model=='hr.employee' and 'payroll_hr' not in ctx['options']:raise NotFound()
  menus=request.env['ir.ui.menu'].browse(list(ctx['allowed_menus']))
  action=menus.filtered(lambda m:m.action and m.action.type=='ir.actions.act_window' and m.action.sudo().res_model==model)[:1].action
  if not action:raise Forbidden()
  return request.redirect('/odoo/action-%s'%action.id,code=303)
 @http.route()
 def open_menu(self,menu_id,**kw):
  ctx=self._service()._workspace_context()
  if menu_id not in ctx['allowed_menus']:raise NotFound()
  menu=request.env['ir.ui.menu'].browse(menu_id);action=menu.action
  model=getattr(action.sudo(),'res_model',None) if action else None
  if model=='account.move' and action.id==request.env.ref('account.action_move_out_invoice_type').id:return request.redirect('/uno360x-facturacion',code=303)
  if model=='res.partner':return request.redirect('/uno360x-contactos',code=303)
  if model=='project.project' and 'projects_services' in ctx['options']:return request.redirect('/uno360x-proyectos',code=303)
  if model=='hr.employee' and 'payroll_hr' in ctx['options']:return request.redirect('/uno360x-empleados',code=303)
  return super().open_menu(menu_id,**kw)
