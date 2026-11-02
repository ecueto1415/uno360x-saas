import http.client,json,tempfile,threading,unittest
from pathlib import Path
from deployment.https_pilot import HTTPSIdentityServer,checked_origin
from control.identity import IdentityService

class HTTPSPilotTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.mail=[]
  self.server=HTTPSIdentityServer(0,Path(self.tmp.name)/'control.sqlite3',self.mail.append,None,'https://cuenta.uno360x.com',['ecueto@outsolutech.com'],'https://piloto.uno360x.com')
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def request(self,path,data=None,host='cuenta.uno360x.com',origin='https://cuenta.uno360x.com'):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
  headers={'Host':host,'Origin':origin,'Content-Type':'application/json'}
  c.request('POST' if data is not None else 'GET',path,json.dumps(data).encode() if data is not None else None,headers)
  r=c.getresponse();body=r.read();headers=dict(r.getheaders());status=r.status;c.close()
  return status,headers,body
 def test_origin_and_host_are_exact(self):
  self.assertEqual(self.request('/session',host='uno360x.com')[0],403)
  self.assertEqual(self.request('/session',origin='https://evil.example')[0],403)
 def test_pilot_cannot_become_public_via_alternate_routes(self):
  self.assertEqual(self.request('/register',{'email':'outsider@example.com'})[0],404)
  self.assertEqual(self.request('/trial/register',{'email':'outsider@example.com','name':'test','modules':[],'consent':True})[0],403)
  self.assertFalse(self.mail)
 def test_real_mail_callback_and_secure_host_cookie(self):
  self.assertEqual(self.request('/trial/register',{'email':'ecueto@outsolutech.com','name':'Cueto','modules':[],'consent':True})[0],200)
  self.assertEqual(len(self.mail),1)
  import sqlite3
  with sqlite3.connect(Path(self.tmp.name)/'control.sqlite3') as db:
   self.assertEqual(db.execute('SELECT consent_version FROM trial_signup_drafts').fetchone()[0],'pilot-invitation-v1')
  db.close()
  self.assertEqual(self.request('/verify',{'token':self.mail[-1]['token'],'password':'Valid pilot password 2026!'})[0],200)
  status,headers,_=self.request('/login',{'email':'ecueto@outsolutech.com','password':'Valid pilot password 2026!'})
  self.assertEqual(status,200)
  cookie=headers['Set-Cookie'];self.assertTrue(cookie.startswith('__Host-uno360x_session='));self.assertIn('; Secure',cookie);self.assertIn('HttpOnly',cookie);self.assertNotIn('Domain=',cookie)
 def test_assets_pin_https_launch_target(self):
  status,headers,body=self.request('/assets/app.js')
  self.assertEqual(headers['Referrer-Policy'],'strict-origin-when-cross-origin')
  self.assertEqual(status,200);self.assertIn(b'target.origin!=="https://piloto.uno360x.com"',body)
  self.assertIn('https://piloto.uno360x.com',headers['Content-Security-Policy'])
  self.assertNotIn('En este laboratorio no enviamos correo real',body.decode())
  self.assertIn('Te enviaremos un correo real de UNO360X',body.decode())
 def test_reject_non_dedicated_origins(self):
  for origin in ['http://cuenta.uno360x.com','https://uno360x.com','https://cuenta.uno360x.com.evil.example','https://cuenta.uno360x.com/path']:
   with self.assertRaises(ValueError):checked_origin(origin)

 def test_step_one_is_a_real_entry_route(self):
  status,_,body=self.request('/prueba/inicio')
  self.assertEqual(status,200)
  self.assertIn(b'id="screen"',body)
  _,_,script=self.request('/assets/app.js')
  self.assertIn(b"case '/prueba/inicio':startTrial();",script)

 def test_public_signup_accepts_multiple_mail_domains_without_allowlist(self):
  self.server.public_signup=True;self.server.consent_version='public-trial-v1'
  for email in ['new.customer@gmail.com','new.customer@outlook.com','new.customer@company.example']:
   status,_,_=self.request('/trial/register',{'email':email,'name':'Public test','modules':[],'consent':True})
   self.assertEqual(status,200)
  self.assertEqual(len(self.mail),3)
  self.assertEqual(self.request('/verify',{'token':self.mail[-1]['token'],'password':'Public test password 2026!'})[0],200)
  self.assertEqual(self.request('/login',{'email':'new.customer@company.example','password':'Public test password 2026!'})[0],200)
 def test_public_copy_and_reserved_addresses_are_safe(self):
  self.server.public_signup=True
  _,_,html=self.request('/prueba/inicio');self.assertNotIn('Acceso por invitación',html.decode())
  self.assertEqual(self.request('/trial/register',{'email':'fake@example.test','name':'Fake','modules':[],'consent':True})[0],400)
  self.assertFalse(self.mail)

 def test_public_optional_selection_survives_signup_and_confirmation(self):
  self.server.public_signup=True
  modules=['payroll_hr','jenifer_ai','projects_services']
  status,_,script=self.request('/assets/app.js')
  self.assertEqual(status,200);self.assertNotIn(b'checkbox" disabled name="modules',script)
  self.assertNotIn(b'function plans(){draft.modules=[]',script)
  self.assertEqual(self.request('/trial/register',{'email':'plans@example.com','name':'Plans','modules':modules,'consent':True})[0],200)
  self.assertEqual(self.request('/verify',{'token':self.mail[-1]['token'],'password':'Plans fictional password 2026!'})[0],200)
  import sqlite3
  with sqlite3.connect(Path(self.tmp.name)/'control.sqlite3') as db:
   self.assertEqual(json.loads(db.execute('SELECT modules FROM trial_signup_drafts').fetchone()[0]),sorted(modules))

 def test_verification_can_be_recovered_without_registering_another_account(self):
  self.server.public_signup=True
  self.assertEqual(self.request('/verify/resend',{'email':'absent@example.com'})[0],200);self.assertFalse(self.mail)
  self.request('/trial/register',{'email':'recover@example.com','name':'Recovery','modules':[],'consent':True});old=self.mail[-1]['token']
  self.assertEqual(self.request('/verify/resend',{'email':'recover@example.com'})[0],200);new=self.mail[-1]['token'];self.assertNotEqual(old,new)
  status,_,body=self.request('/verify',{'token':old,'password':'Recovery fictional password 2026!'})
  self.assertEqual(status,400);self.assertIn('El enlace venció',body.decode())
  self.assertEqual(self.request('/verify',{'token':new,'password':'Recovery fictional password 2026!'})[0],200)
  self.assertEqual(self.request('/login',{'email':'recover@example.com','password':'Recovery fictional password 2026!'})[0],200)

 def test_reconciling_workspace_returns_retry_message_instead_of_bad_request(self):
  from control.identity_http import csrf_for
  from control.trials import Trials
  self.server.public_signup=True;self.server.launch=lambda session,ticket:{}
  identity=IdentityService(Path(self.tmp.name)/'control.sqlite3',self.mail.append)
  try:
   identity.register('waiting@example.com');identity.complete_registration(self.mail[-1]['token'],'Waiting fictional password 2026!')
   session=identity.login('waiting@example.com','Waiting fictional password 2026!')['session']
   company=Trials(identity).create(session,'Waiting company','DO','DOP',[])
   c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
   c.request('POST','/spaces/open',json.dumps({'tenant_id':company['tenant_id']}),{'Host':'cuenta.uno360x.com','Origin':'https://cuenta.uno360x.com','Content-Type':'application/json','Cookie':'__Host-uno360x_session='+session,'X-CSRF-Token':csrf_for(session)})
   response=c.getresponse();self.assertEqual(response.status,503);self.assertIn('verificando tu espacio',response.read().decode());c.close()
  finally:identity.close()

 def public_request(self,path,method='GET',data=None,session='',origin='https://uno360x.com',extra=None):
  headers={'Host':'cuenta.uno360x.com','Origin':origin,'Content-Type':'application/json'}
  if session:headers['Cookie']='__Host-uno360x_session='+session
  if extra:headers.update(extra)
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request(method,path,json.dumps(data).encode() if data is not None else None,headers)
  response=c.getresponse();result=(response.status,dict(response.getheaders()),response.read());c.close();return result
 def test_public_header_state_does_not_expose_account_data_or_private_csrf(self):
  self.server.public_signup=True
  self.request('/trial/register',{'email':'header@example.com','name':'Header','modules':[],'consent':True})
  self.request('/verify',{'token':self.mail[-1]['token'],'password':'Header fictional password 2026!'})
  identity=IdentityService(Path(self.tmp.name)/'control.sqlite3',self.mail.append)
  try:
   session=identity.login('header@example.com','Header fictional password 2026!')['session']
   status,headers,body=self.public_request('/public/session-status',session=session)
   self.assertEqual(status,200);value=json.loads(body);self.assertEqual(set(value),{'authenticated','logout_token'});self.assertTrue(value['authenticated'])
   self.assertEqual(headers['Access-Control-Allow-Origin'],'https://uno360x.com');self.assertEqual(headers['Access-Control-Allow-Credentials'],'true')
   from control.identity_http import csrf_for
   self.assertNotEqual(value['logout_token'],csrf_for(session))
   self.assertEqual(self.public_request('/session',session=session)[0],403)
   self.assertEqual(self.public_request('/public/session-status',session=session,origin='https://evil.example')[0],403)
   bad=self.public_request('/public/logout','POST',{'token':csrf_for(session)},session);self.assertEqual(bad[0],403);identity._account(session)
   out=self.public_request('/public/logout','POST',{'token':value['logout_token']},session)
   self.assertEqual(out[0],200);self.assertTrue(json.loads(out[2])['logged_out']);self.assertIn('Secure',out[1]['Set-Cookie'])
   from control.identity import IdentityError
   with self.assertRaises(IdentityError):identity._account(session)
  finally:identity.close()
 def test_public_logout_preflight_and_anonymous_state_are_limited(self):
  status,headers,body=self.public_request('/public/session-status');self.assertEqual(status,200);self.assertEqual(json.loads(body),{'authenticated':False})
  self.assertEqual(self.public_request('/public/logout','OPTIONS',extra={'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})[0],204)
  self.assertEqual(self.public_request('/login','OPTIONS',extra={'Access-Control-Request-Method':'POST'})[0],403)
  self.assertEqual(self.public_request('/public/logout','OPTIONS',origin='https://erp.uno360x.com',extra={'Access-Control-Request-Method':'POST'})[0],403)
  self.assertEqual(self.public_request('/public/logout','POST',[])[0],403)

 def test_plan_query_and_login_tracking_do_not_break_entry(self):
  self.server.public_signup=True
  self.assertEqual(self.request('/prueba/inicio?modules=projects_services')[0],200)
  self.assertEqual(self.request('/web/login?db=ignored')[0],200)
  status,_,body=self.request('/condiciones');self.assertEqual(status,200);self.assertIn('/assets/app.css',body.decode());self.assertIn('UNO',body.decode())
