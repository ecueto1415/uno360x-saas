import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import Mock

migration = None
if os.name == 'posix':
    path = Path(__file__).resolve().parents[1] / 'integrations/jenifer/migrate_mail_history.py'
    if not path.exists():
        path = Path('/tmp/migrate_mail_history.py')
    spec = importlib.util.spec_from_file_location('mail_history', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)


@unittest.skipUnless(migration, 'Linux migration helper')
class HistoryIdentityTests(unittest.TestCase):
    def test_transport_headers_do_not_duplicate_same_message(self):
        raw = b'Message-ID: <test@example.com>\r\nFrom: a@example.com\r\nTo: b@example.com\r\nSubject: Test\r\n\r\nBody\r\n'
        self.assertEqual(migration.identity(raw), migration.identity(b'Received: from relay\r\nDKIM-Signature: test\r\n' + raw))

    def test_same_message_id_with_different_content_is_preserved(self):
        raw = b'Message-ID: <test@example.com>\r\nSubject: Test\r\n\r\nBody\r\n'
        self.assertNotEqual(migration.identity(raw), migration.identity(raw.replace(b'Body', b'Different body')))

    def test_attachment_change_is_not_skipped(self):
        from email.message import EmailMessage
        a = EmailMessage(); a['Message-ID'] = '<test@example.com>'; a.set_content('Body')
        a.add_attachment(b'original', maintype='application', subtype='pdf', filename='factura.pdf')
        b = EmailMessage(); b['Message-ID'] = '<test@example.com>'; b.set_content('Body')
        b.add_attachment(b'changed', maintype='application', subtype='pdf', filename='factura.pdf')
        self.assertNotEqual(migration.identity(a.as_bytes()), migration.identity(b.as_bytes()))

    def test_folder_unicode_and_ampersand_round_trip(self):
        for name in ['INBOX', 'Días festivos de España', 'A&B/Facturación', 'Prueba 😀']:
            self.assertEqual(migration.decode_folder(migration.encode_folder(name)), name)

    def test_portable_archive_retains_exact_original_and_identity(self):
        raw = b'Message-ID: <test@example.com>\r\nFrom: a@example.com\r\nSubject: Test\r\n\r\nOriginal body\r\n'
        wrapped = migration.archive_wrapper(raw)
        self.assertEqual(migration.identity(raw), migration.identity(wrapped))
        import email
        import email.policy
        msg = email.message_from_bytes(wrapped, policy=email.policy.default)
        originals = [part.get_payload(decode=True) for part in msg.walk()
                     if part.get_filename() == 'Original Microsoft.eml']
        self.assertEqual(originals, [raw])

    def test_quoted_folder_unescapes(self):
        self.assertEqual(migration.decode_folder('"A\\"B"'), 'A"B')

    def test_download_uses_exact_literal_not_exchange_size_estimate(self):
        client = Mock();raw=b'complete message'
        meta=('1 (UID 14 FLAGS (\\Seen) INTERNALDATE "05-Sep-2026 10:15:25 -0400" RFC822.SIZE 999 BODY[] {%s}' % len(raw)).encode()
        client.uid.return_value=('OK',[(meta,raw),b')'])
        self.assertEqual(migration.fetch(client,'14')[0],raw)
        self.assertIn('BODY.PEEK[]',client.uid.call_args.args[2])

    def test_truncated_download_is_rejected(self):
        client=Mock();client.uid.return_value=('OK',[(b'1 (UID 14 RFC822.SIZE 999 BODY[] {99}',b'truncated'),b')'])
        with self.assertRaises(RuntimeError):
            migration.fetch(client,'14')


if __name__ == '__main__':
    unittest.main()
