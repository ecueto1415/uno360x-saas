"""Bounded parallel destination copy using the verified history migration helpers.

No SMTP. Microsoft is selected read-only. Three independent Zoho IMAP sessions
copy archive data while shared identity locks prevent duplicate messages.
"""
import concurrent.futures
import argparse
import datetime as dt
import fcntl
import hashlib
from email.parser import BytesHeaderParser
import importlib.util
import imaplib
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import threading
import time

import migrate_mail_history as mail


def destination(folder):
    names = {'INBOX': 'Recibidos', 'Archivo': 'Archivo', 'Bandeja de salida': 'Salida',
             'Borradores': 'Borradores', 'Calendario': 'Calendario',
             'Calendario/Cumpleaños': 'Cumpleanos',
             'Calendario/Días festivos de España': 'Festivos', 'Contactos': 'Contactos',
             'Correo no deseado': 'No deseado', 'Elementos eliminados': 'Eliminados MS',
             'Elementos enviados': 'Enviados MS', 'Historial de conversaciones': 'Chats MS',
             'Journal': 'Diario', 'Notas': 'Notas', 'Tareas': 'Tareas'}
    if folder not in names:
        raise RuntimeError('Unreviewed source folder mapping: ' + folder)
    return mail.ROOT + '/' + names[folder]


class Copier:
    def __init__(self, mailbox, password, ledger, index, known_folders, verify_only=False):
        self.mailbox, self.password, self.ledger = mailbox, password, ledger
        self.index, self.known_folders = index, known_folders
        self.local = threading.local()
        self.verify_only = verify_only
        self.guard = threading.Lock()
        self.identity_locks = {}
        self.connections = []

    def context(self):
        if not hasattr(self.local, 'client'):
            client = imaplib.IMAP4_SSL('imappro.zoho.com', 993,
                                     ssl_context=ssl.create_default_context(), timeout=60)
            client.login(self.mailbox, self.password)
            db = sqlite3.connect(self.ledger, timeout=30, check_same_thread=False)
            self.local.client, self.local.db = client, db
            with self.guard:
                self.connections.append((client, db))
        return self.local.client, self.local.db

    def locate_copy(self, client, dest, archive_id, key, receipt_uid=None):
        # Some concurrent Zoho APPEND replies report a stale UID. Never resend
        # an accepted message merely because that receipt cannot be fetched.
        for attempt in range(3):
            mail.select(client, dest)
            candidates = [receipt_uid] if receipt_uid and attempt == 0 else []
            if not candidates:
                candidates = mail.uids(client, 'HEADER', 'Message-ID', '"' + archive_id + '"')
            for candidate in candidates:
                try:
                    copied, _, _ = mail.fetch(client, candidate)
                except RuntimeError:
                    continue
                if mail.identity(copied) == key:
                    return candidate
            if attempt < 2:
                time.sleep(1)
        raise RuntimeError('Accepted archive message needs reconciliation; no resend')

    def copy(self, folder, validity, uid, raw, date, flags):
        client, db = self.context()
        mid, digest = mail.identity(raw)
        key = mid, digest
        dest = destination(folder)
        with self.guard:
            identity_lock = self.identity_locks.setdefault(key, threading.Lock())
        with identity_lock:
            with self.guard:
                found = key in self.index
            if not found and re.fullmatch(r'<[A-Za-z0-9.!#$%&\x27*+\-/=?^_`{|}~@]{1,250}>', mid) and date:
                try:
                    recent = dt.datetime.strptime(date.strip('"'), '%d-%b-%Y %H:%M:%S %z').timestamp() >= time.time() - 7200
                except (ValueError, TypeError):
                    recent = False
                if recent:
                    for name in ['INBOX', 'Enviado', 'Correo no deseado']:
                        if name not in self.known_folders:
                            continue
                        mail.select(client, name)
                        for candidate in mail.uids(client, 'HEADER', 'Message-ID', '"' + mid + '"'):
                            candidate_raw, _, _ = mail.fetch(client, candidate)
                            if mail.identity(candidate_raw) == key:
                                with self.guard:
                                    self.index[key] = (name, candidate)
                                found = True
                                break
                        if found:
                            break
            row = db.execute('SELECT status FROM copies WHERE folder=? AND validity=? AND uid=?',
                             (folder, validity, uid)).fetchone()
            status = 'verified_existing'
            if not found:
                if self.verify_only:
                    raise RuntimeError('Verification found missing content: %s UID %s' % (folder, uid))
                if row and row[0] in ('pending', 'uncertain'):
                    raise RuntimeError('Prior unconfirmed append needs reconciliation: %s UID %s' % (folder, uid))
                wrapped = mail.archive_wrapper(raw)
                archive_id = '<uno360x-history-%s@uno360x.local>' % digest
                if mail.identity(wrapped) != key:
                    raise RuntimeError('Archive conversion identity mismatch')
                db.execute('INSERT OR REPLACE INTO copies VALUES(?,?,?,?,?,?,?)',
                           (folder, validity, uid, mid, digest, dest, 'pending'))
                db.commit()
                mail.select(client, dest)
                returned = False
                try:
                    for attempt in range(3):
                        returned = False
                        typ, data = client.append(mail.quoted(dest), flags, date, wrapped)
                        returned = True
                        if typ == 'OK':
                            break
                        print(json.dumps({'event': 'append_rejected', 'folder': folder, 'uid': uid,
                                          'reply': str(data)[:350], 'attempt': attempt + 1}), flush=True)
                        if attempt == 2:
                            raise RuntimeError('Explicit IMAP rejection, message not accepted')
                        time.sleep(3 * (attempt + 1))
                        try:
                            already_stored = self.locate_copy(client, dest, archive_id, key)
                        except RuntimeError:
                            already_stored = None
                        if already_stored:
                            typ, data = 'OK', [('[APPENDUID 1 %s]' % already_stored).encode()]
                            break
                    receipt = re.search(rb'APPENDUID\s+\d+\s+(\d+)', b' '.join(data or []))
                    if not receipt:
                        raise RuntimeError('Append accepted without UID receipt')
                    target_uid = self.locate_copy(client, dest, archive_id, key, receipt[1].decode())
                except Exception:
                    state = 'rejected' if returned and typ != 'OK' else 'uncertain'
                    db.execute('UPDATE copies SET status=? WHERE folder=? AND validity=? AND uid=?',
                               (state, folder, validity, uid))
                    db.commit()
                    raise
                with self.guard:
                    self.index[key] = dest, target_uid
                status = 'verified_copy'
            with self.guard:
                resolved_folder = self.index[key][0]
            db.execute('INSERT OR REPLACE INTO copies VALUES(?,?,?,?,?,?,?)',
                       (folder, validity, uid, mid, digest, resolved_folder, status))
            db.commit()
            return status, len(raw)

    def close(self):
        for client, db in self.connections:
            try:
                client.logout()
            except Exception:
                pass
            db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.apply == args.verify_only:
        parser.error('Choose exactly one of --apply or --verify-only')
    os.umask(0o077)
    ledger = '/var/lib/jenifer-directa/microsoft-zoho-history.sqlite'
    spec = importlib.util.spec_from_file_location('history_worker', '/opt/jenifer-directa/worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    with worker.readonly_odoo() as env:
        p = env['ir.config_parameter'].sudo()
        incoming, outgoing = env['fetchmail.server'].sudo().browse(1), env['ir.mail_server'].sudo().browse(4)
        assert incoming.user.casefold() == outgoing.smtp_user.casefold() == worker.MAILBOX.casefold()
        microsoft = {'client_id': p.get_param('microsoft_outlook_client_id'),
                     'client_secret': p.get_param('microsoft_outlook_client_secret'),
                     'imap_refresh': incoming.microsoft_outlook_refresh_token}
        password = outgoing.smtp_pass
    with Path(ledger + '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = sqlite3.connect(ledger)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS source_metadata(folder TEXT,validity TEXT,uid TEXT,internal_date TEXT,flags TEXT,original_message_id TEXT,original_date TEXT,raw_sha256 TEXT,read_at TEXT,PRIMARY KEY(folder,validity,uid))')
        db.commit()
        tokens = worker.Store(worker.STATE / 'state.sqlite')
        source = target = copier = None
        try:
            token = worker.access_token(microsoft, tokens, 'imap')
            source = imaplib.IMAP4_SSL('outlook.office365.com', 993, ssl_context=ssl.create_default_context(), timeout=60)
            source.authenticate('XOAUTH2', lambda _: ('user=%s\x01auth=Bearer %s\x01\x01' % (worker.MAILBOX, token)).encode())
            target = imaplib.IMAP4_SSL('imappro.zoho.com', 993, ssl_context=ssl.create_default_context(), timeout=60)
            target.login(worker.MAILBOX, password)
            known = {name for name, _ in mail.folders(target)}
            index = {}
            archive_duplicates = 0
            archive_seen = set()
            for folder in sorted(known):
                validity = mail.select(target, folder)
                for uid in mail.uids(target):
                    if db.execute('SELECT 1 FROM excluded_dest WHERE folder=? AND validity=? AND uid=?',
                                  (folder, validity, uid)).fetchone():
                        continue
                    raw, _, _ = mail.fetch(target, uid)
                    key = mail.identity(raw)
                    if folder.startswith(mail.ROOT + '/'):
                        if key in archive_seen:
                            archive_duplicates += 1
                        archive_seen.add(key)
                    index.setdefault(key, (folder, uid))
            print(json.dumps({'event': 'target_indexed', 'messages': len(index), 'archive_duplicates': archive_duplicates}), flush=True)
            if archive_duplicates:
                raise RuntimeError('Archive duplicate requires review')
            snapshot = []
            for folder, _ in mail.folders(source):
                if folder.split('/')[0].casefold() in ('calendario', 'contactos', 'journal', 'notas', 'tareas'):
                    print(json.dumps({'event': 'non_mail_folder_retained_in_microsoft', 'folder': folder}), flush=True)
                    continue
                validity = mail.select(source, folder)
                ids = mail.uids(source)
                if args.verify_only:
                    if destination(folder) not in known:
                        raise RuntimeError('Missing archive folder: ' + folder)
                else:
                    mail.ensure_folder(target, destination(folder), known)
                snapshot.append((folder, validity, ids))
            copier = Copier(worker.MAILBOX, password, ledger, index, known, verify_only=args.verify_only)
            totals = {'source': 0, 'copied': 0, 'existing': 0, 'bytes': 0}
            started = time.monotonic()
            def account(future):
                status, size = future.result()
                totals['source'] += 1
                totals['copied' if status == 'verified_copy' else 'existing'] += 1
                totals['bytes'] += size
                if totals['source'] % 25 == 0:
                    print(json.dumps(dict(event='progress', seconds=round(time.monotonic()-started), **totals)), flush=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                for folder, validity, ids in snapshot:
                    assert mail.select(source, folder) == validity
                    pending = set()
                    for uid in ids:
                        raw, date, flags = mail.fetch(source, uid)
                        headers = BytesHeaderParser(policy=mail.email.policy.default).parsebytes(raw)
                        db.execute('INSERT OR REPLACE INTO source_metadata VALUES(?,?,?,?,?,?,?,?,?)',
                                   (folder, validity, uid, date, flags, str(headers.get('Message-ID','')),
                                    str(headers.get('Date','')), hashlib.sha256(raw).hexdigest(),
                                    dt.datetime.now(dt.timezone.utc).isoformat()))
                        db.commit()
                        pending.add(executor.submit(copier.copy, folder, validity, uid, raw, date, flags))
                        if len(pending) >= 6:
                            done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                            for future in done:
                                account(future)
                    for future in concurrent.futures.as_completed(pending):
                        account(future)
                    print(json.dumps({'event': 'folder_done', 'folder': folder, 'messages': len(ids)}), flush=True)
            unresolved = db.execute("SELECT count(*) FROM copies WHERE status NOT IN ('verified_copy','verified_existing')").fetchone()[0]
            print(json.dumps(dict(event='complete', unresolved=unresolved, seconds=round(time.monotonic()-started), **totals)), flush=True)
            if unresolved:
                raise RuntimeError('Unresolved messages remain')
        finally:
            if copier:
                copier.close()
            for client in (source, target):
                if client:
                    try:
                        client.logout()
                    except Exception:
                        pass
            tokens.db.close()
            db.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'event': 'failed', 'type': type(error).__name__,
                          'reason': str(error) if isinstance(error, RuntimeError) else 'Transport error; secrets omitted'}), flush=True)
        raise SystemExit(1)
