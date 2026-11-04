import pathlib
import tempfile
import unittest
import hashlib
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from fiscal.receiver import Inbox, RECEPTION, APPROVAL
from fiscal.trust import check_material, validate_certificate, crl_signature_valid
from fiscal.operations import backup
from fiscal.declaration import sign_declaration
from certification.xmlsig import sign_xml, parse, verify_xml
import test_dgii_receiver as fixtures


class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ReceiverTests.setUpClass()
        cls.identity = staticmethod(fixtures.ReceiverTests.identity)
        cls.root = cls.identity('CA ROOT FICTICIA', authority=True)
        cls.ca = cls.identity('CA INTERMEDIA FICTICIA', cls.root, authority=True)
        cls.sender = cls.identity('EMISOR FICTICIO', cls.ca)
        cls.receiver = cls.identity('RECEPTOR FICTICIO', cls.ca)

    def crl(self, issuer, revoked=None, expired=False):
        now = datetime.now(timezone.utc)
        builder = x509.CertificateRevocationListBuilder().issuer_name(issuer[1].subject).last_update(now-timedelta(hours=2)).next_update(now-timedelta(hours=1) if expired else now+timedelta(hours=12))
        if revoked:
            builder = builder.add_revoked_certificate(x509.RevokedCertificateBuilder().serial_number(revoked.serial_number).revocation_date(now-timedelta(hours=1)).build())
        return builder.sign(issuer[0], hashes.SHA256()).public_bytes(serialization.Encoding.DER)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.base = pathlib.Path(self.tmp.name)
        self.trust = self.base/'trust';self.trust.mkdir()
        for name, cert in [('root',self.root[1]),('intermediate',self.ca[1])]:
            (self.trust/(name+'.pem')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (self.trust/'root.crl').write_bytes(self.crl(self.root))
        (self.trust/'intermediate.crl').write_bytes(self.crl(self.ca))
        self.inbox = Inbox(self.base/'state', self.trust, '987654321', self.receiver[2], b'qa-only')

    def tearDown(self):
        self.tmp.cleanup()

    def invoice(self, buyer='987654321'):
        data={'document_type':'31','currency':'DOP','move_type':'out_invoice','rounding_method':'round_per_line',
              'invoice_date':'2026-11-04','test_expiry':'2027-12-31','income_type':'01','payment_type':'1',
              'seller':{'rnc':'123456789','name':'FICTICIO','address':'Solo prueba'},
              'buyer':{'rnc':buyer,'name':'FICTICIO'},
              'lines':[{'name':'Prueba','quantity':1,'price_unit':100,'discount':0,'goods_service':'2','tax_rate':18,'subtotal':100}],
              'amount_untaxed':100,'amount_tax':18,'amount_total':118}
        return sign_xml(fixtures.ReceiverTests.builder.build_invoice(data,'E310000000001'),self.sender[2],b'qa-only')

    def test_production_valid_signature_durable_and_idempotent(self):
        xml=self.invoice();status,ack=self.inbox.receive(RECEPTION,xml)
        self.assertEqual(status,200);self.assertEqual(parse(ack).findtext('.//Estado'),'0')
        self.assertTrue(verify_xml(ack,self.receiver[1]))
        self.assertEqual(self.inbox.receive(RECEPTION,xml),(status,ack))
        reopened=Inbox(self.base/'state',self.trust,'987654321',self.receiver[2],b'qa-only')
        self.assertEqual(reopened.receive(RECEPTION,xml),(status,ack))

    def test_revoked_sender_receives_rejection(self):
        (self.trust/'intermediate.crl').write_bytes(self.crl(self.ca,self.sender[1]))
        self.assertEqual(parse(self.inbox.receive(RECEPTION,self.invoice())[1]).findtext('.//CodigoMotivoNoRecibido'),'2')

    def test_revoked_ca_receives_rejection(self):
        (self.trust/'root.crl').write_bytes(self.crl(self.root,self.ca[1]))
        self.assertEqual(parse(self.inbox.receive(RECEPTION,self.invoice())[1]).findtext('.//CodigoMotivoNoRecibido'),'2')

    def test_expired_or_missing_crl_fails_closed(self):
        (self.trust/'intermediate.crl').write_bytes(self.crl(self.ca,expired=True))
        with self.assertRaises(ValueError):check_material(self.trust)
        self.assertEqual(parse(self.inbox.receive(RECEPTION,self.invoice())[1]).findtext('.//CodigoMotivoNoRecibido'),'2')
        (self.trust/'intermediate.crl').unlink()
        with self.assertRaises(ValueError):check_material(self.trust)

    def test_test_ca_cannot_be_installed_in_production(self):
        bad=self.identity('VIAFIRMA TEST FICTICIA',authority=True)
        (self.trust/'bad.pem').write_bytes(bad[1].public_bytes(serialization.Encoding.PEM))
        with self.assertRaises(ValueError):check_material(self.trust)

    def test_leaf_without_optional_basic_constraints_is_valid(self):
        old=self.sender[1]
        leaf=x509.CertificateBuilder().subject_name(old.subject).issuer_name(self.ca[1].subject).public_key(old.public_key()).serial_number(x509.random_serial_number()).not_valid_before(old.not_valid_before_utc).not_valid_after(old.not_valid_after_utc).add_extension(old.extensions.get_extension_for_class(x509.KeyUsage).value,critical=True).sign(self.ca[0],hashes.SHA256())
        self.assertEqual(validate_certificate(leaf,self.trust),leaf)

    def test_crl_from_another_key_is_rejected(self):
        rogue=self.identity('CA INTERMEDIA FICTICIA',self.root,authority=True)
        forged=x509.load_der_x509_crl(self.crl(rogue))
        self.assertFalse(crl_signature_valid(forged,self.ca[1]))
        (self.trust/'intermediate.crl').write_bytes(forged.public_bytes(serialization.Encoding.DER))
        with self.assertRaises(ValueError):check_material(self.trust)

    def test_wrong_recipient_and_tampering_rejected(self):
        self.assertEqual(parse(self.inbox.receive(RECEPTION,self.invoice('111111111'))[1]).findtext('.//CodigoMotivoNoRecibido'),'4')
        self.assertEqual(parse(self.inbox.receive(RECEPTION,self.invoice().replace(b'Prueba',b'Cambio'))[1]).findtext('.//CodigoMotivoNoRecibido'),'2')

    def test_certification_path_is_not_a_production_path(self):
        with self.assertRaises(ValueError):self.inbox.receive('/certificacion/fe/recepcion/api/ecf',self.invoice())

    def test_commercial_approval(self):
        xml=b'<ACECF><DetalleAprobacionComercial><Version>1.0</Version><RNCEmisor>987654321</RNCEmisor><eNCF>E310000000001</eNCF><FechaEmision>04-11-2026</FechaEmision><MontoTotal>118.00</MontoTotal><RNCComprador>123456789</RNCComprador><Estado>1</Estado><FechaHoraAprobacionComercial>04-11-2026 09:00:00</FechaHoraAprobacionComercial></DetalleAprobacionComercial></ACECF>'
        signed=sign_xml(xml,self.sender[2],b'qa-only')
        self.assertEqual(self.inbox.receive(APPROVAL,signed)[0],200)
        self.assertEqual(self.inbox.receive(APPROVAL,signed.replace(b'118.00',b'119.00'))[0],400)

    def test_backup_restores_document_and_database(self):
        self.inbox.receive(RECEPTION,self.invoice())
        result=backup(self.base/'state',self.base/'backup')
        self.assertEqual(result['documents'],1)
        self.assertTrue(result['restore_verified'])

    def test_backup_detects_corrupted_original(self):
        self.inbox.receive(RECEPTION,self.invoice())
        next((self.base/'state').glob('*.xml')).write_bytes(b'corrupt')
        with self.assertRaises(AssertionError):backup(self.base/'state',self.base/'backup')

    def test_declaration_signature_keeps_exact_legal_text(self):
        xml=b'<DeclaracionJurada><DetalleGeneral>DECLARACION FICTICIA SOLO PRUEBA</DetalleGeneral></DeclaracionJurada>'
        signed=sign_declaration(xml,self.receiver[2],b'qa-only',hashlib.sha256(xml).hexdigest())
        self.assertTrue(verify_xml(signed,self.receiver[1]))
        self.assertEqual(parse(signed).findtext('DetalleGeneral'),parse(xml).findtext('DetalleGeneral'))

    def test_declaration_signing_rejects_other_files_and_modified_text(self):
        xml=b'<DeclaracionJurada><DetalleGeneral>SOLO PRUEBA</DetalleGeneral></DeclaracionJurada>'
        with self.assertRaises(ValueError):sign_declaration(xml,self.receiver[2],b'qa-only','0'*64)
        invoice=self.invoice()
        with self.assertRaises(ValueError):sign_declaration(invoice,self.receiver[2],b'qa-only',hashlib.sha256(invoice).hexdigest())
