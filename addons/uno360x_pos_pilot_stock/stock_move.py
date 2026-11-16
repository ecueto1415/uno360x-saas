import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    pos_pilot_reference = fields.Char(copy=False, index=True)
    _sql_constraints = [
        ('pos_pilot_reference_unique', 'unique(company_id,pos_pilot_reference)',
         'Este consumo de POS ya fue registrado.'),
    ]

    @api.model
    def uno360x_pos_consume(self, reference, product_id, source_id, destination_id, quantity):
        if not self.env.cr.dbname.startswith('uno360x_pos_lab'):
            raise AccessError('El conector POS solo opera en una base de laboratorio.')
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError('Se requiere el usuario técnico de inventario de pruebas.')
        if not re.fullmatch(r'[a-f0-9-]{36}:[a-z][a-z0-9_]{0,39}', reference or ''):
            raise UserError('Referencia de consumo inválida.')
        if type(quantity) not in (int, float) or not 0 < quantity <= 100000:
            raise UserError('Cantidad de consumo inválida.')
        company = self.env.company
        product = self.env['product.product'].browse(int(product_id)).exists()
        source, destination = (self.env['stock.location'].browse(int(value)).exists()
                               for value in (source_id, destination_id))
        if (not product or not product.is_storable or product.company_id not in (self.env['res.company'], company)
                or not source or source.company_id != company or source.usage != 'internal'
                or not destination or destination.company_id != company or destination.usage != 'inventory'):
            raise UserError('Producto o ubicaciones fuera del inventario de pruebas.')
        self.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))',
                            [str(company.id), reference])
        move = self.search([('company_id', '=', company.id), ('pos_pilot_reference', '=', reference)], limit=1)
        if move:
            if (move.product_id != product or move.location_id != source or
                    move.location_dest_id != destination or move.product_uom_qty != quantity or move.state != 'done'):
                raise UserError('El movimiento existente no coincide con el consumo del POS.')
        else:
            move = self.create({
                'name': 'Consumo restaurante ' + reference, 'pos_pilot_reference': reference,
                'company_id': company.id, 'product_id': product.id,
                'product_uom': product.uom_id.id, 'product_uom_qty': quantity,
                'location_id': source.id, 'location_dest_id': destination.id,
            })
            move._action_confirm(merge=False)
            move.quantity = quantity
            move.picked = True
            move._action_done()
        return {'id': move.id, 'state': move.state}
