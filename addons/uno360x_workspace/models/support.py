"""Bounded diagnostics: no sudo, secrets, fiscal actions or business writes."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError
from .support_guide import GUIDE, COMPANY_GUIDE

class WorkspaceSupport(models.AbstractModel):
    _inherit = 'uno360x.workspace'

    @api.model
    def support_diagnostics(self):
        context = self._workspace_context()
        self._area_navigation(context)
        company, user = self.env.company, self.env.user
        options = context['options']
        result = {'version':'support-readonly-v1','verified_at':fields.Datetime.now().isoformat(),
            'user_id':user.id,'company_id':company.id,'company':{'name':company.name},
            'menus':[],'features':{},'configuration':{},'limitations':[
                'Lectura local con los permisos del usuario solicitante.',
                'No se consultó DGII ni se firmó, reservó o emitió un comprobante.',
                'No se leen claves, certificados privados, documentos, salarios o datos de otras empresas.']}
        def read_config(key, callback):
            try:
                with self.env.cr.savepoint():
                    value=callback()
                result['configuration'][key]={'verified':True,'value':value}
            except (AccessError,MissingError):
                result['configuration'][key]={'verified':False,'reason':'Sin permiso para verificar esta configuración.'}
        def visible(model, area=None):
            return self._work_area_allowed(area) and model in self.env.registry.models and self.env[model].check_access_rights('read',raise_exception=False)
        def walk(nodes, parents):
            for node in nodes:
                path=parents+[node['name']]
                if node['href']:result['menus'].append({'path':' → '.join(path),'route':node['href']})
                walk(node['children'],path)
        for group in context['groups']:walk(group['nodes'],[group['name']])
        result['menus']=result['menus'][:160]
        for key,path,model,route,option,area,steps in GUIDE:
            installed=model in self.env.registry.models and (not option or option in options)
            available=installed and visible(model,area)
            if key=='adjust_stock':available=available and user.has_group('stock.group_stock_manager')
            if key in ('payroll','contracts') and installed:
                available=available and user.has_group('uno360x_payroll_hr.group_payroll')
            if key=='payroll_additional' and available:
                menu=self.env.ref('uno360x_payroll_hr.menu_additional_register',raise_if_not_found=False)
                available=bool(menu and menu.id in context['allowed_menus'])
                if available:route='/uno360x/open/%s'%menu.id
            result['features'][key]={'installed':bool(installed),'available':bool(available),
                'path':path,'route':route if available else None,
                'steps':steps if available else 'No disponible para este usuario o plan. No ampliar sus permisos desde soporte.'}
        manage_company=user.has_group('base.group_system') or all(user.has_group(group) for group in (
            'sales_team.group_sale_manager','account.group_account_manager','stock.group_stock_manager'))
        for key in ('company','usd'):
            result['features'][key]=dict(COMPANY_GUIDE[key],installed=True,available=bool(manage_company))
        accounting_manager=user.has_group('account.group_account_manager') and self._work_area_allowed('billing')
        for key in ('fiscal','ranges'):
            result['features'][key]=dict(COMPANY_GUIDE[key],installed='uno360x.ecf.range' in self.env.registry.models,
                available=bool(accounting_manager))
            if not accounting_manager:result['features'][key].update(route=None,steps='El administrador de contabilidad debe verificar esta configuración.')
        read_config('company',lambda:{'rnc_configured':bool(company.vat),'currency':company.currency_id.name,
            'document_layout':company.uno360x_document_layout or 'default',
            'logo_configured':bool(company.with_context(bin_size=True).logo)})
        if visible('product.pricelist','sales'):
            read_config('currencies',lambda:sorted(set(self.env['product.pricelist'].search([
                ('company_id','in',[False,company.id])],limit=100).mapped('currency_id.name'))))
        if visible('account.journal','billing'):
            read_config('journals',lambda:{kind:self.env['account.journal'].search_count([
                ('company_id','=',company.id),('type','=',kind),('active','=',True)]) for kind in ('sale','purchase','bank','cash')})
        if visible('account.tax','billing'):
            read_config('sale_taxes',lambda:[{'name':tax.name,'amount':tax.amount,'calculation':tax.amount_type}
                for tax in self.env['account.tax'].search([('company_id','=',company.id),('type_tax_use','=','sale'),('active','=',True)],limit=30)])
        if visible('stock.warehouse','inventory'):
            read_config('inventory',lambda:{'warehouses':self.env['stock.warehouse'].search_count([('company_id','=',company.id)])})
        if accounting_manager and 'uno360x_ecf_enabled' in company._fields:
            read_config('fiscal',lambda:{'enabled_locally':bool(company.uno360x_ecf_enabled),
                'certificate_configured':bool(company.uno360x_ecf_fingerprint),
                'ranges':[{'kind':'E'+row.kind,'expires':row.expires.isoformat() if row.expires else None}
                    for row in self.env['uno360x.ecf.range'].search([('company_id','=',company.id),('active','=',True)],limit=30)]})
        return result
