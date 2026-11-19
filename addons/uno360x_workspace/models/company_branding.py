from odoo import fields, models


DOCUMENT_LAYOUTS = [
    ('standard', 'Clásica'),
    ('boxed', 'Enmarcada'),
    ('bold', 'Moderna'),
    ('striped', 'Con franjas'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    uno360x_document_layout = fields.Selection(
        DOCUMENT_LAYOUTS, string='Plantilla para cotizaciones y facturas', default='bold',
    )

    def _uno360x_document_layout_key(self):
        self.ensure_one()
        layout = self.uno360x_document_layout
        if layout in dict(DOCUMENT_LAYOUTS):
            return f'web.external_layout_{layout}'
        return False
