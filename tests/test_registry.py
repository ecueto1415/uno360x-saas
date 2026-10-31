import tempfile
import unittest
from pathlib import Path

from control.registry import Registry


class TenantRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Registry(Path(self.tmp.name) / 'registry.sqlite3')

    def tearDown(self):
        self.registry.close()
        self.tmp.cleanup()

    def test_clients_have_distinct_resources_and_base_includes_ecf(self):
        a = self.registry.reserve('empresa-alfa', ['jenifer_ai'], 'req-a')
        b = self.registry.reserve('empresa-beta', [], 'req-b')
        for key in a['resources']:
            self.assertNotEqual(a['resources'][key], b['resources'][key])
        self.assertIn('electronic_invoicing', b['modules'])
        self.assertFalse(a['access_enabled'])
        self.assertEqual(self.registry.resolve_registered(a['hostname'])['id'], a['id'])

    def test_retries_are_idempotent_and_changed_requests_rejected(self):
        a = self.registry.reserve('empresa-alfa', [], 'req-a')
        self.assertEqual(a, self.registry.reserve('empresa-alfa', [], 'req-a'))
        with self.assertRaises(ValueError):
            self.registry.reserve('empresa-beta', [], 'req-a')
        with self.assertRaises(ValueError):
            self.registry.reserve('empresa-alfa', [], 'req-b')

    def test_unknown_or_forged_hostnames_never_resolve(self):
        self.registry.reserve('empresa-alfa', [], 'req-a')
        for value in ['unknown.uno360x.com', 'empresa-alfa.uno360x.com.evil.com',
                      'empresa-alfa.uno360x.com:443', '../empresa-alfa',
                      'https://empresa-alfa.uno360x.com', 'empresa-alfa.uno360x.com\n']:
            with self.subTest(value=value), self.assertRaises(LookupError):
                self.registry.resolve_registered(value)

    def test_internal_names_and_invalid_modules_rejected(self):
        for value in ['erp', 'outsolutech', 'admin', 'ABC', 'bad_', '-abc', 'abc-']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.registry.reserve(value, [], value)
        with self.assertRaises(ValueError):
            self.registry.reserve('empresa-alfa', ['unknown'], 'req-a')


if __name__ == '__main__':
    unittest.main()
