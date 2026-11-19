"""Short-lived email challenges for the public SaaS login."""
import hmac
import re
import secrets
import threading
import time

from .identity import digest, IdentityError

TTL = 600


class EmailChallenges:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.pending = {}

    @staticmethod
    def signature(token, code):
        return hmac.digest(token.encode(), code.encode(), 'sha256')

    def issue(self, account, deliver):
        token = secrets.token_urlsafe(32)
        code = f'{secrets.randbelow(1_000_000):06d}'
        key = digest(token)
        now = self.clock()
        with self.lock:
            self.pending = {k: v for k, v in self.pending.items() if v[0] > now}
            if len(self.pending) >= 512:
                raise RuntimeError('Login challenge capacity reached')
            self.pending[key] = (now+TTL, self.signature(token, code), 0, account)
        try:
            deliver({'purpose': 'login_code', 'email': account['email'], 'code': code})
        except Exception:
            with self.lock:
                self.pending.pop(key, None)
            raise
        return token

    def current(self, token):
        with self.lock:
            entry = self.pending.get(digest(token)) if token else None
            return entry[3] if entry and entry[0] > self.clock() else None

    def consume(self, token, code):
        if not isinstance(token, str) or not 1 <= len(token) <= 128:
            raise IdentityError('El código venció. Vuelve a iniciar sesión.')
        if not isinstance(code, str) or not re.fullmatch('[0-9]{6}', code):
            raise IdentityError('Escribe un código de seis dígitos.')
        key = digest(token)
        with self.lock:
            entry = self.pending.get(key)
            if not entry or entry[0] <= self.clock():
                self.pending.pop(key, None)
                raise IdentityError('El código venció. Vuelve a iniciar sesión.')
            expires, expected, attempts, account = entry
            if hmac.compare_digest(expected, self.signature(token, code)):
                del self.pending[key]
                return account
            if attempts >= 4:
                del self.pending[key]
                raise IdentityError('Se agotaron los intentos. Vuelve a iniciar sesión.')
            self.pending[key] = (expires, expected, attempts+1, account)
        raise IdentityError('Código incorrecto.')
