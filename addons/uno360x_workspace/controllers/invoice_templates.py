from odoo import http
from odoo.http import request
from odoo.tools.misc import format_amount
from werkzeug.exceptions import NotFound

from .areas import AreaWorkspace


class InvoiceTemplateWorkspace(AreaWorkspace):
    def _template_page(self):
        service = self._service()
        values = service._area_values('sales')
        values['page_key'] = 'sales'
        model = request.env['uno360x.invoice.template']
        model.check_access('read')
        return model, values

    @http.route('/uno360x/ventas/plantillas', type='http', auth='user', methods=['GET'])
    def invoice_templates(self, plantilla='', factura='', cliente='', **kwargs):
        model, values = self._template_page()
        templates = model.search([('company_id', '=', request.env.company.id)])
        selected = templates.filtered(lambda item: str(item.id) == plantilla)[:1] if plantilla else templates[:1]
        if plantilla and not selected:
            raise NotFound()
        customer_query = cliente.strip()[:100]
        partners = request.env['res.partner'].browse()
        if selected and factura == '1' and customer_query:
            partners = partners.search([
                ('company_id', 'in', [False, request.env.company.id]),
                '|', ('name', 'ilike', customer_query), ('vat', 'ilike', customer_query),
            ], limit=30)
        values.update(
            templates=templates, selected=selected, show_invoice=factura == '1',
            customer_query=customer_query, partners=partners,
            form_url='/odoo/action-%s' % request.env.ref('uno360x_workspace.invoice_template_action').id,
            amount=lambda value: format_amount(request.env, value, request.env.company.currency_id),
        )
        return self._render('uno360x_workspace.invoice_templates', values)

    @http.route('/uno360x/ventas/plantillas/<int:template_id>/eliminar', type='http', auth='user', methods=['POST'])
    def delete_invoice_template(self, template_id, **kwargs):
        model, _ = self._template_page()
        template = model.browse(template_id).exists()
        if not template:
            raise NotFound()
        template.unlink()
        return request.redirect('/uno360x/ventas/plantillas', code=303)

    @http.route('/uno360x/ventas/plantillas/<int:template_id>/factura', type='http', auth='user', methods=['POST'])
    def create_template_invoice(self, template_id, partner_id='', **kwargs):
        model, _ = self._template_page()
        template = model.browse(template_id).exists()
        if not template or not partner_id.isascii() or not partner_id.isdigit() or len(partner_id) > 10:
            raise NotFound()
        template.check_access('read')
        partner = request.env['res.partner'].browse(int(partner_id)).exists()
        if not partner:
            raise NotFound()
        wizard = request.env['uno360x.invoice.template.wizard'].create({
            'template_id': template.id, 'partner_id': partner.id,
        })
        action = wizard.action_create_invoice()
        return request.redirect('/odoo/action-%s/%s' % (action['id'], action['res_id']), code=303)

