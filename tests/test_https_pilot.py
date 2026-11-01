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
