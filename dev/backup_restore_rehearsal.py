"""Encrypt one fictional tenant and restore it to a new private sandbox.

Never production. Restored containers are stopped at the end, not deleted.
Keys/backups stay under protected WSL storage; no secrets reach Git or stdout.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter,STATE
from control_state import DIRECTORY
from tenants import run,exists,inspect,protected
from control.recovery import seal,unseal,safe_volume
from control.bridge_protocol import mint
from control.access_broker import _rpc,NoRedirect
import http.cookiejar

def binary(*args,input=None):
    result=subprocess.run(['podman',*args],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:raise RuntimeError('Operación binaria local falló: '+args[0])
    return result.stdout

def main():
    adapter=LocalAdapter();os.umask(0o077)
    db=sqlite3.connect((DIRECTORY/'control.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:s=json.loads(db.execute("SELECT snapshot FROM preparation_jobs WHERE status='ready_local' ORDER BY tenant_id LIMIT 1").fetchone()[0])
    finally:db.close()
    n=adapter.names(s);backup_id=uuid.uuid4().hex
    directory=STATE/'backups';directory.mkdir(mode=0o700,exist_ok=True);os.chmod(directory,0o700)
    keyfile=directory/'recovery.key'
    if not keyfile.exists():
        fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as handle:handle.write(secrets.token_bytes(32))
    key=keyfile.read_bytes()
    with adapter.lock(s['tenant_id']):
        adapter.check_container(n['app'],s);adapter.check_container(n['database'],s)
        run('stop',n['app'])
        try:
            dump=binary('exec',n['database'],'pg_dump','-U','postgres','-Fc',n['role'])
            files=binary('volume','export',n['files'])
        finally:run('start',n['app'])
    clean,hashes=safe_volume(files)
    manifest={'database_sha256':hashlib.sha256(dump).hexdigest(),'files_sha256':hashlib.sha256(clean).hexdigest(),
              'file_hashes':hashes,'original_database':n['role']}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('database.dump',dump);archive.writestr('files.tar',clean)
        archive.writestr('snapshot.json',json.dumps(s));archive.writestr('manifest.json',json.dumps(manifest))
    envelope=seal(buffer.getvalue(),{'version':1,'tenant_id':s['tenant_id'],'backup_id':backup_id},key)
    path=directory/(backup_id+'.aesgcm');path.write_bytes(envelope)
    metadata,payload=unseal(path.read_bytes(),key,s['tenant_id'])
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if set(archive.namelist())!={'database.dump','files.tar','snapshot.json','manifest.json'}:raise RuntimeError('Contenido de respaldo inesperado.')
        restored_dump=archive.read('database.dump');restored_tar=archive.read('files.tar')
        manifest=json.loads(archive.read('manifest.json'));restored_snapshot=json.loads(archive.read('snapshot.json'))
    assert restored_snapshot==s
    assert hashlib.sha256(restored_dump).hexdigest()==manifest['database_sha256']
    assert hashlib.sha256(restored_tar).hexdigest()==manifest['files_sha256']
    prefix='uno360x-restore-'+backup_id
    network=prefix+'-net';pg=prefix+'-db';app=prefix+'-app'
    pgvolume=prefix+'-pgdata';data=prefix+'-odoodata';role='restore_'+backup_id
    work=directory/backup_id;work.mkdir(mode=0o700)
    labels=['--label','uno360x.environment=local-recovery-test','--label','uno360x.backup='+backup_id]
    run('network','create','--internal',*labels,network)
    run('volume','create',*labels,pgvolume);run('volume','create',*labels,data)
    password=secrets.token_hex(32)
    envfile=protected(work/'postgres.env','POSTGRES_PASSWORD='+secrets.token_hex(32)+'\n')
    sql=protected(work/'bootstrap.sql',"CREATE ROLE %s LOGIN PASSWORD '%s' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; CREATE DATABASE %s OWNER %s; REVOKE CONNECT ON DATABASE %s FROM PUBLIC;"%(role,password,role,role,role));os.chmod(sql,0o644)
    run('run','-d','--name',pg,'--network',network,*labels,'--memory','384m','--cpus','0.4',
        '--env-file',str(envfile),'-v',pgvolume+':/var/lib/postgresql/data','-v',str(sql)+':/docker-entrypoint-initdb.d/01.sql:ro',adapter.images['postgres:16'])
    app_created=False
    try:
        for _ in range(60):
            if run('exec',pg,'pg_isready','-U','postgres','-d',role,check=False).returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('PostgreSQL de restauración no disponible.')
        binary('exec','-i',pg,'pg_restore','-U','postgres','--role',role,'--no-owner','--no-privileges','-d',role,input=restored_dump)
        # Rename only the database filestore directory; sessions are excluded.
        remapped=io.BytesIO();expected={}
        def rename(name):
            name=str(Path(name))
            old='filestore/'+manifest['original_database']
            return 'filestore/'+role+name[len(old):] if name==old or name.startswith(old+'/') else name
        with tarfile.open(fileobj=io.BytesIO(restored_tar)) as source,tarfile.open(fileobj=remapped,mode='w') as target:
            for member in source:
                copied=copy.copy(member);copied.name=rename(member.name);copied.pax_headers=dict(member.pax_headers);copied.pax_headers.pop('path',None)
                target.addfile(copied,source.extractfile(member) if member.isfile() else None)
        for name,value in manifest['file_hashes'].items():expected[rename(name)]=value
        binary('volume','import',data,'-',input=remapped.getvalue())
        _,actual=safe_volume(binary('volume','export',data));assert actual==expected
        # Podman import preserves entries but leaves the volume mountpoint
        # root-owned. Restore ownership of that directory only, not a broad
        # recursive permission rewrite or changes to an operational volume.
        ids=run('run','--rm','--network','none','--entrypoint','python3',adapter.images['odoo:18.0'],
                '-c','import os;print(os.getuid(),os.getgid())').stdout.strip().split()
        uid,gid=map(int,ids)
        run('run','--rm','--network','none','--user','0','--entrypoint','python3',
            '-v',data+':/var/lib/odoo',adapter.images['odoo:18.0'],'-c',
            "import os;os.chown('/var/lib/odoo',%d,%d);os.chmod('/var/lib/odoo',0o750)"%(uid,gid))
        run('exec',pg,'psql','-U','postgres','-d',role,'-c',"UPDATE ir_cron SET active=false; UPDATE ir_mail_server SET active=false; UPDATE mail_mail SET state='cancel' WHERE state IN ('outgoing','exception');")
        config=protected(work/'odoo.conf',f'''[options]
admin_passwd = {secrets.token_hex(32)}
db_host = {pg}
db_user = {role}
db_password = {password}
db_name = {role}
dbfilter = ^{role}$
list_db = False
data_dir = /var/lib/odoo
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
workers = 0
max_cron_threads = 0
''');os.chmod(config,0o644)
        bridge=work/'bridge.key';bridge.write_bytes(secrets.token_bytes(32));os.chmod(bridge,0o644)
        run('run','-d','--name',app,'--network',network,*labels,'--memory','1024m','--cpus','0.7',
            '-v',str(config)+':/etc/odoo/odoo.conf:ro','-v',str(bridge)+':/run/uno360x/bridge.key:ro',
            '-v',str(ROOT/'addons')+':/mnt/extra-addons:ro','-v',data+':/var/lib/odoo',adapter.images['odoo:18.0'],'odoo','-c','/etc/odoo/odoo.conf')
        app_created=True
        info=inspect(app);assert not any(info['NetworkSettings']['Ports'].values())
        ip=info['NetworkSettings']['Networks'][network]['IPAddress']
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(45):
            try:
                with opener.open('http://'+ip+':8069/web/login',timeout=3) as response:
                    if response.status==200:break
            except Exception:pass
            time.sleep(1)
        else:raise RuntimeError('Odoo restaurado no responde.')
        restored_identity=run('exec',pg,'psql','-U','postgres','-d',role,'-Atc','SELECT tenant_id,hostname FROM uno360x_tenant_identity').stdout.strip()
        assert restored_identity==s['tenant_id']+'|'+s['hostname']
        account=run('exec',pg,'psql','-U','postgres','-d',role,'-Atc','SELECT uno360x_account_id FROM res_users WHERE uno360x_account_id IS NOT NULL ORDER BY id LIMIT 1').stdout.strip()
        assertion=mint(bridge.read_bytes(),s['tenant_id'],account)
        authenticated=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}),NoRedirect())
        result=_rpc(authenticated,'http://'+ip+':8069','/uno360x/bridge/login',{'login':'saas_'+account,'assertion':assertion})
        assert result['authenticated'] and result['uid'] not in (1,2)
        companies=_rpc(authenticated,'http://'+ip+':8069','/web/dataset/call_kw/res.company/search_read',{'model':'res.company','method':'search_read','args':[],'kwargs':{'fields':['name'],'limit':10}})
        assert len(companies)==1
        report={'encrypted_backup':True,'authenticated_decryption':True,'database_restored':True,
                'file_hashes_verified':len(expected),'restored_login_http':200,'restored_network_private':True,
                'sessions_excluded':True,'restore_bridge_key_rotated':True,'production_touched':False,
                'restored_user_authenticated':True,
                'external_backup_copy_configured':False,'portable_key_recovery_configured':False}
        (directory/'verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:
        if app_created:run('stop',app,check=False)
        run('stop',pg,check=False)

if __name__=='__main__':main()
