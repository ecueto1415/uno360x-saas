from odoo import fields, models
from odoo.exceptions import AccessError


DOCUMENT_LAYOUTS = [
    ('standard', 'Clásica'),
    ('boxed', 'Enmarcada'),
    ('bold', 'Moderna'),
    ('striped', 'Con franjas'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    uno360x_signature_stamp = fields.Image(
        string='Firma y sello', max_width=1600, max_height=800,
        attachment=True, copy=False,
        help='Imagen visual de la empresa para cotizaciones y facturas.',
    )

    uno360x_document_layout = fields.Selection(
        DOCUMENT_LAYOUTS, string='Plantilla para cotizaciones y facturas', default='bold',
    )

    def write(self, values):
        if 'uno360x_signature_stamp' in values and not self.env.su:
            user = self.env.user
            administrator = user.has_group('base.group_system') or all(
                user.has_group(group) for group in (
                    'sales_team.group_sale_manager',
                    'account.group_account_manager', 'stock.group_stock_manager',
                )
            )
            if not administrator or any(company not in self.env.companies for company in self):
                raise AccessError('Solo el administrador de la empresa puede cambiar Firma y sello.')
        return super().write(values)

    def _uno360x_document_layout_key(self):
        self.ensure_one()
        layout = self.uno360x_document_layout
        if layout in dict(DOCUMENT_LAYOUTS):
            return f'web.external_layout_{layout}'
        return False
