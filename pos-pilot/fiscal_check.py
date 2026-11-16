"""Exercise POS takeout fiscal totals with a throwaway, non-DGII certificate."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from addons.uno360x_ecf_core.builder import build_invoice, validate_signed
from addons.uno360x_ecf_core.crypto import sign_xml, verify_xml


def check():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'UNO360X POS test only')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
            .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False),
                           critical=True).sign(key, hashes.SHA256()))
    password = b'local-test-only'
    p12 = pkcs12.serialize_key_and_certificates(b'pos-test', key, cert, None,
                                               serialization.BestAvailableEncryption(password))
    today = date.today()
    data = {
        'currency': 'DOP', 'move_type': 'out_invoice', 'rounding_method': 'round_per_line',
        'invoice_date': today.isoformat(), 'test_expiry': (today+timedelta(days=30)).isoformat(),
        'income_type': '01', 'payment_type': '1', 'document_type': '31',
        'seller': {'rnc': '123456789', 'name': 'RESTAURANTE FICTICIO', 'address': 'Solo laboratorio'},
        'buyer': {'rnc': '987654321', 'name': 'CLIENTE FICTICIO'},
        'lines': [{'name': item,'quantity': 1,'price_unit': price,'subtotal': price,
                   'goods_service': '1','tax_rate': 18}
                  for item,price in [('Hamburguesa',450),('Alitas',420),('Mojito',300)]],
        'amount_untaxed': '1170.00', 'amount_tax': '210.60', 'amount_total': '1380.60',
    }
    e31 = build_invoice(data, 'E310000000001')
    root = etree.fromstring(e31)
    root.find('Encabezado/IdDoc/TipoeCF').text = '32'
    root.find('Encabezado/IdDoc/eNCF').text = 'E320000000001'
    root.find('Encabezado/IdDoc').remove(root.find('Encabezado/IdDoc/FechaVencimientoSecuencia'))
    root.find('Encabezado/Comprador').clear()
    e32 = etree.tostring(root, encoding='UTF-8')
    signed31 = sign_xml(e31,p12,password)
    signed32 = sign_xml(e32,p12,password)
    assert verify_xml(signed31,cert) and validate_signed(signed31)
    assert verify_xml(signed32,cert)
    schema = etree.parse(str(ROOT/'certification/schemas/ecf32.xsd'))
    ns = {'xs':'http://www.w3.org/2001/XMLSchema'}
    if not schema.xpath('//xs:simpleType[@name="IndicadorServicioTodoIncluidoType"]',namespaces=ns):
        for node in schema.xpath('//xs:element[@name="IndicadorServicioTodoIncluido"]',namespaces=ns):
            node.getparent().remove(node)
    etree.XMLSchema(schema).assertValid(etree.fromstring(signed32))
    print('E31 y E32: firma ficticia y estructura verificadas. Sin RFCE firmado ni envío DGII.')


if __name__ == '__main__':
    check()
