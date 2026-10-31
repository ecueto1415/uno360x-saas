"""Local-only tenant reservation prototype; never provisions infrastructure."""
import json
import re
import sqlite3
import uuid

BASE_DOMAIN = 'uno360x.com'
RESERVED = {'www', 'erp', 'outsolutech', 'admin', 'api', 'mail', 'smtp',
            'imap', 'support', 'status', 'dev', 'test', 'staging', 'control'}
OPTIONAL_MODULES = frozenset({'payroll_hr', 'jenifer_ai', 'projects_services'})


def validate_slug(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,38}[a-z0-9]', value):
        raise ValueError('Nombre: 3-40 caracteres ASCII minúsculos, sin guion final.')
    if value in RESERVED:
        raise ValueError('Subdominio reservado para operación interna.')
    return value


class Registry:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                request_id TEXT UNIQUE NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                hostname TEXT UNIQUE NOT NULL,
                modules TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('reserved'))
            );
        ''')

    def close(self):
        self.db.close()

    def reserve(self, slug, modules, request_id):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            return self._reserve_in_transaction(slug, modules, request_id)

    def _reserve_in_transaction(self, slug, modules, request_id):
        """Internal helper for atomic account/company creation on this connection."""
        if not self.db.in_transaction:
            raise RuntimeError('Se requiere transacción de reserva.')
        slug = validate_slug(slug)
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError('Se requiere una clave de solicitud de hasta 128 caracteres.')
        modules = sorted(set(modules))
        if not set(modules) <= OPTIONAL_MODULES:
            raise ValueError('Módulo desconocido.')
        encoded = json.dumps(modules)
        existing = self.db.execute('SELECT * FROM tenants WHERE request_id=?', (request_id,)).fetchone()
        if existing:
            if existing['slug'] != slug or existing['modules'] != encoded:
                raise ValueError('Solicitud repetida con datos diferentes.')
            return self._public(existing)
        tenant_id = uuid.uuid4().hex
        try:
            self.db.execute('INSERT INTO tenants VALUES (?,?,?,?,?,?)',
                            (tenant_id, request_id, slug, f'{slug}.{BASE_DOMAIN}', encoded, 'reserved'))
        except sqlite3.IntegrityError as exc:
            raise ValueError('Subdominio ya reservado.') from exc
        row = self.db.execute('SELECT * FROM tenants WHERE id=?', (tenant_id,)).fetchone()
        return self._public(row)

    def resolve_registered(self, hostname):
        # Not an HTTP Host parser. Accept only a canonical exact hostname supplied
        # by a trusted future ingress; no URL, port, path or forwarded header.
        if not isinstance(hostname, str) or not re.fullmatch(r'[a-z0-9-]+\.uno360x\.com', hostname):
            raise LookupError('Dominio inválido.')
        row = self.db.execute('SELECT * FROM tenants WHERE hostname=?', (hostname,)).fetchone()
        if row is None:
            raise LookupError('Cliente no registrado.')
        return self._public(row)

    @staticmethod
    def _public(row):
        tenant_id = row['id']
        return {
            'id': tenant_id, 'slug': row['slug'], 'hostname': row['hostname'],
            'state': row['state'], 'access_enabled': False,
            'modules': ['business_base', 'electronic_invoicing'] + json.loads(row['modules']),
            'resources': {
                'database_ref': f'tenant/{tenant_id}/database',
                'filestore_ref': f'tenant/{tenant_id}/files',
                'secret_namespace_ref': f'tenant/{tenant_id}/secrets',
            },
        }
