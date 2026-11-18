import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment.prune_seed_templates import eligible, retire


class SeedRetentionSafety(unittest.TestCase):
    def setUp(self):
        self.name = 'uno_tpl_' + 'a' * 24
        self.row = dict(name=self.name, owner='postgres', allow=False,
                        system_template=False, sessions=0, other_role_dependencies=0)
        self.manifests = {self.name: {'created': time.time() - 7200}}

    def test_only_unreferenced_closed_factory_can_be_selected(self):
        self.assertTrue(eligible(self.row, set(), self.manifests, 3600))
        self.assertFalse(eligible(self.row, {self.name}, self.manifests, 3600))
        self.assertFalse(eligible(self.row, set(), {}, 3600))

    def test_active_system_or_shared_dependencies_are_excluded(self):
        for key, value in [('allow', True), ('system_template', True),
                           ('sessions', 1), ('other_role_dependencies', 1),
                           ('owner', 'tenant_owner')]:
            self.assertFalse(eligible(dict(self.row, **{key: value}), set(), self.manifests, 3600), key)

    def test_customer_system_and_malformed_names_are_always_excluded(self):
        for name in ('tenant_' + 'a' * 32, 'Outsolutech_prueba', 'postgres',
                     self.name + ';drop database postgres', 'uno_tpl_' + 'z' * 24):
            self.assertFalse(eligible(dict(self.row, name=name), set(), {name: self.manifests[self.name]}, 3600))

    def test_recent_templates_have_a_grace_period(self):
        self.assertFalse(eligible(self.row, set(), {self.name: {'created': time.time()}}, 3600))

    def test_postgres_text_oid_is_supported_and_drop_never_forces_sessions(self):
        pool = Mock()
        pool.sql.return_value = SimpleNamespace(returncode=0, stdout='SEED_RETIRED')
        with patch('deployment.prune_seed_templates.verified_cache', return_value=Path('/verified')):
            retire(pool, dict(self.row, oid='12345'), {'installation': {}, 'images': {}})
        script = pool.sql.call_args.args[0]
        self.assertIn('d.oid=12345', script)
        self.assertIn('BEGIN READ ONLY', script)
        self.assertIn('DROP DATABASE "' + self.name + '";', script)
        self.assertNotIn('FORCE', script)

    def test_missing_archive_prevents_all_database_mutations(self):
        pool = Mock()
        with patch('deployment.prune_seed_templates.verified_cache', return_value=None):
            with self.assertRaises(RuntimeError):
                retire(pool, dict(self.row, oid='12345'), {'installation': {}, 'images': {}})
        pool.sql.assert_not_called()


if __name__ == '__main__':
    unittest.main()
