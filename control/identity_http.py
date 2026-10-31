"""Loopback-only JSON API for identity laboratory tests, never production hosting.

No UI, SMTP, DNS, TLS, Odoo session sharing or automatic provisioning.
Run only through a caller supplying a local database and delivery sink.
"""
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json

from .identity import IdentityService,IdentityError
from .onboarding import Onboarding
from .setup import Setup

COOKIE = 'uno360x_lab_session'


def csrf_for(session):
    return hmac.new(session.encode(),b'uno360x-csrf',hashlib.sha256).hexdigest()


class IdentityHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, database, deliver):
        self.database,self.deliver = database,deliver
        # Address cannot be supplied by a request or changed to a public bind.
        super().__init__(('127.0.0.1',port),Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'UNO360XLocal'

    def log_message(self, *args):
        # Never log request bodies, token-bearing URLs, cookies or passwords.
        pass

    def _reply(self, status, value, cookie=None):
        encoded = json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(encoded)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(encoded)

    def _origin_ok(self):
        authority='127.0.0.1:'+str(self.server.server_port)
        return self.headers.get('Host')==authority and self.headers.get('Origin','http://'+authority)=='http://'+authority

    def _session(self):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:raise IdentityError('Sesión inválida.') from None
        return cookie[COOKIE].value if COOKIE in cookie else ''

    def do_GET(self):
        if not self._origin_ok():
            self._reply(403,{'error':'Origen no autorizado.'});return
        if self.path=='/health':
            self._reply(200,{'mode':'local-laboratory','public_ready':False});return
        if self.path!='/session':
            self._reply(404,{'error':'Ruta no disponible.'});return
        service=IdentityService(self.server.database,self.server.deliver)
        try:
            token=self._session()
            account=service._account(token)
            self._reply(200,{'email':account['email'],'csrf_token':csrf_for(token)})
        except IdentityError:
            self._reply(401,{'error':'Sesión inválida o vencida.'})
        finally:service.close()

    def do_POST(self):
        if not self._origin_ok():
            self._reply(403,{'error':'Origen no autorizado.'});return
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
            self._reply(415,{'error':'Se requiere JSON.'});return
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:length=0
        if not 1<=length<=16384:
            self._reply(413,{'error':'Solicitud fuera de tamaño.'});return
        try:
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError()
        except (ValueError,UnicodeError):
            self._reply(400,{'error':'Solicitud inválida.'});return
        service=IdentityService(self.server.database,self.server.deliver)
        try:
            with service.db:
                service.db.execute('BEGIN IMMEDIATE')
                permitted=service._allow('transport',self.client_address[0],maximum=60,window=60)
            if not permitted:
                self._reply(429,{'error':'Espera antes de volver a intentarlo.'});return
            public={
                '/register':lambda:service.register(data['email']),
                '/verify':lambda:service.complete_registration(data['token'],data['password']),
                '/reset/request':lambda:service.request_reset(data['email']),
                '/reset/complete':lambda:service.reset_password(data['token'],data['password']),
            }
            if self.path in public:
                self._reply(200,public[self.path]());return
            if self.path=='/login':
                result=service.login(data['email'],data['password']);session=result.pop('session')
                result['csrf_token']=csrf_for(session)
                self._reply(200,result,cookie=f'{COOKIE}={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age={result["expires_in"]}')
                return
            session=self._session()
            service._account(session)
            supplied=self.headers.get('X-CSRF-Token','')
            if not hmac.compare_digest(supplied,csrf_for(session)):
                self._reply(403,{'error':'Solicitud no autorizada.'});return
            onboarding=Onboarding(service)
            setup=Setup(service)
            private={
                '/logout':lambda:service.logout(session),
                '/companies':lambda:{'companies':service.companies(session)},
                '/companies/create':lambda:service.create_company(session,data['slug'],data.get('modules',[]),data['request_id']),
                '/companies/select':lambda:service.select_company(session,data['tenant_id']),
                '/invitations/create':lambda:service.invite(session,data['tenant_id'],data['email'],data.get('role','member')),
                '/invitations/accept':lambda:service.accept_invitation(session,data['token']),
                '/invitations/revoke':lambda:service.revoke_invitation(session,data['tenant_id'],data['email']),
                '/members/remove':lambda:service.remove_member(session,data['tenant_id'],data['account_id']),
                '/members':lambda:{'members':service.members(session,data['tenant_id'])},
                '/members/role':lambda:service.change_role(session,data['tenant_id'],data['account_id'],data['role']),
                '/preparation/request':lambda:onboarding.request(session,data['tenant_id']),
                '/preparation/status':lambda:onboarding.status(session,data['tenant_id']),
                '/handoff/request':lambda:onboarding.issue_handoff(session,data['tenant_id']),
                '/setup/profile':lambda:setup.save(session,data['tenant_id'],data['profile']),
                '/setup/status':lambda:setup.status(session,data['tenant_id']),
            }
            if self.path not in private:
                self._reply(404,{'error':'Ruta no disponible.'});return
            value=private[self.path]()
            self._reply(200,value,cookie=f'{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' if self.path=='/logout' else None)
        except IdentityError:
            # Same error for wrong login, unknown identity or inaccessible company.
            self._reply(400,{'error':'No se pudo completar la operación.'})
        except (KeyError,TypeError,ValueError):
            self._reply(400,{'error':'Solicitud inválida.'})
        except Exception:
            self._reply(500,{'error':'No se pudo completar la operación.'})
        finally:
            service.close()
