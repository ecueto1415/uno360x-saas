"""Restricted e-CF preparation, no network or allocation.

Original DGII schemas are preserved. Preliminary validation excludes signature
nodes. Signed E45 uses the complete official schema. E31 uses a restricted
schema copy that excludes the optional IndicadorServicioTodoIncluido node,
because the official E31 file references its undefined type. Schema validation
is structural and never implies DGII acceptance or fiscal authorization.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
from lxml import etree

DEMO_ENCF = 'E310000000001'
SCHEMA_DIR = Path(__file__).resolve().parent / 'schemas'
SUPPORTED_TYPES = ('31', '32', '33', '34', '41', '43', '44', '45', '46', '47')

def schema_file(document_type):
    if str(document_type) not in SUPPORTED_TYPES:
        raise PreparationError('Tipo e-CF no implementado; no se genera ni transmite.')
    return SCHEMA_DIR / ('ecf%s.xsd' % document_type)
CENT = Decimal('0.01')


class PreparationError(ValueError):
    pass


def number(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise PreparationError('%s: nÃºmero invÃ¡lido.' % label) from None
    if not result.is_finite():
        raise PreparationError('%s: nÃºmero no finito.' % label)
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fixed(value):
    return format(money(value), '.2f')


def text(value, label, maximum):
    result = str(value or '').strip()
    if not result or len(result) > maximum:
        raise PreparationError('%s: requerido, mÃ¡ximo %s caracteres.' % (label, maximum))
    if any(ord(c) < 32 and c not in '\t\n\r' for c in result):
        raise PreparationError('%s: contiene caracteres XML invÃ¡lidos.' % label)
    return result


def rnc(value, label):
    # Only presentation separators are removed. No silent removal of letters.
    result = re.sub(r'[\s-]', '', str(value or ''))
    if not re.fullmatch(r'(?:[0-9]{9}|[0-9]{11})', result):
        raise PreparationError('%s: debe contener 9 u 11 dÃ­gitos.' % label)
    return result


def iso_date(value, label):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise PreparationError('%s: fecha ISO vÃ¡lida requerida.' % label) from None


def add(parent, tag, value):
    node = etree.SubElement(parent, tag)
    node.text = str(value)
    return node


def validate_preliminary(xml, document_type="31"):
    """Validate unsigned preliminary content, never a fiscally valid document."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    schema_tree = etree.parse(str(schema_file(document_type)), parser)
    namespace = {'xs': 'http://www.w3.org/2001/XMLSchema'}
    seq = schema_tree.xpath('/xs:schema/xs:element[@name="ECF"]/xs:complexType/xs:sequence', namespaces=namespace)[0]
    final = list(seq)[-2:]
    if final[0].get('name') != 'FechaHoraFirma' or final[1].tag != '{http://www.w3.org/2001/XMLSchema}any':
        raise PreparationError('El esquema oficial cambiÃ³; revisar el validador preliminar.')
    for node in final:
        seq.remove(node)
    # Known source defect: this optional node references an undefined type.
    # Do not invent a definition or claim full official validation.
    for node in schema_tree.xpath('//xs:element[@name="IndicadorServicioTodoIncluido"]', namespaces=namespace):
        if not schema_tree.xpath('//xs:simpleType[@name="IndicadorServicioTodoIncluidoType"] | //xs:complexType[@name="IndicadorServicioTodoIncluidoType"]', namespaces=namespace):
            node.getparent().remove(node)
    schema = etree.XMLSchema(schema_tree)
    root = etree.fromstring(xml, parser)
    if not schema.validate(root):
        error = schema.error_log.last_error
        raise PreparationError('Estructura preliminar invÃ¡lida: %s' % error.message)


def build_preview(data):
    """Build a DOP preview with explicit tax categories and prices excluding tax.

    Mandatory totals must be supplied from Odoo. Unsupported conditions are
    rejected by the Odoo adapter and here where possible. No fiscal inference.
    """
    if data.get('currency') != 'DOP':
        raise PreparationError('Esta versiÃ³n solo admite DOP; no convierte monedas.')
    if data.get('rounding_method') != 'round_per_line':
        raise PreparationError('Esta versiÃ³n requiere redondeo de impuestos por lÃ­nea.')
    document_type = str(data.get('document_type', '31'))
    schema_file(document_type)
    expected_move = {'34':'out_refund','41':'in_invoice','43':'in_invoice','47':'in_invoice'}.get(document_type,'out_invoice')
    if data.get('move_type') != expected_move:
        raise PreparationError('El asiento contable no corresponde al tipo de comprobante.')
    issued = iso_date(data.get('invoice_date'), 'Fecha de emisiÃ³n')
    expires = None
    if document_type not in ('32','34'):
        expires = iso_date(data.get('test_expiry'), 'Vencimiento de secuencia')
        if expires < issued:
            raise PreparationError('Vencimiento de secuencia anterior a la emisiÃ³n.')
    reference = None
    if document_type in ('33','34'):
        details = data.get('reference') or {}
        original_ncf = str(details.get('ncf') or '')
        if not re.fullmatch(r'E[0-9]{12}|B[0-9]{10}|A[0-9]{18}', original_ncf):
            raise PreparationError('Indique el NCF original de la nota.')
        original_date = iso_date(details.get('date'), 'Fecha del NCF original')
        if original_date > issued:
            raise PreparationError('La nota no puede ser anterior al comprobante original.')
        modification = str(details.get('code') or '')
        if modification not in (('3',) if document_type == '33' else ('1','2','3')):
            raise PreparationError('Indique el cÃ³digo de modificaciÃ³n correspondiente.')
        reference = (original_ncf,original_date,modification)
    income = str(data.get('income_type', ''))
    if document_type not in ('41','43','47') and income not in ('01', '02', '03', '04', '05', '06'):
        raise PreparationError('Seleccione un tipo de ingresos vÃ¡lido.')
    payment = str(data.get('payment_type', ''))
    if payment not in ('1', '2'):
        raise PreparationError('Solo se admiten contado o crÃ©dito.')
    due = None
    if payment == '2' and document_type != '43':
        due = iso_date(data.get('due_date'), 'Fecha lÃ­mite de pago')
        if due < issued:
            raise PreparationError('Fecha lÃ­mite de pago anterior a la emisiÃ³n.')
    seller = data.get('seller') or {}
    buyer = data.get('buyer') or {}
    seller_rnc = rnc(seller.get('rnc'), 'RNC emisor')
    buyer_rnc = None
    foreign_id = None
    if document_type in ('46','47'):
        foreign_id = text(buyer.get('foreign_id'), 'Identificador extranjero', 20)
    elif document_type != '43' and (document_type != '32' or buyer.get('rnc')):
        buyer_rnc = rnc(buyer.get('rnc'), 'RNC comprador')
    seller_name = text(seller.get('name'), 'RazÃ³n social emisor', 150)
    buyer_name = text(buyer.get('name'), 'RazÃ³n social comprador', 150) if document_type != '43' else None
    address = text(seller.get('address'), 'DirecciÃ³n emisor', 100)
    rows = data.get('lines') or []
    if not 1 <= len(rows) <= 1000:
        raise PreparationError('Se requieren de 1 a 1000 lÃ­neas de producto/servicio.')
    items, net, tax_total = [], Decimal('0'), Decimal('0')
    bases = {k: Decimal('0') for k in ('1','2','3','4')}
    taxes = {k: Decimal('0') for k in ('1','2','3')}
    present = set()
    retained_itbis = retained_isr = Decimal('0')
    for row in rows:
        name = text(row.get('name'), 'Nombre de Ã­tem', 80)
        qty = number(row.get('quantity'), 'Cantidad')
        price = number(row.get('price_unit'), 'Precio')
        if qty <= 0 or qty != qty.quantize(CENT):
            raise PreparationError('Cantidad positiva con mÃ¡ximo 2 decimales requerida.')
        if price < 0 or price != price.quantize(Decimal('0.0001')):
            raise PreparationError('Precio no negativo con mÃ¡ximo 4 decimales requerido.')
        discount = number(row.get('discount', 0), 'Descuento')
        if not 0 <= discount <= 100 or discount != discount.quantize(CENT):
            raise PreparationError('Descuento entre 0 y 100 con mÃ¡ximo dos decimales requerido.')
        if str(row.get('goods_service')) not in ('1', '2'):
            raise PreparationError('Identifique el Ã­tem como bien o servicio.')
        rate = number(row.get('tax_rate'), 'ITBIS')
        category = str(row.get('tax_category') or {'18':'1','16':'2'}.get(str(rate.normalize()), ''))
        if category not in ('1','2','3','4') or rate != {'1':Decimal('18'),'2':Decimal('16'),'3':Decimal('0'),'4':Decimal('0')}[category]:
            raise PreparationError('Indique ITBIS 18%, 16%, tasa cero o exento de forma explÃ­cita y coherente.')
        if document_type in ('43','44','47') and category != '4':
            raise PreparationError('Este comprobante requiere partidas clasificadas como exentas.')
        if document_type == '46' and category != '3':
            raise PreparationError('El E46 requiere partidas de exportación con tasa cero.')
        if document_type == '43' and discount:
            raise PreparationError('El formato E43 no admite descuentos por partida.')
        raw = qty * price * (Decimal('1') - discount / Decimal('100'))
        subtotal = money(raw)
        discount_amount = money(qty * price) - subtotal
        if subtotal != money(money(qty * price) - discount_amount):
            raise PreparationError('El descuento no es representable en centavos.')
        if subtotal != money(number(row.get('subtotal'), 'Subtotal Odoo')):
            raise PreparationError('El subtotal de lÃ­nea difiere de Odoo.')
        # Tax computed from unrounded base; matches Odoo per-line rounding.
        tax = money(raw * rate / Decimal('100'))
        bases[category] += subtotal
        present.add(category)
        if category != '4': taxes[category] += tax
        itbis = money(number(row.get('retained_itbis',0), 'ITBIS retenido'))
        isr = money(number(row.get('retained_isr',0), 'ISR retenido'))
        if not (0 <= itbis <= tax and 0 <= isr <= subtotal):
            raise PreparationError('Revise la retención de la partida.')
        if (itbis or isr) and document_type not in ('41','47'):
            raise PreparationError('El tipo seleccionado no admite este flujo de retenciones.')
        if document_type == '47' and (itbis or not isr):
            raise PreparationError('El E47 requiere ISR retenido explícito por partida.')
        retained_itbis += itbis
        retained_isr += isr
        items.append((name, qty, price, subtotal, str(row['goods_service']), category, discount, discount_amount,itbis,isr))
        net += subtotal
        tax_total += tax
    total = net + tax_total
    if document_type == '32' and (total <= 0 or (total >= 250000 and not buyer_rnc)):
        raise PreparationError('El E32 requiere un total positivo y RNC del comprador desde RD$250,000.')
    if reference and reference[2] == '2' and total:
        raise PreparationError('La nota de crÃ©dito por correcciÃ³n de texto requiere monto total cero.')
    for key, expected in (('amount_untaxed', net), ('amount_tax', tax_total-retained_itbis-retained_isr), ('amount_total', total-retained_itbis-retained_isr)):
        actual = money(number(data.get(key), key))
        if actual != expected:
            raise PreparationError('%s no concuerda con Odoo; revisar redondeo/impuestos.' % key)
    root = etree.Element('ECF')
    root.append(etree.Comment('BORRADOR LOCAL SIN FIRMA - eNCF FICTICIO - NO VALIDO PARA EMISION FISCAL'))
    head = etree.SubElement(root, 'Encabezado')
    add(head, 'Version', '1.0')
    doc = etree.SubElement(head, 'IdDoc')
    add(doc, 'TipoeCF', document_type)
    add(doc, 'eNCF', 'E'+document_type+'0000000001')
    if expires:
        add(doc, 'FechaVencimientoSecuencia', expires.strftime('%d-%m-%Y'))
    if document_type == '34':
        add(doc, 'IndicadorNotaCredito', int((issued - reference[1]).days > 30))
    if document_type not in ('43','44','46','47'):
        add(doc, 'IndicadorMontoGravado', '0')
    if document_type not in ('41','43','47'):
        add(doc, 'TipoIngresos', income)
    add(doc, 'TipoPago', payment)
    if due:
        add(doc, 'FechaLimitePago', due.strftime('%d-%m-%Y'))
    issuer = etree.SubElement(head, 'Emisor')
    add(issuer, 'RNCEmisor', seller_rnc)
    add(issuer, 'RazonSocialEmisor', seller_name)
    add(issuer, 'DireccionEmisor', address)
    add(issuer, 'FechaEmision', issued.strftime('%d-%m-%Y'))
    if document_type != '43':
        customer = etree.SubElement(head, 'Comprador')
        if buyer_rnc:
            add(customer, 'RNCComprador', buyer_rnc)
        if foreign_id:
            add(customer, 'IdentificadorExtranjero', foreign_id)
        add(customer, 'RazonSocialComprador', buyer_name)
    totals = etree.SubElement(head, 'Totales')
    if present - {'4'}:
        add(totals, 'MontoGravadoTotal', fixed(sum(bases[k] for k in ('1','2','3'))))
    for k in ('1','2','3'):
        if k in present: add(totals, 'MontoGravadoI'+k, fixed(bases[k]))
    if '4' in present: add(totals, 'MontoExento', fixed(bases['4']))
    for k, rate in (('1','18'),('2','16'),('3','0')):
        if k in present: add(totals, 'ITBIS'+k, rate)
    if present - {'4'}:
        add(totals, 'TotalITBIS', fixed(tax_total))
    for k in ('1','2','3'):
        if k in present: add(totals, 'TotalITBIS'+k, fixed(taxes[k]))
    add(totals, 'MontoTotal', fixed(total))
    if document_type == '41':
        add(totals, 'TotalITBISRetenido', fixed(retained_itbis))
    if document_type in ('41','47'):
        add(totals, 'TotalISRRetencion', fixed(retained_isr))
    details = etree.SubElement(root, 'DetallesItems')
    for index, (name, qty, price, subtotal, kind, category, discount, discount_amount,itbis,isr) in enumerate(items, 1):
        item = etree.SubElement(details, 'Item')
        add(item, 'NumeroLinea', index)
        add(item, 'IndicadorFacturacion', category)
        if document_type in ('41','47'):
            retention = etree.SubElement(item,'Retencion')
            add(retention,'IndicadorAgenteRetencionoPercepcion','1')
            if document_type == '41':
                add(retention,'MontoITBISRetenido',fixed(itbis))
            add(retention,'MontoISRRetenido',fixed(isr))
        add(item, 'NombreItem', name)
        add(item, 'IndicadorBienoServicio', kind)
        add(item, 'CantidadItem', format(qty, 'f'))
        add(item, 'PrecioUnitarioItem', format(price, 'f'))
        if discount:
            add(item, 'DescuentoMonto', fixed(discount_amount))
            sub = etree.SubElement(etree.SubElement(item, 'TablaSubDescuento'), 'SubDescuento')
            add(sub, 'TipoSubDescuento', '$')
            add(sub, 'MontoSubDescuento', fixed(discount_amount))
        add(item, 'MontoItem', fixed(subtotal))
    if reference:
        ref = etree.SubElement(root, 'InformacionReferencia')
        add(ref, 'NCFModificado', reference[0])
        add(ref, 'FechaNCFModificado', reference[1].strftime('%d-%m-%Y'))
        add(ref, 'CodigoModificacion', reference[2])
    try:
        xml = etree.tostring(root, encoding='UTF-8', xml_declaration=True)
        validate_preliminary(xml, document_type)
    except (etree.Error, ValueError) as exc:
        raise PreparationError(str(exc)) from None
    return xml


def build_invoice(data, encf):
    document_type = str(data.get('document_type', '31'))
    schema_file(document_type)
    if not re.fullmatch('E'+document_type+r'[0-9]{10}', encf):
        raise PreparationError('e-NCF no corresponde al tipo seleccionado.')
    root = etree.fromstring(build_preview(data))
    for node in list(root):
        if isinstance(node, etree._Comment): root.remove(node)
    root.find('Encabezado/IdDoc/eNCF').text = encf
    return etree.tostring(root, encoding='UTF-8', xml_declaration=True)


def validate_signed(xml):
    """Restricted derivative of official XSD; optional undefined field prohibited."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.fromstring(xml, parser)
    document_type = root.findtext('Encabezado/IdDoc/TipoeCF')
    tree = etree.parse(str(schema_file(document_type)), parser)
    ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}
    for n in tree.xpath('//xs:element[@name="IndicadorServicioTodoIncluido"]', namespaces=ns):
        if not tree.xpath('//xs:simpleType[@name="IndicadorServicioTodoIncluidoType"] | //xs:complexType[@name="IndicadorServicioTodoIncluidoType"]', namespaces=ns):
            n.getparent().remove(n)
    schema = etree.XMLSchema(tree)
    root = etree.fromstring(xml, parser)
    if root.getroottree().docinfo.doctype:
        raise PreparationError('DTD no permitido.')
    if not schema.validate(root):
        raise PreparationError('XML e-CF fuera del esquema restringido: ' + schema.error_log.last_error.message)
    return True
