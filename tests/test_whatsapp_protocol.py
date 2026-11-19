import importlib.util
from pathlib import Path
import hashlib
import hmac
import unittest

path=Path(__file__).resolve().parents[1]/'addons/uno360x_whatsapp/protocol.py'
spec=importlib.util.spec_from_file_location('wa_protocol',path)
wa=importlib.util.module_from_spec(spec);spec.loader.exec_module(wa)


class WhatsAppProtocolTests(unittest.TestCase):
    def test_template_is_explicit_and_has_no_payment_action(self):
        result=wa.template_payload('+18095550101','uno360x_aviso_factura','es',
            ['Empresa ficticia','Cliente ficticio','E310000000001','DOP','100.00','19/11/2026'])
        self.assertEqual(result['to'],'18095550101')
        self.assertEqual(result['type'],'template')
        self.assertEqual(result['template']['components'][0]['parameters'][4],{'type':'text','text':'100.00'})
        self.assertNotIn('token',result)
        self.assertNotIn('payment',result)
    def test_phone_requires_country_and_rejects_markup(self):
        self.assertEqual(wa.phone('+1 (809) 555-0101'),'+18095550101')
        for value in ('8095550101','+0123456789','https://example.test','+18095550101\nDROP','+123',''):
            with self.assertRaises(ValueError):wa.phone(value)
    def test_bad_template_and_language(self):
        for name,language in [('Template Name','es'),('ok','javascript'),('../secret','es')]:
            with self.assertRaises(ValueError):wa.template_payload('+18095550101',name,language,['x']*6)
    def test_parameter_count_and_control_characters(self):
        for values in (['x']*5,['x']*7,['a\nb']*6,['x'*501]*6,['']*6):
            with self.assertRaises(ValueError):wa.template_payload('+18095550101','ok','es',values)
    def test_webhook_signature_detects_tampering(self):
        secret=b'local-test-secret-not-a-provider-key'
        body=b'{"entry":[]}'
        signature='sha256='+hmac.new(secret,body,hashlib.sha256).hexdigest()
        self.assertTrue(wa.verify_signature(body,signature,secret))
        self.assertFalse(wa.verify_signature(body+b' ',signature,secret))
        self.assertFalse(wa.verify_signature(body,signature,b'wrong-secret-value'))
        self.assertFalse(wa.verify_signature(body,'',secret))


if __name__=='__main__':unittest.main()
