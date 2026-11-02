import http.client,json,tempfile,threading,unittest
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from control.unified_access import NativeAccess,OP_COOKIE,OP_ID,ERP_ORIGIN,ENTRY,DATABASE
from control.identity import IdentityError,IdentityService
from deployment.https_pilot import HTTPSIdentityServer

PASSWORD='Fictional unified password 2026!'

class UnifiedAccessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.mail=[];self.cookies={};self.csrf='';self.native_ok=True;self.revoked=False;self.now=2000000000
  self.server=HTTPSIdentityServer(0,Path(self.tmp.name)/'identity.sqlite3',self.mail.append,None,'https://cuenta.uno360x.com',[],'https://piloto.uno360x.com',public_signup=True,operational_login=True)
  self.server.operational.clock=lambda:self.now
  self.server.operational.rpc=self.rpc
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def rpc(self,path,params,sid='',client_ip=''):
  if path=='/web/session/authenticate':
   self.assertEqual(params['db'],DATABASE)
   if self.native_ok and params['password']==PASSWORD:
    return {'uid':42,'db':DATABASE,'username':params['login']},'fictional-native-cookie'
   return {},''
  if path=='/web/session/destroy':self.revoked=True;return {},sid
  return ({'uid':42,'db':DATABASE} if not self.revoked else {}),sid
 def request(self,path,data=None,host='cuenta.uno360x.com',origin='https://cuenta.uno360x.com',form=False):
  headers={'Host':host,'Origin':origin,'Cookie':'; '.join(k+'='+v for k,v in self.cookies.items()),'X-CSRF-Token':self.csrf,'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'}
  body=(urlencode(data) if form else json.dumps(data)) if data is not None else None
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request('POST' if data is not None else 'GET',path,body,headers)
  r=c.getresponse();raw=r.read();hs=r.getheaders();status=r.status;c.close()
  for k,v in hs:
   if k.lower()=='set-cookie' and host=='cuenta.uno360x.com':
    jar=SimpleCookie();jar.load(v)
    for n,item in jar.items():self.cookies[n]=item.value
  try:value=json.loads(raw)
  except ValueError:value={}
  if 'csrf_token' in value:self.csrf=value['csrf_token']
  return status,dict(hs),value
 def login(self,email='native@example.test'):
  return self.request('/login',{'email':email,'password':PASSWORD})
 def saas(self,email):
  s=IdentityService(self.server.database,self.mail.append);s.register(email);s.complete_registration(self.mail[-1]['token'],PASSWORD);s.close()
 def test_native_login_companies_one_use_cookie_handoff(self):
  status,_,value=self.login();self.assertEqual(status,200);self.assertNotIn('sid',str(value));self.assertIn(OP_COOKIE,self.cookies)
  status,_,value=self.request('/companies',{});self.assertEqual(status,200);self.assertEqual([c['id'] for c in value['companies']],[OP_ID])
  status,_,value=self.request('/spaces/open',{'tenant_id':OP_ID});self.assertEqual(status,200);self.assertEqual(value['launch_url'],ERP_ORIGIN+ENTRY)
  grant=value['grant'];status,headers,_=self.request(ENTRY,{'grant':grant},host='erp.uno360x.com',form=True)
  self.assertEqual(status,303);self.assertEqual(headers['Location'],'/odoo');self.assertIn('HttpOnly; Secure; SameSite=Lax',headers['Set-Cookie']);self.assertNotIn('Domain=',headers['Set-Cookie'])
  self.assertEqual(self.request(ENTRY,{'grant':grant},host='erp.uno360x.com',form=True)[0],400)
 def test_reentry_needs_no_password_and_logout_revokes(self):
  self.login();self.assertEqual(self.request('/session')[0],200)
  self.assertEqual(self.request('/logout',{})[0],200);self.assertTrue(self.revoked);self.assertEqual(self.request('/session')[0],401)
 def test_invalid_credentials_never_register_or_send_email(self):
  self.assertEqual(self.request('/login',{'email':'native@example.test','password':'incorrect'})[0],400);self.assertFalse(self.mail)
  s=IdentityService(self.server.database,self.mail.append);self.assertEqual(s.db.execute('SELECT count(*) FROM accounts').fetchone()[0],0);s.close()
 def test_origins_csrf_and_cross_company_are_rejected(self):
  self.assertEqual(self.request('/login',{'email':'native@example.test','password':PASSWORD},origin='https://evil.example')[0],403)
  self.login();self.csrf='bad';self.assertEqual(self.request('/spaces/open',{'tenant_id':OP_ID})[0],403)
  self.request('/session');self.assertEqual(self.request('/spaces/open',{'tenant_id':'other-company'})[0],401)
  _,_,value=self.request('/spaces/open',{'tenant_id':OP_ID})
  self.assertEqual(self.request(ENTRY,{'grant':value['grant']},host='erp.uno360x.com',origin='https://evil.example',form=True)[0],403)
  self.assertEqual(self.request(ENTRY,{'grant':value['grant']},form=True)[0],403)
 def test_expired_grant_and_revoked_native_session_are_rejected(self):
  self.login();_,_,value=self.request('/spaces/open',{'tenant_id':OP_ID});self.now+=31
  self.assertEqual(self.request(ENTRY,{'grant':value['grant']},host='erp.uno360x.com',form=True)[0],400)
  self.revoked=True;self.assertEqual(self.request('/session')[0],401)
 def test_saas_only_native_outage_still_allows_login(self):
  self.saas('saas@example.test')
  def down(*args):raise TimeoutError()
  self.server.operational.rpc=down
  self.assertEqual(self.login('saas@example.test')[0],200)
  self.assertEqual(self.request('/companies',{})[2]['companies'],[])
 def test_same_verified_identity_can_choose_both_and_different_identity_clears_native(self):
  self.saas('both@example.test');self.assertEqual(self.login('both@example.test')[0],200)
  s=IdentityService(self.server.database,self.mail.append);token=self.cookies['__Host-uno360x_session'];s.create_company(token,'both-company',[],'create-both');s.close()
  self.assertEqual(len(self.request('/companies',{})[2]['companies']),2)
  self.native_ok=False;self.saas('other@example.test');self.assertEqual(self.login('other@example.test')[0],200)
  self.assertEqual(self.cookies[OP_COOKIE],'');self.assertEqual(self.request('/companies',{})[2]['companies'],[])
 def test_rate_limit_covers_native_fallback(self):
  for _ in range(8):self.assertEqual(self.request('/login',{'email':'limit@example.test','password':'bad'})[0],400)
  self.assertEqual(self.request('/login',{'email':'limit@example.test','password':PASSWORD})[0],429)
 def test_native_mfa_and_wrong_database_cannot_issue_session(self):
  for info in [{'uid':False,'db':DATABASE,'username':'a@example.test'},{'uid':42,'db':'other','username':'a@example.test'}]:
   self.server.operational.rpc=lambda *args,**kwargs:(info,'cookie')
   self.assertIsNone(self.server.operational.authenticate('a@example.test',PASSWORD))
 def test_concurrent_grant_consumption_has_one_winner(self):
  token=self.server.operational.authenticate('a@example.test',PASSWORD);grant=self.server.operational.issue(token)
  def consume(_):
   try:return self.server.operational.consume(grant)
   except IdentityError:return None
  with ThreadPoolExecutor(max_workers=4) as ex:results=list(ex.map(consume,range(4)))
  self.assertEqual(sum(bool(r) for r in results),1)
 def test_directory_skips_saas_emails_and_fails_closed_when_stale(self):
  from control.identity import digest
  directory=Path(self.tmp.name)/'directory.json';directory.write_text(json.dumps({'updated':self.now,'logins':[digest('native@example.test')]}))
  self.server.operational.directory=directory
  self.assertIsNone(self.server.operational.authenticate('saas@example.test',PASSWORD))
  self.assertIsNotNone(self.server.operational.authenticate('native@example.test',PASSWORD))
  self.now+=301
  with self.assertRaises(IdentityError):self.server.operational.authenticate('native@example.test',PASSWORD)
 def test_native_rpc_keeps_client_address_and_fixed_backend(self):
  from unittest.mock import patch,MagicMock
  response=MagicMock();response.__enter__.return_value=response;response.read.return_value=b'{"result":{}}';response.headers.get_all.return_value=[]
  opener=MagicMock();opener.open.return_value=response
  with patch('urllib.request.build_opener',return_value=opener):
   NativeAccess().rpc('/web/session/authenticate',{'db':DATABASE},client_ip='203.0.113.9')
   request=opener.open.call_args.args[0]
   self.assertEqual(request.full_url,'http://127.0.0.1:8069/web/session/authenticate')
   self.assertEqual(request.get_header('X-forwarded-for'),'203.0.113.9')
  with self.assertRaises(ValueError):NativeAccess().rpc('/web/session/authenticate',{},client_ip='invalid, injected')
  with self.assertRaises(ValueError):NativeAccess().rpc('//untrusted.example',{})

if __name__=='__main__':unittest.main()
