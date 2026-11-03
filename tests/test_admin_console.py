import unittest,tempfile,pathlib,time,json,threading,http.client
from admin_console.auth import Auth,Denied,Limited,otp,digest,csrf
from admin_console.server import Server,COOKIE,CHALLENGE

PASS='Fictional owner admin password 2026!'
OWNER='owner@example.test'

class OwnerAuthTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.now=2000000000;self.auth=Auth(self.tmp.name,OWNER,clock=lambda:self.now)
 def tearDown(self):self.auth.close();self.tmp.cleanup()
 def enroll(self):
  token=self.auth.new_enrollment();setup=self.auth.start_enrollment(token,'test-ip');session,codes=self.auth.finish_enrollment(token,PASS,otp(setup['secret'],int(self.now//30)),'agent','test-ip');return token,setup,session,codes
 def test_rfc6238_counter(self):self.assertEqual(otp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',1),'287082')
 def test_enrollment_single_use_no_secrets_in_database(self):
  token,setup,session,codes=self.enroll();self.assertEqual(self.auth.account(session,'agent')['email'],OWNER)
  dump='\n'.join(self.auth.db.iterdump())
  for secret in (PASS,setup['secret'],token,session,*codes):self.assertNotIn(secret,dump)
  with self.assertRaises(Denied):self.auth.start_enrollment(token,'test-ip')
  with self.assertRaises(Denied):self.auth.new_enrollment()
 def test_new_enrollment_invalidates_previous_and_expiration_is_enforced(self):
  first=self.auth.new_enrollment();second=self.auth.new_enrollment()
  with self.assertRaises(Denied):self.auth.start_enrollment(first,'ip')
  self.now+=86401
  with self.assertRaises(Denied):self.auth.start_enrollment(second,'ip')
 def test_password_alone_has_no_session_and_wrong_owner_rejected(self):
  self.enroll();challenge=self.auth.login(OWNER,PASS,'agent','ip')
  with self.assertRaises(Denied):self.auth.account(challenge,'agent')
  with self.assertRaises(Denied):self.auth.login('other@example.test',PASS,'agent','ip')
 def test_mfa_replay_and_agent_change_rejected(self):
  _,setup,_,_=self.enroll();self.now+=30
  challenge=self.auth.login(OWNER,PASS,'agent','ip');code=otp(setup['secret'],int(self.now//30))
  with self.assertRaises(Denied):self.auth.mfa(challenge,code,'other-agent','ip')
  session=self.auth.mfa(challenge,code,'agent','ip');self.auth.account(session,'agent')
  challenge=self.auth.login(OWNER,PASS,'agent','ip')
  with self.assertRaises(Denied):self.auth.mfa(challenge,code,'agent','ip')
 def test_session_idle_and_logout_and_agent_binding(self):
  _,_,session,_=self.enroll()
  with self.assertRaises(Denied):self.auth.account(session,'other-agent')
  self.now+=1700;self.auth.account(session,'agent',touch=False);self.now+=101
  with self.assertRaises(Denied):self.auth.account(session,'agent')
 def test_recovery_requires_password_challenge_and_cannot_be_reused(self):
  _,_,_,codes=self.enroll();challenge=self.auth.login(OWNER,PASS,'agent','ip');self.auth.mfa(challenge,codes[0],'agent','ip')
  challenge=self.auth.login(OWNER,PASS,'agent','ip')
  with self.assertRaises(Denied):self.auth.mfa(challenge,codes[0],'agent','ip')
 def test_rate_limit(self):
  self.enroll()
  for _ in range(8):
   with self.assertRaises(Denied):self.auth.login(OWNER,'incorrect','agent','ip')
  with self.assertRaises(Limited):self.auth.login(OWNER,PASS,'agent','ip')

class OwnerHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.state=pathlib.Path(self.tmp.name)/'auth';self.snapshot=pathlib.Path(self.tmp.name)/'snapshot.json';self.snapshot.write_text(json.dumps({'generated':time.time(),'clients':[{'name':'private-company'}]}));self.now=2000000000
  self.server=Server(0,self.state,self.snapshot,OWNER);self.server.clock=lambda:self.now
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.cookies={};self.csrf=''
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def request(self,path,data=None,host='admin.uno360x.com',origin='https://admin.uno360x.com'):
  headers={'Host':host,'Origin':origin,'User-Agent':'test-agent','Cookie':'; '.join(k+'='+v for k,v in self.cookies.items()),'Content-Type':'application/json','X-CSRF-Token':self.csrf}
  connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port);connection.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),headers)
  response=connection.getresponse();body=response.read();hs=response.getheaders();status=response.status;connection.close()
  from http.cookies import SimpleCookie
  for key,value in hs:
   if key.lower()=='set-cookie':
    self.assertIn('HttpOnly; Secure; SameSite=Strict',value);self.assertNotIn('Domain=',value)
    jar=SimpleCookie();jar.load(value)
    for n,item in jar.items():self.cookies[n]=item.value
  try:value=json.loads(body)
  except ValueError:value={}
  return status,dict(hs),value,body
 def activate(self):
  auth=Auth(self.state,OWNER,clock=lambda:self.now);token=auth.new_enrollment();auth.close()
  status,_,setup,_=self.request('/api/enroll/start',{'token':token});self.assertEqual(status,200)
  status,_,result,_=self.request('/api/enroll/finish',{'token':token,'password':PASS,'code':otp(setup['secret'],int(self.now//30))});self.assertEqual(status,200)
  return setup,result
 def test_no_anonymous_data_or_path_traversal(self):
  for path in ['/api/overview','/api/activity','/api/session']:
   status,_,_,body=self.request(path);self.assertEqual(status,401);self.assertNotIn(b'private-company',body)
  self.assertEqual(self.request('/../../etc/shadow')[0],404)
  self.assertEqual(self.request('/api/login',{'email':OWNER,'password':PASS},origin='https://evil.example')[0],403)
  self.assertEqual(self.request('/api/session',host='cuenta.uno360x.com')[0],403)
 def test_real_http_enrollment_mfa_readonly_dashboard_and_csrf_logout(self):
  setup,result=self.activate();self.assertEqual(len(result['recovery_codes']),8)
  status,_,account,_=self.request('/api/session');self.assertEqual(status,200);self.csrf=account['csrf_token']
  status,_,overview,_=self.request('/api/overview');self.assertEqual(status,200);self.assertFalse(overview['storage_quota_enforced'])
  self.assertEqual(self.request('/api/logout',{})[0],200);self.assertEqual(self.request('/api/overview')[0],401)
  self.assertEqual(self.request('/api/login',{'email':OWNER,'password':PASS})[0],200);self.assertEqual(self.request('/api/overview')[0],401)
  self.now+=30;self.assertEqual(self.request('/api/mfa',{'code':otp(setup['secret'],int(self.now//30))})[0],200)
  self.csrf='invalid';self.assertEqual(self.request('/api/logout',{})[0],403)
  self.assertEqual(self.request('/api/clients/change-plan',{'id':'x'})[0],404)
 def test_assets_have_no_external_scripts_and_strict_csp(self):
  status,headers,_,body=self.request('/');self.assertEqual(status,200);self.assertNotIn('unsafe-inline',headers['Content-Security-Policy']);self.assertEqual(headers['X-Frame-Options'],'DENY')
  self.assertNotIn(b'https://cdn',body)

class OwnerEmailTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.now=2000000000;self.codes=[]
  self.auth=Auth(self.tmp.name,OWNER,clock=lambda:self.now,factor='email',delivery=self.codes.append)
 def tearDown(self):self.auth.close();self.tmp.cleanup()
 def enroll(self):
  token=self.auth.new_enrollment();setup=self.auth.start_enrollment(token,'ip');self.assertNotIn('secret',setup)
  code=self.codes[-1];session,codes=self.auth.finish_enrollment(token,PASS,code,'agent','ip');self.assertEqual(codes,[])
  return token,code,session
 def test_email_enrollment_login_password_first_and_single_use(self):
  token,code,session=self.enroll();self.auth.account(session,'agent')
  with self.assertRaises(Denied):self.auth.finish_enrollment(token,PASS,code,'agent','ip')
  n=len(self.codes)
  with self.assertRaises(Denied):self.auth.login(OWNER,'wrong','agent','ip')
  self.assertEqual(len(self.codes),n)
  challenge=self.auth.login(OWNER,PASS,'agent','ip');code=self.codes[-1]
  with self.assertRaises(Denied):self.auth.account(challenge,'agent')
  result=self.auth.mfa(challenge,code,'agent','ip');self.auth.account(result,'agent')
  with self.assertRaises(Denied):self.auth.mfa(challenge,code,'agent','ip')
  dump='\n'.join(self.auth.db.iterdump())
  for value in (PASS,token,challenge,session):self.assertNotIn(value,dump)
  self.assertNotEqual(self.auth.db.execute('SELECT code FROM email_codes ORDER BY created DESC LIMIT 1').fetchone()[0],digest(code))
 def test_five_attempt_limit_and_expiration(self):
  token=self.auth.new_enrollment();self.auth.start_enrollment(token,'ip');code=self.codes[-1]
  for _ in range(5):
   with self.assertRaises(Denied):self.auth.check_email(token,'activation','not-a-code')
  with self.assertRaises(Denied):self.auth.check_email(token,'activation',code)
  self.now+=61;self.auth.start_enrollment(token,'ip');code=self.codes[-1];self.now+=601
  with self.assertRaises(Denied):self.auth.check_email(token,'activation',code)
 def test_resend_throttles_and_invalidates_old_code(self):
  token=self.auth.new_enrollment();self.auth.start_enrollment(token,'ip');old=self.codes[-1]
  self.auth.start_enrollment(token,'ip');self.assertEqual(len(self.codes),1)
  self.now+=61;self.auth.start_enrollment(token,'ip');self.assertEqual(len(self.codes),2)
  row=self.auth.db.execute('SELECT * FROM email_codes').fetchone();self.assertEqual(row['code'],self.auth.mail_digest(digest('activation:'+token),self.codes[-1]))
  self.assertEqual(row['attempts'],0)
 def test_delivery_failure_never_authenticates(self):
  token=self.auth.new_enrollment()
  def fail(code):raise RuntimeError('provider details')
  self.auth.delivery=fail
  with self.assertRaises(RuntimeError):self.auth.start_enrollment(token,'ip')
  self.assertEqual(self.auth.db.execute('SELECT count(*) FROM email_codes').fetchone()[0],0)
  self.assertEqual(self.auth.db.execute('SELECT count(*) FROM owner').fetchone()[0],0)

class OwnerEmailHTTPTests(OwnerHTTPTests):
 def test_email_http_enrollment_and_login(self):
  codes=[];self.server.factor='email';self.server.delivery=codes.append
  a=Auth(self.state,OWNER,clock=lambda:self.now,factor='email',delivery=codes.append);token=a.new_enrollment();a.close()
  self.assertEqual(self.request('/api/auth-config')[2]['factor'],'email')
  status,_,setup,_=self.request('/api/enroll/start',{'token':token});self.assertEqual(status,200);self.assertNotIn('secret',setup)
  self.assertEqual(self.request('/api/enroll/finish',{'token':token,'password':PASS,'code':codes[-1]})[0],200)
  account=self.request('/api/session')[2];self.csrf=account['csrf_token'];self.assertEqual(account['factor'],'email')
  self.assertEqual(self.request('/api/logout',{})[0],200)
  self.assertEqual(self.request('/api/login',{'email':OWNER,'password':PASS})[2]['factor'],'email')
  self.assertEqual(self.request('/api/overview')[0],401)
  self.assertEqual(self.request('/api/mfa/resend',{})[0],200)
  self.assertEqual(self.request('/api/mfa',{'code':codes[-1]})[0],200)
  self.assertEqual(self.request('/api/overview')[0],200)

if __name__=='__main__':unittest.main()
