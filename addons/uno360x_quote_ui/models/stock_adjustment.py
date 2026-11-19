import math

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare, float_round


class StockAdjustment(models.Model):
    _name = 'uno360x.stock.adjustment'
    _description = 'Corrección de stock UNO360X'
    _order = 'id desc'

    product_tmpl_id = fields.Many2one('product.template', required=True, index=True, ondelete='restrict')
    warehouse_id = fields.Many2one('stock.warehouse', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', string='Usuario', required=True, ondelete='restrict')
    adjusted_at = fields.Datetime(string='Fecha y hora', required=True)
    before_qty = fields.Float(string='Anterior', digits='Product Unit of Measure')
    delta_qty = fields.Float(string='Ajuste', digits='Product Unit of Measure')
    after_qty = fields.Float(string='Final', digits='Product Unit of Measure')
    reason = fields.Text(string='Motivo', required=True)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    uno_adjustment_history_ids = fields.One2many(
        'uno360x.stock.adjustment', 'product_tmpl_id',
        compute='_compute_uno_adjustment_history', groups='stock.group_stock_user',
    )

    uno_adjustment_stock_qty = fields.Float(
        compute='_compute_uno_adjustment_stock_qty', digits='Product Unit of Measure',
        groups='stock.group_stock_user',
    )

    @api.depends('product_variant_id', 'uno_saved_reorder_warehouse_id')
    @api.depends_context('company')
    def _compute_uno_adjustment_stock_qty(self):
        warehouses = self.grouped('uno_saved_reorder_warehouse_id')
        for warehouse, templates in warehouses.items():
            variants = templates.product_variant_id.with_context(
                location=warehouse.lot_stock_id.id, allowed_company_ids=[self.env.company.id],
            ) if warehouse else self.env['product.product']
            quantities = {variant.id: variant.qty_available for variant in variants}
            for template in templates:
                template.uno_adjustment_stock_qty = quantities.get(template.product_variant_id.id, 0)

    @api.depends_context('company')
    def _compute_uno_adjustment_history(self):
        Adjustment = self.env['uno360x.stock.adjustment']
        for product in self:
            product.uno_adjustment_history_ids = Adjustment.search([
                ('product_tmpl_id', '=', product.id),
                ('company_id', '=', self.env.company.id),
            ], limit=20) if product.id else Adjustment.browse()

    def _uno_check_stock_adjustment(self):
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_('Necesitas permiso para ajustar inventario.'))
        self.check_access('read')
        if self.company_id and self.company_id != self.env.company:
            raise AccessError(_('El producto no pertenece a la empresa activa.'))
        if not self.is_storable or self.product_variant_count != 1:
            raise UserError(_('Corrige las existencias de una variante almacenable desde Inventario.'))
        if self.tracking != 'none':
            raise UserError(_('Usa Ajustes de inventario para indicar el lote o número de serie.'))

    def action_uno_correct_stock(self):
        self._uno_check_stock_adjustment()
        warehouse = self.uno_saved_reorder_warehouse_id or self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not warehouse:
            raise UserError(_('Configura un almacén para tu empresa.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Corregir stock'),
            'res_model': 'uno360x.stock.adjustment.wizard',
            'views': [(self.env.ref('uno360x_quote_ui.stock_adjustment_wizard_form').id, 'form')],
            'target': 'new',
            'context': {'default_product_tmpl_id': self.id, 'default_warehouse_id': warehouse.id},
        }


class StockAdjustmentWizard(models.TransientModel):
    _name = 'uno360x.stock.adjustment.wizard'
    _description = 'Corregir stock desde el producto'

    product_tmpl_id = fields.Many2one('product.template', string='Producto', required=True, readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', required=True)
    before_qty = fields.Float(string='Stock registrado', readonly=True, digits='Product Unit of Measure')
    counted_qty = fields.Float(string='Cantidad contada', required=True, digits='Product Unit of Measure')
    delta_qty = fields.Float(string='Ajuste', compute='_compute_delta', digits='Product Unit of Measure')
    reason = fields.Text(string='Motivo', required=True)

    def _stock_scope(self):
        self.ensure_one()
        self.product_tmpl_id._uno_check_stock_adjustment()
        warehouse = self.warehouse_id
        warehouse.check_access('read')
        if (not warehouse or warehouse.company_id != self.env.company
                or self.company_id != self.env.company):
            raise AccessError(_('Selecciona un almacén de la empresa activa.'))
        return self.product_tmpl_id.product_variant_id, warehouse.lot_stock_id

    @api.onchange('warehouse_id', 'product_tmpl_id')
    def _onchange_warehouse(self):
        if self.warehouse_id and self.product_tmpl_id:
            product, location = self._stock_scope()
            quants = self._stock_quants(product, location)
            self.before_qty = sum(quants.mapped('quantity'))
            self.counted_qty = self.before_qty

    @api.depends('counted_qty', 'before_qty')
    def _compute_delta(self):
        for wizard in self:
            wizard.delta_qty = wizard.counted_qty - wizard.before_qty

    def _stock_quants(self, product, location):
        return self.env['stock.quant'].search([
            ('product_id', '=', product.id), ('location_id', 'child_of', location.id),
            ('company_id', '=', self.env.company.id),
        ])

    def action_apply(self):
        self.ensure_one()
        self.check_access('read')
        product, location = self._stock_scope()
        reason = (self.reason or '').strip()
        if not reason or len(reason) > 500:
            raise UserError(_('Escribe un motivo de hasta 500 caracteres.'))
        if not math.isfinite(self.counted_qty) or self.counted_qty < 0:
            raise UserError(_('La cantidad contada debe ser cero o mayor.'))
        rounding = product.uom_id.rounding
        counted = float_round(self.counted_qty, precision_rounding=rounding)
        if not math.isclose(counted, self.counted_qty, abs_tol=min(rounding / 1000, 0.000001)):
            raise UserError(_('Usa una cantidad válida para la unidad de medida del producto.'))

        # Serialize even the first adjustment, when the product has no stock row yet.
        self.env.cr.execute('SELECT id FROM product_product WHERE id = %s FOR UPDATE', [product.id])
        # Write the product row in this transaction so a concurrent adjustment opened
        # with an older snapshot must restart before seeing a first-created quant.
        self.env.cr.execute('UPDATE product_product SET write_date = write_date WHERE id = %s', [product.id])

        quants = self._stock_quants(product, location)
        # Native operations can update these rows too. PostgreSQL retries conflicts.
        if quants:
            self.env.cr.execute(
                'SELECT id FROM stock_quant WHERE id IN %s ORDER BY id FOR UPDATE',
                [tuple(quants.ids)],
            )
            quants.invalidate_recordset(['quantity', 'inventory_quantity_set'])


        direct = quants.filtered(lambda q: q.location_id == location and not (q.lot_id or q.package_id or q.owner_id))
        if len(direct) > 1 or (quants - direct).filtered(
            lambda q: not fields.Float.is_zero(q.quantity, precision_rounding=rounding)
        ):
            raise UserError(_('Usa Ajustes de inventario para indicar la ubicación, paquete o propietario.'))
        if direct.inventory_quantity_set:
            raise UserError(_('Este producto ya tiene un conteo pendiente. Revisa Ajustes de inventario.'))
        current = direct.quantity or 0.0
        if float_compare(current, self.before_qty, precision_rounding=rounding) != 0:
            raise UserError(_('El stock cambió. Cierra esta ventana, vuelve a abrirla y revisa el conteo.'))
        if float_compare(current, counted, precision_rounding=rounding) == 0:
            raise UserError(_('La cantidad contada coincide con el stock registrado.'))
        inventory_context = dict(
            inventory_mode=True, inventory_name=_('Corrección de stock UNO360X: %s', reason),
            set_inventory_quantity_auto_apply=False,
        )
        if direct:
            quant = direct.with_context(**inventory_context)
            quant.write({'inventory_quantity': counted})
        else:
            quant = self.env['stock.quant'].with_context(**inventory_context).create({
                'product_id': product.id, 'location_id': location.id,
                'inventory_quantity': counted,
            })
        if quant.action_apply_inventory():
            raise UserError(_('Revisa el conteo desde Ajustes de inventario.'))
        self.env['uno360x.stock.adjustment'].sudo().create({
            'product_tmpl_id': self.product_tmpl_id.id, 'warehouse_id': self.warehouse_id.id,
            'company_id': self.env.company.id, 'user_id': self.env.uid,
            'adjusted_at': fields.Datetime.now(), 'before_qty': current, 'after_qty': counted,
            'delta_qty': float_round(counted - current, precision_rounding=rounding), 'reason': reason,
        })
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Ajuste registrado'), 'message': _('El stock del almacén se actualizó.'),
                'type': 'success', 'next': {'type': 'ir.actions.act_window_close'},
            },
        }
