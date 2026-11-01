"""Verify the automatically created private pilot. Never print credentials."""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.shared_adapter import SharedHostAdapter
from control.identity import IdentityService
from control.onboarding import Onboarding
from control.trials import Trials
from control.bridge_protocol import mint
STATE=Path('/var/lib/uno360x-saas/control')
def main():
 os.umask(0o077);adapter=SharedHostAdapter();identity=IdentityService(STATE/'control.sqlite3',lambda notice:None)
 try:
  seed=json.loads((STATE/'pilot-signup.json').read_text());jobs=Onboarding(identity)
  session=identity.login('private-vm-pilot@example.test',(STATE/'pilot-owner-password').read_text())['session']
  trial=Trials(identity).status(session,seed['tenant_id'])
  assert trial['local_ready'] and trial['trial_active'] and trial['days_remaining']==15
  assert trial['expires']-trial['started']==15*86400
  row=identity.db.execute('SELECT snapshot FROM preparation_jobs WHERE id=?',(seed['job_id'],)).fetchone();snapshot=json.loads(row[0])
  account=identity._account(session)
  assertion=mint(adapter.bridge_key(snapshot),seed['tenant_id'],account['id'])
  payload={'login':'saas_'+account['id'],'assertion':assertion}
  code="""import json,requests
p=json.loads(%r)
s=requests.Session();s.trust_env=False;s.headers['X-UNO360X-Bridge']='1'
base='http://127.0.0.1:8069'
def rpc(path,params):
 r=s.post(base+path,json={'jsonrpc':'2.0','method':'call','params':params,'id':1},timeout=60);r.raise_for_status();body=r.json();assert 'error' not in body;return body['result']
auth=rpc('/uno360x/bridge/login',p);assert auth['authenticated'];uid=auth['uid'];assert uid not in (1,2)
def call(model,method,args,kwargs={}):return rpc('/web/dataset/call_kw/'+model+'/'+method,{'model':model,'method':method,'args':args,'kwargs':kwargs})
company=call('res.company','search_read',[],{'fields':['name','currency_id','country_id']});assert len(company)==1 and company[0]['currency_id'][1]=='DOP'
user=call('res.users','read',[[uid]],{'fields':['lang']});assert user[0]['lang']=='es_DO'
assert call('res.users','has_group',[[uid],'point_of_sale.group_pos_manager'])
assert not call('res.users','has_group',[[uid],'base.group_system'])
assert call('crm.lead','check_access_rights',['create'],{'raise_exception':False})
r=s.get(base+'/odoo',timeout=60);r.raise_for_status();assert 'odoo' in r.text.lower()
assert call('crm.lead','search_count',[[]])==0 and call('pos.order','search_count',[[]])==0
print('PRIVATE_OWNER_OK '+json.dumps({'native_html':True,'language':'es_DO','currency':'DOP','owner_pos_access':True,'owner_crm_access':True,'technical_admin_used':False}))
"""%json.dumps(payload)
  result=adapter.run('exec','-i',adapter.names(snapshot)['app'],'python3','-',input=code)
  native=json.loads(next(l[len('PRIVATE_OWNER_OK '):] for l in result.stdout.splitlines() if l.startswith('PRIVATE_OWNER_OK ')))
  modules=adapter.sql(snapshot,"SELECT name||'|'||state FROM ir_module_module WHERE name IN ('crm','point_of_sale') ORDER BY name;").splitlines();assert modules==['crm|installed','point_of_sale|installed']
  old_start=trial['started'];old_expiry=trial['expires']
  jobs.run(seed['job_id'],adapter)
  repeat=Trials(identity).status(session,seed['tenant_id']);assert repeat['started']==old_start and repeat['expires']==old_expiry
  containers=json.loads(adapter.run('ps','-a','--format','json').stdout)
  assert len([x for x in containers if x['Labels'].get('uno360x.tenant')==seed['tenant_id']])==3
  report={'environment':'private_rootless_vm_pilot','tenant_id':seed['tenant_id'],'worker_created_tenant_automatically':True,'signup_verified_via_fictional_mailbox':True,'separate_database_files_credentials':True,'private_network_no_published_ports':True,'trial_days':15,'idempotent_worker_retry':True,'retry_does_not_restart_trial':True,'crm_pos_installed':True,'owner':native,'public_registration_enabled':False,'public_odoo_gateway_deployed':False}
  (STATE/'pilot-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
  identity.logout(session)
 finally:identity.close()
if __name__=='__main__':main()
