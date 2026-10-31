"""Read-only checks of the two existing fictional WSL tenants."""
import json
import os
from pathlib import Path
import sqlite3
import urllib.request
from tenants import run, inspect


def main():
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('Solo root en WSL de laboratorio.')
    if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo WSL.')
    path=Path('/var/lib/uno360x-saas-dev/tenants/registry.sqlite3')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        rows=db.execute('SELECT id,slug,hostname FROM tenants ORDER BY slug').fetchall()
    finally:
        db.close()
    assert {r['slug'] for r in rows}=={'empresa-alfa','empresa-beta'}
    details=[]
    for tenant in rows:
        prefix='uno360x-lab-'+tenant['slug']
        app,pg,network=prefix+'-app',prefix+'-db',prefix+'-private'
        ai,pi=inspect(app),inspect(pg)
        assert ai['State']['Running'] and pi['State']['Running']
        assert not any(ai['NetworkSettings']['Ports'].values())
        assert not any(pi['NetworkSettings']['Ports'].values())
        for instance in (ai,pi):
            assert instance['Config']['Labels']['uno360x.tenant']==tenant['id']
            assert set(instance['NetworkSettings']['Networks'])=={network}
        net=json.loads(run('network','inspect',network).stdout)[0]
        assert net['internal'] and len(net['containers'])==2
        role='tenant_'+tenant['id'][:16]
        other=next(r for r in rows if r['id']!=tenant['id'])
        other_role='tenant_'+other['id'][:16]
        sql="""SELECT tenant_id,hostname FROM uno360x_tenant_identity;
SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname='%s';
SELECT count(*) FROM ir_cron WHERE active;
SELECT count(*) FROM ir_mail_server;
SELECT count(*) FROM pg_roles WHERE rolname='%s';
SELECT count(*) FROM pg_database WHERE datname='%s';
SELECT state FROM ir_module_module WHERE name='uno360x_tenant_config';""" % (role,other_role,other_role)
        actual=run('exec',pg,'psql','-U','postgres','-d',role,'-Atc',sql).stdout.strip().splitlines()
        assert actual==[tenant['id']+'|'+tenant['hostname'],'f|f|f|f','0','0','0','0','installed'],actual
        ip=ai['NetworkSettings']['Networks'][network]['IPAddress']
        with urllib.request.urlopen('http://'+ip+':8069/web/login',timeout=10) as response:
            assert response.status==200
        marker="from pathlib import Path;assert Path('/var/lib/odoo/tenant-isolation-check.txt').read_text()==%r;print('OK')" % tenant['id']
        assert run('exec',app,'python3','-c',marker).stdout.strip()=='OK'
        volume=next(m['Name'] for m in ai['Mounts'] if m['Destination']=='/var/lib/odoo')
        details.append({'company':tenant['slug'],'identity_verified':True,'login_http':200,
                        'cron_active':0,'mail_servers':0,'internal_network':True,
                        'ports_published':False,'data_volume':volume,
                        'other_tenant_role_and_database_absent':True})
    assert details[0]['data_volume']!=details[1]['data_volume']
    for current,other in ((rows[0],rows[1]),(rows[1],rows[0])):
        prefix='uno360x-lab-'+current['slug']
        otherprefix='uno360x-lab-'+other['slug']
        otherip=inspect(otherprefix+'-db')['NetworkSettings']['Networks'][otherprefix+'-private']['IPAddress']
        probe="import socket\ns=socket.socket();s.settimeout(2)\ntry:\n s.connect((%r,5432))\nexcept OSError:\n print('BLOCKED')\nelse:\n raise SystemExit(1)\nfinally:\n s.close()" % otherip
        assert run('exec',prefix+'-app','python3','-c',probe).stdout.strip()=='BLOCKED'
    print(json.dumps({'read_only':True,'cross_tenant_network_blocked':True,'tenants':details},indent=2))


if __name__=='__main__':
    main()
