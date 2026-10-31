"""Read existing automatic lab instances and verify isolation; no provisioning."""
import json
import re
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter,STATE
from control_state import DIRECTORY
from tenants import run,inspect
from control.catalog import installation_profile

def main():
    adapter=LocalAdapter()
    db=sqlite3.connect((DIRECTORY/'control.sqlite3').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        jobs=db.execute('SELECT j.*,t.slug,t.modules FROM preparation_jobs j JOIN tenants t ON t.id=j.tenant_id ORDER BY t.slug').fetchall()
        assert {r['slug'] for r in jobs}=={'auto-empresa-alfa','auto-empresa-beta'}
        results=[];snapshots=[]
        for job in jobs:
            assert job['status']=='ready_local'
            assert installation_profile(json.loads(job['modules']))['fingerprint']==job['fingerprint']
            s=json.loads(job['snapshot']);snapshots.append(s);n=adapter.names(s)
            for name in [n['app'],n['database']]:assert adapter.check_container(name,s)['State']['Running']
            network=json.loads(run('network','inspect',n['network']).stdout)[0]
            assert network['internal'] and len(network['containers'])==2
            adapter.check_modules(s)
            state=adapter.sql(s,"SELECT tenant_id,hostname FROM uno360x_tenant_identity; SELECT count(*) FROM ir_cron WHERE active; SELECT count(*) FROM ir_mail_server; SELECT count(*) FROM sale_order; SELECT count(*) FROM purchase_order; SELECT count(*) FROM account_move; SELECT count(*) FROM res_groups_users_rel r JOIN ir_model_data d ON d.model='res.groups' AND d.res_id=r.gid WHERE d.module='base' AND d.name='group_system' AND r.uid IN (SELECT id FROM res_users WHERE uno360x_account_id IS NOT NULL);")
            assert state.splitlines()==[s['tenant_id']+'|'+s['hostname']]+['0']*6,state
            log=(n['directory']/'install.log').read_text()
            counts=re.findall(r'(\d+) failed, (\d+) error\(s\) of (\d+) tests',log)
            assert counts and all(int(a)==0 and int(b)==0 for a,b,c in counts) and int(counts[-1][2])>=3
            optional={'uno360x_payroll_hr','uno360x_jenifer_core','uno360x_projects_services'}
            for excluded in optional-set(s['installation']['addons']):
                assert adapter.sql(s,"SELECT count(*) FROM ir_module_module WHERE name='%s' AND state='installed'"%excluded)=='0'
            results.append({'company':job['slug'],'status':'ready_local','installed_own_packages':len(s['installation']['addons']),
                            'bridge_orm_tests':int(counts[-1][2]),'unselected_options_installed':False,
                            'central_users_have_settings_access':False,'public_ports':False})
        a,b=snapshots
        assert adapter.bridge_key(a)!=adapter.bridge_key(b)
        assert (adapter.names(a)['directory']/'database-password').read_text()!=(adapter.names(b)['directory']/'database-password').read_text()
        assert adapter.names(a)['files']!=adapter.names(b)['files']
        for current,other in [(a,b),(b,a)]:
            target=adapter.names(other)
            ip=inspect(target['database'])['NetworkSettings']['Networks'][target['network']]['IPAddress']
            probe="import socket\ns=socket.socket();s.settimeout(2)\ntry:\n s.connect((%r,5432))\nexcept OSError:\n print('BLOCKED')\nelse:\n raise SystemExit(1)\nfinally:\n s.close()"%ip
            assert run('exec',adapter.names(current)['app'],'python3','-c',probe).stdout.strip()=='BLOCKED'
            assert adapter.sql(current,"SELECT count(*) FROM pg_database WHERE datname='%s'"%target['role'])=='0'
        print(json.dumps({'local_only':True,'cross_database_network_blocked':True,'credentials_and_keys_distinct':True,
                          'file_volumes_distinct':True,'companies':results},indent=2))
    finally:db.close()

if __name__=='__main__':main()
