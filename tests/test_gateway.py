import http.cookiejar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

from control.access_broker import BackendSession, NoRedirect
from control.gateway import GatewayManager, CENTRAL_ORIGIN, checked_path
from control.identity import IdentityService, IdentityError
from control.onboarding import Onboarding
from tests.test_onboarding import FakeAdapter


class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/bootstrap':
            self.send_response(200);self.send_header('Set-Cookie','session_id=fake-native-cookie; Path=/');self.end_headers();return
        if self.path=='/external':
            self.send_response(302);self.send_header('Location','https://external.example/');self.end_headers();return
        if self.path=='/relative':
            self.send_response(302);self.send_header('Location','/odoo');self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Set-Cookie','another_native_cookie=private; Path=/');self.end_headers()
        self.wfile.write(json.dumps({'native_cookie':self.headers.get('Cookie')=='session_id=fake-native-cookie',
                                    'untrusted_header_forwarded':bool(self.headers.get('X-Forwarded-Host'))}).encode())
    def do_POST(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.end_headers();self.wfile.write(body)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.mail=[];self.now=2000000000
        self.database=Path(self.tmp.name)/'control.sqlite3'
        self.identity=IdentityService(self.database,self.mail.append,clock=lambda:self.now)
        self.identity.register('gateway@example.test');self.identity.complete_registration(self.mail[-1]['token'],'Gateway ficticio password 2026')
        self.session=self.identity.login('gateway@example.test','Gateway ficticio password 2026')['session']
        self.tid=self.identity.create_company(self.session,'gateway-ficticio',[],'first')['id']
        jobs=Onboarding(self.identity);job=jobs.request(self.session,self.tid);jobs.run(job['job_id'],FakeAdapter())
        claims=jobs.consume_handoff(self.session,jobs.issue_handoff(self.session,self.tid)['ticket'])
        self.upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        self.thread=threading.Thread(target=self.upstream.serve_forever,daemon=True);self.thread.start()
        base='http://127.0.0.1:'+str(self.upstream.server_port)
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}),NoRedirect())
        opener.open(base+'/bootstrap').close()
        self.backend=BackendSession(jobs,self.session,claims,{},opener,base,9)
        self.manager=GatewayManager(self.database,FakeAdapter(),clock=lambda:self.now)
        with patch('control.gateway.open_space',return_value=self.backend):self.launch=self.manager.launch(self.session,'mock-ticket')
        self.server=self.manager.server(self.tid)
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}),NoRedirect())
    def tearDown(self):
        self.manager.close();self.upstream.shutdown();self.upstream.server_close();self.thread.join();self.identity.close();self.tmp.cleanup()
    def request(self,path='/',method='GET',data=None,headers=None):
        req=urllib.request.Request(self.server.origin+path,data=data,method=method,headers=headers or {})
        try:r=self.client.open(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        with r:return r.status,r.headers,r.read()
    def enter(self):
        return self.request('/__launch','POST',urllib.parse.urlencode({'grant':self.launch['grant']}).encode(),{'Origin':CENTRAL_ORIGIN,'Content-Type':'application/x-www-form-urlencoded'})
    def test_launch_is_single_use_origin_checked_and_cookie_is_opaque(self):
        data=urllib.parse.urlencode({'grant':self.launch['grant']}).encode()
        self.assertEqual(self.request('/__launch','POST',data,{'Origin':'https://evil.example','Content-Type':'application/x-www-form-urlencoded'})[0],403)
        status,headers,_=self.enter();self.assertEqual(status,303);self.assertEqual(headers['Location'],'/odoo')
        cookie=headers['Set-Cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        self.assertNotIn('session_id',cookie);self.assertNotIn(self.session,cookie)
        self.assertEqual(self.enter()[0],403)
    def test_assets_rpc_and_upload_keep_backend_cookies_private(self):
        self.enter()
        status,headers,body=self.request('/web/assets/test.js',headers={'Cookie':self.enter_cookie(),'X-Forwarded-Host':'evil.example'})
        self.assertEqual(status,200);self.assertIsNone(headers.get('Set-Cookie'))
        result=json.loads(body);self.assertTrue(result['native_cookie']);self.assertFalse(result['untrusted_header_forwarded'])
        status,_,body=self.request('/web/dataset/call_kw','POST',b'{"fictional":"payload"}',{'Origin':self.server.origin,'Content-Type':'application/json'})
        self.assertEqual(status,200);self.assertEqual(body,b'{"fictional":"payload"}')
        self.assertEqual(self.request('/web/upload','POST',b'data',{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/web/upload','POST',b'data')[0],403)
    def enter_cookie(self):
        handle=next(iter(self.manager.handles.values()))
        return self.server.cookie+'='+handle.token+'; uno360x_lab_session=must-not-forward'
    def test_native_admin_routes_external_redirect_and_offline_worker_blocked(self):
        self.enter()
        for path in ['/web/database/manager','/web/session/authenticate','/uno360x/bridge/login']:
            self.assertEqual(self.request(path)[0],401)
        status,_,script=self.request('/web/service-worker.js');self.assertEqual(status,200)
        self.assertNotIn(b'caches',script);self.assertNotIn(b'respondWith',script)
        self.assertEqual(self.request('/external')[0],401)
        status,headers,_=self.request('/relative');self.assertEqual(status,302);self.assertEqual(headers['Location'],'/odoo')
        for path in ['https://evil.example/','//evil.example/','/web/../database','/%2f%2fevil.example','/web\\database']:
            with self.assertRaises(IdentityError):checked_path(path)
    def test_cross_tenant_handle_logout_and_replay_are_rejected(self):
        self.enter();handle=next(iter(self.manager.handles.values()))
        with self.assertRaises(IdentityError):self.manager.lookup(handle.token,'another-tenant')
        self.identity.logout(self.session)
        self.assertEqual(self.request('/odoo')[0],401)
        self.assertEqual(self.request('/web/assets/test.js')[0],401)
    def test_expired_trial_blocks_existing_cookie_without_deleting_company(self):
        from control.trials import Trials
        Trials(self.identity)
        account=self.identity._account(self.session)
        with self.identity.db:self.identity.db.execute('INSERT INTO trial_workspaces VALUES (?,?,?,?,?,?,?,?)',
            (account['id'],self.tid,'Fixture','DO','DOP',self.now,self.now,self.now+1))
        self.enter();self.now+=1
        self.assertEqual(self.request('/odoo')[0],401)
        self.assertEqual(self.identity.db.execute('SELECT count(*) FROM tenants').fetchone()[0],1)
    def test_host_and_websocket_origin_are_checked(self):
        self.enter()
        self.assertEqual(self.request('/odoo',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/websocket',headers={'Origin':'https://evil.example','Upgrade':'websocket'})[0],403)


if __name__=='__main__':unittest.main()
