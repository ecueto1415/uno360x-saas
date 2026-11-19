import base64
import re
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError,UserError
from werkzeug.exceptions import NotFound,Forbidden

from ..models.company_branding import DOCUMENT_LAYOUTS
from odoo.addons.uno360x_quote_ui.models.bcrd_quote_rate import official_rate


def _uploaded_company_logo(upload, label='El logo'):
 if not upload or not upload.filename:
  return None
 content = upload.read(2 * 1024 * 1024 + 1)
 if len(content) > 2 * 1024 * 1024:
  raise UserError(f'{label} debe pesar como máximo 2 MB.')
 try:
  with Image.open(BytesIO(content)) as image:
   if image.format not in ('PNG', 'JPEG') or max(image.size) > 4096:
    raise ValueError('Invalid logo format or dimensions')
   image.verify()
  with Image.open(BytesIO(content)) as image:
   image.load()
 except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
  raise UserError('Sube una imagen PNG o JPG válida de hasta 4096 × 4096 píxeles.') from None
 return base64.b64encode(content)


def can_manage_company(user):
 return user.has_group('base.group_system') or all(
  user.has_group(group) for group in (
   'sales_team.group_sale_manager', 'account.group_account_manager', 'stock.group_stock_manager',
  )
 )


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
 @http.route('/uno360x-mi-empresa', type='http', auth='user', methods=['GET', 'POST'], csrf=True)
 def my_company(self, name='', rnc='', operation='', saved='', document_layout='', **kw):
  ctx = self._service()._workspace_context()
  user = request.env.user
  can_edit = can_manage_company(user)
  company = request.env.company
  error = ''
  if request.httprequest.method == 'POST':
   if not can_edit:
    raise Forbidden()
   try:
    with request.env.cr.savepoint():
     if operation == 'profile':
      if not isinstance(name, str) or not 1 <= len(name.strip()) <= 150:
       raise UserError('Indica la razón social de la empresa (hasta 150 caracteres).')
      if not isinstance(rnc, str) or not re.fullmatch(r'[0-9 -]{9,20}', rnc.strip()):
       raise UserError('Escribe un RNC de 9 dígitos o una cédula de 11 dígitos.')
      tax_id = re.sub(r'[ -]', '', rnc.strip())
      if len(tax_id) not in (9, 11) or not int(tax_id):
       raise UserError('Escribe un RNC de 9 dígitos o una cédula de 11 dígitos.')
      company.sudo().write({'name': name.strip(), 'vat': tax_id, 'uno360x_fiscal_legal_name': name.strip()})
     elif operation == 'branding':
      if document_layout and document_layout not in dict(DOCUMENT_LAYOUTS):
       raise UserError('Elige una de las cuatro plantillas.')
      values = {'uno360x_document_layout': document_layout or False}
      logo = _uploaded_company_logo(request.httprequest.files.get('company_logo'))
      if logo:
       values['logo'] = logo
      company.sudo().write(values)
     elif operation == 'signature_stamp':
      image = _uploaded_company_logo(request.httprequest.files.get('signature_stamp'), 'Firma y sello')
      if kw.get('remove_signature_stamp') == '1':
       company.sudo().write({'uno360x_signature_stamp': False})
      elif image:
       company.sudo().write({'uno360x_signature_stamp': image})
      else:
       raise UserError('Selecciona una imagen PNG o JPG para Firma y sello.')
     elif operation == 'usd':
      if company.currency_id.name != 'DOP' or company.parent_id:
       raise UserError('Esta opción está disponible para empresas con moneda base DOP.')
      if not official_rate():
       raise UserError('La tasa oficial del Banco Central todavía no está disponible.')
      usd = request.env.ref('base.USD').sudo()
      usd.active = True
      lists = request.env['product.pricelist'].sudo().with_company(company)
      if not lists.search_count([('company_id', '=', company.id), ('currency_id', '=', usd.id)]):
       lists.create({'name': 'USD - Dólares estadounidenses', 'currency_id': usd.id, 'company_id': company.id})
     else:
      raise NotFound()
   except UserError as exc:
    error = str(exc)
   else:
    return request.redirect('/uno360x-mi-empresa?saved=1', code=303)
  ctx.update(page_key='my_company', can_edit_company=can_edit, company_error=error,
             company_saved=saved == '1', profile_name=name if error and operation == 'profile' else company.uno360x_fiscal_legal_name or company.name,
             profile_rnc=rnc if error and operation == 'profile' else company.vat or '',
             document_layouts=DOCUMENT_LAYOUTS,
             company_document_layout=company.sudo().uno360x_document_layout,
             company_logo=company.sudo().logo,
             company_signature_stamp=company.sudo().uno360x_signature_stamp,
             usd_reference=official_rate() if can_edit and company.currency_id.name == 'DOP' else None)
  return self._render('uno360x_workspace.my_company', ctx)

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
  specs=[('res.partner','display_name','contacts.menu_contacts','Contactos'),('account.move','name','account.menu_finance','Facturas'),('sale.order','name','sale.sale_menu_root','Ventas'),('purchase.order','name','purchase.menu_purchase_root','Compras'),('product.product','display_name','stock.menu_stock_root','Productos'),('maintenance.request','name','maintenance.menu_maintenance_title','Mantenimiento')]
  if 'projects_services' in ctx['options']:specs.append(('project.project','name','project.menu_main_pm','Proyectos'))
  if q:
   for model,field,xmlid,label in specs:
    menu=service._search_menu(model,xmlid,ctx['allowed_menus'])
    if not service._can_read(model) or not menu:continue
    domain=[(field,'ilike',q)]
    if model!='res.partner':domain+=[('company_id','=',request.env.company.id)]
    for record in request.env[model].search(domain,limit=20):
     results.append({'name':record.display_name,'kind':label,'href':'/odoo/action-%s/%s'%(menu.action.id,record.id)})
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
