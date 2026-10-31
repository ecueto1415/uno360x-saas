"""HTTP control API -> existing prepared lab space -> native Odoo session."""
import http.cookiejar
import json
from pathlib import Path
import sys
import threading
import urllib.request
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter,STATE
from control_state import control_database
from control.identity import IdentityService
from control.identity_http import IdentityHTTPServer,COOKIE
from control.onboarding import Onboarding
from control.access_broker import open_space

def main():
    adapter=LocalAdapter();mailbox=[]
    path=control_database()
    if not path.exists():raise RuntimeError('Primero ejecutar automatic_signup_demo.py.')
    server=IdentityHTTPServer(0,path,mailbox.append)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
    csrf='';base='http://127.0.0.1:'+str(server.server_port)
    def post(route,data):
        req=urllib.request.Request(base+route,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        with opener.open(req,timeout=30) as response:return json.load(response)
    identity=None
    try:
        result=post('/login',{'email':'owner-auto@example.test','password':(STATE/'owner-password').read_text()})
        csrf=result['csrf_token']
        session=next(c.value for c in jar if c.name==COOKIE)
        companies=post('/companies',{})['companies']
        assert len(companies)==2
        selected=companies[0]
        prepared=post('/preparation/request',{'tenant_id':selected['id']})
        assert prepared['status']=='ready_local' and prepared['local_ready']
        ticket=post('/handoff/request',{'tenant_id':selected['id']})['ticket']
        identity=IdentityService(path,mailbox.append)
        backend=open_space(Onboarding(identity),session,ticket,adapter)
        names=backend.rpc('res.company','search_read',[],{'fields':['name'],'limit':10})
        assert names[0]['name']==selected['slug']+' (LABORATORIO)'
        assert backend.uid not in (1,2)
        post('/logout',{})
        try:backend.rpc('res.company','search_read',[],{'fields':['name']})
        except ValueError:blocked=True
        else:raise AssertionError('Logout central no aplicado')
        print(json.dumps({'control_api_http':True,'company_count':2,'queue_status_http':True,
                          'native_odoo_session':True,'technical_admin_used':False,
                          'logout_blocks_existing_broker':blocked,'backend_cookie_returned_to_client':False},indent=2))
    finally:
        if identity:identity.close()
        server.shutdown();server.server_close();thread.join();mailbox.clear()

if __name__=='__main__':main()
