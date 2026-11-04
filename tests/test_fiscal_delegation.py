from datetime import datetime,timedelta,timezone
from dataclasses import replace
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from control.fiscal_vault import VerifiedDelegation
from control.identity import IdentityError
import test_fiscal_vault as vault_fixtures


class DelegationTests(vault_fixtures.VaultTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048);now=datetime.now(timezone.utc)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'REPRESENTANTE FICTICIO'),x509.NameAttribute(NameOID.SERIAL_NUMBER,'IDCDO-00000000001')])
        cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=2)).add_extension(x509.KeyUsage(True,False,False,False,False,False,False,False,False),critical=True).sign(key,hashes.SHA256())
        cls.delegated=pkcs12.serialize_key_and_certificates(b'qa-only',key,cert,None,serialization.BestAvailableEncryption(b'fiscal-ficticio'))

    def valid(self,tenant,company,tax,thumb,identifiers):
        return VerifiedDelegation(tenant,company,tax,thumb,identifiers[0],self.identity.clock()+3600,'DGII-FIXTURE-NOT-REAL')

    def test_representative_requires_trusted_verified_delegation(self):
        with self.assertRaises(IdentityError):self.vault.store(self.session,self.a,1,self.delegated,'fiscal-ficticio')
        self.vault.resolve_delegation=self.valid
        result=self.vault.store(self.session,self.a,1,self.delegated,'fiscal-ficticio')
        self.assertEqual(self.vault._load_for_worker(self.a,1,result['certificate_id']),(self.delegated,'fiscal-ficticio'))
        self.assertFalse(self.vault.status(self.session,self.a,1)['emission_enabled'])

    def test_owner_dict_expired_and_other_company_authorizations_rejected(self):
        for change in ({'company_id':2},{'tenant_id':self.b},{'tax_id':'987654321'},
                       {'certificate_sha256':'0'*64},{'holder_identifier':'IDCDO-00000000002'},
                       {'valid_until':self.identity.clock()-1}):
            self.vault.resolve_delegation=lambda *args,change=change:replace(self.valid(*args),**change)
            with self.assertRaises(IdentityError):self.vault.store(self.session,self.a,1,self.delegated,'fiscal-ficticio')
        self.vault.resolve_delegation=lambda *args:{'verified':True}
        with self.assertRaises(IdentityError):self.vault.store(self.session,self.a,1,self.delegated,'fiscal-ficticio')

    def test_revoked_delegation_prevents_worker_access(self):
        self.vault.resolve_delegation=self.valid
        result=self.vault.store(self.session,self.a,1,self.delegated,'fiscal-ficticio')
        self.vault.resolve_delegation=lambda *args:None
        with self.assertRaises(IdentityError):self.vault._load_for_worker(self.a,1,result['certificate_id'])

    def test_changed_tax_id_and_thumbprint_prevent_worker_access(self):
        result=self.vault.store(self.session,self.a,1,self.p12,'fiscal-ficticio')
        self.vault.resolve_company=lambda *args:{'tax_id':'987654321'}
        with self.assertRaises(IdentityError):self.vault._load_for_worker(self.a,1,result['certificate_id'])
        self.vault.resolve_company=lambda *args:{'tax_id':'123456789'}
        with self.identity.db:self.identity.db.execute('UPDATE fiscal_certificates SET thumbprint=? WHERE id=?',('0'*64,result['certificate_id']))
        with self.assertRaises(IdentityError):self.vault._load_for_worker(self.a,1,result['certificate_id'])
