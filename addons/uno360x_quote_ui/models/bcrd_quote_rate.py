import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError

CACHE = Path('/run/uno360x/bcrd-rates/usd.json')
_INTERNAL = object()
TIMEZONE = ZoneInfo('America/Santo_Domingo')


def official_rate(day=None):
    try:
        rates = json.loads(CACHE.read_text())
    except FileNotFoundError:
        return None
    day = str(day or datetime.now(TIMEZONE).date())
    eligible = [key for key in rates if key <= day]
    if not eligible:
        return None
    published = max(eligible)
    return published, Decimal(rates[published])


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _uno360x_quote_rate(self):
        self.ensure_one()
        if (self.state not in ('draft', 'sent') or self.company_id.currency_id.name != 'DOP'
                or self.currency_id.name != 'USD'):
            return None
        order_date = self._get_order_date()
        if order_date:
            order_date = fields.Datetime.context_timestamp(self.with_context(tz=TIMEZONE.key), order_date).date()
        rate = official_rate(order_date)
        if rate:
            return float(rate[1])
        # Allow existing quotes dated before the first available official rate.
        if CACHE.exists() and not order_date:
            raise UserError('La tasa oficial USD/DOP todavía no está disponible.')
        return None

    def _get_pricelist_price(self):
        line = self.with_context(uno360x_quote_bcrd=(_INTERNAL, self._uno360x_quote_rate()))
        return super(SaleOrderLine, line)._get_pricelist_price()

    def _get_pricelist_price_before_discount(self):
        line = self.with_context(uno360x_quote_bcrd=(_INTERNAL, self._uno360x_quote_rate()))
        return super(SaleOrderLine, line)._get_pricelist_price_before_discount()


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _get_conversion_rate(self, from_currency, to_currency, company=None, date=None):
        context_rate = self.env.context.get('uno360x_quote_bcrd')
        rate = context_rate[1] if isinstance(context_rate, tuple) and len(context_rate) == 2 and context_rate[0] is _INTERNAL else None
        if rate and from_currency.name == 'DOP' and to_currency.name == 'USD':
            return 1 / rate
        if rate and from_currency.name == 'USD' and to_currency.name == 'DOP':
            return rate
        return super()._get_conversion_rate(from_currency, to_currency, company, date)
