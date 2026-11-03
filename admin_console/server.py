"""Read-only SaaS owner console on a dedicated origin and system account."""
import json,os,time,hmac,ipaddress,threading
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from admin_console.auth import Auth,Denied,Limited,csrf
from admin_console.storage import overlay,increase,QuotaError,Conflict

COOKIE='__Host-uno360x_admin';CHALLENGE='__Host-uno360x_admin_challenge'
ROOT=Path(__file__).resolve().parent
CSP="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"

class Server(ThreadingHTTPServer):
 daemon_threads=True
 max_concurrent_requests=8
 def __init__(self,port,state,snapshot,owner='ecueto@outsolutech.com',origin='https://admin.uno360x.com',factor='totp',delivery=None):
  self.factor=factor;self.delivery=delivery
  self.state=Path(state);self.snapshot=Path(snapshot);self.owner=owner;self.origin=origin;self.host=urlsplit(origin).netloc;self.clock=time.time
  if origin!='https://admin.uno360x.com':raise ValueError('Dedicated administrative origin required')
  self.slots=threading.BoundedSemaphore(8)
  super().__init__(('127.0.0.1',port),Handler)
 def process_request(self,request,address):
  if not self.slots.acquire(blocking=False):
   try:request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nRetry-After: 5\r\n\r\n')
   finally:self.shutdown_request(request)
   return
  try:super().process_request(request,address)
  except BaseException:self.slots.release();raise
 def process_request_thread(self,request,address):
  try:super().process_request_thread(request,address)
  finally:self.slots.release()

class Handler(BaseHTTPRequestHandler):
 server_version='UNO360X';protocol_version='HTTP/1.0'
 def setup(self):super().setup();self.connection.settimeout(10)
 def log_message(self,*args):pass
 def common(self,code,kind,body,cookies=()):
  self.send_response(code)
  for k,v in [('Content-Type',kind),('Content-Length',str(len(body))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('Content-Security-Policy',CSP),('X-Frame-Options','DENY'),('Cross-Origin-Opener-Policy','same-origin'),('Permissions-Policy','camera=(), microphone=(), geolocation=()')]:self.send_header(k,v)
  for value in cookies:self.send_header('Set-Cookie',value)
  self.end_headers();self.wfile.write(body)
 def reply(self,status,obj,cookies=()):self.common(status,'application/json; charset=utf-8',json.dumps(obj,ensure_ascii=False).encode(),cookies)
 def cookie(self,name):
  try:
   jar=SimpleCookie();jar.load(self.headers.get('Cookie',''));return jar[name].value if name in jar else ''
  except Exception:return ''
 def valid_origin(self):return self.headers.get('Host')==self.server.host and (self.command!='POST' or self.headers.get('Origin')==self.server.origin)
 def auth(self):return Auth(self.server.state,self.server.owner,clock=self.server.clock,factor=self.server.factor,delivery=self.server.delivery)
 def agent(self):return self.headers.get('User-Agent','')[:512]
 def ip(self):
  try:return str(ipaddress.ip_address(self.headers.get('X-UNO360X-Client-IP',self.client_address[0])))
  except ValueError:return self.client_address[0]
 def setcookie(self,name,token='',ttl=0):return f'{name}={token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={ttl}'
 def do_GET(self):
  if not self.valid_origin():self.reply(403,{'error':'Origen no autorizado.'});return
  route=urlsplit(self.path).path
  assets={'/':('text/html','index.html'),'/login':('text/html','index.html'),'/activar':('text/html','index.html'),'/assets/admin.css':('text/css','admin.css'),'/assets/admin.js':('application/javascript','admin.js')}
  if route in assets:
   kind,name=assets[route];self.common(200,kind+'; charset=utf-8',(ROOT/'web'/name).read_bytes());return
  if route=='/api/auth-config':self.reply(200,{'factor':self.server.factor});return
  if route=='/health':self.reply(200,{'status':'available'});return
  if route not in ('/api/session','/api/overview','/api/activity'):
   self.reply(404,{'error':'Ruta no disponible.'});return
  auth=self.auth()
  try:
   account=auth.account(self.cookie(COOKIE),self.agent(),touch=route=='/api/session')
   if route=='/api/session':self.reply(200,account);return
   if route=='/api/activity':
    entries=auth.db.execute('SELECT event,occurred FROM audit ORDER BY id DESC LIMIT 60').fetchall();self.reply(200,{'entries':[dict(r) for r in entries]});return
   data=overlay(auth.db,json.loads(self.server.snapshot.read_text()))
   stale=time.time()-data['generated']>180
   self.reply(200,{'snapshot':data,'stale':stale,'storage_quota_enforced':False,'billing_configured':False})
  except Denied:self.reply(401,{'error':'Inicia sesión para continuar.'})
  except Exception:self.reply(503,{'error':'No pudimos actualizar los datos. Vuelve a intentarlo.'})
  finally:auth.close()
 def do_POST(self):
  if not self.valid_origin():self.reply(403,{'error':'Origen no autorizado.'});return
  if self.path not in ('/api/login','/api/mfa','/api/mfa/resend','/api/enroll/start','/api/enroll/finish','/api/logout','/api/storage/quota'):
   self.reply(404,{'error':'Ruta no disponible.'});return
  auth=None
  try:
   n=int(self.headers.get('Content-Length','0'))
   if self.headers.get('Transfer-Encoding') or not 1<=n<=4096 or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError()
   data=json.loads(self.rfile.read(n))
   if not isinstance(data,dict):raise ValueError()
   auth=self.auth()
   if self.path=='/api/login':
    challenge=auth.login(data.get('email'),data.get('password'),self.agent(),self.ip())
    self.reply(200,{'mfa_required':True,'factor':self.server.factor},[self.setcookie(CHALLENGE,challenge,600 if self.server.factor=='email' else 300),self.setcookie(COOKIE)]);return
   if self.path=='/api/mfa/resend':
    auth.resend_email(self.cookie(CHALLENGE),self.agent(),self.ip());self.reply(200,{'sent':True});return
   if self.path=='/api/mfa':
    session=auth.mfa(self.cookie(CHALLENGE),data.get('code'),self.agent(),self.ip())
    self.reply(200,{'authenticated':True},[self.setcookie(COOKIE,session,28800),self.setcookie(CHALLENGE)]);return
   if self.path=='/api/enroll/start':
    self.reply(200,auth.start_enrollment(data.get('token'),self.ip()));return
   if self.path=='/api/enroll/finish':
    session,codes=auth.finish_enrollment(data.get('token',''),data.get('password'),data.get('code'),self.agent(),self.ip())
    self.reply(200,{'authenticated':True,'recovery_codes':codes},[self.setcookie(COOKIE,session,28800),self.setcookie(CHALLENGE)]);return
   token=self.cookie(COOKIE);auth.account(token,self.agent())
   if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),csrf(token)):self.reply(403,{'error':'Solicitud no autorizada.'});return
   if self.path=='/api/storage/quota':
    auth.allow('storage-change',30);result=increase(auth.db,json.loads(self.server.snapshot.read_text()),data,self.server.owner,self.server.clock());self.reply(200,result);return
   auth.logout(token);self.reply(200,{'logged_out':True},[self.setcookie(COOKIE),self.setcookie(CHALLENGE)])
  except Conflict as error:self.reply(409,{'error':str(error)})
  except QuotaError as error:self.reply(400,{'error':str(error)})
  except Limited as error:self.reply(429,{'error':str(error)})
  except Denied as error:self.reply(400,{'error':str(error)})
  except (ValueError,TypeError,KeyError):self.reply(400,{'error':'Solicitud inválida. La contraseña debe tener de 12 a 128 caracteres.'})
  except Exception:self.reply(503,{'error':'El acceso no está disponible en este momento.'})
  finally:
   if auth:auth.close()

def main():
 os.umask(0o077)
 config=json.loads(Path('/etc/uno360x-admin.json').read_text())
 from admin_console.mail_client import send_code
 server=Server(18185,config['state'],config['snapshot'],config['owner'],factor=config.get('factor','totp'),delivery=send_code)
 server.serve_forever()

if __name__=='__main__':main()
