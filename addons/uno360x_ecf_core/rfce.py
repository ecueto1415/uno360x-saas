from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from lxml import etree

from .crypto import DS, load_identity, parse, sign_xml, verify_xml

TOTAL_FIELDS = ('MontoGravadoTotal', 'MontoGravadoI1', 'MontoGravadoI2', 'MontoGravadoI3',
                'MontoExento', 'TotalITBIS', 'TotalITBIS1', 'TotalITBIS2', 'TotalITBIS3',
                'MontoImpuestoAdicional', 'ImpuestosAdicionales', 'MontoTotal',
                'MontoNoFacturable', 'MontoPeriodo')


def copy_fields(source, target, names):
    for name in names:
        node = source.find(name)
        if node is not None:
            target.append(deepcopy(node))


def build_signed_summary(signed_ecf, p12, password):
    invoice = parse(signed_ecf)
    _, cert = load_identity(p12, password)
    verify_xml(signed_ecf, cert)
    head = invoice.find('Encabezado')
    if head.findtext('IdDoc/TipoeCF') != '32' or not (
            Decimal('0') < Decimal(head.findtext('Totales/MontoTotal')) < Decimal('250000')):
        raise ValueError('RFCE exige E32 menor a RD$250,000.')
    result = etree.Element('RFCE')
    summary = etree.SubElement(result, 'Encabezado')
    copy_fields(head, summary, ('Version',))
    for tag, fields in (
        ('IdDoc', ('TipoeCF','eNCF','TipoIngresos','TipoPago','TablaFormasPago')),
        ('Emisor', ('RNCEmisor','RazonSocialEmisor','FechaEmision')),
        ('Comprador', ('RNCComprador','IdentificadorExtranjero','RazonSocialComprador')),
        ('Totales', TOTAL_FIELDS),
    ):
        src = head.find(tag)
        if src is None and tag != 'Comprador':
            raise ValueError('Falta ' + tag)
        dst = etree.SubElement(summary, tag)
        if src is not None:
            copy_fields(src,dst,fields)
    signature = invoice.findtext('.//{%s}SignatureValue' % DS)
    etree.SubElement(summary,'CodigoSeguridadeCF').text = signature[:6]
    signed = sign_xml(etree.tostring(result),p12,password)
    schema = etree.parse(str(Path(__file__).with_name('schemas')/'rfce32.xsd'))
    # XML Schema regex has no non-capturing group syntax. Preserve the original XSD.
    for facet in schema.findall('.//{http://www.w3.org/2001/XMLSchema}pattern'):
        pattern = facet.get('value')
        facet.set('value', pattern.replace('(?:', '('))
    etree.XMLSchema(schema).assertValid(parse(signed))
    verify_xml(signed, cert)
    return signed

def requires_summary(payload):
    return payload['document_type'] == '32' and Decimal(str(payload['amount_total'])) < 250000


def security_code(signed_ecf):
    value = parse(signed_ecf).findtext('.//{%s}SignatureValue' % DS)
    if not value or len(value) < 6:
        raise ValueError('Falta el código de seguridad del e-CF.')
    return value[:6]
