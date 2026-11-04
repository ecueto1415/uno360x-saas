from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError
from werkzeug.exceptions import NotFound,Forbidden
from .reference import ReferenceWorkspace
from .workspace import WorkspaceController
from ..models.areas import AREAS

class AreaWorkspace(ReferenceWorkspace):
 @http.route('/uno360x/area/<string:key>',type='http',auth='user',methods=['GET'])
 def area(self,key,q='',page=1,selection='all',period=None,**kw):
  if key not in AREAS:raise NotFound()
  if key=='jenifer':return request.redirect('/uno360x-jenifer',code=303)
  try:values=self._service()._area_values(key,q,page,selection,period)
  except AccessError:raise Forbidden() from None
  values['area_back']=request.httprequest.full_path.rstrip('?')
  return self._render('uno360x_workspace.area',values)
 @http.route('/uno360x/area/<string:key>/record/<int:record_id>',type='http',auth='user',methods=['GET'])
 def area_record(self,key,record_id,**kw):
  service=self._service();ctx=service._workspace_context()
  if key not in AREAS or not service._area_available(key,ctx):raise NotFound()
  model=AREAS[key][2];action=service._area_action(key,ctx)
  if not action:raise NotFound()
  record=request.env[model].browse(record_id).exists()
  if not record:raise NotFound()
  record.check_access_rights('read');record.check_access_rule('read')
  if 'company_id' in record._fields and record.company_id and record.company_id!=request.env.company:raise NotFound()
  return request.redirect('/odoo/action-%s/%s'%(action.id,record.id),code=303)
 @http.route('/uno360x-contactos',type='http',auth='user',methods=['GET'])
 def contacts(self,**kw):return self.area('contacts',**kw)
 @http.route('/uno360x-proyectos',type='http',auth='user',methods=['GET'])
 def projects(self,**kw):return self.area('projects',**kw)
 @http.route('/uno360x-facturacion',type='http',auth='user',methods=['GET'])
 def billing(self,**kw):return self.area('billing',**kw)
 @http.route('/uno360x-pos',type='http',auth='user',methods=['GET'])
 def pos_home(self,**kw):return self.area('pos',**kw)
 @http.route()
 def open_menu(self,menu_id,**kw):
  service=self._service();ctx=service._workspace_context()
  if menu_id not in ctx['allowed_menus']:raise NotFound()
  menu=request.env['ir.ui.menu'].browse(menu_id)
  for key in AREAS:
   if key in ('jenifer','reports') or not service._area_available(key,ctx):continue
   action=service._area_action(key,ctx)
   if action and menu.action==action:return request.redirect('/uno360x/area/'+key,code=303)
  if getattr(menu.action.sudo(),'res_model',None)=='hr.employee':return super().open_menu(menu_id,**kw)
  return WorkspaceController.open_menu(self,menu_id,**kw)
 @http.route('/uno360x-jenifer',type='http',auth='user',methods=['GET','POST'],csrf=True)
 def jenifer(self,question='',**kw):
  ctx=self._service()._workspace_context()
  if 'jenifer_ai' not in ctx['options']:raise NotFound()
  uid_key='%s:%s'%(request.env.uid,request.env.company.id);all_history=dict(request.session.get('ux_jenifer_history',{}));history=all_history.get(uid_key,[]);answer=''
  if request.httprequest.method=='POST' and question:
   question=str(question).strip()[:500]
   answer=request.env['uno360x.jenifer.query']._respond(question) or 'Puedes consultar CxC, CxP o cotizaciones pendientes. No se ha realizado ninguna acciÃ³n.'
   history=([{'question':question,'answer':answer}]+history)[:10];all_history={uid_key:history};request.session['ux_jenifer_history']=all_history
  ctx.update(question=question,answer=answer,history=history,page_key='jenifer')
  return self._render('uno360x_workspace.area_jenifer',ctx)
