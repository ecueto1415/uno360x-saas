"""Install and test standard business bundle on the two fictional WSL tenants."""
import json
import os
import re
from pathlib import Path
import sqlite3
import sys
from tenants import run, inspect


def main(modules=None, min_tests=3, log_name='business-base-tests.log'):
    modules=modules or ['uno360x_business_base']
    allowed={'uno360x_business_base','uno360x_quote_ui','uno360x_ecf_core',
             'uno360x_payroll_hr','uno360x_jenifer_core','uno360x_projects_services'}
    assert set(modules)<=allowed
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('Solo root dentro del WSL de laboratorio.')
    if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo WSL; nunca producción.')
    root=Path(__file__).resolve().parents[1]
    state=Path('/var/lib/uno360x-saas-dev/tenants')
    connection=sqlite3.connect((state/'registry.sqlite3').as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    try:
        tenants=connection.execute('SELECT id,slug FROM tenants ORDER BY slug').fetchall()
    finally:
        connection.close()
    assert {t['slug'] for t in tenants}=={'empresa-alfa','empresa-beta'}
    image=json.loads(Path('/var/lib/uno360x-saas-dev/images.json').read_text())['odoo:18.0']
    for tenant in tenants:
        prefix='uno360x-lab-'+tenant['slug']
        app,network,dbname=prefix+'-app',prefix+'-private','tenant_'+tenant['id'][:16]
        instance=inspect(app)
        assert instance['Config']['Labels']['uno360x.tenant']==tenant['id']
        assert not any(instance['NetworkSettings']['Ports'].values())
        assert json.loads(run('network','inspect',network).stdout)[0]['internal']
        common=['--network',network,'--cpus','1','--memory','1536m',
                '-v',str(state/tenant['id']/'odoo.conf')+':/etc/odoo/odoo.conf:ro',
                '-v',str(root/'addons')+':/mnt/extra-addons:ro',
                '-v',prefix+'-odoodata:/var/lib/odoo']
        logpath=state/tenant['id']/log_name
        installed=run('exec',prefix+'-db','psql','-U','postgres','-d',dbname,'-Atc',
                      "SELECT name FROM ir_module_module WHERE state='installed';").stdout.strip().splitlines()
        new=[name for name in modules if name not in installed]
        update=[name for name in modules if name in installed]
        flags=(['-i',','.join(new)] if new else [])+(['-u',','.join(update)] if update else [])
        run('stop',app)
        try:
            result=run('run','--rm',*common,image,'odoo','-c','/etc/odoo/odoo.conf',
                       *flags,
                       '--without-demo=all','--stop-after-init',
                       '--test-enable','--test-tags',','.join('/'+name for name in modules),check=False)
            logpath.write_text(result.stdout+'\n'+result.stderr)
            log=logpath.read_text()
            summary=[line for line in log.splitlines() if 'failed' in line and 'test' in line]
            print(tenant['slug'], '\n'.join(summary[-3:]),flush=True)
            counts=re.findall(r'(\d+) failed, (\d+) error\(s\) of (\d+) tests',log)
            if result.returncode or not counts or any(int(f) or int(e) for f,e,n in counts) or int(counts[-1][2])<min_tests:
                raise RuntimeError('Pruebas fallidas; revisar log local protegido '+str(logpath))
        finally:
            # Disable any new scheduled actions before restarting this lab app.
            run('exec',prefix+'-db','psql','-U','postgres','-d',dbname,'-c',
                'UPDATE ir_cron SET active=false WHERE active;')
            run('start',app)
    print('BUSINESS_BASE_BOTH_TENANTS_OK')


if __name__=='__main__':
    main()
