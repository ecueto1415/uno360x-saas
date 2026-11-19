"""Support gateway: validated central identity, origin protection, no user-selected tenant."""
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import parse_qs
from support_center.store import Store, Invalid, Limited, area_for

PATH='/__support'
ASSETS=Path(__file__).resolve().parents[1]/'support_center'/'web'

def token_for(handle):
    return hmac.new(handle.token.encode(),b'uno360x-support-only-v1',hashlib.sha256).hexdigest()

def dispatch(handler,handle,url):
    identity=handler.server.manager.identity()
    store=None
    def reply(status,value):
        handler.reply(status,json.dumps(value,ensure_ascii=False).encode(),[('Content-Type','application/json; charset=utf-8')])
    try:
        handler.server.manager.validate(handle,identity)
        if url.path in (PATH+'/chat.js',PATH+'/chat.css') and handler.command in ('GET','HEAD'):
            name=url.path.rsplit('/',1)[1]
            handler.reply(200,(ASSETS/name).read_bytes(),[('Content-Type','application/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8')])
            return
        if url.path!=PATH:
            reply(404,{'error':'Ruta no disponible.'});return
        tenant,account=handle.tenant,handle.backend.claims['account_id']
        store=Store()
        if handler.command=='GET':
            params=parse_qs(url.query,keep_blank_values=True)
            if set(params)-{'case_id'} or any(len(v)!=1 for v in params.values()):
                raise Invalid('Solicitud inválida.')
            value=store.listing(tenant,account,params.get('case_id',[None])[0])
            reply(200,dict(value,csrf_token=token_for(handle)));return
        if handler.command!='POST':
            reply(405,{'error':'Método no permitido.'});return
        if not hmac.compare_digest(handler.headers.get('X-CSRF-Token',''),token_for(handle)):
            reply(403,{'error':'Solicitud no autorizada.'});return
        if handler.headers.get('Content-Type','').split(';')[0]!='application/json' or handler.headers.get('Transfer-Encoding'):
            raise Invalid('Solicitud inválida.')
        try:
            size=int(handler.headers.get('Content-Length','0'))
            if not 1<=size<=14000:
                raise ValueError()
            data=json.loads(handler.rfile.read(size))
            if not isinstance(data,dict):
                raise ValueError()
        except (ValueError,TypeError):
            raise Invalid('Solicitud inválida.') from None
        if set(data)=={'case_id','resume'} and data['resume'] is True:
            from .support_context import capture
            store.case(tenant,account,data['case_id'])
            store.resume_ai(tenant,account,data['case_id'],capture(handler.server.manager,handle))
            case_id=data['case_id']
        elif set(data)=={'case_id','handoff'} and data['handoff'] is True:
            store.handoff(tenant,account,data['case_id']);case_id=data['case_id']
        else:
            from .support_context import capture
            # Human-only messages need no AI context and do not perform an Odoo read.
            context=capture(handler.server.manager,handle) if store.needs_context(tenant,account,data) else None
            case_id=store.send(tenant,account,data,context=context)
        reply(200,dict(store.listing(tenant,account,case_id),csrf_token=token_for(handle)))
    except Limited as error:
        reply(429,{'error':str(error)})
    except Invalid as error:
        reply(400,{'error':str(error)})
    finally:
        identity.close()
        if store:
            store.close()

def decorate(path,status,headers,body):
    route=path.split('?',1)[0]
    if (status==200 and (route.startswith(('/uno360x-','/uno360x/')) or route in ('/web','/odoo') or route.startswith('/odoo/'))
        and any(k.lower()=='content-type' and v.startswith('text/html') for k,v in headers)
        and b'</body>' in body and b'id="uno-support-loader"' not in body):
        addition=b'<link rel="stylesheet" href="/__support/chat.css?v=1"><script id="uno-support-loader" defer src="/__support/chat.js?v=1"></script>'
        body=body.replace(b'</body>',addition+b'</body>',1)
        headers=[(k,v) for k,v in headers if k.lower() not in ('etag','last-modified','content-length')]
    return status,headers,body

def record(handle,path,status,milliseconds):
    # Telemetry failure must never stop invoicing or other customer activity.
    if area_for(path) is None:
        return
    try:
        store=Store(timeout=.025)
        try:
            store.record_metric(handle.tenant,path,status,milliseconds)
        finally:
            store.close()
    except Exception:
        pass
