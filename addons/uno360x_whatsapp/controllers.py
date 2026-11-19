from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError
from werkzeug.exceptions import NotFound
from odoo.addons.uno360x_workspace.controllers.workspace import WorkspaceController
from .models import require_collector, require_manager

PATH='/uno360x/cobros/whatsapp'


class WhatsAppWorkspace(WorkspaceController):
    def _context(self):
        require_collector(request.env)
        ctx=self._service()._workspace_context()
        ctx.update(page_key='billing',wa_path=PATH,wa_error='',wa_manager=request.env.user.has_group('account.group_account_manager'))
        return ctx

    def _invoice(self, move_id):
        move=request.env['account.move'].search([('id','=',move_id),('company_id','=',request.env.company.id),('move_type','=','out_invoice')],limit=1)
        if not move:raise NotFound()
        return move

    @http.route(PATH,type='http',auth='user',methods=['GET'])
    def wa_home(self,**kw):
        ctx=self._context()
        invoices=request.env['account.move'].search([('company_id','=',request.env.company.id),('move_type','=','out_invoice'),('state','=','posted'),('amount_residual','>',0),('payment_state','not in',['paid','reversed'])],order='invoice_date_due,id',limit=50)
        history=request.env['uno360x.wa.reminder'].search([('company_id','=',request.env.company.id)],limit=30)
        visible=request.env['uno360x.wa.reminder']
        for item in history:
            try:item.check_access('read')
            except AccessError:continue
            visible|=item
        ctx.update(wa_invoices=invoices,wa_history=visible,wa_number=lambda m:m._ux_accepted_ecf_number() or m.name,
                   wa_connection=request.env['uno360x.wa.connection'].search([('company_id','=',request.env.company.id)],limit=1))
        return self._render('uno360x_whatsapp.home',ctx)

    @http.route(PATH+'/factura/<int:move_id>',type='http',auth='user',methods=['GET','POST'],csrf=True)
    def wa_invoice(self,move_id,**kw):
        ctx=self._context();move=self._invoice(move_id)
        consent=request.env['uno360x.wa.consent'].search([('company_id','=',move.company_id.id),('partner_id','=',move.partner_id.commercial_partner_id.id)],limit=1)
        preview=None
        try:preview=request.env['uno360x.wa.reminder']._snapshot(move,consent)
        except (AccessError,UserError) as exc:ctx['wa_error']=str(exc)
        if request.httprequest.method=='POST' and preview:
            reminder=request.env['uno360x.wa.reminder']._prepare(move,consent)
            return request.redirect(PATH+'/aviso/'+str(reminder.id),code=303)
        ctx.update(wa_invoice=move,wa_preview=preview,wa_consent=consent,
                   wa_customer=move.partner_id.commercial_partner_id)
        return self._render('uno360x_whatsapp.review',ctx)

    @http.route(PATH+'/aviso/<int:reminder_id>',type='http',auth='user',methods=['GET','POST'],csrf=True)
    def wa_reminder(self,reminder_id,**kw):
        ctx=self._context()
        item=request.env['uno360x.wa.reminder'].search([('id','=',reminder_id),('company_id','=',request.env.company.id)],limit=1)
        if not item:raise NotFound()
        item.check_access('read')
        if request.httprequest.method=='POST':
            item._simulate()
            return request.redirect(PATH+'/aviso/'+str(item.id),code=303)
        ctx.update(wa_reminder=item)
        return self._render('uno360x_whatsapp.reminder',ctx)

    @http.route(PATH+'/configuracion',type='http',auth='user',methods=['GET','POST'],csrf=True)
    def wa_configuration(self,**kw):
        require_manager(request.env);ctx=self._context()
        connection=request.env['uno360x.wa.connection'].search([('company_id','=',request.env.company.id)],limit=1)
        if request.httprequest.method=='POST':
            try:
                with request.env.cr.savepoint():
                    data={'display_phone':kw.get('display_phone','').strip(),'template_name':kw.get('template_name','').strip(),'language':kw.get('language','es')}
                    connection.write(data) if connection else request.env['uno360x.wa.connection'].create(data)
                return request.redirect(PATH,code=303)
            except (UserError,ValueError) as exc:ctx['wa_error']=str(exc) if isinstance(exc,UserError) else 'Revisa el número, la plantilla y el idioma.'
        ctx.update(wa_connection=connection)
        return self._render('uno360x_whatsapp.configuration',ctx)

    @http.route(PATH+'/cliente/<int:partner_id>',type='http',auth='user',methods=['GET','POST'],csrf=True)
    def wa_customer(self,partner_id,**kw):
        require_manager(request.env);ctx=self._context()
        partner=request.env['res.partner'].search([('id','=',partner_id),('company_id','in',[False,request.env.company.id])],limit=1)
        if not partner or partner!=partner.commercial_partner_id:raise NotFound()
        consent=request.env['uno360x.wa.consent'].search([('company_id','=',request.env.company.id),('partner_id','=',partner.id)],limit=1)
        if request.httprequest.method=='POST':
            try:
                with request.env.cr.savepoint():
                    data={'recipient':kw.get('recipient','').strip(),'state':kw.get('state','unknown'),'evidence':kw.get('evidence','').strip()[:500]}
                    consent.write(data) if consent else request.env['uno360x.wa.consent'].create(dict(data,partner_id=partner.id))
                return request.redirect(PATH,code=303)
            except (UserError,ValueError) as exc:ctx['wa_error']=str(exc) if isinstance(exc,UserError) else 'Revisa el número y la autorización.'
        ctx.update(wa_customer=partner,wa_consent=consent)
        return self._render('uno360x_whatsapp.customer',ctx)
