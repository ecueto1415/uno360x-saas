import http.client,json,tempfile,threading,unittest,urllib.parse,urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from control.identity import IdentityService,IdentityError
from control.onboarding import Onboarding
from control.access_broker import BackendSession,NoRedirect
from deployment.https_pilot import HTTPSGatewayManager,BoundedHTTPServer
from tests.test_onboarding import FakeAdapter

class SharedGatewayTests(unittest.TestCase):
 def setUp(self):
  self.server_patch=patch('deployment.https_pilot.BoundedHTTPServer',side_effect=lambda address,handler:BoundedHTTPServer(('127.0.0.1',0),handler));self.server_patch.start();self.addCleanup(self.server_patch.stop)
  self.tmp=tempfile.TemporaryDirectory();self.mail=[];self.now=2000000000
  self.database=Path(self.tmp.name)/'control.sqlite3';self.identity=IdentityService(self.database,self.mail.append,clock=lambda:self.now)
  self.upstreams=[];self.threads=[];self.sessions=[];self.tenants=[];self.origins={}
  for i in range(2):
   email='shared%s@example.test'%i;self.identity.register(email);self.identity.complete_registration(self.mail[-1]['token'],'Fictional shared password 2026!')
   session=self.identity.login(email,'Fictional shared password 2026!')['session'];self.sessions.append(session)
   tid=self.identity.create_company(session,'shared-company-'+str(i),[],'request-'+str(i))['id'];self.tenants.append(tid)
   jobs=Onboarding(self.identity);jobs.run(jobs.request(session,tid)['job_id'],FakeAdapter())
   class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
     body=json.dumps({'company':self.server.company}).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   server=ThreadingHTTPServer(('127.0.0.1',0),Upstream);server.company=tid
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.upstreams.append(server);self.threads.append(thread);self.origins[tid]='http://127.0.0.1:'+str(server.server_port)
  self.manager=HTTPSGatewayManager(self.database,FakeAdapter(),'https://cuenta.uno360x.com','https://piloto.uno360x.com',shared_origin=True,clock=lambda:self.now)
  def open_backend(jobs,session,ticket,adapter):
   claims=jobs.consume_handoff(session,ticket);snapshot=json.loads(jobs.db.execute('SELECT snapshot FROM preparation_jobs WHERE tenant_id=?',(claims['tenant_id'],)).fetchone()[0])
   return BackendSession(jobs,session,claims,snapshot,urllib.request.build_opener(NoRedirect(),urllib.request.ProxyHandler({})),self.origins[claims['tenant_id']],3)
  self.patch=patch('control.gateway.open_space',side_effect=open_backend);self.patch.start()
 def tearDown(self):
  self.patch.stop();self.manager.close()
  for server,thread in zip(self.upstreams,self.threads):server.shutdown();server.server_close();thread.join()
  self.identity.close();self.tmp.cleanup()
 def request(self,path,cookie='',data=None,origin=None):
  c=http.client.HTTPConnection('127.0.0.1',self.manager.servers['shared'].server_port,timeout=10);headers={'Host':'piloto.uno360x.com','Cookie':cookie}
  if origin:headers['Origin']=origin
  if data is not None:headers['Content-Type']='application/x-www-form-urlencoded'
  c.request('POST' if data is not None else 'GET',path,data,headers);r=c.getresponse();status=r.status;h=dict(r.getheaders());body=r.read();c.close();return status,h,body
 def launch(self,i):
  jobs=Onboarding(self.identity);ticket=jobs.issue_handoff(self.sessions[i],self.tenants[i])['ticket'];grant=self.manager.launch(self.sessions[i],ticket)
  result=self.request('/__launch',data=urllib.parse.urlencode({'grant':grant['grant']}).encode(),origin='https://cuenta.uno360x.com')
  self.assertEqual(result[0],303);self.assertEqual(result[1]['Location'],'/uno360x-resumen');self.assertIn('storage',result[1]['Clear-Site-Data']);return result[1]['Set-Cookie'].split(';')[0]
 def test_two_companies_share_entry_without_sharing_backend_or_permissions(self):
  first=self.launch(0);second=self.launch(1)
  self.assertNotEqual(first,second)
  self.assertEqual(json.loads(self.request('/odoo',first)[2])['company'],self.tenants[0])
  self.assertEqual(json.loads(self.request('/odoo',second)[2])['company'],self.tenants[1])
  self.assertEqual(json.loads(self.request('/odoo?tenant_id='+self.tenants[1],first)[2])['company'],self.tenants[0])
  token=first.split('=',1)[1]
  with self.assertRaises(IdentityError):self.manager.lookup(token,self.tenants[1])
  self.identity.logout(self.sessions[0]);self.assertEqual(self.request('/odoo',first)[0],401)
  self.assertEqual(self.request('/odoo',second)[0],200)
  self.assertEqual(self.request('/odoo',first+'forged')[0],401)

 def test_company_parameters_are_not_rewritten_on_each_login(self):
  from control.trials import Trials
  Trials(self.identity)
  account=self.identity._account(self.sessions[0])['id'];tid=self.tenants[0]
  with self.identity.db:self.identity.db.execute('INSERT INTO trial_workspaces VALUES (?,?,?,?,?,?,?,?)',(account,tid,'Fictional company','DO','DOP',self.now,self.now,self.now+1296000))
  calls=[];self.manager.adapter.configure_company=lambda *args:calls.append(args)
  self.launch(0);self.launch(0)
  self.assertEqual(len(calls),1)
