"""Add a selectable Zoho transport to the native Jenifer worker.

Does not select the provider, enable jobs, change routing, or store credentials.
Passwords remain in the restricted ir.mail_server record, read only into RAM.
"""
import ast
import difflib
from pathlib import Path


def patch(source):
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('Worker source differs from reviewed transport revision')
        source = source.replace(old, new, 1)

    replace("    incoming = env['fetchmail.server'].sudo().browse(1)", """    provider = p.get_param('jenifer_directa.mail_provider', 'microsoft')
    if provider == 'zoho':
        server_id = int(p.get_param('jenifer_directa.zoho_server_id', '4'))
        server = env['ir.mail_server'].sudo().browse(server_id).exists()
        if (not server or server.smtp_user.casefold() != MAILBOX.casefold()
                or server.smtp_host != 'smtppro.zoho.com' or server.smtp_port != 587
                or server.smtp_encryption != 'starttls_strict'
                or server.smtp_authentication != 'login' or not server.smtp_pass):
            raise RuntimeError('Zoho mailbox configuration incomplete')
        inbox_provider = p.get_param('jenifer_directa.inbox_provider', 'zoho')
        if inbox_provider not in ('microsoft', 'zoho'):
            raise RuntimeError('Unsupported inbox provider')
        result = {'provider': 'zoho', 'inbox_provider': inbox_provider, 'password': server.smtp_pass}
        if inbox_provider == 'microsoft':
            incoming = env['fetchmail.server'].sudo().browse(1)
            if incoming.user.casefold() != MAILBOX.casefold():
                raise RuntimeError('Microsoft inbox mismatch')
            result.update(client_id=p.get_param('microsoft_outlook_client_id'),
                          client_secret=p.get_param('microsoft_outlook_client_secret'),
                          imap_refresh=incoming.microsoft_outlook_refresh_token)
        return result
    if provider != 'microsoft':
        raise RuntimeError('Unsupported mailbox provider')
    incoming = env['fetchmail.server'].sudo().browse(1)""")
    replace('        self.store = store\n        imap_token = access_token(config, store, \'imap\')', """        self.provider = config.get('provider', 'microsoft')
        self.inbox_provider = config.get('inbox_provider', self.provider)
        self.store = MailboxStore(store, self.inbox_provider)
        imap_token = None if self.inbox_provider == 'zoho' else access_token(config, store, 'imap')""")
    replace("        self.imap = imaplib.IMAP4_SSL('outlook.office365.com', 993, ssl_context=ssl.create_default_context(), timeout=30)\n        self.imap.authenticate('XOAUTH2', lambda _: ('user=%s\\x01auth=Bearer %s\\x01\\x01' % (MAILBOX, imap_token)).encode())", """        host = 'imappro.zoho.com' if self.inbox_provider == 'zoho' else 'outlook.office365.com'
        self.imap = imaplib.IMAP4_SSL(host, 993, ssl_context=ssl.create_default_context(), timeout=30)
        if self.inbox_provider == 'zoho':
            self.imap.login(MAILBOX, config['password'])
        else:
            self.imap.authenticate('XOAUTH2', lambda _: ('user=%s\\x01auth=Bearer %s\\x01\\x01' % (MAILBOX, imap_token)).encode())""")
    replace("    def _connect_smtp(self):\n        smtp_token = access_token(self.config, self.store, 'smtp')", """    def _connect_smtp(self):
        if self.provider == 'zoho':
            self.smtp = smtplib.SMTP('smtppro.zoho.com', 587, timeout=30)
            self.smtp.ehlo()
            self.smtp.starttls(context=ssl.create_default_context())
            self.smtp.ehlo()
            self.smtp.login(MAILBOX, self.config['password'])
            return
        smtp_token = access_token(self.config, self.store, 'smtp')""")
    replace("            typ, _ = self.imap.append(self.sent_box, '\\\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())", """            # Zoho SMTP stores its own Sent copy. Never APPEND a second copy.
            if self.provider == 'zoho' and self.inbox_provider == 'zoho':
                typ = 'OK'
            else:
                typ, _ = self.imap.append(self.sent_box, '\\\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())""")
    replace("            key = 'inbound:%s:%s' % (validity, uid)", """            key = ('inbound:zoho:%s:%s' if self.inbox_provider == 'zoho'
                   else 'inbound:%s:%s') % (validity, uid)""")
    replace('class Microsoft:\n', '''class MailboxStore:
    """Separate mailbox UID checkpoints; keep all dispatch deduplication shared."""
    def __init__(self, store, provider):
        self.base, self.provider = store, provider

    def _key(self, key):
        if self.provider == 'zoho' and key.startswith('inbox:'):
            return 'zoho:' + key
        return key

    def get(self, key):
        return self.base.get(self._key(key))

    def set(self, key, value):
        return self.base.set(self._key(key), value)

    def __getattr__(self, name):
        return getattr(self.base, name)


class Microsoft:
''')
    replace("    auth = str(message.get('Authentication-Results', ''))\n    dmarc = re.search", """    auth = str(message.get('Authentication-Results', ''))
    if auth.split(';', 1)[0].strip().casefold() == 'mx.zohomail.com':
        # Only the receiving provider's first Authentication-Results header counts.
        # SPF-aligned mail is valid even when the domain has no DMARC policy yet.
        for section in auth.split(';')[1:]:
            if re.match(r'\\s*spf=pass\\b', section, re.I):
                match = re.search(r'\\bsmtp\\.mailfrom=["<]?([^\\s;>"()]+)', section, re.I)
                if match and match[1].rsplit('@', 1)[-1].casefold() == 'outsolutech.com':
                    return True
            if re.match(r'\\s*dkim=pass\\b', section, re.I):
                if re.search(r'\\bheader\\.d=outsolutech\\.com(?=[;\\s]|$)', section, re.I):
                    return True
            if re.match(r'\\s*dmarc=pass\\b', section, re.I):
                if re.search(r'\\b(?:header\\.from|fromdomain)=outsolutech\\.com(?=[;\\s]|$)', section, re.I):
                    return True
        return False
    dmarc = re.search""")
    ast.parse(source)
    return source


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    before = args.source.read_text(encoding='utf-8-sig')
    after = patch(before)
    args.output.write_text(after, encoding='utf-8')
    print(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                     fromfile='worker.py.before', tofile='worker.py')))
