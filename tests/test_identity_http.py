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
        self.assertEqual(status,200);self.assertEqual(body['email'],email.strip().casefold());self.csrf=body['csrf_token']
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

    def test_preparation_request_queues_without_privileged_work(self):
        self.login()
        _,company,_=self.post('/companies/create',{'slug':'empresa-queue','modules':[],'request_id':'queue'})
        status,job,_=self.post('/preparation/request',{'tenant_id':company['id']})
        self.assertEqual(status,200);self.assertEqual(job['status'],'queued')
        self.assertFalse(job['completed_steps']);self.assertFalse(job['local_ready'])
        self.assertEqual(job,self.post('/preparation/status',{'tenant_id':company['id']})[1])
        self.assertNotEqual(self.post('/handoff/request',{'tenant_id':company['id']})[0],200)

    def test_approved_ui_and_home_preserve_navigation_without_remote_assets(self):
        for path in ('/','/prueba','/prueba/empresa','/web/login','/planes-y-precios','/condiciones','/privacidad'):
            with self.opener.open(self.base+path,timeout=20) as response:
                html=response.read().decode()
                self.assertEqual(response.status,200)
                for label in ('Soluciones','Planes y precios','Cómo funciona','Contacto','Iniciar sesión','Solicitar demo'):
                    self.assertIn(label,html)
                self.assertNotIn('https://cdn.',html)
                self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        for path in ('/assets/app.js','/assets/app.css','/assets/plans.js'):
            with self.opener.open(self.base+path,timeout=20) as response:self.assertEqual(response.status,200)
        for path in ('/assets/../identity.py','/assets/no-such-file','/mailbox'):
            with self.assertRaises(urllib.error.HTTPError):self.opener.open(self.base+path,timeout=20)

    def test_trial_flow_preserves_selection_and_does_not_start_while_queued(self):
        self.assertEqual(self.post('/trial/register',{'name':'Prueba HTTP','email':'trial-http@example.test','modules':['projects_services'],'consent':True})[0],200)
        token=self.messages[-1]['token']
        self.assertEqual(self.post('/verify',{'token':token,'password':PASSWORD})[0],200)
        _,body,_=self.post('/login',{'email':'trial-http@example.test','password':PASSWORD});self.csrf=body['csrf_token']
        self.assertEqual(self.post('/trial/draft',{})[1]['modules'],['projects_services'])
        data={'name':'Empresa de prueba','country':'DO','currency':'DOP','modules':['projects_services']}
        status,trial,_=self.post('/trial/create',data)
        self.assertEqual(status,200);self.assertEqual(trial['status'],'queued')
        self.assertIsNone(trial['started']);self.assertFalse(trial['card_required']);self.assertFalse(trial['automatic_charge'])
        self.assertEqual(self.post('/trial/create',data)[1]['tenant_id'],trial['tenant_id'])
        self.assertEqual(self.post('/trial/status',{'tenant_id':trial['tenant_id']})[0],200)
        self.assertEqual(self.post('/trial/create',data,headers={'X-CSRF-Token':'wrong'})[0],403)

    def test_capacity_queue_is_not_reported_as_verification_and_never_launches(self):
        import sqlite3
        self.login()
        _,co,_=self.post('/companies/create',{'slug':'capacity-example','modules':[],'request_id':'capacity-1'})
        self.post('/preparation/request',{'tenant_id':co['id']})
        with sqlite3.connect(self.server.database) as db:
            db.execute("UPDATE preparation_jobs SET current_step='capacity' WHERE tenant_id=?",(co['id'],))
        def launch(*args):raise AssertionError('Queued company must not open a backend')
        self.server.launch=launch
        status,body,_=self.post('/spaces/open',{'tenant_id':co['id']})
        self.assertEqual(status,409)
        self.assertEqual(body['code'],'workspace_capacity')
        self.assertIn('capacidad',body['error'])
        self.assertNotIn('verificando',body['error'])
        self.assertEqual(self.post('/preparation/status',{'tenant_id':co['id']})[1]['current_step'],'capacity')

    def test_capacity_is_checked_before_allocating_a_new_company(self):
        import time,sqlite3
        self.login('capacity-gate@example.test')
        gate=Path(self.tmp.name)/'admission.json';gate.write_text(json.dumps({'checked':time.time(),'can_prepare':False}))
        self.server.admission_status_path=gate
        status,body,_=self.post('/trial/create',{'name':'Should not be allocated','country':'DO','currency':'DOP','modules':[]})
        self.assertEqual(status,503)
        self.assertEqual(body['code'],'activation_capacity_unavailable')
        self.assertEqual(self.post('/companies',{})[1]['companies'],[])
        gate.write_text(json.dumps({'checked':time.time()-30,'can_prepare':True}))
        self.assertEqual(self.post('/trial/create',{'name':'Stale capacity','country':'DO','currency':'DOP','modules':[]})[0],503)
        gate.write_text(json.dumps({'checked':time.time(),'can_prepare':True}))
        status,trial,_=self.post('/trial/create',{'name':'Capacity available','country':'DO','currency':'DOP','modules':[]})
        self.assertEqual(status,200)
        gate.write_text(json.dumps({'checked':time.time(),'can_prepare':False}))
        self.assertEqual(self.post('/trial/create',{'name':'Capacity available','country':'DO','currency':'DOP','modules':[]})[1]['tenant_id'],trial['tenant_id'])
