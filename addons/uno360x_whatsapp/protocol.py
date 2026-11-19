"""Cloud API request preparation only. This module performs no network I/O."""
import hashlib
import hmac
import re


def phone(value):
    normalized=re.sub(r'[ ()-]', '', str(value or '').strip())
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', normalized):
        raise ValueError('Indica el número completo con código de país, por ejemplo +18095550101.')
    return normalized


def template_payload(recipient, template, language, parameters):
    recipient=phone(recipient)
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,511}', template or ''):
        raise ValueError('Nombre de plantilla inválido.')
    if language not in ('es','es_ES','es_MX','en_US'):
        raise ValueError('Idioma de plantilla no admitido.')
    if len(parameters)!=6 or any(not isinstance(p,str) or not p.strip() or len(p)>500 or any(c in p for c in '\r\n\x00') for p in parameters):
        raise ValueError('Parámetros de aviso inválidos.')
    return {'messaging_product':'whatsapp','recipient_type':'individual','to':recipient[1:],
            'type':'template','template':{'name':template,'language':{'code':language},
            'components':[{'type':'body','parameters':[{'type':'text','text':p} for p in parameters]}]}}


def verify_signature(body, header, app_secret):
    if not isinstance(body,bytes) or not isinstance(app_secret,bytes) or len(app_secret)<16:
        return False
    if not isinstance(header,str) or not re.fullmatch(r'sha256=[a-f0-9]{64}',header):
        return False
    expected='sha256='+hmac.new(app_secret,body,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,header)
