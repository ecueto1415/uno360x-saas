"""Run on the Linux host with WORKER_SOURCE pointing at the staged worker."""
import importlib.util
import os
from pathlib import Path
import tempfile
from email.message import EmailMessage
import unittest
from unittest.mock import MagicMock, patch

worker = None
if os.environ.get('WORKER_SOURCE'):
    spec = importlib.util.spec_from_file_location('mail_worker', os.environ['WORKER_SOURCE'])
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)


@unittest.skipUnless(worker, 'Requires staged Linux worker via WORKER_SOURCE')
class ZohoTransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = worker.Store(Path(self.directory.name) / 'state.sqlite')
        self.imap = MagicMock()
        self.imap.select.return_value = ('OK', [b'3'])
        self.imap.list.return_value = ('OK', [b'(\\Sent) "/" "Enviado"'])
        self.imap.response.return_value = ('UIDVALIDITY', [b'29'])
        self.imap.uid.return_value = ('OK', [b'1 2 3'])
        self.imap.append.return_value = ('OK', [])
        self.smtp = MagicMock()
        self.smtp.noop.return_value = (250, b'OK')
        self.smtp.docmd.return_value = (235, b'OK')
        self.smtp.send_message.return_value = {}
        self.patches = [patch.object(worker.imaplib, 'IMAP4_SSL', return_value=self.imap),
                        patch.object(worker.smtplib, 'SMTP', return_value=self.smtp),
                        patch.object(worker, 'access_token', return_value='test-token'),
                        patch.object(worker, 'COPIES', [])]
        for item in self.patches:
            item.start()
        self.transport = None

    def tearDown(self):
        if self.transport:
            self.transport.close()
        for item in reversed(self.patches):
            item.stop()
        self.store.db.close()
        self.directory.cleanup()

    def connect(self, provider='zoho'):
        self.transport = worker.Microsoft({'provider': provider, 'password': 'test-only'}, self.store)
        return self.transport

    def test_zoho_uses_verified_tls_and_login(self):
        self.connect()
        self.assertEqual(worker.imaplib.IMAP4_SSL.call_args.args[:2], ('imappro.zoho.com', 993))
        self.assertTrue(worker.imaplib.IMAP4_SSL.call_args.kwargs['ssl_context'].check_hostname)
        self.imap.login.assert_called_once_with(worker.MAILBOX, 'test-only')
        self.imap.select.assert_called_once_with('INBOX', readonly=True)
        self.smtp.starttls.assert_called_once()
        self.assertTrue(self.smtp.starttls.call_args.kwargs['context'].check_hostname)
        self.smtp.login.assert_called_once_with(worker.MAILBOX, 'test-only')

    def test_send_and_retry_do_not_duplicate_or_append_sent(self):
        transport = self.connect()
        plan = {'email_to': 'ecueto@outsolutech.com', 'subject': 'Test', 'body_html': '<p>Test</p>'}
        self.assertEqual(transport.send(plan, 'test-once'), 'accepted')
        self.assertEqual(transport.send(plan, 'test-once'), 'duplicate')
        self.smtp.send_message.assert_called_once()
        self.imap.append.assert_not_called()

    def test_uncertain_delivery_cannot_be_retried(self):
        transport = self.connect()
        self.smtp.send_message.side_effect = OSError('test disconnect')
        plan = {'email_to': 'ecueto@outsolutech.com', 'body_html': '<p>Test</p>'}
        with self.assertRaises(RuntimeError):
            transport.send(plan, 'test-uncertain')
        self.assertEqual(transport.send(plan, 'test-uncertain'), 'duplicate')
        self.assertEqual(self.store.needs_review(), 1)
        self.smtp.send_message.assert_called_once()

    def test_new_provider_baselines_without_historical_replies(self):
        self.store.set('inbox:uid', '9000')
        self.store.set('inbox:validity', '11')
        transport = self.connect()
        self.assertEqual(transport.inbound({}, live=True), 0)
        self.assertEqual(self.store.get('zoho:inbox:uid'), '3')
        self.assertEqual(self.store.get('zoho:inbox:validity'), '29')
        self.assertEqual(self.store.get('inbox:uid'), '9000')
        self.smtp.send_message.assert_not_called()

    def test_dry_run_does_not_initialize_checkpoint(self):
        self.assertEqual(self.connect().inbound({}, live=False), 0)
        self.assertIsNone(self.store.get('zoho:inbox:uid'))

    def test_existing_dispatch_dedup_is_shared_across_providers(self):
        self.store.reserve('ibids:existing', '<test@example.com>', {'email_to': 'ecueto@outsolutech.com'})
        self.assertEqual(self.connect().send({'email_to': 'ecueto@outsolutech.com'}, 'ibids:existing'), 'duplicate')
        self.smtp.send_message.assert_not_called()

    def test_microsoft_keeps_original_checkpoints_and_sent_append(self):
        transport = self.connect('microsoft')
        transport.store.set('inbox:uid', '21')
        self.assertEqual(self.store.get('inbox:uid'), '21')
        self.assertIsNone(self.store.get('zoho:inbox:uid'))
        plan = {'email_to': 'ecueto@outsolutech.com', 'body_html': '<p>Test</p>'}
        self.assertEqual(transport.send(plan, 'microsoft-test'), 'accepted')
        self.imap.append.assert_called_once()
        self.imap.authenticate.assert_called_once()
        self.imap.login.assert_not_called()

    def test_hybrid_keeps_microsoft_inbox_but_sends_via_zoho(self):
        self.transport = worker.Microsoft({'provider': 'zoho', 'inbox_provider': 'microsoft',
                                          'password': 'test-only'}, self.store)
        self.assertEqual(worker.imaplib.IMAP4_SSL.call_args.args[0], 'outlook.office365.com')
        self.assertEqual(worker.smtplib.SMTP.call_args.args[0], 'smtppro.zoho.com')
        self.imap.authenticate.assert_called_once()
        self.smtp.login.assert_called_once()
        self.transport.store.set('inbox:uid', '42')
        self.assertEqual(self.store.get('inbox:uid'), '42')
        self.assertEqual(self.transport.send({'email_to': 'ecueto@outsolutech.com',
                                             'body_html': '<p>Test</p>'}, 'hybrid-test'), 'accepted')
        self.imap.append.assert_called_once()

    def test_zoho_receiver_authenticated_aligned_spf_is_recognized(self):
        worker.COPIES = ['ecueto@outsolutech.com']
        msg = EmailMessage()
        msg['Authentication-Results'] = 'mx.zohomail.com; spf=pass smtp.mailfrom=ecueto@outsolutech.com; arc=pass'
        self.assertTrue(worker.trusted_internal(msg, 'ecueto@outsolutech.com'))

    def test_zoho_rejects_forged_later_headers_and_ms_internal_marker(self):
        worker.COPIES = ['ecueto@outsolutech.com']
        msg = EmailMessage()
        msg['Authentication-Results'] = 'mx.zohomail.com; spf=fail smtp.mailfrom=ecueto@outsolutech.com'
        msg['Authentication-Results'] = 'fake; dmarc=pass header.from=outsolutech.com'
        msg['X-MS-Exchange-Organization-AuthAs'] = 'internal'
        self.assertFalse(worker.trusted_internal(msg, 'ecueto@outsolutech.com'))

    def test_zoho_rejects_spf_pass_for_an_unaligned_domain(self):
        worker.COPIES = ['ecueto@outsolutech.com']
        msg = EmailMessage()
        msg['Authentication-Results'] = 'mx.zohomail.com; spf=pass smtp.mailfrom=ecueto@outsolutech.com.attacker.test'
        self.assertFalse(worker.trusted_internal(msg, 'ecueto@outsolutech.com'))


if __name__ == '__main__':
    unittest.main()
