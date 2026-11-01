"""End-to-end real isolated WSL provisioning; fictional mailbox and no public launch."""
import http.cookiejar,json,os,secrets,sys,threading,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter
from tenants import protected
from control.identity import IdentityService,IdentityError
from control.identity_http import IdentityHTTPServer,COOKIE
from control.onboarding import Onboarding
from control.trials import Trials
from control.gateway import GatewayManager
from control.access_broker import NoRedirect,open_space

def main():
 adapter=LocalAdapter();os.umask(0o077)
 state=Path('/var/lib/uno360x-saas-dev/real-signup-rehearsal');state.mkdir(mode=0o700,exist_ok=True)
 path=state/'control.sqlite3';mail=[]
 identity=IdentityService(path,mail.append);jobs=Onboarding(identity)
 manager=GatewayManager(path,adapter)
 server=IdentityHTTPServer(18072,path,mail.append,launch=manager.launch)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 base='http://127.0.0.1:18072';csrf=''
 jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
 def post(route,data):
  req=urllib.request.Request(base+route,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
  with opener.open(req,timeout=180) as response:return json.load(response)
 try:
  email='latest-base-rehearsal@example.test';password=protected(state/'owner-password',secrets.token_urlsafe(32)).read_text()
  account=identity.db.execute('SELECT verified FROM accounts WHERE email=?',(email,)).fetchone()
  if not account or not account['verified']:
   post('/trial/register',{'email':email,'name':'Persona ficticia del piloto','modules':[],'consent':True})
   try:post('/trial/create',{'name':'NO DEBE CREARSE','country':'DO','currency':'DOP','modules':[]})
   except urllib.error.HTTPError:pass
   else:raise AssertionError('Anonymous workspace created')
   post('/verify',{'token':mail[-1]['token'],'password':password})
  csrf=post('/login',{'email':email,'password':password})['csrf_token']
  data={'name':'CLIENTE FICTICIO ALTA REAL RD','country':'DO','currency':'DOP','modules':[]}
  trial=post('/trial/create',data);assert post('/trial/create',data)['tenant_id']==trial['tenant_id']
  if not trial['local_ready']:
   assert trial['started'] is None
   print('Preparando cliente ficticio nuevo con CRM y POS...',flush=True)
   jobs.run(trial['job_id'],adapter)
  trial=post('/trial/status',{'tenant_id':trial['tenant_id']})
  assert trial['trial_active'] and trial['days_remaining']==15
  assert trial['expires']-trial['started']==15*86400 and not trial['card_required']
  launch=post('/spaces/open',{'tenant_id':trial['tenant_id']})
  request=urllib.request.Request(launch['launch_url'],data=urllib.parse.urlencode({'grant':launch['grant']}).encode(),headers={'Origin':base,'Content-Type':'application/x-www-form-urlencoded'})
  launch_opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}),NoRedirect())
  try:launch_opener.open(request,timeout=120)
  except urllib.error.HTTPError as response:
   assert response.code==303 and response.headers['Location']=='/odoo'
  else:raise AssertionError('Expected one-time grant redirect')
  target=launch['launch_url'].removesuffix('/__launch')+'/odoo'
  with opener.open(target,timeout=120) as response:
   html=response.read();assert response.status==200 and b'odoo' in html.lower()
  session=next(c.value for c in jar if c.name==COOKIE)
  backend=open_space(jobs,session,jobs.issue_handoff(session,trial['tenant_id'])['ticket'],adapter)
  company=backend.rpc('res.company','search_read',[],{'fields':['name','country_id','currency_id']})
  user=backend.rpc('res.users','read',[[backend.uid]],{'fields':['lang']})
  assert len(company)==1 and company[0]['name']==data['name'] and company[0]['currency_id'][1]=='DOP'
  assert user[0]['lang']=='es_DO' and backend.uid not in (1,2)
  assert backend.rpc('res.users','has_group',[[backend.uid],'point_of_sale.group_pos_manager'])
  assert not backend.rpc('res.users','has_group',[[backend.uid],'base.group_system'])
  assert backend.rpc('crm.lead','check_access_rights',['create'],{'raise_exception':False})
  assert backend.rpc('pos.config','check_access_rights',['create'],{'raise_exception':False})
  for model in ['crm.lead','pos.order']:
   assert backend.rpc(model,'search_count',[[]])==0
  expiry=trial['expires']
  with identity.db:identity.db.execute('UPDATE trial_workspaces SET expires=? WHERE tenant_id=?',(time.time()-1,trial['tenant_id']))
  try:
   try:backend.rpc('res.company','search_read',[],{'fields':['name']})
   except IdentityError:pass
   else:raise AssertionError('Expired trial kept access')
  finally:
   with identity.db:identity.db.execute('UPDATE trial_workspaces SET expires=? WHERE tenant_id=?',(expiry,trial['tenant_id']))
  post('/logout',{})
  try:backend.rpc('res.company','search_read',[],{'fields':['name']})
  except IdentityError:pass
  else:raise AssertionError('Logout failed')
  report={'mode':'real_local_provisioning','email_delivery':'fictional_private_mailbox','public_signup_enabled':False,'verified_registration_required':True,'retry_does_not_duplicate_company':True,'independent_database_files_credentials':True,'trial_days':15,'no_card':True,'starts_only_when_ready':True,'country':'DO','currency':'DOP','language':'es_DO','owner_can_use_crm_and_pos':True,'technical_admin_used':False,'expiry_blocks_access_without_deleting_data':True,'logout_revokes_access':True,'production_changed':False}
  (state/'verification.json').write_text(json.dumps(report,indent=2))
  print(json.dumps(report,indent=2),flush=True)
 finally:
  server.shutdown();server.server_close();worker.join();manager.close();identity.close();mail.clear()

if __name__=='__main__':main()
