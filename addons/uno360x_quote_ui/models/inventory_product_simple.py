import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    uno_initial_qty = fields.Float(store=False)
    uno_warehouse_id = fields.Many2one(
        'stock.warehouse', store=False,
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1),
    )
    uno_reorder = fields.Boolean(store=False)
    uno_min_qty = fields.Float(store=False)
    uno_target_qty = fields.Float(store=False)
    uno_generate_barcode = fields.Boolean(store=False)

    uno_saved_reorder = fields.Boolean(compute='_compute_uno_saved_reorder', readonly=False)
    uno_saved_min_qty = fields.Float(compute='_compute_uno_saved_reorder', readonly=False)
    uno_saved_target_qty = fields.Float(compute='_compute_uno_saved_reorder', readonly=False)
    uno_saved_reorder_warehouse_id = fields.Many2one('stock.warehouse', compute='_compute_uno_saved_reorder')
    uno_saved_reorder_multiple = fields.Boolean(compute='_compute_uno_saved_reorder')

    def _uno_current_reorder_rules(self):
        self.ensure_one()
        return self.env['stock.warehouse.orderpoint'].with_context(active_test=False).search([
            ('product_id', '=', self.product_variant_id.id),
            ('company_id', '=', self.env.company.id),
        ], order='active desc, id', limit=2)

    @api.depends('product_variant_id')
    @api.depends_context('company')
    def _compute_uno_saved_reorder(self):
        default_warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        for product in self:
            rules = product._uno_current_reorder_rules() if product.id and product.product_variant_id else self.env['stock.warehouse.orderpoint']
            rule = rules[:1]
            product.uno_saved_reorder = rule.active
            product.uno_saved_min_qty = rule.product_min_qty
            product.uno_saved_target_qty = rule.product_max_qty
            product.uno_saved_reorder_warehouse_id = rule.warehouse_id or default_warehouse
            product.uno_saved_reorder_multiple = len(rules) > 1

    def write(self, values):
        values = dict(values)
        fields_to_update = {
            'uno_saved_reorder': 'active',
            'uno_saved_min_qty': 'product_min_qty',
            'uno_saved_target_qty': 'product_max_qty',
        }
        rule_values = {target: values.pop(source) for source, target in fields_to_update.items() if source in values}
        result = super().write(values)
        if rule_values:
            for product in self:
                product._uno_update_saved_reorder(rule_values)
        return result

    def _uno_update_saved_reorder(self, changes):
        self.ensure_one()
        if not self.is_storable or self.product_variant_count != 1:
            raise UserError(_('Selecciona un producto almacenable con una sola variante.'))
        rules = self._uno_current_reorder_rules()
        if len(rules) > 1:
            raise UserError(_('Abre las reglas de reposición para editar el almacén correspondiente.'))
        minimum = changes.get('product_min_qty', rules.product_min_qty)
        maximum = changes.get('product_max_qty', rules.product_max_qty)
        if not all(map(math.isfinite, (minimum, maximum))) or not 0 <= minimum <= maximum:
            raise UserError(_('El stock objetivo debe ser igual o mayor al mínimo.'))
        if rules:
            rules.write(changes)
        elif changes.get('active'):
            warehouse = self.uno_saved_reorder_warehouse_id
            if not warehouse:
                raise UserError(_('Configura un almacén para tu empresa.'))
            self.env['stock.warehouse.orderpoint'].create({
                'product_id': self.product_variant_id.id,
                'warehouse_id': warehouse.id,
                'location_id': warehouse.lot_stock_id.id,
                'company_id': warehouse.company_id.id,
                'trigger': 'manual',
                'product_min_qty': minimum,
                'product_max_qty': maximum,
            })
        self.invalidate_recordset(['uno_saved_reorder', 'uno_saved_min_qty', 'uno_saved_target_qty',
                                   'uno_saved_reorder_warehouse_id', 'uno_saved_reorder_multiple'])

    @api.model_create_multi
    def create(self, vals_list):
        options = []
        product_values = []
        for original in vals_list:
            vals = dict(original)
            options.append((
                vals.pop('uno_initial_qty', 0), vals.pop('uno_warehouse_id', False),
                vals.pop('uno_reorder', False), vals.pop('uno_min_qty', 0),
                vals.pop('uno_target_qty', 0), vals.pop('uno_generate_barcode', False),
            ))
            product_values.append(vals)
        products = super().create(product_values)
        for product, (quantity, warehouse_id, reorder, minimum, target, barcode) in zip(products, options):
            if barcode and not product.barcode:
                product.action_uno360x_convert_barcode()
            if not quantity and not reorder:
                continue
            if not math.isfinite(quantity) or quantity < 0:
                raise UserError(_('La cantidad inicial debe ser cero o mayor.'))
            if reorder and (not all(map(math.isfinite, (minimum, target))) or not 0 <= minimum <= target):
                raise UserError(_('El stock objetivo debe ser igual o mayor al mínimo.'))
            warehouse = self.env['stock.warehouse'].browse(warehouse_id).exists()
            if not warehouse or warehouse.company_id != self.env.company:
                raise UserError(_('Selecciona un almacén de tu empresa.'))
            if not product.is_storable or len(product.product_variant_ids) != 1:
                raise UserError(_('Selecciona un producto almacenable con una sola variante.'))
            variant = product.product_variant_id
            if quantity:
                quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
                    'product_id': variant.id, 'location_id': warehouse.lot_stock_id.id,
                    'inventory_quantity': quantity,
                })
                if quant.action_apply_inventory():
                    raise UserError(_('Completa la existencia inicial desde Ajustes de inventario.'))
            if reorder:
                self.env['stock.warehouse.orderpoint'].create({
                    'product_id': variant.id, 'warehouse_id': warehouse.id,
                    'location_id': warehouse.lot_stock_id.id, 'company_id': warehouse.company_id.id,
                    'trigger': 'manual', 'product_min_qty': minimum, 'product_max_qty': target,
                })
        return products

    def action_uno_open_full_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.display_name, 'res_model': self._name,
            'res_id': self.id, 'views': [(self.env.ref('product.product_template_only_form_view').id, 'form')],
            'target': 'current',
        }
