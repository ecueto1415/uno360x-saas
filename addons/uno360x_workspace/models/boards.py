from datetime import timedelta
from urllib.parse import urlencode

from odoo import api, models
from odoo.tools.misc import format_amount


class WorkspaceBoards(models.AbstractModel):
    _inherit = 'uno360x.workspace'

    @api.model
    def _board_values(self, ctx, requested, detail):
        first, end, today = ctx['month_start'], ctx['month_end'], ctx['today']
        month = first.strftime('%Y-%m')
        company = [('company_id', '=', self.env.company.id)]
        money = lambda value: format_amount(self.env, value, self.env.company.currency_id)
        options = ctx['options']
        scopes = {
            'sales': self._can_read('sale.order'),
            'finance': self._can_read('account.move'),
            'stock': self._work_area_allowed('inventory') and self._can_read('stock.picking'),
            'projects': 'projects_services' in options and self._can_read('project.project'),
        }
        titles = {'general': 'General', 'sales': 'Ventas', 'finance': 'Finanzas', 'operations': 'Operaciones'}
        available = {
            'general': True, 'sales': scopes['sales'], 'finance': scopes['finance'],
            'operations': scopes['stock'] or scopes['projects'],
        }
        board = requested if available.get(requested) else 'general'

        def url(tab, item=None):
            params = {'selection': tab, 'period': month}
            if item:
                params['detail'] = item
            return '/uno360x/area/reports?' + urlencode(params)

        invoices = [('state', '=', 'posted')]
        receivable = invoices + [('move_type', '=', 'out_invoice'), ('amount_residual', '>', 0)]
        payable = invoices + [('move_type', '=', 'in_invoice'), ('amount_residual', '>', 0)]
        receipts = [('picking_type_code', '=', 'incoming')]
        project = [('active', '=', True)]
        datasets = {
            'net': ('Facturación neta', 'finance', 'account.move', invoices + [
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('invoice_date', '>=', first), ('invoice_date', '<', end)
            ], 'amount_total_signed', 1),
            'receivable': ('Por cobrar', 'finance', 'account.move', receivable, 'amount_residual_signed', 1),
            'payable': ('Por pagar', 'finance', 'account.move', payable, 'amount_residual_signed', -1),
            'overdue': ('Facturas de clientes vencidas', 'finance', 'account.move',
                        receivable + [('invoice_date_due', '<', today)], None, 1),
            'overdue_vendor': ('Facturas de proveedores vencidas', 'finance', 'account.move',
                               payable + [('invoice_date_due', '<', today)], None, 1),
            'collections': ('Cobros registrados', 'finance', 'account.payment', [
                ('partner_type', '=', 'customer'), ('payment_type', '=', 'inbound'),
                ('state', 'in', ['paid', 'in_process']), ('date', '>=', first), ('date', '<', end)
            ], 'amount_company_currency_signed', 1),
            'quotes': ('Cotizaciones abiertas', 'sales', 'sale.order', [('state', 'in', ['draft', 'sent'])], None, 1),
            'confirmed': ('Pedidos confirmados', 'sales', 'sale.order', [
                ('state', '=', 'sale'), ('date_order', '>=', first), ('date_order', '<', end)
            ], None, 1),
            'to_invoice': ('Pedidos por facturar', 'sales', 'sale.order', [('invoice_status', '=', 'to invoice')], None, 1),
            'expiring': ('Cotizaciones por vencer', 'sales', 'sale.order', [
                ('state', 'in', ['draft', 'sent']), ('validity_date', '>=', today),
                ('validity_date', '<', today + timedelta(days=8))
            ], None, 1),
            'receipts': ('Recepciones pendientes', 'stock', 'stock.picking',
                         receipts + [('state', 'not in', ['done', 'cancel'])], None, 1),
            'received': ('Recepciones completadas', 'stock', 'stock.picking',
                         receipts + [('state', '=', 'done'), ('date_done', '>=', first), ('date_done', '<', end)], None, 1),
            'projects': ('Proyectos activos', 'projects', 'project.project', project, None, 1),
        }
        metric_keys = {
            'general': ('net', 'receivable', 'to_invoice'),
            'sales': ('quotes', 'confirmed', 'to_invoice'),
            'finance': ('receivable', 'payable', 'collections'),
            'operations': ('receipts', 'low_stock', 'projects'),
        }
        attention_keys = {
            'general': ('overdue', 'to_invoice', 'low_stock'),
            'sales': ('expiring', 'to_invoice'),
            'finance': ('overdue', 'overdue_vendor'),
            'operations': ('receipts', 'low_stock'),
        }
        keys = set(metric_keys[board] + attention_keys[board])
        stock_rows = []
        if 'low_stock' in keys and scopes['stock'] and all(
            self._can_read(name) for name in ('stock.warehouse.orderpoint', 'stock.move', 'stock.warehouse', 'product.product')
        ):
            rules = self.env['stock.warehouse.orderpoint'].search(company + [('active', '=', True)])
            products = self.env['product.product'].search([('id', 'in', rules.product_id.ids)])
            stock = self._inventory_replenishment_summary(products, all_locations=True)
            stock_rows = [item for item in stock.values() if item['low']]
        else:
            keys.discard('low_stock')

        def dataset(key):
            label, scope, model_name, domain, field, sign = datasets[key]
            if not scopes[scope] or not self._can_read(model_name):
                return None
            return label, self.env[model_name], company + domain, field, sign

        def aggregate(model, domain, field, sign):
            if field is None:
                return model.search_count(domain)
            return (model.read_group(domain, [field + ':sum'], [])[0].get(field) or 0) * sign

        cards = {}
        for key in keys:
            if key == 'low_stock':
                cards[key] = dict(label='Productos con stock bajo', value=len({row['rule'].product_id.id for row in stock_rows}), href=url(board, key))
                continue
            data = dataset(key)
            if data:
                label, model, domain, field, sign = data
                value = aggregate(model, domain, field, sign)
                cards[key] = dict(label=label, value=money(value) if field else value, href=url(board, key))
        chart = {'general': ('net', 'invoice_date', 'Facturación neta por semana'),
                 'sales': ('confirmed', 'date_order', 'Pedidos confirmados por semana'),
                 'finance': ('collections', 'date', 'Cobros por semana'),
                 'operations': ('received', 'date_done', 'Recepciones por semana')}[board]
        chart_key, date_field, chart_title = chart
        data = dataset(chart_key)
        bars = []
        if data:
            _, model, domain, field, sign = data
            start = first
            while start < end:
                stop = min(start + timedelta(days=7), end)
                value = aggregate(model, domain + [(date_field, '>=', start), (date_field, '<', stop)], field, sign)
                bars.append(dict(label=f'{start.day}–{(stop - timedelta(days=1)).day}', value=value, display=money(value) if field else value))
                start = stop
            maximum = max([abs(bar['value']) for bar in bars] + [1])
            for bar in bars:
                bar['width'] = 100 * abs(bar['value']) / maximum

        selected = cards.get(detail)
        details = []
        detail_total = 0
        if selected:
            if detail == 'low_stock':
                names = [record.display_name for record in self.env['product.product'].browse(sorted({item['rule'].product_id.id for item in stock_rows}))]
                detail_total = len(names)
                details = names[:30]
            else:
                _, model, domain, _, _ = dataset(detail)
                detail_total = model.search_count(domain)
                details = model.search(domain, limit=30, order='id desc').mapped('display_name')
        return dict(board_key=board, board_month=month, board_tabs=[
            dict(label=label, href=url(key), active=key == board)
            for key, label in titles.items() if available[key]
        ], board_metrics=[cards[k] for k in metric_keys[board] if k in cards],
            board_pending=[cards[k] for k in attention_keys[board] if k in cards],
            board_chart=bars, board_chart_title=chart_title, board_back=url(board),
            board_detail=selected, board_detail_rows=details, board_detail_total=detail_total)
