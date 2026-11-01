"""Read-only installed product and test-log checks on existing fictional tenants."""
import json
import os
from pathlib import Path
import re
import sqlite3
from tenants import run

def main():
    if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo WSL root de laboratorio.')
    state=Path('/var/lib/uno360x-saas-dev/tenants')
    db=sqlite3.connect((state/'registry.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:rows=db.execute('SELECT id,slug FROM tenants ORDER BY slug').fetchall()
    finally:db.close()
    assert {slug for tid,slug in rows}=={'empresa-alfa','empresa-beta'}
    modules=['uno360x_business_base','uno360x_quote_ui','uno360x_ecf_core',
             'uno360x_payroll_hr','uno360x_jenifer_core','uno360x_projects_services','point_of_sale']
    result=[]
    for tid,slug in rows:
        sql="SELECT name,state FROM ir_module_module WHERE name IN (%s) ORDER BY name;" % ','.join("'%s'"%x for x in modules)
        actual=run('exec','uno360x-lab-'+slug+'-db','psql','-U','postgres','-d','tenant_'+tid[:16],'-Atc',sql).stdout.strip().splitlines()
        assert actual==[m+'|installed' for m in sorted(modules)],actual
        log=(state/tid/'product-tests.log').read_text()
        counts=re.findall(r'(\d+) failed, (\d+) error\(s\) of (\d+) tests',log)
        assert counts and all(int(f)==0 and int(e)==0 for f,e,n in counts) and int(counts[-1][2])>=18
        pos_log=(state/tid/'pos-tests.log').read_text()
        pos_counts=re.findall(r'(\d+) failed, (\d+) error\(s\) of (\d+) tests',pos_log)
        assert pos_counts and all(int(f)==0 and int(e)==0 for f,e,n in pos_counts) and int(pos_counts[-1][2])>=10
        # Data created by ORM test transactions must not remain in the tenant.
        checks="SELECT count(*) FROM sale_order; SELECT count(*) FROM purchase_order; SELECT count(*) FROM account_move; SELECT count(*) FROM ir_mail_server; SELECT count(*) FROM ir_cron WHERE active; SELECT count(*) FROM mail_mail; SELECT count(*) FROM pos_order; SELECT count(*) FROM pos_session;"
        values=run('exec','uno360x-lab-'+slug+'-db','psql','-U','postgres','-d','tenant_'+tid[:16],'-Atc',checks).stdout.strip().splitlines()
        # Visual rehearsal retains one explicitly labelled, archived fixture.
        fixture_sql="SELECT s.id,s.move_id FROM pos_session s JOIN pos_config c ON c.id=s.config_id WHERE c.name='CAJA FICTICIA - REVISION UNO360X' AND NOT c.active AND s.state='closed';"
        fixture=run('exec','uno360x-lab-'+slug+'-db','psql','-U','postgres','-d','tenant_'+tid[:16],'-Atc',fixture_sql).stdout.strip().splitlines()
        expected=['0']*8
        if fixture:
            assert slug=='empresa-alfa' and len(fixture)==1,fixture
            session_id,move_id=fixture[0].split('|')
            assert session_id.isdigit() and move_id.isdigit()
            expected[2]='2';expected[6]='1';expected[7]='1'
            audit_sql=f"SELECT count(*) FROM pos_order WHERE session_id={session_id} AND state='done' AND amount_total=450 AND account_move IS NULL; SELECT count(*) FROM account_move WHERE id={move_id}; SELECT count(*) FROM account_bank_statement_line WHERE pos_session_id={session_id} AND move_id IN (SELECT id FROM account_move) AND amount=450;"
            audit=run('exec','uno360x-lab-'+slug+'-db','psql','-U','postgres','-d','tenant_'+tid[:16],'-Atc',audit_sql).stdout.strip().splitlines()
            assert audit==['1','1','1'],audit
        rd_sql="SELECT count(*) FROM pos_session s JOIN pos_config c ON c.id=s.config_id JOIN res_company co ON co.id=c.company_id JOIN res_currency r ON r.id=co.currency_id WHERE c.name='CAJA DEMO RD - LABORATORIO' AND r.name='DOP' AND s.state='closed' AND s.move_id IS NULL AND NOT EXISTS (SELECT 1 FROM pos_order o WHERE o.session_id=s.id);"
        rd_closed=int(run('exec','uno360x-lab-'+slug+'-db','psql','-U','postgres','-d','tenant_'+tid[:16],'-Atc',rd_sql).stdout.strip())
        expected[7]=str(int(expected[7])+rd_closed)
        assert values==expected,values
        result.append({'company':slug,'installed_packages':len(modules),'orm_tests':int(counts[-1][2]),
                       'pos_tests':int(pos_counts[-1][2]),'errors':0,'failures':0,'transactional_test_residue':False,'archived_visual_fixture':bool(fixture),
                       'outgoing_mail':0,'cron_active':0})
    print(json.dumps({'read_only':True,'companies':result,'commercial_release_ready':False},indent=2))

if __name__=='__main__':main()
