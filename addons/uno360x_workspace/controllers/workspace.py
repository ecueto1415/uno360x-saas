from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError,UserError
from werkzeug.exceptions import NotFound,Forbidden

class WorkspaceController(http.Controller):
 def _pos_values(self,error=''):
  ctx=self._service()._workspace_context()
  if not request.env.user.has_group('point_of_sale.group_pos_user'):raise Forbidden()
  ctx.update(pos_configs=request.env['pos.config'].search([('company_id','=',request.env.company.id),('active','=',True)]),can_manage_pos=request.env.user.has_group('point_of_sale.group_pos_manager'),pos_error=error,page_key='pos')
  return ctx
 @http.route('/uno360x-pos',type='http',auth='user',methods=['GET'])
 def pos_home(self,**kw):return self._render('uno360x_workspace.pos_home',self._pos_values())
 @http.route('/uno360x/pos/create',type='http',auth='user',methods=['POST'],csrf=True)
 def pos_create(self,name='',**kw):
  values=self._pos_values()
  if not values['can_manage_pos']:raise Forbidden()
  if not isinstance(name,str) or not 1<=len(name.strip())<=80:return self._render('uno360x_workspace.pos_home',self._pos_values('Indica un nombre de caja de hasta 80 caracteres.'))
  try:
   with request.env.cr.savepoint():request.env['pos.config'].create({'name':name.strip(),'company_id':request.env.company.id})
  except UserError as error:return self._render('uno360x_workspace.pos_home',self._pos_values(str(error)))
  return request.redirect('/uno360x-pos',code=303)
 @http.route('/uno360x/pos/open/<int:box_id>',type='http',auth='user',methods=['POST'],csrf=True)
 def pos_open(self,box_id,**kw):
  values=self._pos_values();box=values['pos_configs'].filtered(lambda box:box.id==box_id)
  if not box:raise NotFound()
  try:
   with request.env.cr.savepoint():action=box.open_ui()
  except UserError as error:return self._render('uno360x_workspace.pos_home',self._pos_values(str(error)))
  url=action.get('url','')
  if not url.startswith('/pos/ui?'):raise NotFound()
  return request.redirect(url,code=303)
 def _service(self):
  if not request.env.user.has_group('base.group_user'):raise Forbidden()
  return request.env['uno360x.workspace']
 def _render(self,template,values):
  values['csrf']=request.csrf_token()
  response=request.render(template,values)
  response.headers['Cache-Control']='no-store'
  return response
 @http.route('/uno360x-resumen',type='http',auth='user',methods=['GET'])
 def overview(self,period=None,**kw):
  return self._render('uno360x_workspace.dashboard',self._service()._dashboard(period))
 @http.route('/uno360x/open/<int:menu_id>',type='http',auth='user',methods=['GET'])
 def open_menu(self,menu_id,**kw):
  ctx=self._service()._workspace_context()
  if menu_id not in ctx['allowed_menus']:raise NotFound()
  menu=request.env['ir.ui.menu'].browse(menu_id)
  if not menu.action:raise NotFound()
  if menu.action in tuple(request.env.ref(xmlid,raise_if_not_found=False) for xmlid in ('point_of_sale.action_pos_config_kanban','point_of_sale.action_client_pos_menu')):return request.redirect('/uno360x-pos',code=303)
  return request.redirect('/odoo/action-%s?menu_id=%s'%(menu.action.id,menu.id),code=303)
 @http.route('/uno360x-aplicaciones',type='http',auth='user',methods=['GET'])
 def apps(self,**kw):return self._render('uno360x_workspace.apps',self._service()._workspace_context())
 @http.route('/uno360x-ayuda',type='http',auth='user',methods=['GET'])
 def help(self,**kw):return self._render('uno360x_workspace.help',self._service()._workspace_context())
 @http.route('/uno360x/language/<string:lang>',type='http',auth='user',methods=['POST'],csrf=True)
 def language(self,lang,**kw):
  self._service()
  if lang not in ('es_DO','en_US') or not request.env['res.lang'].search_count([('code','=',lang)]):raise NotFound()
  request.env.user.write({'lang':lang});request.session['context']=dict(request.session.context,lang=lang)
  return request.redirect('/uno360x-resumen',code=303)
 @http.route('/uno360x-buscar',type='http',auth='user',methods=['GET'])
 def search(self,q='',**kw):
  service=self._service();ctx=service._workspace_context();q=str(q).strip()[:100];results=[]
  specs=[('res.partner','display_name','contacts.menu_contacts','Contactos'),('account.move','name','account.menu_finance','Facturas')]
  if 'projects_services' in ctx['options']:specs.append(('project.project','name','project.menu_main_pm','Proyectos'))
  if q:
   for model,field,xmlid,label in specs:
    menu=request.env.ref(xmlid,raise_if_not_found=False)
    if not service._can_read(model) or not menu or menu.id not in ctx['allowed_menus']:continue
    domain=[(field,'ilike',q)]
    if model!='res.partner':domain+=[('company_id','=',request.env.company.id)]
    for record in request.env[model].search(domain,limit=20):
     results.append({'name':record.display_name,'kind':label,'href':'/uno360x/open/%s'%menu.id})
  ctx.update(query=q,results=results)
  return self._render('uno360x_workspace.search',ctx)
 @http.route('/uno360x-jenifer',type='http',auth='user',methods=['GET','POST'],csrf=True)
 def jenifer(self,question='',**kw):
  ctx=self._service()._workspace_context()
  if 'jenifer_ai' not in ctx['options']:raise NotFound()
  answer=''
  if request.httprequest.method=='POST' and question:
   question=str(question).strip()[:500]
   answer=request.env['uno360x.jenifer.query']._respond(question) or 'Puedes consultar CxC, CxP o cotizaciones pendientes. No se ha realizado ninguna acción.'
  ctx.update(question=question,answer=answer,page_key='jenifer')
  return self._render('uno360x_workspace.jenifer',ctx)
