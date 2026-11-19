from odoo import _, Command, fields, models
from odoo.exceptions import UserError


class InvoiceTemplate(models.Model):
    _name = 'uno360x.invoice.template'
    _description = 'Plantilla de facturación'
    _order = 'name, id'
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    line_ids = fields.One2many('uno360x.invoice.template.line', 'template_id', copy=True)

    def copy(self, default=None):
        raise UserError(_('Usa Crear factura para reutilizar esta plantilla.'))

    def action_open_invoice_wizard(self):
        self.ensure_one()
        self.check_access('read')
        self.env['account.move'].check_access('create')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear factura'),
            'res_model': 'uno360x.invoice.template.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_template_id': self.id},
        }


class InvoiceTemplateLine(models.Model):
    _name = 'uno360x.invoice.template.line'
    _description = 'Línea de plantilla de facturación'
    _order = 'sequence, id'
    _check_company_auto = True

    template_id = fields.Many2one('uno360x.invoice.template', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='template_id.company_id', store=True)
    currency_id = fields.Many2one(related='template_id.currency_id')
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product', required=True, check_company=True, domain=[('sale_ok', '=', True)])
    name = fields.Char(string='Descripción')
    quantity = fields.Float(string='Cantidad', required=True, default=1)
    price_unit = fields.Monetary(string='Precio unitario', required=True)
    _sql_constraints = [
        ('positive_qty', 'CHECK(quantity > 0)', 'La cantidad debe ser positiva.'),
        ('nonnegative_price', 'CHECK(price_unit >= 0)', 'El precio debe ser igual o mayor a cero.'),
    ]


class InvoiceTemplateWizard(models.TransientModel):
    _name = 'uno360x.invoice.template.wizard'
    _description = 'Crear factura desde plantilla'

    template_id = fields.Many2one('uno360x.invoice.template', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True)

    def action_create_invoice(self):
        self.ensure_one()
        template = self.template_id
        template.check_access('read')
        self.partner_id.check_access('read')
        if template.company_id != self.env.company or not template.active or not template.line_ids:
            raise UserError(_('Selecciona una plantilla activa de esta empresa que tenga productos.'))
        if self.partner_id.company_id and self.partner_id.company_id != template.company_id:
            raise UserError(_('El cliente pertenece a otra empresa.'))
        if any(not line.product_id.active or not line.product_id.sale_ok for line in template.line_ids):
            raise UserError(_('Actualiza los productos inactivos o no disponibles para ventas en la plantilla.'))
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'company_id': template.company_id.id,
            'currency_id': template.currency_id.id,
            'partner_id': self.partner_id.id,
            'invoice_line_ids': [Command.create({
                'product_id': line.product_id.id,
                **({'name': line.name} if line.name else {}),
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'sequence': line.sequence,
            }) for line in template.line_ids],
        })
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        action.update(res_id=invoice.id, views=[(False, 'form')])
        return action

