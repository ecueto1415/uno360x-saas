from odoo import api, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def _create_picking_from_pos_order_lines(self, location_dest_id, lines, picking_type, partner=False):
        user = self.env.user
        scoped_cashier = (user.has_group('uno360x_business_base.group_scoped_employee')
                          and user.has_group('uno360x_business_base.group_area_pos')
                          and not user.has_group('uno360x_business_base.group_area_inventory'))
        if not self.env.su and scoped_cashier:
            # POS links transfers to the session after it creates them.
            lines.check_access('read')
            return super(StockPicking, self.sudo())._create_picking_from_pos_order_lines(
                location_dest_id, lines, picking_type, partner)
        return super()._create_picking_from_pos_order_lines(location_dest_id, lines, picking_type, partner)
