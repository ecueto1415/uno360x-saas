from datetime import datetime,timedelta,timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from odoo.tests.common import TransactionCase,tagged
from ..crypto import sign_xml,load_identity,verify_xml,parse
from ..policy import transmit
from ..preflight import check_invoice
from ..builder import build_preview,validate_preliminary,PreparationError

@tagged('post_install','-at_install')
class TestOfflineFiscal(TransactionCase):
    def test_fictional_e31_e45_structures_and_rejected_totals(self):
        data={'currency':'DOP','move_type':'out_invoice','rounding_method':'round_per_line',
          'invoice_date':'2026-10-31','test_expiry':'2027-12-31','income_type':'01','payment_type':'1',
          'seller':{'rnc':'123456789','name':'EMISOR FICTICIO','address':'Solo laboratorio'},
          'buyer':{'rnc':'987654321','name':'CLIENTE FICTICIO'},
          'lines':[{'name':'Servicio ficticio','quantity':2,'price_unit':100,'discount':10,
                    'goods_service':'2','tax_rate':18,'subtotal':180}],
          'amount_untaxed':180,'amount_tax':32.4,'amount_total':212.4}
        for kind in ('31','45'):
            data['document_type']=kind
            xml=build_preview(data)
            validate_preliminary(xml,kind)
            self.assertIn(b'BORRADOR LOCAL',xml)
            self.assertIn(('E'+kind+'0000000001').encode(),xml)
        data['amount_total']=999
        with self.assertRaises(PreparationError):build_preview(data)

    def test_fiscal_transmission_is_blocked(self):
        with self.assertRaises(RuntimeError):transmit()
        result=check_invoice({})
        self.assertFalse(result['sent']);self.assertFalse(result['dgii_acceptance'])

    def test_synthetic_certificate_signs_and_detects_tampering(self):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'UNO360X FICTICIO SOLO PRUEBAS')])
        now=datetime.now(timezone.utc)
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,encipher_only=False,decipher_only=False),critical=True).sign(key,hashes.SHA256())
        p12=pkcs12.serialize_key_and_certificates(b'fictional',key,cert,None,serialization.BestAvailableEncryption(b'fictional-test'))
        xml=sign_xml(b'<SemillaModel><valor>ficticio</valor></SemillaModel>',p12,b'fictional-test')
        self.assertTrue(verify_xml(xml,cert))
        with self.assertRaises(ValueError):load_identity(p12,b'wrong-fictional')
        with self.assertRaises(ValueError):verify_xml(xml.replace(b'ficticio',b'alterado'),cert)
        with self.assertRaises(ValueError):parse(b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><ECF>&y;</ECF>')
