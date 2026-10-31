"""Create exactly two fictional tenants, only inside the existing WSL lab.

No DNS, external mail, AI, fiscal services, production or payment provider.
Separate PostgreSQL containers are a laboratory isolation fixture, not a final
commercial hosting topology. All secrets remain in root-only Linux storage.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from control.registry import Registry


def run(*args, input=None, check=True):
    p = subprocess.run(['podman', *args], input=input, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        # Never echo config contents, SQL credentials or command stderr.
        raise RuntimeError('Falló operación local Podman: ' + args[0])
    return p


def exists(kind, name):
    return run(kind, 'exists', name, check=False).returncode == 0


def protected(path, content):
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(content)
    return path


def inspect(name):
    return json.loads(run('inspect', name).stdout)[0]


def main():
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('Solo root en el WSL de laboratorio.')
    if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo WSL; prohibido ejecutar en la VM operativa.')
    state = Path('/var/lib/uno360x-saas-dev/tenants')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    images = json.loads(Path('/var/lib/uno360x-saas-dev/images.json').read_text())
    registry = Registry(state / 'registry.sqlite3')
    results = []
    try:
        for slug, modules in [('empresa-alfa', ['jenifer_ai']),
                              ('empresa-beta', ['payroll_hr', 'projects_services'])]:
            tenant = registry.reserve(slug, modules, 'lab-' + slug)
            directory = state / tenant['id']
            directory.mkdir(mode=0o700, exist_ok=True)
            os.chmod(directory, 0o700)
            prefix = 'uno360x-lab-' + slug
            network, db, app, init = (prefix + s for s in ('-private', '-db', '-app', '-init'))
            role = 'tenant_' + tenant['id'][:16]
            dbname = role
            password = protected(directory / 'database-password', secrets.token_hex(32)).read_text()
            admin_pass = protected(directory / 'admin-password', secrets.token_hex(32)).read_text()
            envfile = protected(directory / 'postgres.env', 'POSTGRES_PASSWORD=' + secrets.token_hex(32) + '\n')
            sql = protected(directory / 'bootstrap.sql',
                            "CREATE ROLE %s LOGIN PASSWORD '%s' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;\nCREATE DATABASE %s OWNER %s;\nREVOKE CONNECT ON DATABASE %s FROM PUBLIC;\n" % (role, password, dbname, role, dbname))
            config = protected(directory / 'odoo.conf', '''[options]
admin_passwd = %s
db_host = %s
db_port = 5432
db_user = %s
db_password = %s
db_name = %s
dbfilter = ^%s$
list_db = False
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
data_dir = /var/lib/odoo
http_interface = 0.0.0.0
workers = 0
max_cron_threads = 0
proxy_mode = False
without_demo = all
''' % (secrets.token_hex(32), db, role, password, dbname, dbname))
            # Root-only parent; Odoo/postgres must read these bind-mounted files.
            os.chmod(config, 0o644)
            os.chmod(sql, 0o644)
            if not exists('network', network):
                run('network', 'create', '--internal', network)
            for volume in (prefix + '-pgdata', prefix + '-odoodata'):
                if not exists('volume', volume):
                    run('volume', 'create', volume)
            labels = ['--label', 'uno360x.environment=local-development',
                      '--label', 'uno360x.tenant=' + tenant['id']]
            if not exists('container', db):
                run('run', '-d', '--name', db, '--network', network, *labels,
                    '--cpus', '0.4', '--memory', '384m', '--env-file', str(envfile),
                    '-v', prefix + '-pgdata:/var/lib/postgresql/data',
                    '-v', str(sql) + ':/docker-entrypoint-initdb.d/01-tenant.sql:ro',
                    images['postgres:16'])
            else:
                run('start', db)
            for _ in range(60):
                if run('exec', db, 'pg_isready', '-U', 'postgres', '-d', dbname, check=False).returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Base de laboratorio no disponible.')
            common = ['--network', network, *labels, '--cpus', '0.8', '--memory', '1024m',
                      '-v', str(config) + ':/etc/odoo/odoo.conf:ro',
                      '-v', str(ROOT / 'addons') + ':/mnt/extra-addons:ro',
                      '-v', prefix + '-odoodata:/var/lib/odoo']
            if not (directory / 'initialized').exists():
                if exists('container', init):
                    old = inspect(init)
                    if old['State']['Running'] or old['State']['ExitCode'] != 0:
                        raise RuntimeError('Instalación pendiente: revisar contenedor ' + init)
                else:
                    run('run', '--name', init, *common, images['odoo:18.0'], 'odoo',
                        '-c', '/etc/odoo/odoo.conf', '-i', 'uno360x_tenant_config',
                        '--without-demo=all', '--stop-after-init')
                identity = '''import json
p=json.loads(%r)
Identity=env['uno360x.tenant.identity']
existing=Identity.search([])
if existing:
    assert len(existing)==1 and existing.tenant_id==p['id'] and existing.hostname==p['hostname']
else:
    Identity.create({'tenant_id':p['id'],'hostname':p['hostname']})
env.ref('base.main_company').name=p['slug']+' (LABORATORIO)'
env.ref('base.user_admin').write({'login':'admin@'+p['hostname'], 'password':p['password']})
env['ir.cron'].search([]).write({'active':False})
env.cr.commit()
print('IDENTITY_OK')
''' % json.dumps({'id': tenant['id'], 'slug': slug, 'hostname': tenant['hostname'], 'password': admin_pass})
                response = run('run', '--rm', '-i', *common, images['odoo:18.0'],
                               'odoo', 'shell', '-c', '/etc/odoo/odoo.conf', '--no-http', input=identity)
                assert 'IDENTITY_OK' in response.stdout
                (directory / 'initialized').touch()
            if not exists('container', app):
                run('run', '-d', '--name', app, *common, images['odoo:18.0'],
                    'odoo', '-c', '/etc/odoo/odoo.conf')
            else:
                run('start', app)
            appinfo, dbinfo = inspect(app), inspect(db)
            assert not any(appinfo['NetworkSettings']['Ports'].values())
            assert not any(dbinfo['NetworkSettings']['Ports'].values())
            net = json.loads(run('network', 'inspect', network).stdout)[0]
            assert net['internal']
            assert len(net['containers']) == 2, 'Solo aplicación y base por red'
            ip = appinfo['NetworkSettings']['Networks'][network]['IPAddress']
            for _ in range(45):
                try:
                    with urllib.request.urlopen('http://' + ip + ':8069/web/login', timeout=3) as r:
                        assert r.status == 200
                    break
                except Exception:
                    time.sleep(1)
            else:
                raise RuntimeError('Login de laboratorio no disponible.')
            results.append({'tenant_id':tenant['id'], 'hostname':tenant['hostname'],
                            'modules_desired':tenant['modules'], 'app':app,'db':db,
                            'network':network,'database':dbname,'role':role,
                            'data_volume':prefix+'-odoodata','login_http':200,
                            'ports_published':False, 'external_access_enabled':False})
        assert results[0]['data_volume'] != results[1]['data_volume']
        assert results[0]['database'] != results[1]['database']
        for current, other in ((results[0],results[1]),(results[1],results[0])):
            wrong_password=(state / other['tenant_id'] / 'database-password').read_text()
            credentials_probe='''import configparser,psycopg2
c=configparser.ConfigParser();c.read('/etc/odoo/odoo.conf');o=c['options']
conn=psycopg2.connect(host=o['db_host'],user=o['db_user'],password=o['db_password'],dbname=o['db_name'],connect_timeout=3);conn.close()
try:
 conn=psycopg2.connect(host=o['db_host'],user=o['db_user'],password=%r,dbname=o['db_name'],connect_timeout=3)
except psycopg2.OperationalError:
 print('INDEPENDENT_CREDENTIALS_OK')
else:
 conn.close();raise SystemExit(1)
''' % wrong_password
            assert 'INDEPENDENT_CREDENTIALS_OK' in run('exec','-i',current['app'],'python3','-',input=credentials_probe).stdout
            marker="from pathlib import Path;p=Path('/var/lib/odoo/tenant-isolation-check.txt');p.write_text(%r);assert p.read_text()==%r;print('FILES_OK')" % (current['tenant_id'],current['tenant_id'])
            assert 'FILES_OK' in run('exec',current['app'],'python3','-c',marker).stdout
            # Other tenant has no role or database in this private PostgreSQL server.
            checks = run('exec', current['db'], 'psql', '-U', 'postgres', '-d', current['database'], '-Atc',
                         "SELECT count(*) FROM pg_roles WHERE rolname='%s'; SELECT count(*) FROM pg_database WHERE datname='%s'; SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname='%s'; SELECT count(*) FROM ir_cron WHERE active; SELECT tenant_id,hostname FROM uno360x_tenant_identity; SELECT count(*) FROM ir_mail_server;" % (other['role'],other['database'],current['role'])).stdout.strip().splitlines()
            assert checks == ['0','0','f|f|f|f','0',current['tenant_id']+'|'+current['hostname'],'0'], checks
            # Verify network-level separation: peer server has no route from app.
            otherip=inspect(other['db'])['NetworkSettings']['Networks'][other['network']]['IPAddress']
            probe="import socket\ns=socket.socket();s.settimeout(2)\ntry:\n s.connect((%r,5432))\nexcept OSError:\n print('BLOCKED')\nelse:\n raise SystemExit(1)\n" % otherip
            assert 'BLOCKED' in run('exec', current['app'], 'python3', '-c', probe).stdout
        report={'mode':'isolated_local_lab','real_lab_instances':True,
                'commercial_modules_installed':False,'dns_created':False,
                'cross_tenant_network_blocked':True,'independent_credentials_verified':True,
                'independent_file_volumes_verified':True,'tenants':results}
        protected(state / 'README.txt','Credenciales de laboratorio: no publicar ni copiar al repositorio.\n')
        (state / 'verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        registry.close()


if __name__ == '__main__':
    main()
