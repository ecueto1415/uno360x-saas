"""Read-only checks after installing the standard business dependency bundle."""
import json
import os
from pathlib import Path
import re
import sqlite3
from tenants import run


def main():
    if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo root dentro de WSL de laboratorio.')
    state=Path('/var/lib/uno360x-saas-dev/tenants')
    connection=sqlite3.connect((state/'registry.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:
        rows=connection.execute('SELECT id,slug FROM tenants ORDER BY slug').fetchall()
    finally:
        connection.close()
    assert {slug for _,slug in rows}=={'empresa-alfa','empresa-beta'}
    modules=['uno360x_business_base','uno360x_tenant_config','contacts','sale_management',
             'sale_stock','purchase_stock','account','purchase','stock','l10n_do']
    results=[]
    for tid,slug in rows:
        sql="SELECT name,state FROM ir_module_module WHERE name IN (%s) ORDER BY name;" % ','.join("'%s'"%m for m in modules)
        actual=run('exec','uno360x-lab-'+slug+'-db','psql','-U','postgres','-d','tenant_'+tid[:16],'-Atc',sql).stdout.strip().splitlines()
        assert actual==[m+'|installed' for m in sorted(modules)],actual
        fiscal=run('exec','uno360x-lab-'+slug+'-db','psql','-U','postgres','-d','tenant_'+tid[:16],'-Atc',
                   "SELECT count(*) FROM res_company WHERE uno360x_ecf_setup_state IS DISTINCT FROM 'not_started';").stdout.strip()
        assert fiscal=='0'
        log=(state/tid/'business-base-tests.log').read_text()
        counts=re.findall(r'(\d+) failed, (\d+) error\(s\) of (\d+) tests',log)
        assert counts and all(int(f)==0 and int(e)==0 for f,e,n in counts) and int(counts[-1][2])>=3
        results.append({'company':slug,'standard_modules_installed':len(modules),
                        'business_tests':int(counts[-1][2]),'failed':0,'errors':0,
                        'fiscal_setup_not_started':True})
    print(json.dumps({'read_only':True,'commercial_parity_with_production':False,'companies':results},indent=2))


if __name__=='__main__':
    main()
