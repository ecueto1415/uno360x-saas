"""Trusted loopback web gateway, separate from the account HTTP process.

One immutable tenant per loopback origin. Native Odoo cookies stay in memory.
This is a laboratory transport, not a supported public hosting configuration.
"""
from dataclasses import dataclass, field
import base64
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import select
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .access_broker import open_space
from .identity import IdentityService, IdentityError, digest
from .onboarding import Onboarding
from .trials import check_trial_access

MAX_BODY = 16 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
CENTRAL_ORIGIN = 'http://127.0.0.1:18072'
SAFE_RESPONSE_HEADERS = {'content-type', 'content-disposition', 'content-language',
                         'accept-ranges', 'content-range', 'last-modified', 'etag'}
SAFE_REQUEST_HEADERS = {'content-type', 'accept', 'accept-language', 'range', 'if-range', 'user-agent'}


def checked_path(path):
    if not isinstance(path, str) or len(path) > 8192 or any(ord(c) < 32 for c in path):
        raise IdentityError('Ruta inválida.')
    url = urllib.parse.urlsplit(path)
    decoded = urllib.parse.unquote(url.path)
    if url.scheme or url.netloc or url.fragment or not path.startswith('/') or '\\' in decoded or '..' in decoded.split('/') or decoded.startswith('//'):
        raise IdentityError('Ruta inválida.')
    if decoded.startswith(('/web/database', '/uno360x/bridge', '/web/session/authenticate',
                           '/web/reset_password', '/web/signup', '/web/login')):
        raise IdentityError('Acceso reservado al control central.')
    if 'service-worker' in decoded or 'service_worker' in decoded:
        raise IdentityError('Servicio offline no habilitado.')
    return path


@dataclass
class Handle:
    token: str
    tenant: str
    backend: object
    lock: object = field(default_factory=threading.Lock)
    sockets: object = field(default_factory=lambda: threading.BoundedSemaphore(3))
    active: bool = True


class GatewayManager:
    def __init__(self, database, adapter, deliver=lambda notice: None, clock=time.time):
        self.database, self.adapter, self.deliver, self.clock = database, adapter, deliver, clock
        self.handles, self.grants, self.servers = {}, {}, {}
        self.lock = threading.RLock()
        self.stopping = threading.Event()

    def identity(self):
        return IdentityService(self.database, self.deliver, clock=self.clock)

    def validate(self, handle, identity):
        if not handle.active:
            raise IdentityError('Sesión de espacio cerrada.')
        backend = handle.backend
        account = identity._account(backend.central_session)
        member = identity._membership(account['id'], handle.tenant)
        if account['id'] != backend.claims['account_id'] or member['role'] != backend.claims['role']:
            raise IdentityError('El acceso cambió.')
        check_trial_access(identity, handle.tenant)
        if not Onboarding(identity).status(backend.central_session, handle.tenant)['local_ready']:
            raise IdentityError('Empresa no disponible.')

    def server(self, tenant):
        with self.lock:
            if tenant not in self.servers:
                if len(self.servers) >= 16:
                    raise IdentityError('Capacidad local de empresas alcanzada.')
                server = TenantServer(self, tenant)
                self.servers[tenant] = server
                threading.Thread(target=server.serve_forever, daemon=True).start()
            return self.servers[tenant]

    def launch(self, session, ticket):
        identity = self.identity()
        try:
            jobs = Onboarding(identity)
            backend = open_space(jobs, session, ticket, self.adapter)
            tenant = backend.claims['tenant_id']
            server = self.server(tenant)
            # Only the trusted broker applies basic data; no fiscal data or credentials.
            if identity.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
                row = identity.db.execute('SELECT name,country,currency FROM trial_workspaces WHERE tenant_id=?', (tenant,)).fetchone()
                if row:
                    with self.adapter.lock(tenant):
                        self.adapter.configure_company(backend.snapshot, dict(row), server.origin)
                    identity.db.execute('''CREATE TABLE IF NOT EXISTS trial_company_parameters (
                        tenant_id TEXT PRIMARY KEY, applied REAL NOT NULL)''')
                    with identity.db:
                        identity.db.execute('INSERT INTO trial_company_parameters VALUES (?,?) ON CONFLICT(tenant_id) DO UPDATE SET applied=excluded.applied', (tenant, self.clock()))
            handle = Handle(secrets.token_urlsafe(32), tenant, backend)
            self.validate(handle, identity)
            grant = secrets.token_urlsafe(32)
            with self.lock:
                self.grants = {k:v for k,v in self.grants.items() if v[1] > self.clock()}
                stale = [k for k,h in self.handles.items() if h.backend.claims['account_id'] == backend.claims['account_id'] and h.tenant == tenant]
                for key in stale:
                    self.handles[key].active = False
                    del self.handles[key]
                if len(self.handles) >= 64:
                    raise IdentityError('Capacidad local de sesiones alcanzada.')
                self.handles[digest(handle.token)] = handle
                self.grants[digest(grant)] = (handle, self.clock() + 60)
            return {'launch_url': server.origin + '/__launch', 'grant': grant, 'expires_in': 60, 'public_access': False}
        finally:
            identity.close()

    def consume(self, grant, tenant):
        if not isinstance(grant, str) or not 32 <= len(grant) <= 128:
            raise IdentityError('Entrada inválida.')
        with self.lock:
            result = self.grants.get(digest(grant))
            if not result or result[1] <= self.clock() or result[0].tenant != tenant:
                raise IdentityError('Entrada inválida o vencida.')
            del self.grants[digest(grant)]
        identity = self.identity()
        try:
            self.validate(result[0], identity)
            return result[0]
        finally:
            identity.close()

    def lookup(self, token, tenant):
        if not isinstance(token, str) or len(token) > 128:
            raise IdentityError('Sesión inválida.')
        with self.lock:
            handle = self.handles.get(digest(token))
        if not handle or handle.tenant != tenant:
            raise IdentityError('Sesión inválida.')
        return handle

    def forward(self, handle, method, path, headers, body):
        path = checked_path(path)
        if len(body) > MAX_BODY:
            raise ValueError('Archivo demasiado grande para el laboratorio.')
        identity = self.identity()
        try:
            with handle.lock:
                self.validate(handle, identity)
                # Backend is pinned by the owned snapshot, never a browser parameter.
                upstream = handle.backend.base
                clean = {k:v for k,v in headers.items() if k.lower() in SAFE_REQUEST_HEADERS and '\r' not in v and '\n' not in v and len(v) <= 2048}
                clean['Accept-Encoding'] = 'identity'
                request = urllib.request.Request(upstream + path, data=body if method not in ('GET','HEAD') else None, headers=clean, method=method)
                try:
                    response = handle.backend.opener.open(request, timeout=60)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    content = response.read(MAX_RESPONSE + 1)
                    if len(content) > MAX_RESPONSE:
                        raise ValueError('Respuesta demasiado grande para el laboratorio.')
                    result_headers = [(k,v) for k,v in response.headers.items() if k.lower() in SAFE_RESPONSE_HEADERS]
                    location = response.headers.get('Location')
                    if location:
                        target = urllib.parse.urlsplit(urllib.parse.urljoin(upstream + '/', location))
                        base = urllib.parse.urlsplit(upstream)
                        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
                            raise IdentityError('Redirección externa bloqueada.')
                        result_headers.append(('Location', target.path + ('?' + target.query if target.query else '') + ('#' + target.fragment if target.fragment else '')))
                    # Do not release bytes if access changed while Odoo was responding.
                    self.validate(handle, identity)
                    return response.status, result_headers, content
        finally:
            identity.close()

    def close(self):
        self.stopping.set()
        with self.lock:
            for handle in self.handles.values():
                handle.active = False
            self.grants.clear()
        for server in list(self.servers.values()):
            server.shutdown()
            server.server_close()


class TenantServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, manager, tenant):
        self.manager, self.tenant = manager, tenant
        super().__init__(('127.0.0.1', 0), GatewayHandler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)
        self.cookie = 'uno360x_space_' + tenant


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'UNO360XGatewayLocal'

    def log_message(self, *args):
        pass

    def reply(self, status, body=b'', headers=()):
        self.send_response(status)
        self.send_header('Connection','close')
        self.close_connection=True
        for key,value in headers:
            self.send_header(key, value)
        if self.path=='/__launch' and status==303 and getattr(self.server,'secure_cookie',''):
            self.send_header('Clear-Site-Data','"cache", "storage"')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Content-Security-Policy', "frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def cookie_handle(self):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie',''))
        except Exception:
            raise IdentityError('Sesión inválida.') from None
        token = jar[self.server.cookie].value if self.server.cookie in jar else ''
        return self.server.manager.lookup(token, self.server.tenant)

    def dispatch(self):
        authority = getattr(self.server, 'authority', '127.0.0.1:' + str(self.server.server_port))
        if self.headers.get('Host') != authority:
            self.reply(403);return
        origin = self.headers.get('Origin')
        if self.path == '/__launch' and self.command == 'POST':
            if origin != getattr(self.server, 'central_origin', CENTRAL_ORIGIN) or self.headers.get('Content-Type','').split(';')[0] != 'application/x-www-form-urlencoded':
                self.reply(403);return
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 1 <= size <= 2048 or self.headers.get('Transfer-Encoding'):
                    raise ValueError()
                data = urllib.parse.parse_qs(self.rfile.read(size).decode(), strict_parsing=True)
                if set(data) != {'grant'} or len(data['grant']) != 1:
                    raise ValueError()
                handle = self.server.manager.consume(data['grant'][0], self.server.tenant)
                self.reply(303, headers=[('Location','/odoo'),('Set-Cookie',f'{self.server.cookie}={handle.token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{getattr(self.server, "secure_cookie", "")}')])
            except (ValueError, IdentityError):
                self.reply(403)
            return
        if (origin and origin != self.server.origin) or (self.command not in ('GET','HEAD') and origin != self.server.origin):
            self.reply(403);return
        try:
            handle = self.cookie_handle()
            if urllib.parse.urlsplit(self.path).path == '/web/service-worker.js' and self.command in ('GET','HEAD'):
                identity = self.server.manager.identity()
                try:
                    self.server.manager.validate(handle, identity)
                finally:
                    identity.close()
                # Pass-through worker: no caches, no fetch interception, no offline data.
                script = b"self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));"
                self.reply(200,script,[('Content-Type','text/javascript; charset=utf-8'),('Service-Worker-Allowed','/')]);return
            if self.path.startswith('/web/session/logout'):
                identity = self.server.manager.identity()
                try:
                    self.server.manager.validate(handle, identity)
                    identity.logout(handle.backend.central_session)
                    handle.active = False
                finally:
                    identity.close()
                self.reply(303, headers=[('Location', getattr(self.server, 'central_origin', CENTRAL_ORIGIN) + '/web/login'), ('Set-Cookie',f'{self.server.cookie}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{getattr(self.server, "secure_cookie", "")}')]);return
            if self.headers.get('Upgrade','').lower() == 'websocket':
                self.websocket(handle);return
            if self.headers.get('Transfer-Encoding'):
                self.reply(400);return
            size = int(self.headers.get('Content-Length','0'))
            if not 0 <= size <= MAX_BODY:
                self.reply(413);return
            body = self.rfile.read(size) if size else b''
            status,headers,body = self.server.manager.forward(handle,self.command,self.path,dict(self.headers),body)
            self.reply(status, body, headers)
        except IdentityError:
            message = b'<!doctype html><html lang="es"><meta charset="utf-8"><title>Acceso UNO360X</title><h1>Vuelve a iniciar sesi\xc3\xb3n</h1><p>El acceso a esta empresa ya no est\xc3\xa1 disponible.</p><a href="http://127.0.0.1:18072/web/login">Ir a UNO360X</a></html>'
            message=message.replace(b'http://127.0.0.1:18072',getattr(self.server,'central_origin',CENTRAL_ORIGIN).encode())
            self.reply(401, message, [('Content-Type','text/html; charset=utf-8')])
        except (ValueError, OSError, urllib.error.URLError):
            self.reply(502, b'La empresa no responde. Vuelve a intentarlo.', [('Content-Type','text/plain; charset=utf-8')])

    def websocket(self, handle):
        if self.headers.get('Origin') != self.server.origin or urllib.parse.urlsplit(self.path).path != '/websocket':
            self.reply(403);return
        key = self.headers.get('Sec-WebSocket-Key','')
        if not re.fullmatch('[A-Za-z0-9+/]{22}==', key) or self.headers.get('Sec-WebSocket-Version') != '13' or not handle.sockets.acquire(blocking=False):
            self.reply(400);return
        identity = self.server.manager.identity();upstream = None
        try:
            self.server.manager.validate(handle,identity)
            target = urllib.parse.urlsplit(handle.backend.base)
            request = urllib.request.Request(handle.backend.base + self.path)
            with handle.lock:
                for handler in handle.backend.opener.handlers:
                    if isinstance(handler, urllib.request.HTTPCookieProcessor):
                        handler.cookiejar.add_cookie_header(request)
            cookie = request.get_header('Cookie','')
            upstream = socket.create_connection((target.hostname,target.port or 80), timeout=5)
            wire = f'GET {self.path} HTTP/1.1\r\nHost: {target.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nOrigin: {handle.backend.base}\r\nCookie: {cookie}\r\n\r\n'
            upstream.sendall(wire.encode())
            handshake = b''
            while b'\r\n\r\n' not in handshake and len(handshake) <= 16384:
                part = upstream.recv(4096)
                if not part:
                    break
                handshake += part
            head,_,tail = handshake.partition(b'\r\n\r\n')
            rows = head.decode('iso-8859-1').split('\r\n')
            if not rows or not re.match(r'HTTP/1\.[01] 101 ', rows[0]):
                self.reply(503);return
            headers = dict(row.split(': ',1) for row in rows[1:] if ': ' in row)
            accept = next((v for k,v in headers.items() if k.lower() == 'sec-websocket-accept'), '')
            expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if accept!=expected:
                self.reply(502);return
            self.server.manager.validate(handle,identity)
            self.send_response(101)
            self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade');self.send_header('Sec-WebSocket-Accept',accept);self.end_headers()
            if tail:
                self.connection.sendall(tail)
            upstream.settimeout(5);self.connection.settimeout(5)
            while not self.server.manager.stopping.is_set():
                self.server.manager.validate(handle,identity)
                ready,_,_=select.select([self.connection,upstream],[],[],1)
                for source in ready:
                    data=source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.connection else self.connection).sendall(data)
        except (IdentityError,OSError,ValueError):
            pass
        finally:
            if upstream:
                upstream.close()
            identity.close();handle.sockets.release();self.close_connection=True

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_PATCH = dispatch
    do_DELETE = dispatch
    do_OPTIONS = dispatch
