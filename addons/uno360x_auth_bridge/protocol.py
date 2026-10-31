"""Short-lived per-instance HMAC assertion. No passwords or public redirects."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time


def mint(key, tenant_id, account_id, clock=time.time):
    now=int(clock())
    payload={'aud':tenant_id,'sub':account_id,'login':'saas_'+account_id,
             'jti':secrets.token_hex(16),'iat':now,'exp':now+30}
    raw=base64.urlsafe_b64encode(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).rstrip(b'=')
    signature=hmac.new(key,raw,hashlib.sha256).hexdigest()
    return raw.decode()+'.'+signature


def verify(key, token, tenant_id, login, clock=time.time):
    if not isinstance(token,str) or len(token)>4096 or len(key)!=32:
        raise ValueError('Invalid assertion')
    try:
        raw,signature=token.split('.')
        expected=hmac.new(key,raw.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):raise ValueError()
        data=json.loads(base64.b64decode(raw+'='*(-len(raw)%4),altchars=b'-_',validate=True))
        if not isinstance(data,dict) or set(data)!={'aud','sub','login','jti','iat','exp'}:raise ValueError()
        if data['aud']!=tenant_id or data['login']!=login or data['login']!='saas_'+data['sub']:raise ValueError()
        if not all(isinstance(data[x],str) and re.fullmatch('[a-f0-9]{32}',data[x]) for x in ('aud','sub','jti')):raise ValueError()
        if type(data['iat']) is not int or type(data['exp']) is not int:raise ValueError()
        now=clock()
        if not data['iat']<=now+5 or not now<data['exp'] or not 0<data['exp']-data['iat']<=60 or data['iat']<now-60:raise ValueError()
        return data
    except (ValueError,TypeError,KeyError,UnicodeError):
        raise ValueError('Invalid assertion') from None
