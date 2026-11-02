import json,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from deployment.runtime_status import Handler
class RuntimeStatusTests(unittest.TestCase):
 def setUp(self):
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.base='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
 def test_health_reports_registration_disabled_when_configured_off(self):
  with patch('deployment.runtime_status.public_signup_enabled',return_value=False),urllib.request.urlopen(self.base+'/health') as r:
   self.assertEqual(json.load(r),{'status':'preparing','signup_enabled':False})
   self.assertIsNone(r.headers.get('Set-Cookie'));self.assertEqual(r.headers['Cache-Control'],'no-store')
 def test_registration_cannot_collect_credentials(self):
  request=urllib.request.Request(self.base+'/register',data=b'{"email":"fictional@example.test","password":"synthetic"}',headers={'Content-Type':'application/json'})
  with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
  self.assertEqual(caught.exception.code,503)
 def test_no_proxy_to_operational_login_or_private_files(self):
  for route in ['/web/login','/etc/odoo18.conf','/../health']:
   with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(self.base+route)
   self.assertEqual(caught.exception.code,404)

 def test_health_reports_public_registration_when_enabled(self):
  with patch('deployment.runtime_status.public_signup_enabled',return_value=True),urllib.request.urlopen(self.base+'/health') as response:
   self.assertEqual(json.load(response),{'status':'available','signup_enabled':True})
