"""606 NG07-2018/05-2019. Official workbook reviewed 2026-11-19.

No Odoo dependency, no submission, no fiscal values inferred from missing data.
NC amounts are positive in the TXT; net totals apply their sign separately.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from stdnum.do import cedula, rnc

KEYS = ('supplier', 'id_type', 'expense', 'ncf', 'modified', 'issued', 'paid',
        'services', 'goods', 'total', 'vat', 'vat_withheld', 'proportional',
        'cost_vat', 'advance', 'vat_perceived', 'isr_type', 'isr_withheld',
        'isr_perceived', 'isc', 'other', 'tip', 'payment_form')
AMOUNTS = KEYS[7:16] + KEYS[17:22]
NCF = re.compile(r'(?:B(?:01|03|04|11|13|14|15|17)\d{8}|E(?:31|33|34|41|43|44|45|47)\d{10})\Z')
ORIGINAL = re.compile(r'(?:B\d{10}|E\d{12}|A\d{18})\Z')


def money(value):
    if value is None or value is False or value == '':
        raise ValueError('Monto pendiente de revisión')
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number >= Decimal('100000000000'):
            raise ValueError('Monto fuera de rango')
        return number.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError('Monto inválido') from None


def tax_id(value):
    return re.sub(r'[ -]', '', str(value or ''))


def valid_id(value):
    return bool(re.fullmatch(r'\d{9}', value) and rnc.is_valid(value) or
                re.fullmatch(r'\d{11}', value) and cedula.is_valid(value))


def fiscal_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), '%Y-%m-%d').date()


def build(issuer, period, entries, today=None):
    today = today or date.today()
    errors, rows, seen = [], [], {}
    entries = list(entries)
    originals = {(tax_id(e.get('supplier')), str(e.get('ncf') or '').strip().upper()) for e in entries}
    issuer = tax_id(issuer)
    if not valid_id(issuer):
        errors.append({'source': 'Empresa', 'field': 'RNC', 'message': 'RNC/cédula inválido.'})
    try:
        start = datetime.strptime(period + '01', '%Y%m%d').date()
        assert len(period) == 6 and start >= date(2018, 5, 1) and start.replace(day=1) <= today.replace(day=1)
    except (ValueError, TypeError, AssertionError):
        return {'rows': [], 'errors': errors + [{'source': 'Período', 'field': 'Mes/año', 'message': 'Período inválido; se admite desde mayo de 2018 hasta el mes actual.'}], 'totals': {}}
    totals = {key: Decimal('0.00') for key in ('total', 'vat', 'vat_withheld', 'isr_withheld')}
    for entry in entries:
        data = dict(entry)
        source = str(data.get('source') or data.get('move_id') or 'Factura')
        def error(field, message):
            errors.append({'source': source, 'move_id': data.get('move_id'), 'field': field, 'message': message})
        for problem in data.get('errors', []):
            error(problem[0], problem[1])
        data['supplier'] = tax_id(data.get('supplier'))
        if not valid_id(data['supplier']): error('RNC proveedor', 'Completa un RNC o cédula válido.')
        data['id_type'] = '1' if len(data['supplier']) == 9 else '2'
        if data.get('expense') not in {f'{n:02}' for n in range(1, 12)}: error('Tipo de gasto', 'Selecciona la clasificación fiscal; no se asigna por defecto.')
        number = str(data.get('ncf') or '').strip().upper()
        data['ncf'] = number
        if not NCF.fullmatch(number): error('NCF/e-NCF', 'Comprobante de compras B/E inválido o de tipo no admitido.')
        elif not int(number[3:]): error('NCF/e-NCF', 'La secuencia no puede ser cero.')
        credit = number.startswith(('B04', 'E34'))
        debit = number.startswith(('B03', 'E33'))
        modified = str(data.get('modified') or '').strip().upper()
        data['modified'] = modified
        if credit or debit:
            if not ORIGINAL.fullmatch(modified) or modified == number:
                error('NCF modificado', 'Indica el comprobante original afectado por la nota.')
            if (data['supplier'], modified) not in originals and not data.get('original_reported'):
                error('NCF original reportado', 'Confirma que el original fue reportado previamente o inclúyelo en el período correspondiente.')
        elif modified: error('NCF modificado', 'Solo corresponde a una nota de crédito/débito.')
        if bool(data.get('credit')) != credit: error('Tipo de documento', 'La nota de crédito contable y el NCF no coinciden.')
        key = (data['supplier'], number)
        if key in seen:
            error('NCF duplicado', 'Duplicado con ' + seen[key])
        seen[key] = source
        try:
            issued = fiscal_date(data.get('issued'))
            if issued > today: error('Fecha comprobante', 'No puede ser futura.')
            data['issued'] = issued.strftime('%Y%m%d')
        except (ValueError, TypeError):
            issued = None; error('Fecha comprobante', 'Falta una fecha válida.'); data['issued'] = ''
        try:
            paid = fiscal_date(data['paid']) if data.get('paid') else None
            if paid and (paid > today or issued and paid < issued): error('Fecha pago', 'Fecha futura o anterior al comprobante.')
            data['paid'] = paid.strftime('%Y%m%d') if paid else ''
        except (ValueError, TypeError):
            paid = None; error('Fecha pago', 'Fecha inválida.'); data['paid'] = ''
        for key in AMOUNTS:
            try: data[key] = money(data.get(key))
            except ValueError as exc: error(key, str(exc)); data[key] = Decimal('0.00')
        if data['services'] + data['goods'] != data['total']: error('Bienes/servicios', 'La suma debe coincidir con el monto facturado sin impuestos.')
        if data['cost_vat'] > data['vat'] or data['advance'] != data['vat'] - data['cost_vat']: error('ITBIS al costo/adelanto', 'El adelanto debe ser ITBIS facturado menos ITBIS llevado al costo.')
        if data['proportional'] > data['vat']: error('ITBIS proporcional', 'No puede superar el ITBIS facturado.')
        if data['vat_withheld'] > data['vat']: error('ITBIS retenido', 'No puede superar el facturado.')
        if data['vat_perceived'] or data['isr_perceived']: error('Impuestos percibidos', 'Campos no habilitados en el instructivo vigente; revisar normativa antes de reportarlos.')
        if data['isr_withheld'] and data.get('isr_type') not in {f'{n:02}' for n in range(1, 10)}: error('Tipo retención ISR', 'Indica el tipo de retención ISR.')
        if data.get('isr_type') and not data['isr_withheld']: error('Tipo retención ISR', 'Indica el monto retenido o elimina el tipo.')
        retention = data['vat_withheld'] or data['isr_withheld']
        if retention and not paid: error('Fecha pago', 'Obligatoria para retenciones efectivamente pagadas.')
        if issued and issued.strftime('%Y%m') != period:
            if not (paid and paid.strftime('%Y%m') == period and retention and issued.strftime('%Y%m') < period):
                error('Período', 'Un comprobante anterior solo se repite por retenciones pagadas en este período.')
        if paid and paid.strftime('%Y%m') != period: error('Fecha pago', 'El pago reportado debe pertenecer al período seleccionado.')
        if data.get('payment_form') not in {f'{n:02}' for n in range(1, 8)}: error('Forma de pago', 'Completa la forma de pago fiscal.')
        if credit and data.get('payment_form') != '06': error('Forma de pago', 'Una nota de crédito utiliza 06.')
        if number.startswith(('B13', 'E43')) and data['supplier'] != issuer:
            error('RNC gastos menores', 'Debe ser el RNC de la empresa que reporta.')
        if number.startswith(('B17', 'E47')):
            if data['supplier'] != issuer: error('RNC pagos al exterior', 'Debe ser el RNC del encabezado.')
            if any(data[k] for k in ('vat_withheld','proportional','cost_vat','isr_perceived','isc','other','tip')): error('Pagos al exterior', 'Contiene importes en campos no aplicables.')
        if not data.get('reviewed'): error('Revisión fiscal', 'Contabilidad debe revisar y marcar los datos fiscales del comprobante.')
        for key in AMOUNTS: data[key] = f'{data[key]:.2f}'
        data['isr_type'] = data.get('isr_type') or ''
        data['retention_only'] = bool(issued and issued.strftime('%Y%m') < period)
        for key in totals:
            if data['retention_only'] and key in ('total','vat'): continue
            totals[key] += Decimal(data[key]) * (-1 if credit else 1)
        rows.append(data)
    if len(rows) > 10000: errors.append({'source': 'Reporte', 'field': 'Registros', 'message': 'Supera los 10,000 registros; requiere tratamiento por contabilidad.'})
    if not rows: errors.append({'source': 'Reporte', 'field': 'Registros', 'message': 'Sin operaciones: revisar declaración informativa en cero en la Oficina Virtual.'})
    return {'rows': rows, 'errors': errors, 'totals': {k: str(v) for k,v in totals.items()}, 'issuer': issuer, 'period': period}


def export_txt(result):
    if result['errors']:
        raise ValueError('Corrige los errores fiscales antes de exportar.')
    lines = ['606|%s|%s|%s' % (result['issuer'], result['period'], len(result['rows']))]
    lines.extend('|'.join(str(row.get(key) or '') for key in KEYS) for row in result['rows'])
    return '\r\n'.join(lines).encode('ascii')
