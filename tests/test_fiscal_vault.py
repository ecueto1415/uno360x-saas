from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from control.identity import IdentityService,IdentityError
from control.fiscal_vault import FiscalVault,MemoryKeys

class VaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048);now=datetime.now(timezone.utc)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CERTIFICADO FICTICIO NO FISCAL'),x509.NameAttribute(NameOID.SERIAL_NUMBER,'123456789')])
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=10)).add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,encipher_only=False,decipher_only=False),critical=True).sign(key,hashes.SHA256())
        cls.p12=pkcs12.serialize_key_and_certificates(b'fictional',key,cert,None,serialization.BestAvailableEncryption(b'fiscal-ficticio'))
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.mail=[]
        self.identity=IdentityService(Path(self.tmp.name)/'control.sqlite3',self.mail.append)
        self.identity.register('owner@example.test');self.identity.complete_registration(self.mail[-1]['token'],'Clave ficticia fiscal 2026')
        self.session=self.identity.login('owner@example.test','Clave ficticia fiscal 2026')['session']
        self.a=self.identity.create_company(self.session,'fiscal-alfa',[],'a')['id']
        self.b=self.identity.create_company(self.session,'fiscal-beta',[],'b')['id']
        self.vault=FiscalVault(self.identity,MemoryKeys(),lambda tenant,company:{'tax_id':'123456789' if tenant==self.a else '987654321'} if company==1 else None)
    def tearDown(self):self.identity.close();self.tmp.cleanup()
    def test_encrypted_store_and_status_never_activate_emission(self):
        result=self.vault.store(self.session,self.a,1,self.p12,'fiscal-ficticio')
        dump='\n'.join(self.identity.db.iterdump())
        self.assertNotIn('fiscal-ficticio',dump)
        self.assertEqual(self.vault._load_for_worker(self.a,1,result['certificate_id']),(self.p12,'fiscal-ficticio'))
        self.assertEqual(self.vault.status(self.session,self.a,1)['state'],'pending_validation')
        self.assertFalse(self.vault.status(self.session,self.a,1)['emission_enabled'])
    def test_wrong_company_password_and_unknown_company_rejected(self):
        for tenant,company,password in [(self.b,1,'fiscal-ficticio'),(self.a,1,'wrong'),(self.a,2,'fiscal-ficticio')]:
            with self.assertRaises(IdentityError):self.vault.store(self.session,tenant,company,self.p12,password)
    def test_cipher_tampering_and_cross_company_load_rejected(self):
        result=self.vault.store(self.session,self.a,1,self.p12,'fiscal-ficticio')
        with self.assertRaises(IdentityError):self.vault._load_for_worker(self.b,1,result['certificate_id'])
        with self.identity.db:self.identity.db.execute("UPDATE fiscal_certificates SET cipher=x'0102' WHERE id=?",(result['certificate_id'],))
        with self.assertRaises(IdentityError):self.vault._load_for_worker(self.a,1,result['certificate_id'])
