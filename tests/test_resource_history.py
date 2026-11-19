import datetime
import http.client
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from admin_console.resource_history import record_sample, read_history, import_sysstat, WEEK, RETENTION
from admin_console.server import Server, COOKIE
from admin_console.auth import Auth, otp


class ResourceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'resource-history.sqlite3'
        self.now = 2000000000
        self.sample = dict(cpu_percent=10, memory_used=40, memory_total=100, disk_used=30, disk_total=200)

    def test_real_samples_aggregate_and_duplicate_timestamp_does_not_duplicate(self):
        for delta, cpu in [(180, 0), (120, 40), (60, 10)]:
            record_sample(self.path, dict(self.sample, cpu_percent=cpu), self.now - delta, now=self.now)
        record_sample(self.path, dict(self.sample, cpu_percent=10), self.now - 60, now=self.now)
        data = read_history(self.path, 'cpu', self.now)
        self.assertEqual(data['summary']['samples'], 3)
        self.assertEqual(data['summary']['low'], 0)
        self.assertEqual(data['summary']['high'], 40)
        self.assertAlmostEqual(data['summary']['average'], 50 / 3)
        self.assertEqual(data['start'], self.now - WEEK)
        self.assertEqual(read_history(self.path, 'memory', self.now)['latest']['value'], 40)
        self.assertEqual(read_history(self.path, 'disk', self.now)['latest']['value'], 15)

    def test_missing_and_invalid_measurements_are_not_filled(self):
        self.assertEqual(read_history(self.path, 'disk', self.now)['points'], [])
        record_sample(self.path, dict(cpu_percent=float('nan'), memory_used=200, memory_total=100), self.now, now=self.now)
        for metric in ('cpu', 'memory', 'disk'):
            self.assertIsNone(read_history(self.path, metric, self.now)['summary'])
        with self.assertRaises(ValueError):
            read_history(self.path, '../../etc/shadow', self.now)

    def test_retention_and_one_week_window(self):
        record_sample(self.path, self.sample, self.now - RETENTION + 60, now=self.now - 3600)
        record_sample(self.path, self.sample, self.now - WEEK - 1, now=self.now)
        record_sample(self.path, self.sample, self.now, now=self.now)
        self.assertEqual(read_history(self.path, 'cpu', self.now)['summary']['samples'], 1)
        record_sample(self.path, self.sample, self.now + 7200, now=self.now + 7200)
        import sqlite3
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT min(ts) FROM resource_samples').fetchone()[0], self.now - WEEK - 1)

    def test_sysstat_import_preserves_real_live_sample_and_never_invents_disk(self):
        directory = self.root / 'sysstat'; directory.mkdir()
        file = directory / 'sa18'; file.write_text('fixture')
        import os
        os.utime(file, (self.now, self.now))
        ts = self.now - 600
        stamp = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        total = 7600840 * 1024
        host = {'sysstat': {'hosts': [{'statistics': [{
            'timestamp': {'date': stamp.strftime('%Y-%m-%d'), 'time': stamp.strftime('%H:%M:%S'), 'tz': 'UTC'},
            'cpu-load': [{'cpu': 'all', 'idle': 79.43, 'iowait': .58, 'steal': 1.98}],
            'memory': {'memused': 1492984, 'memused-percent': 19.64, 'avail': 5027792},
        }]}]}}
        from types import SimpleNamespace
        with patch('admin_console.resource_history.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(host))):
            self.assertEqual(import_sysstat(self.path, directory, total, self.now), 1)
        self.assertAlmostEqual(read_history(self.path, 'cpu', self.now)['latest']['value'], 18.01)
        self.assertAlmostEqual(read_history(self.path, 'memory', self.now)['latest']['value'], 100 * (total - 5027792 * 1024) / total)
        self.assertEqual(read_history(self.path, 'disk', self.now)['points'], [])
        record_sample(self.path, self.sample, ts, now=self.now)
        with patch('admin_console.resource_history.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(host))):
            import_sysstat(self.path, directory, total, self.now)
        self.assertEqual(read_history(self.path, 'cpu', self.now)['latest']['value'], 10)


class ResourceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.now = 2000000000
        self.server = Server(0, self.root / 'auth', self.root / 'snapshot.json', owner='owner@example.test')
        self.server.clock = lambda: self.now
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.cookie = ''
        record_sample(self.root / 'resource-history.sqlite3', {'cpu_percent': 23}, self.now, now=self.now)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, path, host='admin.uno360x.com', method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, path, headers={'Host': host, 'User-Agent': 'history-test', 'Cookie': self.cookie, 'Origin': 'https://admin.uno360x.com'})
        response = connection.getresponse(); result = (response.status, dict(response.getheaders()), json.loads(response.read()))
        connection.close(); return result

    def authenticate(self):
        auth = Auth(self.root / 'auth', 'owner@example.test', clock=lambda: self.now)
        token = auth.new_enrollment(); setup = auth.start_enrollment(token, 'test-ip')
        session, _ = auth.finish_enrollment(token, 'Fictional history test password!', otp(setup['secret'], self.now // 30), 'history-test', 'test-ip')
        auth.close(); self.cookie = COOKIE + '=' + session

    def test_history_requires_owner_session_and_dedicated_origin(self):
        self.assertEqual(self.request('/api/resources/history?metric=cpu')[0], 401)
        self.authenticate()
        status, headers, body = self.request('/api/resources/history?metric=cpu')
        self.assertEqual(status, 200); self.assertEqual(body['latest']['value'], 23)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request('/api/resources/history?metric=cpu', host='cuenta.uno360x.com')[0], 403)
        self.assertEqual(self.request('/api/resources/history', method='POST')[0], 404)
        for suffix in ('?metric=bad', '?metric=cpu&metric=disk', '?metric=cpu&path=/etc/shadow', '?metric='):
            self.assertEqual(self.request('/api/resources/history' + suffix)[0], 400)


if __name__ == '__main__':
    unittest.main()
