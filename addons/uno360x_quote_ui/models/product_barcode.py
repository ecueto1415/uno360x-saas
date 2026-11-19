from odoo import _, models
from odoo.exceptions import UserError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_uno360x_convert_barcode(self):
        self.ensure_one()
        self.check_access("write")
        variant = self.product_variant_ids
        if self.type in ("service", "combo") or len(variant) != 1:
            raise UserError(_("Choose a physical product with a single variant."))
        variant.check_access("write")
        if variant.barcode:
            raise UserError(_("This product already has a barcode."))
        reference = (variant.default_code or "").strip()
        if reference:
            if not reference.isascii() or not reference.isprintable():
                raise UserError(_("Use printable ASCII characters in the internal reference."))
            variant.write({"barcode": reference})
        else:
            reference = f"PROD-{variant.id:04d}"
            other_products = variant.with_context(active_test=False)
            suffix = 0
            candidate = reference
            while other_products.search_count([
                ("id", "!=", variant.id),
                "|", ("default_code", "=", candidate), ("barcode", "=", candidate),
            ], limit=1):
                suffix += 1
                candidate = f"{reference}-{suffix}"
            variant.write({"default_code": candidate, "barcode": candidate})
        return {"type": "ir.actions.client", "tag": "reload"}
