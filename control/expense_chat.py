"""Fixed user-session RPCs. Tenant is taken only from the validated handle."""
import hashlib
import hmac
import json
import urllib.request
from .identity import IdentityError
from support_center.expense_processor import process

PATH='/__expenses'


def csrf(handle):
    return hmac.new(handle.token.encode(),b'uno360x-expense-only-v1',hashlib.sha256).hexdigest()


def rpc(manager, handle, method, args=None):
    if method not in {'capture_options','capture_draft','capture_history'}:
        raise ValueError('Operación no disponible.')
    identity=manager.identity()
    try:
        manager.validate(handle,identity)
        body=json.dumps({'jsonrpc':'2.0','method':'call','id':1,'params':{
            'model':'uno360x.expense.capture','method':method,'args':args or [],'kwargs':{}}}).encode()
        request=urllib.request.Request(handle.backend.base+'/web/dataset/call_kw/uno360x.expense.capture/'+method,
            data=body,headers={'Content-Type':'application/json','X-UNO360X-Bridge':'1'})
        with handle.lock:
            with handle.backend.opener.open(request,timeout=20) as response:
                raw=response.read(65537)
        manager.validate(handle,identity)
        if len(raw)>65536:raise ValueError('Respuesta demasiado grande.')
        value=json.loads(raw)
        if 'error' in value:
            error=value['error'].get('data',{})
            if str(error.get('name','')).endswith(('UserError','ValidationError')):
                raise ValueError(str(error.get('message') or 'Revisa los datos del gasto.')[:400])
            raise ValueError('Se requiere permiso de contabilidad para registrar gastos.')
        return value['result']
    finally:
        identity.close()


def submit(manager,handle,data,processor=process):
    if not isinstance(data,dict) or set(data)!={'filename','image','message'}:
        raise ValueError('Solicitud inválida.')
    if (not isinstance(data['filename'],str) or len(data['filename'])>200 or
        not isinstance(data['image'],str) or len(data['image'])>2700000 or
        not isinstance(data['message'],str) or len(data['message'])>2000):
        raise ValueError('Adjunta una foto de hasta 2 MB y un mensaje corto.')
    options=rpc(manager,handle,'capture_options')
    if not options.get('enabled') or options.get('user_id')!=handle.backend.uid:
        raise ValueError('Permiso de contabilidad no disponible.')
    extracted=processor(dict(data,options=options))
    if extracted['faltantes']:
        return {'reply':'Necesito que confirmes: '+', '.join(str(s) for s in extracted['faltantes'])+
                '. Añade el dato al mensaje y vuelve a preparar con la misma foto.',
                'history':rpc(manager,handle,'capture_history')}
    # Revalidates membership/session after OCR/AI and before the only write.
    draft=rpc(manager,handle,'capture_draft',[data['filename'],data['image'],extracted['datos']])
    if draft.get('status') in ('draft','existing'):
        return {'reply':('Ese gasto ya existe; no lo dupliqué.' if draft['status']=='existing' else
            'Preparé el gasto en borrador y adjunté la foto original.')+
            '\nComprobante: '+str(draft['comprobante'])+'\nTotal: '+str(draft['moneda'])+' '+str(draft['total'])+
            '\n'+str(draft.get('pendientes',''))+'\nContabilidad debe revisarlo antes de confirmar.',
            'draft':draft,'history':rpc(manager,handle,'capture_history')}
    return {'reply':('No pude identificar un proveedor único con ese RNC. Contabilidad debe revisar o crear el proveedor.'
        if draft.get('status')=='needs_supplier' else
        'Falta completar: '+', '.join(draft.get('faltan',[]))), 'history':rpc(manager,handle,'capture_history')}


def dispatch(handler,handle,url):
    def reply(status,value):
        handler.reply(status,json.dumps(value,ensure_ascii=False).encode(),
                      [('Content-Type','application/json; charset=utf-8'),('Cache-Control','no-store')])
    try:
        if url.path!=PATH or url.query:raise ValueError('Ruta inválida.')
        if handler.command=='GET':
            options=rpc(handler.server.manager,handle,'capture_options')
            reply(200,{'enabled':True,'csrf_token':csrf(handle),
                       'history':rpc(handler.server.manager,handle,'capture_history')});return
        if handler.command!='POST':reply(405,{'error':'Método no permitido.'});return
        if not hmac.compare_digest(handler.headers.get('X-CSRF-Token',''),csrf(handle)):
            reply(403,{'error':'Solicitud no autorizada.'});return
        if handler.headers.get('Content-Type','').split(';')[0]!='application/json' or handler.headers.get('Transfer-Encoding'):
            raise ValueError('Solicitud inválida.')
        size=int(handler.headers.get('Content-Length','0'))
        if not 1<=size<=2800000:raise ValueError('Foto demasiado grande.')
        data=json.loads(handler.rfile.read(size))
        reply(200,submit(handler.server.manager,handle,data))
    except IdentityError:
        reply(401,{'error':'Vuelve a iniciar sesión para continuar.'})
    except (ValueError,TypeError) as error:
        reply(400,{'error':str(error)[:400]})
    except Exception:
        reply(503,{'error':'No se pudo completar. Revisa tus gastos preparados antes de reintentar.'})
