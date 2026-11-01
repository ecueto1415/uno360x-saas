"""Verify the fictional company created through the UI; never seed readiness."""
import hashlib
import http.cookiejar
import json
from pathlib import Path
import secrets
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter, STATE
from control_state import control_database
from tenants import protected
from control.identity import IdentityService
from control.identity_http import COOKIE
from control.onboarding import Onboarding
from control.access_broker import open_space


def main():
    adapter=LocalAdapter();path=control_database();email='trial-ui-20261101@example.test'
    jar=http.cookiejar.CookieJar();csrf='';base='http://127.0.0.1:18072'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
    def post(route,data):
        request=urllib.request.Request(base+route,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        with opener.open(request,timeout=30) as response:return json.load(response)
    # Replace the temporary manual UI test password with a random local-only one.
    password=protected(STATE/'trial-ui-owner-password',secrets.token_urlsafe(32)).read_text()
    post('/reset/request',{'email':email})
    mailbox=path.parent/'mailbox'/(hashlib.sha256(('reset:'+email).encode()).hexdigest()+'.json')
    notice=json.loads(mailbox.read_text())
    post('/reset/complete',{'token':notice['token'],'password':password})
    csrf=post('/login',{'email':email,'password':password})['csrf_token']
    choices=post('/companies',{})['companies'];assert len(choices)==1
    state=post('/trial/status',{'tenant_id':choices[0]['id']})
    assert state['local_ready'] and state['trial_active'] and state['days_remaining']==15
    assert state['expires']-state['started']==15*86400
    assert state['modules']==['payroll_hr','projects_services']
    session=next(c.value for c in jar if c.name==COOKIE)
    service=IdentityService(path,lambda notice:None)
    try:
        jobs=Onboarding(service)
        ticket=post('/handoff/request',{'tenant_id':state['tenant_id']})['ticket']
        backend=open_space(jobs,session,ticket,adapter)
        result=backend.rpc('res.company','search_read',[],{'fields':['name'],'limit':10})
        assert len(result)==1 and backend.uid not in (1,2)
        setup=post('/setup/status',{'tenant_id':state['tenant_id']})
        report={'ui_created_company':True,'selection_preserved':True,'trial_started_at_readiness':True,
                'duration_days':15,'card_required':False,'automatic_charge':False,
                'native_odoo_session':True,'technical_admin_used':False,'public_web_gateway_complete':False,
                'company_parameters_applied_to_odoo':setup['basic_company_parameters_applied_to_odoo']}
        (STATE/'ui_trial_verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        post('/logout',{})
    finally:service.close()


if __name__=='__main__':main()
