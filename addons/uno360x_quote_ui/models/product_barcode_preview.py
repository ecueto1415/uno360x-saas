import base64
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    uno_barcode_preview = fields.Binary(
        string='Vista previa del código de barras',
        compute='_compute_uno_barcode_preview',
    )

    @api.depends('barcode')
    def _compute_uno_barcode_preview(self):
        report = self.env['ir.actions.report']
        for product in self:
            product.uno_barcode_preview = False
            if not product.barcode:
                continue
            try:
                png = report.barcode('auto', product.barcode, width=540, height=92, quiet=1)
            except ValueError:
                _logger.info('Preview unavailable for product template %s', product.id)
                continue
            product.uno_barcode_preview = base64.b64encode(png)
