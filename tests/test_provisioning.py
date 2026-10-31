import json
import tempfile
import unittest
from pathlib import Path

from control.registry import Registry
from control.provisioning import build_plan, SimulatedProvisioner, STEPS


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.registry = Registry(self.path / 'registry.sqlite3')
        self.a = self.registry.reserve('empresa-alfa', ['jenifer_ai'], 'a')
        self.b = self.registry.reserve('empresa-beta', ['payroll_hr', 'projects_services'], 'b')
        self.worker = SimulatedProvisioner(self.path / 'simulation.sqlite3', self.registry)

    def tearDown(self):
        self.worker.close()
        self.registry.close()
        self.tmp.cleanup()

    def test_scope_and_resources_are_independent_without_real_credentials(self):
        a = build_plan(self.registry, self.a['hostname'])
        b = build_plan(self.registry, self.b['hostname'])
        for key in a['resources']:
            self.assertNotEqual(a['resources'][key], b['resources'][key])
        self.assertNotIn('payroll_hr', a['modules'])
        self.assertNotIn('jenifer_ai', b['modules'])
        for plan in (a, b):
            self.assertIn('electronic_invoicing', plan['modules'])
            self.assertFalse(any(plan['integrations'].values()))
            self.assertFalse(plan['fiscal']['emission_enabled'])
            self.assertFalse(plan['access_enabled'])
            self.assertEqual(plan, json.loads(json.dumps(plan)))

    def test_complete_retry_survives_reopen_without_duplicate_steps(self):
        first = self.worker.run(self.a['hostname'])
        self.worker.close()
        self.worker = SimulatedProvisioner(self.path / 'simulation.sqlite3', self.registry)
        self.assertEqual(first, self.worker.run(self.a['hostname']))
        self.assertEqual(list(STEPS), first['completed_steps'])
        self.assertEqual('simulated', first['status'])
        self.assertFalse(first['real_resources_created'])
        self.assertFalse(self.registry.resolve_registered(self.a['hostname'])['access_enabled'])

    def test_failure_at_each_step_resumes_and_does_not_affect_another_tenant(self):
        for step in STEPS:
            with self.subTest(step=step):
                worker = SimulatedProvisioner(self.path / (step + '.sqlite3'), self.registry)
                try:
                    failed = worker.run(self.a['hostname'], fail_at=step)
                    self.assertEqual('failed', failed['status'])
                    self.assertEqual(step, failed['failed_step'])
                    self.assertEqual(list(STEPS[:STEPS.index(step)]), failed['completed_steps'])
                    beta = worker.run(self.b['hostname'])
                    resumed = worker.run(self.a['hostname'])
                    self.assertEqual('simulated', resumed['status'])
                    self.assertEqual(list(STEPS), resumed['completed_steps'])
                    self.assertEqual(beta, worker.result(self.b['id']))
                finally:
                    worker.close()

    def test_unknown_hosts_and_invalid_failure_do_not_create_jobs(self):
        for hostname in ('erp.uno360x.com', 'unknown.uno360x.com',
                         self.a['hostname'] + '.evil.com'):
            with self.assertRaises(LookupError):
                self.worker.run(hostname)
        with self.assertRaises(ValueError):
            self.worker.run(self.a['hostname'], fail_at='publish')
        self.assertEqual(0, self.worker.db.execute('SELECT count(*) FROM simulations').fetchone()[0])

    def test_changed_configuration_is_rejected_without_overwriting_journal(self):
        old = self.worker.run(self.a['hostname'])
        # Model a future configuration change; current registry has no edit API.
        with self.registry.db:
            self.registry.db.execute('UPDATE tenants SET modules=? WHERE id=?',
                                     (json.dumps(['payroll_hr']), self.a['id']))
        with self.assertRaises(ValueError):
            self.worker.run(self.a['hostname'])
        self.assertEqual(old, self.worker.result(self.a['id']))
