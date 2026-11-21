"""Copy only Jenifer's Microsoft IMAP history into a separate Zoho archive.

Source is always read-only; no SMTP, expunge, delete, or automatic replies.
Credentials are read in RAM from the existing restricted native configuration.
Every copied message is read back and compared semantically, including attachments.
"""
import argparse
import base64
import datetime as dt
import email
import email.policy
import email.utils
from email.message import EmailMessage
import fcntl
import hashlib
import imaplib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl

ROOT = 'Historial Microsoft Jenifer'


def decode_folder(value):
    if value.startswith('"'):
        value = re.sub(r'\\(.)', r'\1', value[1:-1])
    def replace(match):
        data = match[1]
        if not data:
            return '&'
        return base64.b64decode(data.replace(',', '/') + '=' * (-len(data) % 4)).decode('utf-16-be')
    return re.sub(r'&([^-]*)-', replace, value)


def encode_folder(value):
    def replace(match):
        return '&' + base64.b64encode(match[0].encode('utf-16-be')).decode().rstrip('=').replace('/', ',') + '-'
    return re.sub(r'[^\x20-\x7e]+', replace, value.replace('&', '&-'))


def quoted(value):
    return '"' + encode_folder(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def folders(client):
    typ, data = client.list()
    if typ != 'OK':
        raise RuntimeError('Folder inventory failed')
    result = []
    for line in data:
        match = re.match(rb'\(([^)]*)\)\s+(?:"([^"]*)"|NIL)\s+(.+)$', line)
        if not match:
            raise RuntimeError('Unsupported folder listing')
        flags, delimiter, name = match.groups()
        if b'\\noselect' not in flags.lower():
            result.append((decode_folder(name.decode('ascii')), (delimiter or b'/').decode('ascii')))
    return result


def select(client, folder):
    typ, _ = client.select(quoted(folder), readonly=True)
    if typ != 'OK':
        raise RuntimeError('Cannot select folder: ' + folder)
    return client.response('UIDVALIDITY')[1][0].decode()


def uids(client, *criteria):
    typ, data = client.uid('search', None, *(criteria or ('ALL',)))
    if typ != 'OK':
        raise RuntimeError('Cannot inventory messages')
    return (data[0] or b'').decode().split()


def fetch(client, uid):
    typ, data = client.uid('fetch', str(uid), '(UID FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[])')
    payload = next((item for item in data if isinstance(item, tuple)), None)
    if typ != 'OK' or not payload:
        raise RuntimeError('Cannot retrieve message UID ' + str(uid))
    meta, raw = payload
    # Exchange's RFC822.SIZE can be a cached estimate before MIME conversion.
    # The literal is the exact transmitted octet count; verify that, then read back.
    literal = re.search(rb'\{(\d+)\}$', meta)
    if not literal or int(literal[1]) != len(raw):
        raise RuntimeError('Message literal size verification failed')
    date = re.search(rb'INTERNALDATE ("[^"]+")', meta)
    flags = re.search(rb'FLAGS \(([^)]*)\)', meta)
    keep = [v.decode() for v in (flags[1].split() if flags else [])
            if v.lower() in (b'\\seen', b'\\answered', b'\\flagged', b'\\draft')]
    return raw, date[1].decode() if date else None, '(' + ' '.join(keep) + ')'


def identity(raw, _depth=0):
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    original_hash = str(msg.get('X-UNO360X-Archive-Original-SHA256', '')).strip()
    if _depth < 2 and re.fullmatch(r'[a-f0-9]{64}', original_hash):
        for part in msg.walk():
            if part.get_filename() == 'Original Microsoft.eml':
                original = part.get_payload(decode=True)
                if original and hashlib.sha256(original).hexdigest() == original_hash:
                    return identity(original, _depth + 1)
    message_id = str(msg.get('Message-ID', '')).strip()
    headers = []
    for name in ('Message-ID', 'From', 'To', 'Cc', 'Bcc', 'Reply-To', 'Subject', 'Date',
                 'In-Reply-To', 'References'):
        values = [' '.join(str(v).split()) for v in msg.get_all(name, [])]
        if name == 'Date' and values:
            try:
                values = [email.utils.parsedate_to_datetime(values[0]).astimezone(dt.timezone.utc).isoformat()]
            except (TypeError, ValueError, OverflowError):
                pass
        headers.append((name, values))
    parts = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        body = part.get_payload(decode=True)
        if body is None:
            body = str(part.get_payload()).encode('utf-8', 'surrogatepass')
        if part.get_content_maintype() == 'text':
            try:
                body = body.decode(part.get_content_charset() or 'ascii').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
            except (UnicodeError, LookupError):
                pass
        parts.append((part.get_content_type(), str(part.get_filename() or ''),
                      part.get_content_disposition(), hashlib.sha256(body).hexdigest()))
    digest = hashlib.sha256(json.dumps([headers, parts], ensure_ascii=True).encode()).hexdigest()
    return message_id, digest


def archive_wrapper(raw):
    """Portable MIME plus byte-exact original; some Exchange MIME is unreadable in Zoho."""
    original = email.message_from_bytes(raw, policy=email.policy.default)
    message = EmailMessage(policy=email.policy.SMTP)
    for name in ('From', 'To', 'Cc', 'Bcc', 'Reply-To', 'Subject', 'Date',
                 'In-Reply-To', 'References'):
        value = original.get(name)
        if value is not None:
            message[name] = str(value).replace('\r', '').replace('\n', ' ')
    original_id = original.get('Message-ID')
    if original_id:
        message['X-UNO360X-Original-Message-ID'] = str(original_id).replace('\r', '').replace('\n', ' ')
    message['Message-ID'] = '<uno360x-history-%s@uno360x.local>' % identity(raw)[1]
    message['X-UNO360X-Archive-Original-SHA256'] = hashlib.sha256(raw).hexdigest()
    def text(part):
        try:
            return str(part.get_content()) if part else ''
        except (LookupError, UnicodeError, TypeError):
            return ''
    plain = text(original.get_body(preferencelist=('plain',)))
    html = text(original.get_body(preferencelist=('html',)))
    message.set_content(plain or 'Correo histórico de Microsoft. El mensaje original completo está adjunto como archivo EML.')
    if html:
        message.add_alternative(html, subtype='html')
    for part in original.walk():
        if part.is_multipart() or not part.get_filename():
            continue
        content = part.get_payload(decode=True)
        if content is not None:
            filename = str(part.get_filename()).replace('\r', '').replace('\n', ' ')
            message.add_attachment(content, maintype=part.get_content_maintype(),
                                   subtype=part.get_content_subtype(), filename=filename)
    message.add_attachment(raw, maintype='application', subtype='octet-stream',
                           filename='Original Microsoft.eml')
    return message.as_bytes()


def ensure_folder(client, name, known):
    parent = []
    for segment in name.split('/'):
        parent.append(segment)
        value = '/'.join(parent)
        if value in known:
            continue
        typ, data = client.create(quoted(value))
        if typ != 'OK':
            raise RuntimeError('Cannot create archive folder: ' + value + ' ' + str(data)[:350])
        known.add(value)


if __name__ == '__main__':
    # Keep the original entry point, with explicit --apply or --verify-only.
    from migrate_mail_history_parallel import main
    main()
