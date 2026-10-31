"""Read-only checks of the local Podman laboratory."""
import json
from pathlib import Path
import subprocess
import urllib.request


def podman(*args):
    return subprocess.check_output(['podman', *args], text=True).strip()


sql = """SELECT name,state FROM ir_module_module
WHERE name = 'uno360x_tenant_config';
SELECT rolname,rolsuper,rolcreatedb,rolcreaterole FROM pg_roles
WHERE rolname = 'uno360x_dev';"""
network = json.loads(podman('network', 'inspect', 'uno360x-dev-private'))[0]
assert network['internal'] is True
app = json.loads(podman('inspect', 'uno360x-dev-app'))[0]
ports = app['NetworkSettings']['Ports']
assert not any(ports.values())
db = json.loads(podman('inspect', 'uno360x-dev-db'))[0]
assert not any(db['NetworkSettings']['Ports'].values())
assert app['State']['Running'] and db['State']['Running']
result = podman('exec', 'uno360x-dev-db', 'psql', '-U', 'postgres',
                '-d', 'uno360x_dev', '-Atc', sql)
assert 'uno360x_tenant_config|installed' in result
assert 'uno360x_dev|f|f|f' in result
with urllib.request.urlopen('http://127.0.0.1:18069/web/login', timeout=20) as response:
    assert response.status == 200
print(json.dumps({'network_internal': True, 'loopback_only': True,
                  'database_port_published': False, 'application_role_privileged': False,
                  'module_installed': True, 'login_http': 200,
                  'images': json.loads(Path('/var/lib/uno360x-saas-dev/images.json').read_text())}, indent=2))
print(podman('stats', '--no-stream', '--format', '{{.Name}} {{.MemUsage}} {{.CPU}}'))
