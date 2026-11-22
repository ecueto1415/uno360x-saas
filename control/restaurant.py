"""Authenticated SaaS restaurant pilot; only the gateway signs tenant/user claims.

No native OUTSOLUTECH route, no fiscal transport, no arbitrary upstream URLs.
"""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
import threading
from .identity import IdentityError
from .access_broker import _rpc

PATH='/uno360x-restaurante'
KEY=Path('/var/lib/uno360x-saas/restaurant/proxy.key')
UPSTREAM='http://127.0.0.1:18248'
_staff_cache={}
_cache_lock=threading.Lock()

def rpc(handle,model,method,args,kwargs=None):
    if model!='res.users' or method not in ('has_group','read','search_read'):
        raise IdentityError('Operación de POS no autorizada.')
    with handle.lock:
        # BackendSession owns a SQLite connection on its original login thread.
        # Revalidate through a fresh manager identity, then reuse only the fixed
        # Odoo opener/base; never reuse that thread-bound connection here.
        return _rpc(handle.backend.opener,handle.backend.base,'/web/dataset/call_kw/'+model+'/'+method,
                    {'model':model,'method':method,'args':args,'kwargs':kwargs or {}})

def claims(manager,handle):
    identity=manager.identity()
    try:manager.validate(handle,identity)
    finally:identity.close()
    uid=handle.backend.uid
    can_use=rpc(handle,'res.users','has_group',[[uid],'point_of_sale.group_pos_user'])
    if not can_use:raise IdentityError('No tienes permiso de Punto de venta.')
    supervisor=rpc(handle,'res.users','has_group',[[uid],'point_of_sale.group_pos_manager'])
    user=rpc(handle,'res.users','read',[[uid]],{'fields':['name','company_id']})[0]
    company=user['company_id'][0]
    cache_key=(handle.tenant,company)
    with _cache_lock:cached=_staff_cache.get(cache_key)
    people=cached[1] if cached and cached[0]>time.monotonic() else None
    if people is None:
        staff=rpc(handle,'res.users','search_read',[[('active','=',True),('share','=',False),('company_ids','in',[company])]],{'fields':['id','name'],'limit':50,'order':'name'})
        people=[{'id':str(p['id']),'name':p['name']} for p in staff
                if rpc(handle,'res.users','has_group',[[p['id']],'point_of_sale.group_pos_user'])]
        with _cache_lock:_staff_cache[cache_key]=(time.monotonic()+30,people)
    if not any(p['id']==str(uid) for p in people):people=people[:49]+[{'id':str(uid),'name':user['name']}]
    identity=manager.identity()
    try:manager.validate(handle,identity)
    finally:identity.close()
    return {'scope':handle.tenant+':company-'+str(company),'account':str(uid),'displayName':user['name'],
            'branchName':user['company_id'][1],'role':'supervisor' if supervisor else 'caja','staff':people}

def dispatch(handler,handle,url):
    try:
        if url.path==PATH:
            handler.reply(303,headers=[('Location',PATH+'/')]);return
        route=url.path[len(PATH):]
        allowed={'/','/app.mjs','/domain.mjs','/style.css','/images/burger.jpg','/images/wings.jpg','/images/mojito.jpg','/api/state','/api/command'}
        if route not in allowed or url.query:
            handler.reply(404);return
        if handler.command not in ('GET','HEAD','POST') or (handler.command=='POST')!=(route=='/api/command'):
            handler.reply(405);return
        body=b''
        if handler.command=='POST':
            if handler.headers.get('Transfer-Encoding') or handler.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Formato no permitido.')
            size=int(handler.headers.get('Content-Length','0'))
            if not 1<=size<=850000:raise ValueError('Solicitud demasiado grande.')
            body=handler.rfile.read(size)
            if len(body)!=size:raise ValueError('Solicitud incompleta.')
        if route not in ('/api/state','/api/command'):
            identity=handler.server.manager.identity()
            try:handler.server.manager.validate(handle,identity)
            finally:identity.close()
            value={'scope':handle.tenant+':company-0','account':str(handle.backend.uid),'role':'caja','staff':[]}
        else:value=claims(handler.server.manager,handle)
        value.update(exp=time.time()+45,method=handler.command,path=route,bodyHash=hashlib.sha256(body).hexdigest())
        payload=base64.urlsafe_b64encode(json.dumps(value,ensure_ascii=False).encode()).rstrip(b'=').decode()
        signature=hmac.new(KEY.read_text().strip().encode(),payload.encode(),hashlib.sha256).hexdigest()
        req=urllib.request.Request(UPSTREAM+route,data=body if handler.command=='POST' else None,method=handler.command,
            headers={'X-UNO-POS-Proof':payload+'.'+signature,'Content-Type':'application/json'})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:response=opener.open(req,timeout=20)
        except urllib.error.HTTPError as error:response=error
        with response:
            result=response.read(4*1024*1024+1)
            if len(result)>4*1024*1024:raise ValueError('Respuesta demasiado grande.')
            mime=response.headers.get('Content-Type','application/octet-stream')
            if route=='/' and response.status==200:
                result=result.replace(b'<a class="brand" href="/">',b'<a class="brand" href="/uno360x-pos">')
            handler.reply(response.status,result,[('Content-Type',mime)])
    except IdentityError:
        handler.reply(403,b'Acceso de Punto de venta no autorizado.',[('Content-Type','text/plain; charset=utf-8')])
    except (ValueError,OSError,urllib.error.URLError,KeyError,IndexError,TypeError):
        handler.reply(503,b'El POS no pudo completar la solicitud. Conserva el pedido y vuelve a intentar.',[('Content-Type','text/plain; charset=utf-8')])

def decorate(path,status,headers,body):
    if path.split('?')[0]!='/uno360x-pos' or status!=200 or not KEY.is_file():return status,headers,body
    if not any(k.lower()=='content-type' and 'text/html' in v for k,v in headers):return status,headers,body
    button=b'<section class="ux-card"><h2>Restaurantes y bares</h2><p>Mesas, Cocina, Barra y caja. Piloto en pruebas: sin emision a DGII.</p><a class="ux-button" href="/uno360x-restaurante/">Restaurante</a></section>'
    if b'/uno360x-restaurante/' not in body:body=body.replace(b'</main>',button+b'</main>',1)
    return status,headers,body
