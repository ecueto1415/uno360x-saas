import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from control.identity_http import IdentityHTTPServer

PASSWORD='Clave ficticia HTTP de prueba'


class IdentityHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.messages=[]
        self.server=IdentityHTTPServer(0,Path(self.tmp.name)/'identity.sqlite3',self.messages.append)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}))
        self.csrf=''

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def post(self,path,data,headers=None):
        h={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        h.update(headers or {})
        request=urllib.request.Request(self.base+path,data=json.dumps(data).encode(),headers=h)
        try:response=self.opener.open(request,timeout=20)
        except urllib.error.HTTPError as error:response=error
        with response:return response.status,json.load(response),response.headers

    def login(self,email='owner@example.test'):
        self.assertEqual(self.post('/register',{'email':email})[0],200)
        self.assertEqual(self.post('/verify',{'token':self.messages[-1]['token'],'password':PASSWORD})[0],200)
        status,body,headers=self.post('/login',{'email':email,'password':PASSWORD})
        self.assertEqual(status,200);self.csrf=body['csrf_token']
        self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertNotIn('session',body)

    def test_http_registration_company_invitation_and_recovery(self):
        self.login()
        status,company,_=self.post('/companies/create',{'slug':'empresa-http','modules':['jenifer_ai'],'request_id':'http-1'})
        self.assertEqual(status,200);self.assertFalse(company['access_enabled'])
        self.assertEqual(self.post('/companies',{})[1]['companies'][0]['id'],company['id'])
        self.assertEqual(self.post('/invitations/create',{'tenant_id':company['id'],'email':'worker@example.test'})[0],200)
        invite=self.messages[-1]['token']
        self.post('/logout',{});self.login('worker@example.test')
        self.assertEqual(self.post('/companies',{})[1]['companies'],[])
        self.assertEqual(self.post('/invitations/accept',{'token':invite})[0],200)
        self.assertEqual(self.post('/companies/select',{'tenant_id':company['id']})[1]['role'],'member')
        self.post('/reset/request',{'email':'worker@example.test'});reset=self.messages[-1]['token']
        self.assertEqual(self.post('/reset/complete',{'token':reset,'password':PASSWORD+' nueva'})[0],200)
        self.assertNotEqual(self.post('/companies',{})[0],200)

    def test_csrf_wrong_origin_and_host_are_rejected(self):
        self.login()
        self.assertEqual(self.post('/companies',{},headers={'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.post('/companies',{},headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.post('/companies',{},headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.post('/register',{'email':'x@example.test'},headers={'Content-Type':'text/plain'})[0],415)

    def test_session_refresh_no_cors_no_cache_and_logout(self):
        self.login()
        with self.opener.open(self.base+'/session',timeout=20) as response:
            body=json.load(response)
            self.assertEqual(body['csrf_token'],self.csrf)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
        self.assertEqual(self.post('/logout',{})[0],200)
        with self.assertRaises(urllib.error.HTTPError):self.opener.open(self.base+'/session',timeout=20)

    def test_anonymous_requests_never_return_companies(self):
        self.assertNotEqual(self.post('/companies',{})[0],200)
        status,body,_=self.post('/register',{'email':'absent@example.test'})
        self.assertEqual(status,200)
        self.assertNotIn('token',body);self.assertNotIn('companies',body)
        status,body,_=self.post('/reset/request',{'email':'absent@example.test'})
        self.assertEqual(status,200);self.assertNotIn('token',body)
