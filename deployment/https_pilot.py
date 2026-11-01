"""Explicit HTTPS pilot transport. Loopback only; nginx terminates verified TLS.
No public rollout: only the operator allowlist may register. One tenant per host.
"""
import io,json,os,re,threading
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from control.identity_http import Handler as LocalHandler
from control.gateway import GatewayManager,TenantServer,GatewayHandler
from control.identity import email_key,digest,IdentityError
from control.web_pages import asset


def checked_origin(origin):
 u=urlsplit(origin)
 if u.scheme!='https' or not re.fullmatch(r'[a-z0-9-]+\.uno360x\.com',u.netloc) or u.path or u.query or u.fragment:
  raise ValueError('Dedicated HTTPS subdomain required')
 return u.netloc

HTTP_SLOTS=threading.BoundedSemaphore(6)

class BoundedHTTPServer(ThreadingHTTPServer):
 daemon_threads=True
 def __init__(self,*args,**kw):
  self.slots=HTTP_SLOTS
  super().__init__(*args,**kw)
 def process_request(self,request,address):
  if not self.slots.acquire(blocking=False):
   try:
    body=b'{"error":"Hay varias solicitudes. Intenta de nuevo en unos segundos."}'
    request.sendall(('HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\nRetry-After: 3\r\nContent-Length: %s\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n'%len(body)).encode()+body)
   finally:self.shutdown_request(request)
   return
  try:super().process_request(request,address)
  except BaseException:self.slots.release();raise
 def process_request_thread(self,request,address):
  try:super().process_request_thread(request,address)
  finally:self.slots.release()

class HTTPSIdentityServer(BoundedHTTPServer):
 daemon_threads=True
 def __init__(self,port,database,deliver,launch,origin,allowed_emails,tenant_origin,public_signup=False):
  self.authority=checked_origin(origin);self.origin=origin
  self.tenant_origin=tenant_origin;checked_origin(tenant_origin)
  self.database,self.deliver,self.launch=database,deliver,launch
  self.public_signup=public_signup
  self.consent_version='public-trial-v1' if public_signup else 'pilot-invitation-v1'
  self.allowed_emails=frozenset(email_key(e) for e in allowed_emails)
  if not self.allowed_emails and not public_signup:raise ValueError('Explicit pilot allowlist required')
  super().__init__(('127.0.0.1',port),HTTPSIdentityHandler)

class HTTPSIdentityHandler(LocalHandler):
 def _origin_ok(self):
  return self.headers.get('Host')==self.server.authority and self.headers.get('Origin',None if self.command=='POST' else self.server.origin)==self.server.origin
 def _reply(self,status,value,cookie=None):
  if cookie:cookie=cookie.replace('uno360x_lab_session=','__Host-uno360x_session=')+'; Secure'
  if self.path=='/health':value={'mode':'public-https' if self.server.public_signup else 'controlled-https-pilot','public_signup_enabled':self.server.public_signup}
  super()._reply(status,value,cookie)
 def _session(self):
  jar=SimpleCookie()
  try:jar.load(self.headers.get('Cookie',''))
  except Exception:return ''
  return jar['__Host-uno360x_session'].value if '__Host-uno360x_session' in jar else ''
 def do_GET(self):
  if not self._origin_ok():self._reply(403,{'error':'Origen no autorizado.'});return
  if self.path=='/':
   self.send_response(303);self.send_header('Location','/web/login');self.send_header('Cache-Control','no-store');self.end_headers();return
  resource=asset(self.path)
  if not resource:return super().do_GET()
  kind,body=resource
  text=body.decode('utf-8')
  text=text.replace('Laboratorio privado · Datos de prueba · Sin cargos ni correo real','Piloto UNO360X · Acceso por invitación · Sin cargos')
  text=text.replace(' En laboratorio, consulta el buzón privado.',' Revisa tu correo electrónico.')
  text=text.replace('Acceso de laboratorio.','Acceso seguro a tu empresa.')
  text=text.replace('trabajador local','servicio de preparación')
  text=text.replace('En este laboratorio no enviamos correo real. El enlace se guarda en el buzón privado del equipo para las pruebas.','Te enviaremos un correo real de UNO360X. Revisa también la carpeta de correo no deseado.')
  text=text.replace('condiciones de la prueba de laboratorio','condiciones del piloto')
  text=text.replace('href="/#','href="https://uno360x.com/#').replace('href="/planes-y-precios"','href="https://uno360x.com/planes-y-precios"')
  text=text.replace('Empieza con la Base Empresarial y agrega los módulos que necesitas.','Este piloto por invitación utiliza Base Empresarial con CRM y POS. Los módulos adicionales están en preparación.')
  text=text.replace('function plans(){steps(1);','function plans(){draft.modules=[];save();steps(1);')
  text=text.replace('type="checkbox" name="modules"','type="checkbox" disabled name="modules"')
  text=text.replace('Agregar a mi prueba','En preparación')
  text=text.replace("target.protocol!=='http:'||target.hostname!=='127.0.0.1'||target.pathname!=='/__launch'||!target.port",
                    "target.origin!=="+json.dumps(self.server.tenant_origin)+"||target.pathname!=='/__launch'")
  if self.path in ('/condiciones','/privacidad'):
   title='Condiciones del piloto' if self.path=='/condiciones' else 'Privacidad del piloto'
   content=('Piloto por invitación durante 15 días desde la preparación del espacio, sin tarjeta, cargos automáticos ni contratación comercial. Base Empresarial incluye CRM y POS. La emisión fiscal requiere validación independiente. Los módulos adicionales y precios siguen en preparación.' if self.path=='/condiciones' else 'El correo identifica tu cuenta. Los datos se almacenan en la infraestructura de UNO360X; Resend procesa los mensajes de confirmación y recuperación. Las contraseñas se guardan mediante hash y los enlaces son temporales y de un solo uso. Usa información de prueba durante este piloto. Para solicitar asistencia o eliminación, contacta a ecueto@outsolutech.com.')
   text='<html lang="es"><meta charset="utf-8"><title>'+title+'</title><h1>'+title+'</h1><p>'+content+'</p><a href="/prueba/cuenta">Volver</a></html>'
  if self.server.public_signup:
   text=text.replace('Piloto UNO360X · Acceso por invitación · Sin cargos','UNO360X · 15 días gratis · Sin tarjeta')
   text=text.replace('Este piloto por invitación utiliza Base Empresarial con CRM y POS. Los módulos adicionales están en preparación.','Empieza con Base Empresarial, CRM y POS. Los módulos adicionales están en preparación.')
   text=text.replace('condiciones del piloto','condiciones de la prueba').replace('Condiciones del piloto','Condiciones de la prueba')
   text=text.replace('Privacidad del piloto','Privacidad de la prueba').replace('Piloto por invitación durante 15 días','Prueba gratis durante 15 días')
  encoded=text.encode('utf-8')
  self.send_response(200);self.send_header('Content-Type',kind+'; charset=utf-8')
  self.send_header('Content-Length',str(len(encoded)));self.send_header('Cache-Control','no-store')
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
  self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; form-action 'self' "+self.server.tenant_origin+"; base-uri 'none'; frame-ancestors 'none'")
  self.end_headers();self.wfile.write(encoded)
 def do_POST(self):
  # Never let alternate company-creation or invitation routes bypass pilot capacity.
  permitted={'/trial/register','/verify','/reset/request','/reset/complete','/login','/logout',
   '/companies','/trial/draft','/trial/create','/trial/status','/spaces/open','/setup/profile','/setup/status'}
  if not self._origin_ok():self._reply(403,{'error':'Origen no autorizado.'});return
  if self.path not in permitted:self._reply(404,{'error':'Ruta no disponible.'});return
  if self.path in ('/trial/register','/reset/request','/login','/trial/create'):
   try:
    n=int(self.headers.get('Content-Length','0'))
    if not 1<=n<=16384 or self.headers.get('Transfer-Encoding'):raise ValueError()
    raw=self.rfile.read(n);data=json.loads(raw)
    if self.path!='/trial/create' and not self.server.public_signup and email_key(data['email']) not in self.server.allowed_emails:
     self._reply(403,{'error':'Este piloto tiene acceso por invitación.'});return
    if self.server.public_signup and self.path=='/trial/register' and email_key(data['email']).endswith(('.test','.invalid','.localhost')):
     self._reply(400,{'error':'Utiliza un correo que pueda recibir el enlace de confirmación.'});return
    if self.path in ('/trial/create','/trial/register') and data.get('modules'):
     self._reply(400,{'error':'El piloto inicial utiliza Base Empresarial con CRM y POS.'});return
    self.rfile=io.BytesIO(raw)
   except (ValueError,KeyError,TypeError):self._reply(400,{'error':'Solicitud inválida.'});return
  super().do_POST()

class HTTPSGatewayManager(GatewayManager):
 def __init__(self,database,adapter,central_origin,tenant_origin,shared_origin=False,**kw):
  self.shared_origin=shared_origin
  self.central_origin=central_origin;checked_origin(central_origin)
  self.tenant_origin=tenant_origin;checked_origin(tenant_origin)
  super().__init__(database,adapter,**kw)
 def server(self,tenant):
  with self.lock:
   key='shared' if self.shared_origin else tenant
   if key not in self.servers:
    if self.servers:raise RuntimeError('Single pilot tenant capacity')
    server=BoundedHTTPServer(('127.0.0.1',18184),GatewayHandler)
    server.manager,server.tenant=self,None if self.shared_origin else tenant
    server.origin=self.tenant_origin;server.authority=checked_origin(server.origin)
    server.central_origin=self.central_origin;server.cookie='__Host-uno360x_pilot_space'
    server.secure_cookie='; Secure'
    self.servers[key]=server
    threading.Thread(target=server.serve_forever,daemon=True).start()
   return self.servers[key]
 def consume(self,grant,tenant):
  if tenant is None:
   if not self.shared_origin or not isinstance(grant,str):raise IdentityError('Entrada inválida.')
   with self.lock:
    result=self.grants.get(digest(grant))
    if not result:raise IdentityError('Entrada inválida.')
    tenant=result[0].tenant
  return super().consume(grant,tenant)
 def lookup(self,token,tenant):
  if tenant is None:
   if not self.shared_origin or not isinstance(token,str):raise IdentityError('Sesión inválida.')
   with self.lock:
    handle=self.handles.get(digest(token))
    if not handle:raise IdentityError('Sesión inválida.')
    tenant=handle.tenant
  return super().lookup(token,tenant)
 def launch(self,session,ticket):
  result=super().launch(session,ticket)
  result['public_access']=True
  return result
