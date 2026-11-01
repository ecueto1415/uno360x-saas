import unittest
from unittest.mock import patch, MagicMock
from control.mail_delivery import SMTPDelivery


class MailDeliveryTests(unittest.TestCase):
    def config(self):
        return dict(host='smtp.provider.example',port=465,security='ssl',username='new-saas-account',password='synthetic-only',
                    from_address='pruebas@uno360x.com',public_origin='https://app.uno360x.com',independent_saas_mailbox=True)
    def test_tls_transport_and_one_time_fragment_link_without_real_network(self):
        client=MagicMock();client.__enter__.return_value=client
        with patch('control.mail_delivery.smtplib.SMTP_SSL',return_value=client) as connect:
            SMTPDelivery(self.config())({'purpose':'verify','email':'recipient@example.com','token':'A'*43})
        self.assertTrue(connect.call_args.kwargs['context'].check_hostname)
        message=client.send_message.call_args.args[0]
        self.assertEqual(message['From'],'pruebas@uno360x.com')
        self.assertIn('/prueba/confirmar#token='+'A'*43,message.get_content())
        self.assertNotIn('synthetic-only',message.as_string())
    def test_starttls_precedes_authentication(self):
        config=self.config();config.update(port=587,security='starttls')
        client=MagicMock();client.__enter__.return_value=client
        with patch('control.mail_delivery.smtplib.SMTP',return_value=client):
            SMTPDelivery(config)({'purpose':'reset','email':'recipient@example.com','token':'B'*43})
        names=[call[0] for call in client.mock_calls]
        self.assertLess(names.index('starttls'),names.index('login'))
    def test_plaintext_wrong_domain_production_reuse_flag_and_test_recipients_rejected(self):
        for replacement in [dict(port=25,security='plain'),dict(from_address='existing@outsolutech.com'),
                            dict(public_origin='http://app.uno360x.com'),dict(public_origin='https://uno360x.com.evil.example'),
                            dict(independent_saas_mailbox=False),dict(host='host\r\nInjected')]:
            config=self.config();config.update(replacement)
            with self.assertRaises(ValueError):SMTPDelivery(config)
        with patch('control.mail_delivery.smtplib.SMTP_SSL') as transport:
            with self.assertRaises(ValueError):SMTPDelivery(self.config())({'purpose':'verify','email':'fixture@example.test','token':'A'*43})
            transport.assert_not_called()
