import base64
import importlib.util
from pathlib import Path
import unittest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree
import test_fiscal_vault as vault_fixtures

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('fiscal_fixture_'+name,ROOT/'addons/uno360x_ecf_core'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
crypto=module('crypto');builder=module('builder');policy=module('policy')


class FiscalXMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vault_fixtures.VaultTests.setUpClass()
        cls.p12=vault_fixtures.VaultTests.p12
        cls.key,cls.certificate=crypto.load_identity(cls.p12,b'fiscal-ficticio')

    def test_e31_and_e45_produce_signed_xml_matching_schema(self):
        data={'document_type':'31','currency':'DOP','move_type':'out_invoice','rounding_method':'round_per_line',
              'invoice_date':'2026-11-04','test_expiry':'2027-12-31','income_type':'01','payment_type':'1',
              'seller':{'rnc':'123456789','name':'FICTICIO','address':'Solo prueba'},'buyer':{'rnc':'987654321','name':'FICTICIO'},
              'lines':[{'name':'Prueba','quantity':1,'price_unit':100,'discount':0,'goods_service':'2','tax_rate':18,'subtotal':100}],
              'amount_untaxed':100,'amount_tax':18,'amount_total':118}
        for kind in ('31','45'):
            data['document_type']=kind
            xml=crypto.sign_xml(builder.build_invoice(data,'E'+kind+'0000000001'),self.p12,b'fiscal-ficticio')
            self.assertTrue(xml.startswith(b'<?xml'))
            builder.validate_signed(xml)
            self.assertTrue(crypto.verify_xml(xml,self.certificate))
            with self.assertRaises(Exception):crypto.verify_xml(xml.replace(b'<MontoTotal>118.00</MontoTotal>',b'<MontoTotal>119.00</MontoTotal>'),self.certificate)

    def test_default_namespace_xmldsig_is_verified_without_algorithm_fallback(self):
        xml=crypto.sign_xml(b'<SemillaModel><valor>FICTICIA</valor><fecha>2026-11-04</fecha></SemillaModel>',self.p12,b'fiscal-ficticio')
        xml=xml.replace(b'ds:',b'').replace(b'xmlns:ds=',b'xmlns=')
        root=crypto.parse(xml);sig=root.find('{%s}Signature'%crypto.DS);info=sig.find('{%s}SignedInfo'%crypto.DS)
        sig.find('{%s}SignatureValue'%crypto.DS).text=base64.b64encode(self.key.sign(crypto.canonical_signed_info(info),padding.PKCS1v15(),hashes.SHA256())).decode()
        signed=etree.tostring(root)
        self.assertTrue(crypto.verify_xml(signed,self.certificate))
        with self.assertRaises(ValueError):crypto.verify_xml(signed.replace(b'FICTICIA',b'CAMBIADA'),self.certificate)

    def test_xml_work_does_not_unlock_transmission(self):
        with self.assertRaises(RuntimeError):policy.transmit()
