"""Subscription pages on the trusted SaaS gateway; never routed to native OUTSOLUTECH."""
import hashlib
import hmac
import re
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import parse_qs

from .subscription_store import Subscription, BillingInvalid, MAX_PROOF
from .subscription_views import PATH, ASSET, screen, embed, link
from . import team_access, support

STYLE=Path(__file__).with_name('subscription.css')

def token(handle):return hmac.new(handle.token.encode(),b'uno360x-subscription-v1',hashlib.sha256).hexdigest()

def form(handler):
    if handler.headers.get('Transfer-Encoding'):raise BillingInvalid('Solicitud no válida.')
    try:size=int(handler.headers.get('Content-Length','0'))
    except ValueError:raise BillingInvalid('Solicitud no válida.') from None
    if not 1<=size<=MAX_PROOF+16384:raise BillingInvalid('La solicitud supera el límite permitido.')
    kind=handler.headers.get('Content-Type','')
    raw=handler.rfile.read(size)
    if len(raw)!=size:raise BillingInvalid('No se recibió la solicitud completa.')
    if kind.split(';')[0]=='application/x-www-form-urlencoded':
        data=parse_qs(raw.decode(),strict_parsing=True,keep_blank_values=True,max_num_fields=8)
        if any(len(v)!=1 for v in data.values()):raise BillingInvalid('Solicitud no válida.')
        return {k:v[0] for k,v in data.items()}
    if kind.split(';')[0]!='multipart/form-data' or '\r' in kind or '\n' in kind:raise BillingInvalid('Formato no permitido.')
    msg=BytesParser(policy=default).parsebytes(('Content-Type: '+kind+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
    if not msg.is_multipart():raise BillingInvalid('Adjunto no válido.')
    data={}
    for part in msg.iter_parts():
        name=part.get_param('name',header='content-disposition')
        if name not in {'csrf','operation','request_id','invoice','reference','proof'} or name in data or part.is_multipart():raise BillingInvalid('Solicitud no válida.')
        value=part.get_payload(decode=True)
        if value is None:raise BillingInvalid('Adjunto no válido.')
        if name!='proof' and len(value)>512:raise BillingInvalid('Campo demasiado largo.')
        data[name]=value if name=='proof' else value.decode('utf-8')
    return data

def dispatch(handler,handle,url):
    manager=handler.server.manager;identity=manager.identity();ledger=Subscription(identity)
    try:
        manager.validate(handle,identity)
        try:ledger.authorize(handle.backend.central_session,handle.tenant)
        except PermissionError:
            handler.reply(403,'Solo el administrador de esta empresa puede gestionar la suscripción.'.encode(),[('Content-Type','text/plain; charset=utf-8')]);return
        if url.path==ASSET+'/style.css' and handler.command in ('GET','HEAD'):
            handler.reply(200,STYLE.read_bytes(),[('Content-Type','text/css; charset=utf-8')]);return
        if url.path!=PATH:handler.reply(404);return
        params=parse_qs(url.query,keep_blank_values=True,max_num_fields=8)
        if set(params)-{'tab','year','state','q','pdf','saved'} or any(len(v)!=1 for v in params.values()):raise BillingInvalid('Solicitud no válida.')
        tab=params.get('tab',['summary'])[0]
        if tab not in ('summary','payment','history'):raise BillingInvalid('Sección no disponible.')
        # Schema is installed at release time, never by an unauthorized request.
        notice=''
        if handler.command=='POST':
            values=form(handler)
            if not hmac.compare_digest(values.get('csrf',''),token(handle)):
                handler.reply(403);return
            if values.get('operation')=='preferences' and set(values)=={'csrf','operation','method','email'}:
                ledger.preferences(handle.backend.central_session,handle.tenant,values['method'],values['email']);saved='preferences'
            elif values.get('operation')=='transfer' and set(values)=={'csrf','operation','request_id','invoice','reference','proof'}:
                ledger.report_transfer(handle.backend.central_session,handle.tenant,values['invoice'],values['reference'],values['proof'],values['request_id']);saved='transfer'
            else:raise BillingInvalid('Solicitud no válida.')
            handler.reply(303,headers=[('Location',link(tab='payment',saved=saved))]);return
        if handler.command not in ('GET','HEAD'):handler.reply(405);return
        if 'pdf' in params:
            row=ledger.invoice(handle.backend.central_session,handle.tenant,params['pdf'][0])
            filename=re.sub('[^A-Za-z0-9_-]','_',row['number'])[:90]+'.pdf'
            handler.reply(200,row['pdf'],[('Content-Type','application/pdf'),('Content-Disposition','attachment; filename="'+filename+'"'),('X-Content-Type-Options','nosniff')]);return
        if params.get('saved')==['preferences']:notice='Método de pago y correo de facturación guardados. No se realizó ningún cargo.'
        if params.get('saved')==['transfer']:notice='Comprobante recibido. El pago está pendiente de verificación.'
        data=ledger.overview(handle.backend.central_session,handle.tenant)
        year,state,query=[params.get(k,[''])[0] for k in ('year','state','q')]
        records=ledger.invoices(handle.backend.central_session,handle.tenant,year,state,query)
        content=screen(data,records,token(handle),tab,notice,year,state,query)
        status,headers,workspace=manager.forward(handle,'GET','/uno360x-aplicaciones',dict(handler.headers),b'')
        if status!=200:raise BillingInvalid('No se pudo cargar el menú. Vuelve a intentarlo.')
        _,_,workspace=team_access.decorate(handle,PATH,200,headers,workspace)
        body=embed(workspace,content)
        _,_,body=support.decorate(PATH,200,[('Content-Type','text/html')],body)
        handler.reply(200,body,[('Content-Type','text/html; charset=utf-8')])
    except (BillingInvalid,ValueError,UnicodeError) as error:
        # No upstream financial data or internal details in errors.
        message=str(error) if isinstance(error,BillingInvalid) else 'Revisa los datos y vuelve a intentarlo.'
        from html import escape
        body=('<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Suscripción | UNO360X</title><h1>No se pudo guardar</h1><p>'+escape(message)+'</p><a href="'+link(tab='payment')+'">Volver a Suscripción</a></html>').encode()
        handler.reply(400,body,[('Content-Type','text/html; charset=utf-8')])
    finally:identity.close()
