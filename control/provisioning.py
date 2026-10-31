"""Deterministic desired configuration and a local-only provisioning rehearsal.

No adapter here creates databases, files, credentials, users, DNS or network calls.
The registry remains reserved; a successful rehearsal never enables access.
"""
import hashlib
import json
import sqlite3
from .catalog import installation_profile


STEPS = ('database', 'filestore', 'secret_namespace', 'configuration', 'validation')
PRODUCT_VERSION = '0.3-packaging-lab'


def build_plan(registry, hostname):
    """Only registered canonical hosts can produce an authoritative plan."""
    tenant = registry.resolve_registered(hostname)
    return {
        'schema_version': 1,
        'product_version': PRODUCT_VERSION,
        'mode': 'simulation',
        'tenant_id': tenant['id'],
        'hostname': tenant['hostname'],
        'modules': tenant['modules'],
        'installation': installation_profile(tenant['modules']),
        'resources': tenant['resources'],
        'access_enabled': False,
        'integrations': {'mail': False, 'jenifer': False, 'dgii': False},
        'fiscal': {'company_scoped': True, 'state': 'not_started',
                   'certificate_loaded': False, 'emission_enabled': False},
        # Commercial capabilities, not a claim that Odoo addons are implemented.
        'module_status': 'desired_scope_not_installation',
    }


class SimulatedProvisioner:
    """SQLite journal; every completed step can be resumed without duplication."""

    def __init__(self, path, registry):
        self.registry = registry
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS simulations (
                tenant_id TEXT PRIMARY KEY,
                plan TEXT NOT NULL,
                digest TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('running','failed','simulated')),
                failed_step TEXT
            );
            CREATE TABLE IF NOT EXISTS simulation_steps (
                tenant_id TEXT NOT NULL REFERENCES simulations(tenant_id),
                step TEXT NOT NULL,
                PRIMARY KEY(tenant_id, step)
            );
        ''')
        self.db.execute('PRAGMA foreign_keys=ON')

    def close(self):
        self.db.close()

    def run(self, hostname, fail_at=None):
        if fail_at is not None and fail_at not in STEPS:
            raise ValueError('Paso de simulación desconocido.')
        plan = build_plan(self.registry, hostname)
        encoded = json.dumps(plan, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        tenant_id = plan['tenant_id']
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old = self.db.execute('SELECT * FROM simulations WHERE tenant_id=?',
                                  (tenant_id,)).fetchone()
            if old and old['digest'] != digest:
                raise ValueError('Configuración distinta: requiere una migración explícita.')
            if old and old['status'] == 'simulated':
                return self.result(tenant_id)
            self.db.execute('''INSERT INTO simulations VALUES (?,?,?,'running',NULL)
                ON CONFLICT(tenant_id) DO UPDATE SET status='running',failed_step=NULL''',
                            (tenant_id, encoded, digest))
        for step in STEPS:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                if self.db.execute('SELECT 1 FROM simulation_steps WHERE tenant_id=? AND step=?',
                                   (tenant_id, step)).fetchone():
                    continue
                if step == fail_at:
                    self.db.execute("UPDATE simulations SET status='failed',failed_step=? WHERE tenant_id=?",
                                    (step, tenant_id))
                    break
                # Record only the simulation; never call a real infrastructure API.
                self.db.execute('INSERT INTO simulation_steps VALUES (?,?)', (tenant_id, step))
        else:
            with self.db:
                self.db.execute("UPDATE simulations SET status='simulated',failed_step=NULL WHERE tenant_id=?",
                                (tenant_id,))
        return self.result(tenant_id)

    def result(self, tenant_id):
        row = self.db.execute('SELECT * FROM simulations WHERE tenant_id=?', (tenant_id,)).fetchone()
        if row is None:
            raise LookupError('Simulación no encontrada.')
        done = {r[0] for r in self.db.execute(
            'SELECT step FROM simulation_steps WHERE tenant_id=?', (tenant_id,))}
        return {'tenant_id': tenant_id, 'status': row['status'],
                'failed_step': row['failed_step'], 'plan_digest': row['digest'],
                'completed_steps': [step for step in STEPS if step in done],
                'access_enabled': False, 'real_resources_created': False}
