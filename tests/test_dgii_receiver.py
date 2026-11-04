import importlib.util
import pathlib
import tempfile
import unittest
import base64
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree
from certification.receiver import Inbox,RECEPTION,APPROVAL,upload,compile_schema,SCHEMAS
from certification.xmlsig import sign_xml,verify_xml,parse,canonical_signed_info,DS


class ReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=pathlib.Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('offline_invoice_builder',cls.root/'addons/uno360x_ecf_core/builder.py')
        cls.builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.builder)
        def identity(name,ca=None,authority=False,expired=False):
            key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,name)])
            now=datetime.now(timezone.utc)
            issuer=ca[1].subject if ca else subject
            cert=x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=3) if expired else now-timedelta(days=1)).not_valid_after(now-timedelta(days=2) if expired else now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=authority,path_length=None),critical=True).add_extension(x509.KeyUsage(True,False,False,False,False,authority,authority,False,False),critical=True).sign(ca[0] if ca else key,hashes.SHA256())
            p12=pkcs12.serialize_key_and_certificates(b'qa-only',key,cert,None,serialization.BestAvailableEncryption(b'qa-only'))
            return key,cert,p12
        cls.identity=staticmethod(identity)
        cls.ca=identity('FICTICIA RAIZ SOLO PRUEBA',authority=True)
        cls.sender=identity('FICTICIO EMISOR',cls.ca)
        cls.receiver=identity('FICTICIO RECEPTOR',cls.ca)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();base=pathlib.Path(self.tmp.name)
        self.trust=base/'trust';self.trust.mkdir();(self.trust/'root.pem').write_bytes(self.ca[1].public_bytes(serialization.Encoding.PEM))
        self.inbox=Inbox(base/'state',self.trust,'987654321',self.receiver[2],b'qa-only')

    def tearDown(self):
        self.tmp.cleanup()

    def invoice(self,buyer='987654321',encf='E310000000001'):
        data={'document_type':'31','currency':'DOP','move_type':'out_invoice','rounding_method':'round_per_line',
              'invoice_date':'2026-11-03','test_expiry':'2027-12-31','income_type':'01','payment_type':'1',
              'seller':{'rnc':'123456789','name':'FICTICIO','address':'Solo prueba'},
              'buyer':{'rnc':buyer,'name':'FICTICIO'},
              'lines':[{'name':'Prueba','quantity':1,'price_unit':100,'discount':0,'goods_service':'2','tax_rate':18,'subtotal':100}],
              'amount_untaxed':100,'amount_tax':18,'amount_total':118}
        return sign_xml(self.builder.build_invoice(data,encf),self.sender[2],b'qa-only')

    def test_all_official_schemas_compile_without_altering_originals(self):
        for p in SCHEMAS.glob('*.xsd'):
            before=p.read_bytes();compile_schema(p);self.assertEqual(p.read_bytes(),before)

    def test_received_ack_is_signed_and_durable(self):
        status,ack=self.inbox.receive(RECEPTION,self.invoice())
        self.assertEqual(status,200);self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/Estado'),'0')
        self.assertTrue(verify_xml(ack,self.receiver[1]))
        self.inbox.schemas['arecf'].assertValid(parse(ack))
        with self.inbox.database() as db:self.assertEqual(db.execute('SELECT accepted FROM messages').fetchone()[0],1)

    def test_tampered_invoice_receives_signed_rejection(self):
        xml=self.invoice().replace(b'<NombreItem>Prueba</NombreItem>',b'<NombreItem>CAMBIO</NombreItem>')
        status,ack=self.inbox.receive(RECEPTION,xml)
        self.assertEqual(status,200);self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/CodigoMotivoNoRecibido'),'2')

    def test_default_namespace_signature_retains_declared_inclusive_c14n(self):
        xml=self.invoice().replace(b'ds:',b'').replace(b'xmlns:ds=',b'xmlns=')
        root=parse(xml);sig=root.find('{%s}Signature'%DS);info=sig.find('{%s}SignedInfo'%DS)
        sig.find('{%s}SignatureValue'%DS).text=base64.b64encode(self.sender[0].sign(canonical_signed_info(info),padding.PKCS1v15(),hashes.SHA256())).decode()
        signed=etree.tostring(root)
        self.assertTrue(verify_xml(signed,self.sender[1]))
        self.assertEqual(parse(self.inbox.receive(RECEPTION,signed)[1]).findtext('DetalleAcusedeRecibo/Estado'),'0')
        self.assertEqual(parse(self.inbox.receive(RECEPTION,signed.replace(b'Prueba',b'Cambio'))[1]).findtext('DetalleAcusedeRecibo/CodigoMotivoNoRecibido'),'2')

    def test_wrong_destination_never_accepts(self):
        _,ack=self.inbox.receive(RECEPTION,self.invoice('111111111'))
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/CodigoMotivoNoRecibido'),'4')

    def test_unknown_trust_never_accepts(self):
        (self.trust/'root.pem').unlink()
        _,ack=self.inbox.receive(RECEPTION,self.invoice())
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/CodigoMotivoNoRecibido'),'2')

    def test_retry_after_trust_installation_is_revalidated(self):
        root_bytes=(self.trust/'root.pem').read_bytes();(self.trust/'root.pem').unlink()
        xml=self.invoice();_,ack=self.inbox.receive(RECEPTION,xml)
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/Estado'),'1')
        (self.trust/'root.pem').write_bytes(root_bytes)
        _,ack=self.inbox.receive(RECEPTION,xml)
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/Estado'),'0')
        with self.inbox.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0],2)

    def test_parallel_retry_keeps_one_original_receipt(self):
        xml=self.invoice()
        with ThreadPoolExecutor(3) as pool:results=list(pool.map(lambda _:self.inbox.receive(RECEPTION,xml),range(3)))
        self.assertEqual(results,[results[0]]*3)
        with self.inbox.database() as db:self.assertEqual(db.execute('SELECT count(*) FROM messages').fetchone()[0],1)

    def test_commercial_approval_and_rejection_status(self):
        xml=b'<ACECF><DetalleAprobacionComercial><Version>1.0</Version><RNCEmisor>987654321</RNCEmisor><eNCF>E310000000001</eNCF><FechaEmision>03-11-2026</FechaEmision><MontoTotal>118.00</MontoTotal><RNCComprador>123456789</RNCComprador><Estado>1</Estado><FechaHoraAprobacionComercial>03-11-2026 09:00:00</FechaHoraAprobacionComercial></DetalleAprobacionComercial></ACECF>'
        signed=sign_xml(xml,self.sender[2],b'qa-only')
        self.assertEqual(self.inbox.receive(APPROVAL,signed)[0],200)
        self.assertEqual(self.inbox.receive(APPROVAL,signed.replace(b'118.00',b'119.00'))[0],400)

    def test_entity_and_multipart_path_attacks_are_rejected(self):
        with self.assertRaises(ValueError):parse(b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><ECF>&y;</ECF>')
        with self.assertRaises(ValueError):upload('multipart/form-data; boundary=x',b'--x\r\nContent-Disposition: form-data; name="wrong"; filename="../../file"\r\n\r\n<ECF/>\r\n--x--\r\n')
        self.assertEqual(upload('text/xml',b'<ECF/>'),b'<ECF/>')


    def test_confirmed_intermediate_can_be_an_explicit_scoped_anchor(self):
        intermediate=self.identity('CA INTERMEDIA FICTICIA',self.ca,authority=True)
        self.sender=self.identity('EMISOR FICTICIO INTERMEDIO',intermediate)
        (self.trust/'root.pem').write_bytes(intermediate[1].public_bytes(serialization.Encoding.PEM))
        _,ack=self.inbox.receive(RECEPTION,self.invoice())
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/Estado'),'0')

    def test_same_named_unknown_intermediate_is_not_trusted(self):
        trusted=self.identity('MISMO NOMBRE CA FICTICIA',self.ca,authority=True)
        impostor=self.identity('MISMO NOMBRE CA FICTICIA',self.ca,authority=True)
        self.sender=self.identity('EMISOR FICTICIO NO CONFIABLE',impostor)
        (self.trust/'root.pem').write_bytes(trusted[1].public_bytes(serialization.Encoding.PEM))
        _,ack=self.inbox.receive(RECEPTION,self.invoice())
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/CodigoMotivoNoRecibido'),'2')

    def test_leaf_certificate_cannot_be_installed_as_a_ca_anchor(self):
        (self.trust/'root.pem').write_bytes(self.sender[1].public_bytes(serialization.Encoding.PEM))
        _,ack=self.inbox.receive(RECEPTION,self.invoice())
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/CodigoMotivoNoRecibido'),'2')

    def test_expired_intermediate_anchor_is_rejected(self):
        intermediate=self.identity('CA VENCIDA FICTICIA',self.ca,authority=True,expired=True)
        self.sender=self.identity('EMISOR FICTICIO CA VENCIDA',intermediate)
        (self.trust/'root.pem').write_bytes(intermediate[1].public_bytes(serialization.Encoding.PEM))
        _,ack=self.inbox.receive(RECEPTION,self.invoice())
        self.assertEqual(parse(ack).findtext('DetalleAcusedeRecibo/CodigoMotivoNoRecibido'),'2')


if __name__=='__main__':unittest.main()
