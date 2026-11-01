"""Queue one fictional signup through loopback HTTP; no actual email sent."""
import http.cookiejar,json,os,secrets,sys,threading,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from control.identity import IdentityService
from control.identity_http import IdentityHTTPServer
from deployment.shared_adapter import SharedHostAdapter
STATE=Path('/var/lib/uno360x-saas/control')
def main():
 os.umask(0o077);adapter=SharedHostAdapter();STATE.mkdir(mode=0o700,exist_ok=True)
 path=STATE/'control.sqlite3';mail=[];identity=IdentityService(path,mail.append)
 password=adapter.protected(STATE/'pilot-owner-password',secrets.token_urlsafe(32)).read_text()
 server=IdentityHTTPServer(0,path,mail.append);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}));csrf=''
 def post(route,data):
  request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+route,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
  with opener.open(request,timeout=30) as response:return json.load(response)
 try:
  email='private-vm-pilot@example.test';old=identity.db.execute('SELECT verified FROM accounts WHERE email=?',(email,)).fetchone()
  if not old or not old['verified']:
   post('/trial/register',{'email':email,'name':'Persona ficticia piloto VM','modules':[],'consent':True})
   post('/verify',{'token':mail[-1]['token'],'password':password})
  csrf=post('/login',{'email':email,'password':password})['csrf_token']
  data={'name':'CLIENTE FICTICIO VM - UNO360X','country':'DO','currency':'DOP','modules':[]}
  result=post('/trial/create',data);again=post('/trial/create',data);assert result['tenant_id']==again['tenant_id']
  report={'job_id':result['job_id'],'tenant_id':result['tenant_id'],'signup_transport':'loopback_HTTP','email_transport':'in_memory_fictional','public_signup_enabled':False,'idempotent_create':True,'status':result['status']}
  (STATE/'pilot-signup.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
  post('/logout',{})
 finally:server.shutdown();server.server_close();thread.join();identity.close();mail.clear()
if __name__=='__main__':main()
