from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import html2plaintext

from .query_parser import parse_query


HELP = '''Consultas de solo lectura: CxC, CxP y Cotizaciones pendientes. Puedes filtrar con dos puntos y un nombre. Se respetan tus permisos y empresas. No se envían mensajes, no se registran pagos y no se llama a una IA externa.'''


class JeniferQuery(models.AbstractModel):
    _name = 'uno360x.jenifer.query'
    _description = 'Consultas de Jenifer con permisos del solicitante'

    @api.model
    def _respond(self, text):
        intent = parse_query(text)
        if not intent:
            return None
        kind, partner = intent
        if kind == 'help':
            return HELP
        if kind == 'readonly':
            return 'Esta consulta solo permite lectura. No he enviado correos ni modificado registros.\n\n' + HELP
        try:
            return self._quotes(partner) if kind == 'quotes' else self._invoices(kind, partner)
        except AccessError:
            return 'Tu usuario no tiene permiso para consultar esos datos. No he ampliado tus accesos.'

    @api.model
    def _partner_domain(self, model, partner):
        if not partner:
            return []
        matches = self.env['res.partner'].search([('name', 'ilike', partner)], limit=101)
        if len(matches) > 100:
            return None
        roots = matches.mapped('commercial_partner_id').ids
        return [('partner_id', 'child_of', roots)] if roots else [('id', '=', 0)]

    @api.model
    def _invoices(self, kind, partner):
        model = self.env['account.move.line']
        model.check_access('read')
        self.env['account.move'].check_access('read')
        today = fields.Date.context_today(self)
        domain = [
            ('company_id', 'in', self.env.companies.ids),
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', '=', 'out_invoice' if kind == 'receivable' else 'in_invoice'),
            ('account_id.account_type', '=', 'asset_receivable' if kind == 'receivable' else 'liability_payable'),
            ('reconciled', '=', False),
            ('amount_residual', '>' if kind == 'receivable' else '<', 0),
            ('date_maturity', '<', today),
        ]
        pd = self._partner_domain(model, partner)
        if pd is None:
            return 'El nombre coincide con demasiados contactos; escribe un nombre más específico después de los dos puntos.'
        records = model.search(domain + pd, order='date_maturity, id')
        invoices = {}
        totals = defaultdict(float)
        for line in records:
            line.move_id.check_access('read')
            currency = line.currency_id or line.company_id.currency_id
            amount = abs(line.amount_residual_currency) if line.currency_id else abs(line.amount_residual)
            key = (line.move_id.id, currency.id)
            if key not in invoices:
                invoices[key] = [line.move_id, currency, line.date_maturity, 0.0]
            invoices[key][3] += amount
            totals[(line.company_id.name, currency.name)] += amount
        heading = 'CUENTAS POR COBRAR VENCIDAS' if kind == 'receivable' else 'CUENTAS POR PAGAR VENCIDAS'
        lines = [heading, 'Fecha de consulta: %s | Facturas: %s' % (today, len(invoices))]
        for record, currency, due, amount in list(invoices.values())[:80]:
            lines.append('%s | %s | %s | vencimiento más antiguo %s | %s días | saldo vencido %s %s' % (
                record.company_id.name, record.partner_id.display_name, record.name,
                due, (today - due).days, currency.name, format(amount, ',.2f'),
            ))
        for (company, currency), total in sorted(totals.items()):
            lines.append('TOTAL %s | %s %s' % (company, currency, format(total, ',.2f')))
        if len(invoices) > 80:
            lines.append('Se muestran 80 facturas; los totales incluyen todas las coincidencias accesibles. Filtra por cliente/proveedor para ver más detalle.')
        if not invoices:
            lines.append('Sin facturas vencidas con saldo dentro de tus permisos y del filtro indicado.')
        lines.append('Solo cuotas vencidas de facturas; no compensa notas de crédito ni anticipos. No se enviaron mensajes ni se registraron pagos.')
        return '\n'.join(lines)

    @api.model
    def _quotes(self, partner):
        model = self.env['sale.order']
        model.check_access('read')
        pd = self._partner_domain(model, partner)
        if pd is None:
            return 'Especifica mejor el nombre del cliente después de los dos puntos.'
        records = model.search([
            ('company_id', 'in', self.env.companies.ids),
            ('state', 'in', ['draft', 'sent']),
        ] + pd, order='date_order, id')
        today = fields.Date.context_today(self)
        lines = ['COTIZACIONES PENDIENTES', 'Fecha: %s | Coincidencias: %s' % (today, len(records))]
        for record in records[:80]:
            date = fields.Date.to_date(record.date_order)
            age = max(0, (today - date).days) if date else 0
            lines.append('%s | %s | %s | %s %s | %s días | %s' % (
                record.name, record.partner_id.display_name, record.company_id.name,
                record.currency_id.name, format(record.amount_total, ',.2f'), age,
                'revisar seguimiento (16 días o más)' if age >= 16 else 'menos de 16 días',
            ))
        if len(records) > 80:
            lines.append('Se muestran las 80 más antiguas. Filtra por cliente para acotar.')
        if not records:
            lines.append('No hay cotizaciones pendientes accesibles para el filtro indicado.')
        lines.append('Incluye borradores y enviadas; antigüedad desde la fecha de cotización. No acredita ausencia de respuesta del cliente. No se enviaron correos ni se cambiaron precios.')
        return '\n'.join(lines)
