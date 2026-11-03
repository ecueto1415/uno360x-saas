"""Shared container provisioning mechanics. Environment guards live in adapters."""
from contextlib import contextmanager
import subprocess
import json
import os
from pathlib import Path
import re
import secrets
import time
import urllib.request



class ContainerAdapter:
    def __init__(self, state, images, root, environment, prefix):
        self.state=Path(state);self.root=Path(root)
        self.environment,self.prefix=environment,prefix
        assert re.fullmatch('[a-z0-9-]+',prefix)
        self.state.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.state.is_symlink() or self.state.stat().st_uid!=os.geteuid():
            raise RuntimeError('Unowned provisioning state')
        os.chmod(self.state,0o700);self.images=dict(images)

    def run(self,*args,input=None,check=True):
        p=subprocess.run(['podman',*args],input=input,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1200)
        if check and p.returncode:raise RuntimeError('Container operation failed: '+args[0])
        return p

    def exists(self,kind,name):return self.run(kind,'exists',name,check=False).returncode==0
    def inspect(self,name):return json.loads(self.run('inspect',name).stdout)[0]
    def protected(self,path,content):
        if path.is_symlink():raise RuntimeError('Unexpected secret path')
        if not path.exists():
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as out:out.write(content)
        return path

    def names(self,snapshot):
        tid=snapshot['tenant_id']
        if not re.fullmatch('[a-f0-9]{32}',tid) or snapshot['mode']!='local_laboratory':
            raise ValueError('Identidad local inválida.')
        prefix=self.prefix+tid
        return {'prefix':prefix,'network':prefix+'-net','database':prefix+'-db',
                'app':prefix+'-app','init':prefix+'-init','role':'tenant_'+tid,
                'pgvolume':prefix+'-pgdata','files':prefix+'-odoodata','directory':self.state/tid}

    @contextmanager
    def lock(self,tid):
        import fcntl
        if not re.fullmatch('[a-f0-9]{32}',tid):raise ValueError('Identidad inválida.')
        directory=self.state/tid
        if directory.is_symlink():raise RuntimeError('Unexpected tenant path')
        directory.mkdir(mode=0o700,exist_ok=True);os.chmod(directory,0o700)
        with (directory/'worker.lock').open('a') as handle:
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Otra preparación está en curso.') from None
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)

    def labels(self,s):
        return {'uno360x.environment':self.environment,'uno360x.tenant':s['tenant_id'],
                'uno360x.product':s.get('resource_fingerprint',s['installation']['fingerprint'])}

    def label_args(self,s):
        return [value for k,v in self.labels(s).items() for value in ('--label',k+'='+v)]

    def check_container(self,name,s,info=None):
        if info is None:info=self.inspect(name)
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
        if not self.exists('volume',name):self.run('volume','create',*self.label_args(s),name)
        info=json.loads(self.run('volume','inspect',name).stdout)[0]
        if not all((info.get('Labels') or {}).get(k)==v for k,v in self.labels(s).items()):
            raise RuntimeError('Volumen ajeno; no se modifica.')

    def network(self,s):
        n=self.names(s)
        if not self.exists('network',n['network']):
            self.run('network','create','--internal',*self.label_args(s),n['network'])
        info=json.loads(self.run('network','inspect',n['network']).stdout)[0]
        if not info['internal'] or not all((info.get('labels') or {}).get(k)==v for k,v in self.labels(s).items()):
            raise RuntimeError('Red ajena o no aislada; no se modifica.')

    def database(self,s):
        n=self.names(s);directory=n['directory']
        self.volume(n['pgvolume'],s);self.volume(n['files'],s)
        password=self.protected(directory/'database-password',secrets.token_hex(32)).read_text()
        self.protected(directory/'operator-password',secrets.token_hex(32))
        key=directory/'bridge.key'
        if not key.exists():
            fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as handle:handle.write(secrets.token_bytes(32))
        os.chmod(key,0o644)  # Parent root-only; read-only file bind inside own app.
        pg_env=self.protected(directory/'postgres.env','POSTGRES_PASSWORD='+secrets.token_hex(32)+'\n')
        sql=self.protected(directory/'bootstrap.sql',"CREATE ROLE %s LOGIN PASSWORD '%s' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;\nCREATE DATABASE %s OWNER %s;\nREVOKE CONNECT ON DATABASE %s FROM PUBLIC;\n"%(n['role'],password,n['role'],n['role'],n['role']))
        config=self.protected(directory/'odoo.conf','''[options]
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
db_maxconn = 12
proxy_mode = False
without_demo = all
http_interface = 0.0.0.0
'''%(secrets.token_hex(32),n['database'],n['role'],password,n['role'],n['role']))
        os.chmod(sql,0o644);os.chmod(config,0o644)
        if not self.exists('container',n['database']):
            self.run('run','-d','--name',n['database'],'--network',n['network'],*self.label_args(s),
                *getattr(self,'database_limits',['--cpus','0.4','--memory','384m']),'--env-file',str(pg_env),
                '-v',n['pgvolume']+':/var/lib/postgresql/data','-v',str(sql)+':/docker-entrypoint-initdb.d/01-tenant.sql:ro',self.images['postgres:16'],*getattr(self,'database_command',[]))
        else:
            self.check_container(n['database'],s);self.run('start',n['database'])
        for _ in range(60):
            # pg_isready alone also succeeds during the image's temporary
            # bootstrap server, before the tenant DB exists. Wait for PID 1
            # to be the final PostgreSQL server and verify the actual database.
            probe=self.run('exec',n['database'],'sh','-c',"test \"$(cat /proc/1/comm)\" = postgres && psql -U postgres -d "+n['role']+" -Atc 'SELECT 1'",check=False)
            if probe.returncode==0 and probe.stdout.strip()=='1':return
            time.sleep(1)
        raise RuntimeError('Base de datos no disponible.')

    def common(self,s):
        n=self.names(s)
        return ['--network',n['network'],*self.label_args(s),'--cpus','1','--memory','1536m',
                '-v',str(n['directory']/'odoo.conf')+':/etc/odoo/odoo.conf:ro',
                '-v',str(n['directory']/'bridge.key')+':/run/uno360x/bridge.key:ro',
                '-v',str(self.root/'addons')+':/mnt/extra-addons:ro','-v',n['files']+':/var/lib/odoo']

    def sql(self,s,sql):
        n=self.names(s)
        return self.run('exec',n['database'],'psql','-U','postgres','-d',n['role'],'-Atc',sql).stdout.strip()

    def installation(self,s):
        n=self.names(s);addons=sorted(s['installation']['addons'])
        marker=n['directory']/'installed.json'
        if marker.exists():
            if json.loads(marker.read_text())['fingerprint']!=s['installation']['fingerprint']:
                raise RuntimeError('Se requiere migración de producto.')
            self.check_modules(s);return
        if self.exists('container',n['init']):
            info=self.check_container(n['init'],s)
            if info['State']['Running'] or info['State']['ExitCode']!=0:
                raise RuntimeError('Instalación pendiente; revisar sin duplicar recursos.')
        else:
            result=self.run('run','--name',n['init'],'--log-driver','k8s-file','--oom-score-adj','500',*self.common(s),self.images['odoo:18.0'],
                       'odoo','-c','/etc/odoo/odoo.conf','-i',','.join(addons),'--without-demo=all','--stop-after-init',
                       '--test-enable','--test-tags','/uno360x_auth_bridge',check=False)
            (n['directory']/'install.log').write_text(result.stdout+'\n'+result.stderr)
            if result.returncode:raise RuntimeError('Instalación fallida; revisar log local protegido.')
        log=(n['directory']/'install.log').read_text() if (n['directory']/'install.log').exists() else self.run('logs',n['init']).stdout
        counts=re.findall(r'(\d+) failed, (\d+) error\(s\) of (\d+) tests',log)
        if not counts or any(int(a) or int(b) for a,b,c in counts) or int(counts[-1][2])<3:
            raise RuntimeError('Suite de autenticación no aprobada.')
        self.check_modules(s)
        marker.write_text(json.dumps({'fingerprint':s['installation']['fingerprint']}))

    def check_modules(self,s):
        wanted=sorted(s['installation']['addons'])
        actual=self.sql(s,"SELECT name FROM ir_module_module WHERE state='installed' AND name IN (%s) ORDER BY name"%','.join("'%s'"%name for name in wanted)).splitlines()
        if actual!=wanted:raise RuntimeError('Instalación incompleta.')

    @contextmanager
    def batch_shell(self,s):
        if hasattr(self,'_shell_scripts'):raise RuntimeError('Nested identity batch')
        self._shell_scripts=[]
        try:
            yield
            scripts=self._shell_scripts
        finally:
            del self._shell_scripts
        if scripts:self.shell(s,'\n'.join(scripts))

    def shell(self,s,code):
        if hasattr(self,'_shell_scripts'):
            self._shell_scripts.append(code);return 'UNO360X_OK'
        result=self.run('run','--rm','-i','--oom-score-adj','500',*self.common(s),self.images['odoo:18.0'],
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
 lang=env['res.lang'].with_context(active_test=False).search([('code','=','es_DO')])
 assert len(lang)==1
 if not lang.active:
  env['base.language.install'].create({'lang_ids':[(6,0,lang.ids)],'overwrite':False}).lang_install()
env.ref('base.user_admin').with_context(no_reset_password=True).write({'login':'operator_'+p['tenant'],'password':p['operator_password']})
env['ir.cron'].search([]).write({'active':False})
env.cr.commit()
print('UNO360X_OK')
"""%json.dumps(p))

    def validation(self,s):
        n=self.names(s)
        if not self.exists('container',n['app']):
            self.run('run','-d','--name',n['app'],*self.common(s),self.images['odoo:18.0'],'odoo','-c','/etc/odoo/odoo.conf')
        else:
            self.check_container(n['app'],s);self.run('start',n['app'])
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

    def _user_is_current(self,s,claims,groups):
        # Read-only equivalence check, not an authorization cache. Any missing
        # identity, role/group drift or company mismatch takes the normal ORM
        # synchronization path. The incoming identity is checked by sync_user.
        import base64
        payload=base64.b64encode(json.dumps(dict(claims,groups=groups)).encode()).decode()
        query="""WITH RECURSIVE
        payload AS (SELECT convert_from(decode('%s','base64'),'UTF8')::jsonb p),
        wanted AS (SELECT d.res_id id,d.module||'.'||d.name xmlid FROM ir_model_data d,payload
          WHERE d.model='res.groups' AND d.module||'.'||d.name IN (SELECT jsonb_array_elements_text(p->'groups') FROM payload)),
        expected_groups(id) AS (SELECT id FROM wanted UNION SELECT rel.hid FROM res_groups_implied_rel rel JOIN expected_groups e ON rel.gid=e.id),
        company AS (SELECT c.id,co.code FROM res_company c JOIN ir_model_data d ON d.res_id=c.id AND d.model='res.company' AND d.module='base' AND d.name='main_company'
          LEFT JOIN res_partner cp ON cp.id=c.partner_id LEFT JOIN res_country co ON co.id=cp.country_id),
        home AS (SELECT res_id id FROM ir_model_data WHERE module='uno360x_workspace' AND name='action_home')
        SELECT u.id FROM res_users u JOIN res_partner partner ON partner.id=u.partner_id,company,payload
        WHERE u.uno360x_account_id=p->>'account_id' AND u.login='saas_'||(p->>'account_id')
          AND u.id NOT IN (1,2) AND u.active AND NOT u.share AND partner.email=p->>'email'
          AND u.company_id=company.id
          AND (SELECT array_agg(cid ORDER BY cid) FROM res_company_users_rel WHERE user_id=u.id)=ARRAY[company.id]
          AND (SELECT count(DISTINCT xmlid) FROM wanted)=jsonb_array_length(p->'groups')
          AND NOT EXISTS(SELECT id FROM expected_groups EXCEPT SELECT gid FROM res_groups_users_rel WHERE uid=u.id)
          AND NOT EXISTS(SELECT gid FROM res_groups_users_rel WHERE uid=u.id EXCEPT SELECT id FROM expected_groups)
          AND NOT EXISTS(SELECT 1 FROM expected_groups e JOIN ir_model_data d ON d.res_id=e.id AND d.model='res.groups' WHERE d.module='base' AND d.name='group_system')
          AND (company.code IS DISTINCT FROM 'DO' OR NOT EXISTS(SELECT 1 FROM res_lang WHERE code='es_DO') OR partner.lang='es_DO')
          AND (NOT (to_jsonb(u) ? 'action_id') OR NOT EXISTS(SELECT 1 FROM home) OR (to_jsonb(u)->>'action_id')::int=(SELECT id FROM home))
          AND (coalesce(p->>'display_name','')='' OR partner.name IS DISTINCT FROM p->>'email' OR partner.name=p->>'display_name')
        LIMIT 2"""%payload
        try:result=self.sql(s,query).strip()
        except RuntimeError:return False
        return result.isdigit() and int(result)>2

    def sync_user(self,s,claims):
        if not re.fullmatch('[a-f0-9]{32}',claims['account_id']) or claims['tenant_id']!=s['tenant_id']:
            raise RuntimeError('Identidad de acceso inválida.')
        groups=['base.group_user','sales_team.group_sale_salesman']
        if claims['role'] in ('owner','admin'):
            groups+=['sales_team.group_sale_manager','purchase.group_purchase_manager','stock.group_stock_manager','account.group_account_manager','point_of_sale.group_pos_manager']
            if 'uno360x_payroll_hr' in s['installation']['addons']:groups+=['hr.group_hr_manager','hr_attendance.group_hr_attendance_manager','hr_holidays.group_hr_holidays_manager']
            if 'uno360x_projects_services' in s['installation']['addons']:groups+=['project.group_project_manager','hr_timesheet.group_timesheet_manager']
        if self._user_is_current(s,claims,groups):return
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
values={'name':p.get('display_name') or p['email'],'email':p['email'],'login':'saas_'+p['account_id'],
 'uno360x_account_id':p['account_id'],'active':True,'company_id':company.id,
 'company_ids':[(6,0,[company.id])],'groups_id':[(6,0,group_ids)]}
if company.country_id.code=='DO' and env['res.lang'].search([('code','=','es_DO')]):
 values['lang']='es_DO'
home=env.ref('uno360x_workspace.action_home',raise_if_not_found=False)
if home and 'action_id' in users._fields:values['action_id']=home.id
if user:
 assert len(user)==1
 if not p.get('display_name') or user.name!=p['email']:values.pop('name',None)
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
