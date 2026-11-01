"""Real local HTTP gateway/asset/RPC/websocket and revocation rehearsal."""
import base64
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import secrets
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter,STATE
from control_state import control_database
from tenants import protected
from control.access_broker import NoRedirect


def main():
    LocalAdapter();path=control_database();central='http://127.0.0.1:18072';email='trial-ui-20261101@example.test'
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}),NoRedirect())
    csrf=''
    def request(url,body=None,headers=None):
        req=urllib.request.Request(url,data=body,headers=headers or {})
        try:r=client.open(req,timeout=120)
        except urllib.error.HTTPError as error:r=error
        with r:return r.status,r.headers,r.read()
    def post(route,data):
        status,_,body=request(central+route,json.dumps(data).encode(),{'Content-Type':'application/json','X-CSRF-Token':csrf})
        if status!=200:raise RuntimeError('Falló solicitud del control: '+route)
        return json.loads(body)
    password=protected(STATE/'trial-ui-owner-password',secrets.token_urlsafe(32)).read_text()
    post('/reset/request',{'email':email})
    notice=json.loads((path.parent/'mailbox'/(hashlib.sha256(('reset:'+email).encode()).hexdigest()+'.json')).read_text())
    post('/reset/complete',{'token':notice['token'],'password':password})
    csrf=post('/login',{'email':email,'password':password})['csrf_token']
    company=post('/companies',{})['companies'][0];tid=company['id']
    launch=post('/spaces/open',{'tenant_id':tid})
    gateway=launch['launch_url'].removesuffix('/__launch')
    status,headers,_=request(launch['launch_url'],urllib.parse.urlencode({'grant':launch['grant']}).encode(),
                             {'Origin':central,'Content-Type':'application/x-www-form-urlencoded'})
    assert status==303 and headers['Location']=='/odoo'
    assert 'session_id=' not in headers['Set-Cookie']
    status,_,body=request(gateway+'/odoo');assert status==200
    html=body.decode();assets=list(dict.fromkeys(re.findall(r'(?:src|href)="(/web/assets/[^\"]+)',html)))
    assert assets
    for asset in assets:
        status,headers,body=request(gateway+asset);assert status==200 and body
        assert not headers.get('Set-Cookie')
    def rpc(route,params):
        status,headers,body=request(gateway+route,json.dumps({'jsonrpc':'2.0','method':'call','params':params,'id':1}).encode(),
                                    {'Origin':gateway,'Content-Type':'application/json'})
        assert status==200 and not headers.get('Set-Cookie')
        result=json.loads(body)
        if 'error' in result:raise RuntimeError('Odoo rechazó una comprobación del gateway.')
        return result['result']
    info=rpc('/web/session/get_session_info',{})
    assert info['uid'] not in (1,2) and not info.get('is_system',False)
    def model(name,method,args,kwargs):
        return rpc('/web/dataset/call_kw/'+name+'/'+method,dict(model=name,method=method,args=args,kwargs=kwargs))
    values=model('res.company','search_read',[],{'fields':['name','country_id','currency_id'],'limit':10})
    assert len(values)==1 and values[0]['name']=='Empresa Diseño de Prueba' and values[0]['currency_id'][1]=='DOP'
    country=model('res.country','read',[[values[0]['country_id'][0]]],{'fields':['code']});assert country[0]['code']=='DO'
    projects=model('project.project','search_read',[[['name','=','Validación gateway UNO360X']]],{'fields':['name']})
    assert len(projects)==1
    status,_,worker=request(gateway+'/web/service-worker.js');assert status==200 and b'caches' not in worker
    status,_,_=request(gateway+'/web/database/manager');assert status==401
    ws_target=urllib.parse.urlsplit(gateway)
    ws=socket.create_connection((ws_target.hostname,ws_target.port),timeout=5)
    try:
        key=base64.b64encode(secrets.token_bytes(16)).decode()
        cookie='; '.join(c.name+'='+c.value for c in jar if c.name=='uno360x_space_'+tid)
        version=info.get('websocket_worker_version')
        if not version:raise RuntimeError('No se obtuvo versión de websocket en sesión Odoo.')
        wire=f'GET /websocket?version={urllib.parse.quote(version)} HTTP/1.1\r\nHost: {ws_target.netloc}\r\nOrigin: {gateway}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nCookie: {cookie}\r\n\r\n'
        ws.sendall(wire.encode());response=b''
        while b'\r\n\r\n' not in response:
            chunk=ws.recv(4096)
            if not chunk:break
            response+=chunk
        assert response.startswith(b'HTTP/1.1 101'),response[:100]
        post('/logout',{})
        closed=False
        while True:
            chunk=ws.recv(65536)
            if not chunk:closed=True;break
        assert closed
    finally:ws.close()
    status,_,_=request(gateway+'/odoo');assert status==401
    report={'real_local_gateway':True,'native_webclient_html':True,'asset_files_verified':len(assets),
            'native_rpc':True,'ui_created_project_persisted':True,'company_country_currency_applied':True,
            'native_cookie_exposed':False,'websocket_handshake':True,'websocket_revoked_on_logout':True,
            'existing_http_cookie_revoked_on_logout':True,'technical_admin_used':False,'public_access':False,
            'real_mail_configured':False}
    (STATE/'gateway_verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
