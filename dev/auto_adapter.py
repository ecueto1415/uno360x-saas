"""Privileged WSL-only adapter. Strictly owned, private, fictional resources."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import time
import urllib.request

from tenants import run,exists,inspect,protected,ROOT

STATE=Path('/var/lib/uno360x-saas-dev/automatic')


class LocalAdapter:
    def __init__(self):
        if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
            raise RuntimeError('Solo WSL root de laboratorio.')
        STATE.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(STATE,0o700)
        self.images=json.loads(Path('/var/lib/uno360x-saas-dev/images.json').read_text())

    def names(self,snapshot):
        tid=snapshot['tenant_id']
        if not re.fullmatch('[a-f0-9]{32}',tid) or snapshot['mode']!='local_laboratory':
            raise ValueError('Identidad local inválida.')
        prefix='uno360x-auto-'+tid
        return {'prefix':prefix,'network':prefix+'-net','database':prefix+'-db',
                'app':prefix+'-app','init':prefix+'-init','role':'tenant_'+tid,
                'pgvolume':prefix+'-pgdata','files':prefix+'-odoodata','directory':STATE/tid}

    @contextmanager
    def lock(self,tid):
        if not re.fullmatch('[a-f0-9]{32}',tid):raise ValueError('Identidad inválida.')
        directory=STATE/tid;directory.mkdir(mode=0o700,exist_ok=True);os.chmod(directory,0o700)
        with (directory/'worker.lock').open('a') as handle:
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Otra preparación está en curso.') from None
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)

    def labels(self,s):
        return {'uno360x.environment':'local-development','uno360x.tenant':s['tenant_id'],
                'uno360x.product':s['installation']['fingerprint']}

    def label_args(self,s):
        return [value for k,v in self.labels(s).items() for value in ('--label',k+'='+v)]

    def check_container(self,name,s):
        info=inspect(name)
        actual=info['Config']['Labels']
        if not all(actual.get(k)==v for k,v in self.labels(s).items()):
            raise RuntimeError('Recurso ajeno o configuración distinta; no se modifica.')
        image=self.images['postgres:16' if name==self.names(s)['database'] else 'odoo:18.0']
        if info['Image'].removeprefix('sha256:')!=image.removeprefix('sha256:'):
            raise RuntimeError('Imagen distinta; no se modifica.')
        if set(info['NetworkSettings']['Networks'])!={self.names(s)['network']}:
            raise RuntimeError('Red inesperada.')
        if any(info['NetworkSettings']['Ports'].values()):raise RuntimeError('Puertos publicados inesperados.')
        return info

    def volume(self,name,s):
        if not exists('volume',name):run('volume','create',*self.label_args(s),name)
        info=json.loads(run('volume','inspect',name).stdout)[0]
        if not all((info.get('Labels') or {}).get(k)==v for k,v in self.labels(s).items()):
            raise RuntimeError('Volumen ajeno; no se modifica.')

    def network(self,s):
        n=self.names(s)
        if not exists('network',n['network']):
            run('network','create','--internal',*self.label_args(s),n['network'])
        info=json.loads(run('network','inspect',n['network']).stdout)[0]
        if not info['internal'] or not all((info.get('labels') or {}).get(k)==v for k,v in self.labels(s).items()):
            raise RuntimeError('Red ajena o no aislada; no se modifica.')

    def database(self,s):
        n=self.names(s);directory=n['directory']
        self.volume(n['pgvolume'],s);self.volume(n['files'],s)
        password=protected(directory/'database-password',secrets.token_hex(32)).read_text()
        protected(directory/'operator-password',secrets.token_hex(32))
        key=directory/'bridge.key'
        if not key.exists():
            fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as handle:handle.write(secrets.token_bytes(32))
        os.chmod(key,0o644)  # Parent root-only; read-only file bind inside own app.
        pg_env=protected(directory/'postgres.env','POSTGRES_PASSWORD='+secrets.token_hex(32)+'\n')
        sql=protected(directory/'bootstrap.sql',"CREATE ROLE %s LOGIN PASSWORD '%s' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;\nCREATE DATABASE %s OWNER %s;\nREVOKE CONNECT ON DATABASE %s FROM PUBLIC;\n"%(n['role'],password,n['role'],n['role'],n['role']))
        config=protected(directory/'odoo.conf','''[options]
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
workers = 0
max_cron_threads = 0
proxy_mode = False
without_demo = all
http_interface = 0.0.0.0
'''%(secrets.token_hex(32),n['database'],n['role'],password,n['role'],n['role']))
        os.chmod(sql,0o644);os.chmod(config,0o644)
        if not exists('container',n['database']):
            run('run','-d','--name',n['database'],'--network',n['network'],*self.label_args(s),
                '--cpus','0.4','--memory','384m','--env-file',str(pg_env),
                '-v',n['pgvolume']+':/var/lib/postgresql/data','-v',str(sql)+':/docker-entrypoint-initdb.d/01-tenant.sql:ro',self.images['postgres:16'])
        else:
            self.check_container(n['database'],s);run('start',n['database'])
        for _ in range(60):
            if run('exec',n['database'],'pg_isready','-U','postgres','-d',n['role'],check=False).returncode==0:return
            time.sleep(1)
        raise RuntimeError('Base de datos no disponible.')

    def common(self,s):
        n=self.names(s)
        return ['--network',n['network'],*self.label_args(s),'--cpus','1','--memory','1536m',
                '-v',str(n['directory']/'odoo.conf')+':/etc/odoo/odoo.conf:ro',
                '-v',str(n['directory']/'bridge.key')+':/run/uno360x/bridge.key:ro',
                '-v',str(ROOT/'addons')+':/mnt/extra-addons:ro','-v',n['files']+':/var/lib/odoo']

    def sql(self,s,sql):
        n=self.names(s)
        return run('exec',n['database'],'psql','-U','postgres','-d',n['role'],'-Atc',sql).stdout.strip()

    def installation(self,s):
        n=self.names(s);addons=sorted(s['installation']['addons'])
        marker=n['directory']/'installed.json'
        if marker.exists():
            if json.loads(marker.read_text())['fingerprint']!=s['installation']['fingerprint']:
                raise RuntimeError('Se requiere migración de producto.')
            self.check_modules(s);return
        if exists('container',n['init']):
            info=self.check_container(n['init'],s)
            if info['State']['Running'] or info['State']['ExitCode']!=0:
                raise RuntimeError('Instalación pendiente; revisar sin duplicar recursos.')
        else:
            result=run('run','--name',n['init'],'--log-driver','k8s-file',*self.common(s),self.images['odoo:18.0'],
                       'odoo','-c','/etc/odoo/odoo.conf','-i',','.join(addons),'--without-demo=all','--stop-after-init',
                       '--test-enable','--test-tags','/uno360x_auth_bridge',check=False)
            (n['directory']/'install.log').write_text(result.stdout+'\n'+result.stderr)
            if result.returncode:raise RuntimeError('Instalación fallida; revisar log local protegido.')
        log=(n['directory']/'install.log').read_text() if (n['directory']/'install.log').exists() else run('logs',n['init']).stdout
        counts=re.findall(r'(\d+) failed, (\d+) error\(s\) of (\d+) tests',log)
        if not counts or any(int(a) or int(b) for a,b,c in counts) or int(counts[-1][2])<3:
            raise RuntimeError('Suite de autenticación no aprobada.')
        self.check_modules(s)
        marker.write_text(json.dumps({'fingerprint':s['installation']['fingerprint']}))

    def check_modules(self,s):
        wanted=sorted(s['installation']['addons'])
        actual=self.sql(s,"SELECT name FROM ir_module_module WHERE state='installed' AND name IN (%s) ORDER BY name"%','.join("'%s'"%name for name in wanted)).splitlines()
        if actual!=wanted:raise RuntimeError('Instalación incompleta.')

    def shell(self,s,code):
        result=run('run','--rm','-i',*self.common(s),self.images['odoo:18.0'],
                   'odoo','shell','-c','/etc/odoo/odoo.conf','--no-http',input=code,check=False)
        if result.returncode or 'UNO360X_OK' not in result.stdout:
            raise RuntimeError('Configuración local no comprobada.')
        return result.stdout

    def identity(self,s):
        n=self.names(s)
        p={'tenant':s['tenant_id'],'hostname':s['hostname'],'slug':s['slug'],
           'operator_password':(n['directory']/'operator-password').read_text(),
           'company_profile':s.get('company_profile')}
        self.shell(s,"""import json
p=json.loads(%r)
identity=env['uno360x.tenant.identity'].search([])
if identity:
 assert len(identity)==1 and identity.tenant_id==p['tenant'] and identity.hostname==p['hostname']
else:
 env['uno360x.tenant.identity'].create({'tenant_id':p['tenant'],'hostname':p['hostname']})
env.ref('base.main_company').name=p['slug']+' (LABORATORIO)'
if p['company_profile']:
 profile=p['company_profile']
 assert profile['country']=='DO' and profile['currency'] in ('DOP','USD')
 company=env.ref('base.main_company')
 country=env['res.country'].search([('code','=',profile['country'])],limit=1)
 currency=env['res.currency'].with_context(active_test=False).search([('name','=',profile['currency'])],limit=1)
 assert country and currency
 if company.currency_id!=currency:
  assert not env['account.move'].search_count([]) and not env['sale.order'].search_count([]) and not env['purchase.order'].search_count([])
 currency.active=True
 company.write({'name':profile['name'],'country_id':country.id,'currency_id':currency.id})
env.ref('base.user_admin').with_context(no_reset_password=True).write({'login':'operator_'+p['tenant'],'password':p['operator_password']})
env['ir.cron'].search([]).write({'active':False})
env.cr.commit()
print('UNO360X_OK')
"""%json.dumps(p))

    def validation(self,s):
        n=self.names(s)
        if not exists('container',n['app']):
            run('run','-d','--name',n['app'],*self.common(s),self.images['odoo:18.0'],'odoo','-c','/etc/odoo/odoo.conf')
        else:
            self.check_container(n['app'],s);run('start',n['app'])
        info=self.check_container(n['app'],s)
        self.check_container(n['database'],s)
        self.check_modules(s)
        expected=s['tenant_id']+'|'+s['hostname']+'\n0\n0\nf|f|f|f'
        actual=self.sql(s,"SELECT tenant_id,hostname FROM uno360x_tenant_identity; SELECT count(*) FROM ir_cron WHERE active; SELECT count(*) FROM ir_mail_server; SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname='%s';"%n['role'])
        if actual!=expected:raise RuntimeError('Validación de aislamiento o identidad falló.')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url='http://'+info['NetworkSettings']['Networks'][n['network']]['IPAddress']+':8069/web/login'
        for _ in range(45):
            try:
                with opener.open(url,timeout=3) as response:
                    if response.status==200:return
            except Exception:pass
            time.sleep(1)
        raise RuntimeError('Aplicación local no responde.')

    def backend(self,s):
        info=self.check_container(self.names(s)['app'],s)
        return 'http://'+info['NetworkSettings']['Networks'][self.names(s)['network']]['IPAddress']+':8069'

    def sync_user(self,s,claims):
        if not re.fullmatch('[a-f0-9]{32}',claims['account_id']) or claims['tenant_id']!=s['tenant_id']:
            raise RuntimeError('Identidad de acceso inválida.')
        groups=['base.group_user','sales_team.group_sale_salesman']
        if claims['role'] in ('owner','admin'):
            groups+=['sales_team.group_sale_manager','purchase.group_purchase_manager','stock.group_stock_manager','account.group_account_manager']
            if 'uno360x_payroll_hr' in s['installation']['addons']:groups+=['hr.group_hr_manager','hr_attendance.group_hr_attendance_manager','hr_holidays.group_hr_holidays_manager']
            if 'uno360x_projects_services' in s['installation']['addons']:groups+=['project.group_project_manager','hr_timesheet.group_timesheet_manager']
        p=dict(claims,groups=groups,password=secrets.token_urlsafe(32))
        self.shell(s,"""import json
p=json.loads(%r)
company=env.ref('base.main_company')
identity=env['uno360x.tenant.identity'].search([])
assert len(identity)==1 and identity.tenant_id==p['tenant_id']
group_ids=[env.ref(xmlid).id for xmlid in p['groups']]
assert env.ref('base.group_system').id not in group_ids
users=env['res.users'].with_context(no_reset_password=True,tracking_disable=True)
user=users.search([('uno360x_account_id','=',p['account_id'])])
values={'name':p['email'],'email':p['email'],'login':'saas_'+p['account_id'],
 'uno360x_account_id':p['account_id'],'active':True,'company_id':company.id,
 'company_ids':[(6,0,[company.id])],'groups_id':[(6,0,group_ids)]}
if user:
 assert len(user)==1
 user.write(values)
else:
 values['password']=p['password']
 user=users.create(values)
assert not user.has_group('base.group_system')
env.cr.commit()
print('UNO360X_OK')
"""%json.dumps(p))

    def bridge_key(self,s):
        return (self.names(s)['directory']/'bridge.key').read_bytes()

    def configure_company(self,s,profile,origin):
        if set(profile)!={'name','country','currency'} or profile['country']!='DO' or profile['currency'] not in ('DOP','USD') or not isinstance(profile['name'],str) or not 1<=len(profile['name'])<=150:
            raise ValueError('Perfil básico inválido.')
        if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}',origin):
            raise ValueError('Origen local inválido.')
        self.check_container(self.names(s)['app'],s)
        payload=dict(profile,tenant=s['tenant_id'],origin=origin)
        self.shell(s,"""import json
p=json.loads(%r)
identity=env['uno360x.tenant.identity'].search([])
assert len(identity)==1 and identity.tenant_id==p['tenant']
company=env.ref('base.main_company')
country=env['res.country'].search([('code','=',p['country'])],limit=1)
currency=env['res.currency'].with_context(active_test=False).search([('name','=',p['currency'])],limit=1)
assert country and currency
if company.currency_id!=currency:
 assert not env['account.move'].search_count([]) and not env['sale.order'].search_count([]) and not env['purchase.order'].search_count([])
currency.active=True
company.write({'name':p['name'],'country_id':country.id,'currency_id':currency.id})
assert company.name==p['name'] and company.country_id.code==p['country'] and company.currency_id.name==p['currency']
parameters=env['ir.config_parameter'].sudo()
parameters.set_param('web.base.url',p['origin'])
parameters.set_param('web.base.url.freeze','True')
env.cr.commit()
print('UNO360X_OK')
"""%json.dumps(payload))
