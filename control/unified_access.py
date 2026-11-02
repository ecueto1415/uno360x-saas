"""Native credentials stay in native Odoo; ephemeral, single-use browser entry."""
import hashlib
import hmac
import json
import ipaddress
import pathlib
import secrets
import threading
import time
import urllib.request
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

from control.identity import IdentityService, IdentityError, email_key, digest
from control.identity_http import csrf_for
from control.trials import Trials

OP_COOKIE = '__Host-uno360x_operational'
SAAS_COOKIE = '__Host-uno360x_session'
OP_ID = '__operational__'
ERP_ORIGIN = 'https://erp.uno360x.com'
ENTRY = '/__operational/enter'
DATABASE = 'Outsolutech_prueba'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class NativeAccess:
    def __init__(self, clock=time.time, directory=None):
        self.clock = clock
        self.directory = pathlib.Path(directory) if directory else None
        self.lock = threading.RLock()
        self.sessions, self.grants = {}, {}

    def rpc(self, path, params, sid='', client_ip=''):
        if path not in ('/web/session/authenticate', '/web/session/get_session_info', '/web/session/destroy'):
            raise ValueError('Fixed native session endpoints required')
        headers = {'Content-Type': 'application/json', 'Host': 'erp.uno360x.com'}
        if client_ip:
            headers['X-Forwarded-For'] = str(ipaddress.ip_address(client_ip))
            headers['X-Forwarded-Host'] = 'erp.uno360x.com'
            headers['X-Forwarded-Proto'] = 'https'
        if sid:
            headers['Cookie'] = 'session_id=' + sid
        request = urllib.request.Request('http://127.0.0.1:8069' + path,
            json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params, 'id': 1}).encode(), headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=6) as response:
            value = json.loads(response.read(1024 * 1024))
            jar = SimpleCookie()
            for cookie in response.headers.get_all('Set-Cookie', []):
                jar.load(cookie)
            cookie = jar['session_id'].value if 'session_id' in jar else sid
        return value.get('result') or {}, cookie

    def prune(self):
        now = self.clock()
        self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > now}
        self.grants = {k: v for k, v in self.grants.items() if v[1] > now and v[0] in self.sessions}

    def authenticate(self, email, password, client_ip=''):
        if self.directory:
            directory = json.loads(self.directory.read_text())
            if not self.clock() - 300 <= directory['updated'] <= self.clock() + 30:
                # Refreshed every minute; fail closed if the directory is stale.
                raise IdentityError('Directorio operativo pendiente de actualizar.')
            if digest(email) not in directory['logins']:
                return None
        result, sid = self.rpc('/web/session/authenticate',
            {'db': DATABASE, 'login': email, 'password': password}, client_ip=client_ip)
        # Pending MFA has no authenticated uid. Never create or bypass a native identity.
        if not result.get('uid') or result.get('db') != DATABASE or not sid:
            return None
        if email_key(result.get('username', '')) != email:
            return None
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.prune()
            if len(self.sessions) >= 512:
                raise IdentityError('Hay varias solicitudes. Intenta de nuevo.')
            self.sessions[digest(token)] = {'email': email, 'sid': sid,
                'uid': result['uid'], 'expires': self.clock() + 3600}
        return token

    def account(self, token, validate=True):
        with self.lock:
            self.prune()
            row = self.sessions.get(digest(token))
        if not row:
            raise IdentityError('Sesión vencida.')
        if validate:
            info, _ = self.rpc('/web/session/get_session_info', {}, row['sid'])
            if info.get('uid') != row['uid'] or info.get('db') != DATABASE:
                self.remove(token)
                raise IdentityError('Sesión vencida.')
        return row

    def issue(self, token):
        self.account(token)
        grant = secrets.token_urlsafe(32)
        with self.lock:
            self.prune()
            if len(self.grants) >= 1024:
                raise IdentityError('Hay varias solicitudes. Intenta de nuevo.')
            self.grants[digest(grant)] = (digest(token), self.clock() + 30)
        return grant

    def consume(self, grant):
        with self.lock:
            self.prune()
            item = self.grants.pop(digest(grant), None)
            row = self.sessions.get(item[0]) if item else None
        if not row:
            raise IdentityError('Entrada vencida o utilizada.')
        info, _ = self.rpc('/web/session/get_session_info', {}, row['sid'])
        if info.get('uid') != row['uid'] or info.get('db') != DATABASE:
            raise IdentityError('Sesión vencida.')
        return row['sid']

    def remove(self, token):
        with self.lock:
            row = self.sessions.pop(digest(token), None)
            self.prune()
        return row


class UnifiedAccessMixin:
    def _op_token(self):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
            return jar[OP_COOKIE].value if OP_COOKIE in jar else ''
        except Exception:
            return ''

    def _unified_reply(self, status, value, cookies=()):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        for key, val in [('Content-Type', 'application/json; charset=utf-8'),
            ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'),
            ('Referrer-Policy', 'no-referrer'), ('X-Content-Type-Options', 'nosniff'),
            ('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")]:
            self.send_header(key, val)
        for cookie in cookies:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _secure_cookie(name, token='', seconds=0):
        return f'{name}={token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age={seconds}'

    def _unified_accounts(self, service):
        saas, native = None, None
        try:
            saas = service._account(self._session())
        except IdentityError:
            pass
        if self._op_token():
            try:
                native = self.server.operational.account(self._op_token())
            except Exception:
                pass
        # Never combine two people left in different browser cookies.
        if saas and native and saas['email'] != native['email']:
            native = None
        if not saas and not native:
            raise IdentityError('Sesión vencida.')
        primary = self._session() if saas else self._op_token()
        return saas, native, primary

    def unified_get(self):
        if self.path != '/session' or not self._op_token():
            return False
        if not self._origin_ok():
            self._unified_reply(403, {'error': 'Origen no autorizado.'}); return True
        service = IdentityService(self.server.database, self.server.deliver)
        try:
            saas, native, token = self._unified_accounts(service)
            self._unified_reply(200, {'email': (saas or native)['email'], 'csrf_token': csrf_for(token)})
        except IdentityError:
            self._unified_reply(401, {'error': 'Sesión vencida.'})
        finally:
            service.close()
        return True

    def unified_entry(self):
        # This endpoint is exposed only by an exact Nginx location on ERP.
        if self.headers.get('Host') != 'erp.uno360x.com' or self.headers.get('Origin') != self.server.origin:
            self._unified_reply(403, {'error': 'Origen no autorizado.'}); return
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if not 1 <= n <= 512 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
                raise ValueError()
            data = parse_qs(self.rfile.read(n).decode(), strict_parsing=True)
            if set(data) != {'grant'} or len(data['grant']) != 1:
                raise ValueError()
            sid = self.server.operational.consume(data['grant'][0])
            self.send_response(303)
            self.send_header('Location', '/odoo')
            self.send_header('Set-Cookie', f'session_id={sid}; HttpOnly; Secure; SameSite=Lax; Path=/')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Length', '0')
            self.end_headers()
        except Exception:
            self._unified_reply(400, {'error': 'El acceso venció. Vuelve a iniciar sesión en cuenta.uno360x.com.'})

    def unified_post(self):
        if self.path == ENTRY:
            self.unified_entry(); return True
        if self.path not in ('/login', '/companies', '/spaces/open', '/logout'):
            return False
        if self.path != '/login' and not self._op_token():
            return False
        if not self._origin_ok():
            self._unified_reply(403, {'error': 'Origen no autorizado.'}); return True
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if not 1 <= n <= 16384 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError()
            raw = self.rfile.read(n)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
        except Exception:
            self._unified_reply(400, {'error': 'Solicitud inválida.'}); return True
        service = IdentityService(self.server.database, self.server.deliver)
        try:
            if self.path == '/login':
                email, password = email_key(data['email']), data['password']
                if not isinstance(password, str) or not 1 <= len(password) <= 4096:
                    raise ValueError()
                with service.db:
                    service.db.execute('BEGIN IMMEDIATE')
                    allowed = service._allow('unified-login', email, maximum=8, window=300)
                    transport = service._allow('unified-transport', self.client_address[0], maximum=60, window=60)
                if not allowed or not transport:
                    self._unified_reply(429, {'error': 'Espera unos minutos antes de volver a intentarlo.'}); return True
                saas, native, unavailable = None, None, False
                try:
                    saas = service.login(email, password)
                except IdentityError:
                    pass
                try:
                    native = self.server.operational.authenticate(email, password,
                        self.headers.get('X-UNO360X-Client-IP', self.client_address[0]))
                except Exception:
                    unavailable = True
                if not saas and not native:
                    self._unified_reply(503 if unavailable else 400, {'error': 'El acceso operativo no responde. Intenta de nuevo.' if unavailable else 'Contraseña incorrecta.'}); return True
                # Replace both cookies, so a prior different account cannot leak into this login.
                cookies = [self._secure_cookie(SAAS_COOKIE, saas['session'] if saas else '', saas['expires_in'] if saas else 0),
                    self._secure_cookie(OP_COOKIE, native or '', 3600 if native else 0)]
                token = saas['session'] if saas else native
                old = self._op_token()
                if old:
                    self.server.operational.remove(old)
                with service.db:
                    service.db.execute('DELETE FROM identity_limits WHERE bucket=?', (digest('unified-login:' + email),))
                self._unified_reply(200, {'email': email, 'csrf_token': csrf_for(token)}, cookies)
                return True
            saas, native, token = self._unified_accounts(service)
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), csrf_for(token)):
                self._unified_reply(403, {'error': 'Solicitud no autorizada.'}); return True
            if self.path == '/companies':
                companies = Trials(service).companies(self._session())['companies'] if saas else []
                if native:
                    companies.append({'id': OP_ID, 'name': 'OUTSOLUTECH', 'slug': 'outsolutech', 'role': 'member', 'operational': True})
                self._unified_reply(200, {'companies': companies}); return True
            if self.path == '/spaces/open':
                if data.get('tenant_id') != OP_ID:
                    if not saas:
                        raise IdentityError('No tienes acceso a esa empresa.')
                    import io
                    self.rfile = io.BytesIO(raw)
                    return False
                if not native:
                    raise IdentityError('No tienes acceso a esa empresa.')
                grant = self.server.operational.issue(self._op_token())
                self._unified_reply(200, {'launch_url': ERP_ORIGIN + ENTRY, 'grant': grant, 'operational_access': True}); return True
            if self.path == '/logout':
                if saas:
                    service.logout(self._session())
                row = self.server.operational.remove(self._op_token())
                if row:
                    try:
                        self.server.operational.rpc('/web/session/destroy', {}, row['sid'])
                    except Exception:
                        pass
                self._unified_reply(200, {'logged_out': True}, [self._secure_cookie(SAAS_COOKIE), self._secure_cookie(OP_COOKIE)])
                return True
        except IdentityError:
            self._unified_reply(401, {'error': 'Vuelve a iniciar sesión.'})
        except (ValueError, KeyError, TypeError):
            self._unified_reply(400, {'error': 'Solicitud inválida.'})
        except Exception:
            self._unified_reply(503, {'error': 'No pudimos abrir tu empresa. Intenta de nuevo.'})
        finally:
            service.close()
        return True
