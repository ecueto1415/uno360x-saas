import concurrent.futures
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

migration = None
if os.name == 'posix':
    folder = Path(__file__).resolve().parents[1] / 'integrations/jenifer'
    if not folder.exists():
        folder = Path('/tmp')
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location('history_parallel', folder/'migrate_mail_history_parallel.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)


class FakeTarget:
    def __init__(self):
        self.records = {}
        self.guard = threading.Lock()
        self.appends = 0

    def append(self, folder, flags, date, raw):
        with self.guard:
            self.appends += 1
            uid = str(len(self.records) + 1)
            self.records[uid] = raw
            return 'OK', [('[APPENDUID 1 %s] accepted' % uid).encode()]

    def logout(self):
        pass


@unittest.skipUnless(migration, 'Linux migration helper')
class ParallelHistoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name)/'ledger.sqlite')
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE copies(folder TEXT,validity TEXT,uid TEXT,message_id TEXT,digest TEXT,target_folder TEXT,status TEXT,PRIMARY KEY(folder,validity,uid))')
        self.target = FakeTarget()
        target = self.target
        class FakeCopier(migration.Copier):
            def context(copier):
                if not hasattr(copier.local, 'db'):
                    copier.local.db = sqlite3.connect(copier.ledger, timeout=30, check_same_thread=False)
                    with copier.guard:
                        copier.connections.append((target, copier.local.db))
                return target, copier.local.db
        self.copier = FakeCopier('test@example.com', 'test-only', self.path, {}, set())
        self.patches = [patch.object(migration.mail, 'select', return_value='1'),
                        patch.object(migration.mail, 'fetch', side_effect=lambda c,u: (c.records[u], None, '()')),
                        patch.object(migration.mail, 'uids', return_value=[])]
        for item in self.patches:
            item.start()

    def tearDown(self):
        self.copier.close()
        for item in reversed(self.patches):
            item.stop()
        self.folder.cleanup()

    def raw(self, mid):
        return ('Message-ID: <%s@example.com>\r\nSubject: Test\r\n\r\nBody\r\n' % mid).encode()

    def test_three_concurrent_copies_of_same_message_append_once(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self.copier.copy, 'INBOX', '1', str(i), self.raw('same'), None, '()') for i in range(3)]
            statuses = [future.result()[0] for future in futures]
        self.assertEqual(self.target.appends, 1)
        self.assertEqual(statuses.count('verified_copy'), 1)
        self.assertEqual(statuses.count('verified_existing'), 2)

    def test_three_distinct_messages_are_all_verified(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self.copier.copy, 'INBOX', '1', str(i), self.raw(str(i)), None, '()') for i in range(3)]
            self.assertTrue(all(f.result()[0] == 'verified_copy' for f in futures))
        self.assertEqual(self.target.appends, 3)

    def test_pending_unknown_append_is_not_retried(self):
        raw = self.raw('same');mid,digest=migration.mail.identity(raw)
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO copies VALUES(?,?,?,?,?,?,?)', ('INBOX','1','1',mid,digest,'archive','uncertain'))
        with self.assertRaises(RuntimeError):
            self.copier.copy('INBOX','1','1',raw,None,'()')
        self.assertEqual(self.target.appends, 0)

    def test_disconnect_after_rejection_remains_uncertain(self):
        with patch.object(self.target, 'append', side_effect=[('NO', [b'busy']), OSError('disconnect')]), patch.object(migration.time, 'sleep'):
            with self.assertRaises(OSError):
                self.copier.copy('INBOX','1','1',self.raw('same'),None,'()')
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM copies').fetchone()[0], 'uncertain')

    def test_verify_only_does_not_append_missing_message(self):
        self.copier.verify_only = True
        with self.assertRaises(RuntimeError):
            self.copier.copy('INBOX','1','1',self.raw('missing'),None,'()')
        self.assertEqual(self.target.appends, 0)

    def test_verify_only_recognizes_existing_message_without_appending(self):
        raw = self.raw('existing')
        self.copier.index[migration.mail.identity(raw)] = ('archive','9')
        self.copier.verify_only = True
        self.assertEqual(self.copier.copy('INBOX','1','1',raw,None,'()')[0], 'verified_existing')
        self.assertEqual(self.target.appends, 0)

    def test_stale_uid_receipt_reconciles_without_second_append(self):
        def append(folder,flags,date,raw):
            self.target.appends += 1
            self.target.records['105'] = raw
            return 'OK', [b'[APPENDUID 1 104]']
        def fetch(client,uid):
            if uid not in client.records:
                raise RuntimeError('Not found')
            return client.records[uid], None, '()'
        with patch.object(self.target,'append',side_effect=append), patch.object(migration.mail,'fetch',side_effect=fetch), patch.object(migration.mail,'uids',return_value=['105']), patch.object(migration.time,'sleep'):
            self.assertEqual(self.copier.copy('INBOX','1','1',self.raw('same'),None,'()')[0],'verified_copy')
        self.assertEqual(self.target.appends,1)


if __name__ == '__main__':
    unittest.main()
