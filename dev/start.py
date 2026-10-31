"""Local WSL lab only. No production endpoints, imports or credentials."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

if os.name != 'posix' or os.geteuid() != 0:
    raise SystemExit('Ejecutar dentro del WSL de laboratorio como root.')
if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
    raise SystemExit('Este laboratorio solo se ejecuta en WSL, nunca en la VM operativa.')

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/uno360x-saas-dev')
STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chmod(STATE, 0o700)
NETWORK = 'uno360x-dev-private'
DB = 'uno360x-dev-db'
APP = 'uno360x-dev-app'
INIT = 'uno360x-dev-init'


def run(*args, capture=False, check=True):
    return subprocess.run(['podman', *args], check=check, text=True,
                          stdout=subprocess.PIPE if capture else None)


def exists(kind, name):
    return run(kind, 'exists', name, capture=True, check=False).returncode == 0


def secret_file(name, content):
    p = STATE / name
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(content)
    return p


# Resolve images before touching lab resources; save immutable IDs for this run.
images = {}
for name in ['odoo:18.0', 'postgres:16']:
    qualified = 'docker.io/library/' + name
    inspected = json.loads(run('image', 'inspect', qualified, capture=True).stdout)[0]
    images[name] = inspected['Id']
(STATE / 'images.json').write_text(json.dumps(images, indent=2))

admin = secret_file('postgres.env', 'POSTGRES_PASSWORD=' + secrets.token_hex(32) + '\n')
app_password = secret_file('app-password', secrets.token_hex(32)).read_text()
config = secret_file('odoo.conf', '''[options]
admin_passwd = %s
db_host = %s
db_port = 5432
db_user = uno360x_dev
db_password = %s
db_name = uno360x_dev
dbfilter = ^uno360x_dev$
list_db = False
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
data_dir = /var/lib/odoo
http_interface = 0.0.0.0
http_port = 8069
workers = 0
max_cron_threads = 0
proxy_mode = False
without_demo = all
log_level = info
''' % (secrets.token_hex(32), DB, app_password))
# Parent directory is root-only; container's Odoo user must read the bind mount.
os.chmod(config, 0o644)
bootstrap = secret_file('01-bootstrap.sql', "CREATE ROLE uno360x_dev LOGIN PASSWORD '%s' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;\nCREATE DATABASE uno360x_dev OWNER uno360x_dev;\n" % app_password)
os.chmod(bootstrap, 0o644)

if not exists('network', NETWORK):
    run('network', 'create', '--internal', NETWORK)
for volume in ['uno360x-dev-pgdata', 'uno360x-dev-odoodata']:
    if not exists('volume', volume):
        run('volume', 'create', volume)
if not exists('container', DB):
    run('run', '-d', '--name', DB, '--network', NETWORK,
        '--label', 'uno360x.environment=local-development',
        '--cpus', '0.5', '--memory', '512m', '--env-file', str(admin),
        '-v', 'uno360x-dev-pgdata:/var/lib/postgresql/data',
        '-v', str(bootstrap) + ':/docker-entrypoint-initdb.d/01-bootstrap.sql:ro',
        images['postgres:16'])
else:
    run('start', DB)
for _ in range(60):
    ready = run('exec', DB, 'pg_isready', '-U', 'postgres', '-d', 'uno360x_dev', capture=True, check=False)
    if ready.returncode == 0:
        break
    time.sleep(1)
else:
    raise SystemExit('PostgreSQL de laboratorio no está listo.')

common = ['--network', NETWORK, '--cpus', '1', '--memory', '1536m',
          '--label', 'uno360x.environment=local-development',
          '-v', str(config) + ':/etc/odoo/odoo.conf:ro',
          '-v', str(ROOT / 'addons') + ':/mnt/extra-addons:ro',
          '-v', 'uno360x-dev-odoodata:/var/lib/odoo']
if not (STATE / 'initialized').exists():
    if exists('container', INIT):
        raise SystemExit('Existe una instalación interrumpida; revisar logs antes de reintentar.')
    run('run', '--name', INIT, *common, images['odoo:18.0'],
        'odoo', '-c', '/etc/odoo/odoo.conf', '-i', 'uno360x_tenant_config',
        '--without-demo=all', '--stop-after-init', '--test-enable',
        '--test-tags', '/uno360x_tenant_config')
    (STATE / 'initialized').touch()
if not exists('container', APP):
    run('run', '-d', '--name', APP, *common,
        images['odoo:18.0'], 'odoo', '-c', '/etc/odoo/odoo.conf')
else:
    run('start', APP)
inspected = json.loads(run('inspect', APP, capture=True).stdout)[0]
target = inspected['NetworkSettings']['Networks'][NETWORK]['IPAddress']
pidfile = STATE / 'proxy.pid'
running = False
if pidfile.exists():
    pid = int(pidfile.read_text())
    proc = Path(f'/proc/{pid}/cmdline')
    running = proc.exists() and b'loopback_proxy.py' in proc.read_bytes()
if not running:
    with (STATE / 'proxy.log').open('ab') as log:
        proc = subprocess.Popen([sys.executable, str(ROOT / 'dev/loopback_proxy.py'),
                                 '--target', target], stdin=subprocess.DEVNULL,
                                stdout=log, stderr=log, start_new_session=True)
    time.sleep(0.3)
    if proc.poll() is not None:
        raise SystemExit('No se pudo abrir el acceso local; revisar proxy.log.')
    pidfile.write_text(str(proc.pid))
print('Laboratorio local iniciado: http://127.0.0.1:18069/web/login')
print('Sin datos operativos ni integraciones externas; credenciales solo en almacenamiento Linux local.')
