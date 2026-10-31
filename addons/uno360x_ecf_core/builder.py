"""Restricted E31/E45 preparation, no network or allocation.

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
SUPPORTED_TYPES = ('31', '45')

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
        raise PreparationError('%s: número inválido.' % label) from None
    if not result.is_finite():
        raise PreparationError('%s: número no finito.' % label)
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fixed(value):
    return format(money(value), '.2f')


def text(value, label, maximum):
    result = str(value or '').strip()
    if not result or len(result) > maximum:
        raise PreparationError('%s: requerido, máximo %s caracteres.' % (label, maximum))
    if any(ord(c) < 32 and c not in '\t\n\r' for c in result):
        raise PreparationError('%s: contiene caracteres XML inválidos.' % label)
    return result


def rnc(value, label):
    # Only presentation separators are removed. No silent removal of letters.
    result = re.sub(r'[\s-]', '', str(value or ''))
    if not re.fullmatch(r'(?:[0-9]{9}|[0-9]{11})', result):
        raise PreparationError('%s: debe contener 9 u 11 dígitos.' % label)
    return result


def iso_date(value, label):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise PreparationError('%s: fecha ISO válida requerida.' % label) from None


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
        raise PreparationError('El esquema oficial cambió; revisar el validador preliminar.')
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
        raise PreparationError('Estructura preliminar inválida: %s' % error.message)


def build_preview(data):
    """Build E31/E45 preview, DOP, explicit tax categories, prices excluding tax.

    Mandatory totals must be supplied from Odoo. Unsupported conditions are
    rejected by the Odoo adapter and here where possible. No fiscal inference.
    """
    if data.get('currency') != 'DOP':
        raise PreparationError('Esta versión solo admite DOP; no convierte monedas.')
    if data.get('move_type') != 'out_invoice':
        raise PreparationError('Esta versión solo prepara facturas de cliente E31.')
    if data.get('rounding_method') != 'round_per_line':
        raise PreparationError('Esta versión requiere redondeo de impuestos por línea.')
    document_type = str(data.get('document_type', '31'))
    schema_file(document_type)
    issued = iso_date(data.get('invoice_date'), 'Fecha de emisión')
    expires = iso_date(data.get('test_expiry'), 'Vencimiento de secuencia de prueba')
    if expires < issued:
        raise PreparationError('Vencimiento de prueba anterior a la emisión.')
    income = str(data.get('income_type', ''))
    if income not in ('01', '02', '03', '04', '05', '06'):
        raise PreparationError('Seleccione un tipo de ingresos válido.')
    payment = str(data.get('payment_type', ''))
    if payment not in ('1', '2'):
        raise PreparationError('Solo se admiten contado o crédito.')
    due = None
    if payment == '2':
        due = iso_date(data.get('due_date'), 'Fecha límite de pago')
        if due < issued:
            raise PreparationError('Fecha límite de pago anterior a la emisión.')
    seller = data.get('seller') or {}
    buyer = data.get('buyer') or {}
    seller_rnc = rnc(seller.get('rnc'), 'RNC emisor')
    buyer_rnc = rnc(buyer.get('rnc'), 'RNC comprador')
    seller_name = text(seller.get('name'), 'Razón social emisor', 150)
    buyer_name = text(buyer.get('name'), 'Razón social comprador', 150)
    address = text(seller.get('address'), 'Dirección emisor', 100)
    rows = data.get('lines') or []
    if not 1 <= len(rows) <= 1000:
        raise PreparationError('Se requieren de 1 a 1000 líneas de producto/servicio.')
    items, net, tax_total = [], Decimal('0'), Decimal('0')
    bases = {k: Decimal('0') for k in ('1','2','3','4')}
    taxes = {k: Decimal('0') for k in ('1','2','3')}
    present = set()
    for row in rows:
        name = text(row.get('name'), 'Nombre de ítem', 80)
        qty = number(row.get('quantity'), 'Cantidad')
        price = number(row.get('price_unit'), 'Precio')
        if qty <= 0 or qty != qty.quantize(CENT):
            raise PreparationError('Cantidad positiva con máximo 2 decimales requerida.')
        if price < 0 or price != price.quantize(Decimal('0.0001')):
            raise PreparationError('Precio no negativo con máximo 4 decimales requerido.')
        discount = number(row.get('discount', 0), 'Descuento')
        if not 0 <= discount <= 100 or discount != discount.quantize(CENT):
            raise PreparationError('Descuento entre 0 y 100 con máximo dos decimales requerido.')
        if str(row.get('goods_service')) not in ('1', '2'):
            raise PreparationError('Identifique el ítem como bien o servicio.')
        rate = number(row.get('tax_rate'), 'ITBIS')
        category = str(row.get('tax_category') or {'18':'1','16':'2'}.get(str(rate.normalize()), ''))
        if category not in ('1','2','3','4') or rate != {'1':Decimal('18'),'2':Decimal('16'),'3':Decimal('0'),'4':Decimal('0')}[category]:
            raise PreparationError('Indique ITBIS 18%, 16%, tasa cero o exento de forma explícita y coherente.')
        raw = qty * price * (Decimal('1') - discount / Decimal('100'))
        subtotal = money(raw)
        discount_amount = money(qty * price) - subtotal
        if subtotal != money(money(qty * price) - discount_amount):
            raise PreparationError('El descuento no es representable en centavos.')
        if subtotal != money(number(row.get('subtotal'), 'Subtotal Odoo')):
            raise PreparationError('El subtotal de línea difiere de Odoo.')
        # Tax computed from unrounded base; matches Odoo per-line rounding.
        tax = money(raw * rate / Decimal('100'))
        bases[category] += subtotal
        present.add(category)
        if category != '4': taxes[category] += tax
        items.append((name, qty, price, subtotal, str(row['goods_service']), category, discount, discount_amount))
        net += subtotal
        tax_total += tax
    total = net + tax_total
    for key, expected in (('amount_untaxed', net), ('amount_tax', tax_total), ('amount_total', total)):
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
    add(doc, 'FechaVencimientoSecuencia', expires.strftime('%d-%m-%Y'))
    add(doc, 'IndicadorMontoGravado', '0')
    add(doc, 'TipoIngresos', income)
    add(doc, 'TipoPago', payment)
    if due:
        add(doc, 'FechaLimitePago', due.strftime('%d-%m-%Y'))
    issuer = etree.SubElement(head, 'Emisor')
    add(issuer, 'RNCEmisor', seller_rnc)
    add(issuer, 'RazonSocialEmisor', seller_name)
    add(issuer, 'DireccionEmisor', address)
    add(issuer, 'FechaEmision', issued.strftime('%d-%m-%Y'))
    customer = etree.SubElement(head, 'Comprador')
    add(customer, 'RNCComprador', buyer_rnc)
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
    details = etree.SubElement(root, 'DetallesItems')
    for index, (name, qty, price, subtotal, kind, category, discount, discount_amount) in enumerate(items, 1):
        item = etree.SubElement(details, 'Item')
        add(item, 'NumeroLinea', index)
        add(item, 'IndicadorFacturacion', category)
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
