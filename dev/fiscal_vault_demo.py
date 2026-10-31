"""Persist/reopen only synthetic certificate custody in a disposable WSL fixture."""
from datetime import datetime,timedelta,timezone
import json,os,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from control.identity import IdentityService
from control.fiscal_vault import FiscalVault,DirectoryKeys

def main():
    if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise RuntimeError('Solo WSL root.')
    with tempfile.TemporaryDirectory(prefix='uno360x-fiscal-fixture-') as directory:
        root=Path(directory);mail=[]
        identity=IdentityService(root/'control.sqlite3',mail.append)
        identity.register('owner@example.test');identity.complete_registration(mail[-1]['token'],'Clave fiscal ficticia 2026')
        session=identity.login('owner@example.test','Clave fiscal ficticia 2026')['session']
        tenant=identity.create_company(session,'vault-ficticio',[],'one')['id']
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048);now=datetime.now(timezone.utc)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'FICTICIO NO USAR PARA EMISION'),x509.NameAttribute(NameOID.SERIAL_NUMBER,'123456789')])
        cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=10)).add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,encipher_only=False,decipher_only=False),critical=True).sign(key,hashes.SHA256())
        p12=pkcs12.serialize_key_and_certificates(b'fictional',key,cert,None,serialization.BestAvailableEncryption(b'clave-ficticia'))
        resolver=lambda tid,cid:{'tax_id':'123456789'} if tid==tenant and cid==1 else None
        vault=FiscalVault(identity,DirectoryKeys(root/'keys'),resolver)
        version=vault.store(session,tenant,1,p12,'clave-ficticia')['certificate_id']
        identity.close()
        identity=IdentityService(root/'control.sqlite3',mail.append)
        try:
            vault=FiscalVault(identity,DirectoryKeys(root/'keys'),resolver)
            assert vault._load_for_worker(tenant,1,version)==(p12,'clave-ficticia')
            assert not vault.status(session,tenant,1)['emission_enabled']
            print(json.dumps({'synthetic_only':True,'encrypted_persistence_reopened':True,'company_identity_checked':True,'emission_enabled':False,'real_dgii_credentials_used':False},indent=2))
        finally:identity.close()

if __name__=='__main__':main()
