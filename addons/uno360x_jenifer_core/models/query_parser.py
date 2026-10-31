"""Deterministic intent routing; no AI and no record writes."""
import re
import unicodedata


def parse_query(text):
    normalized = ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if unicodedata.category(c) != 'Mn')
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if normalized in ('ayuda jenifer', '/jenifer', 'comandos jenifer'):
        return ('help', '')
    kind = None
    if re.search(r'\bcxc\b|cuentas? por cobrar|facturas? (?:de clientes? )?vencidas?', normalized):
        kind = 'receivable'
    if re.search(r'\bcxp\b|cuentas? por pagar|facturas? (?:de )?(?:proveedores?|suplidores?)', normalized):
        kind = 'payable'
    if re.search(r'cotizaciones? pendientes?|presupuestos? pendientes?', normalized):
        kind = 'quotes'
    if kind is None:
        return None
    # Writes must never be misinterpreted as requests for a read-only report.
    write_text = re.sub(r'cuentas? por pagar', 'cxp', normalized)
    if re.search(r'\b(envia|enviar|manda|mandar|paga|pagar|borra|borrar|elimina|eliminar|cambia|cambiar|modifica|modificar|descuento|aprueba|aprobar|confirma|confirmar)\b', write_text):
        return ('readonly', '')
    # A colon makes optional partner filtering explicit and unambiguous.
    partner = text.split(':', 1)[1].strip() if ':' in text else ''
    return (kind, partner[:160])
