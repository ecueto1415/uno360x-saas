"""Trusted local handoff proof. Backend cookies stay in memory, never returned.

Every RPC revalidates the central session, current membership and preparation.
A public web gateway with TLS is a separate deployment step, not this helper.
"""
import http.cookiejar
import json
import re
import urllib.request
import urllib.error

from .bridge_protocol import mint
from .identity import IdentityError


class BackendSession:
    def __init__(self,onboarding,central_session,claims,snapshot,opener,base,uid):
        self.onboarding=onboarding;self.central_session=central_session;self.claims=claims
        self.snapshot=snapshot;self.opener=opener;self.base=base;self.uid=uid

    def _check(self):
        service=self.onboarding.identity
        account=service._account(self.central_session)
        member=service._membership(account['id'],self.claims['tenant_id'])
        from .trials import check_trial_access
        check_trial_access(service, self.claims['tenant_id'])
        if account['id']!=self.claims['account_id'] or member['role']!=self.claims['role']:
            raise IdentityError('El acceso cambió; vuelve a entrar a tu espacio.')
        if not self.onboarding.status(self.central_session,self.claims['tenant_id'])['local_ready']:
            raise IdentityError('Espacio no disponible.')

    def rpc(self,model,method,args=None,kwargs=None):
        self._check()
        if not isinstance(method,str) or not re.fullmatch('[a-z][a-z0-9_]{0,80}',method) or not isinstance(model,str) or not re.fullmatch('[a-z][a-z0-9_.]{0,80}',model):
            raise IdentityError('Operación inválida.')
        return _rpc(self.opener,self.base,'/web/dataset/call_kw/'+model+'/'+method,
                    {'model':model,'method':method,'args':args or [],'kwargs':kwargs or {}})


def _rpc(opener,base,path,params):
    body=json.dumps({'jsonrpc':'2.0','method':'call','params':params,'id':1}).encode()
    request=urllib.request.Request(base+path,data=body,headers={'Content-Type':'application/json','X-UNO360X-Bridge':'1'})
    with opener.open(request,timeout=45) as response:result=json.load(response)
    if 'error' in result:raise IdentityError('Odoo rechazó el acceso o la operación.')
    return result['result']


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


def open_space(onboarding,session,ticket,adapter):
    # This operation must remain in the trusted worker/broker, not in the
    # unprivileged public request handler.
    claims=onboarding.consume_handoff(session,ticket)
    row=onboarding.db.execute('SELECT snapshot FROM preparation_jobs WHERE id=?',(claims['job_id'],)).fetchone()
    snapshot=json.loads(row['snapshot'])
    with adapter.lock(claims['tenant_id']):
        base=None
        if callable(getattr(type(adapter),'access_backend',None)):
            base=adapter.access_backend(snapshot)
        else:
            adapter.validation(snapshot)
        adapter.sync_user(snapshot,claims)
        # Recheck after user synchronization, before making a new Odoo session.
        account=onboarding.identity._account(session)
        member=onboarding.identity._membership(account['id'],claims['tenant_id'])
        if member['role']!=claims['role']:raise IdentityError('El acceso cambió.')
        assertion=mint(adapter.bridge_key(snapshot),claims['tenant_id'],claims['account_id'])
        if base is None:base=adapter.backend(snapshot)
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}),NoRedirect())
        result=_rpc(opener,base,'/uno360x/bridge/login',{'login':'saas_'+claims['account_id'],'assertion':assertion})
        if not result.get('authenticated'):raise IdentityError('Completa la autenticación adicional de Odoo.')
    return BackendSession(onboarding,session,claims,snapshot,opener,base,result['uid'])


def resume_space(onboarding,session,ticket,existing):
    """Reuse only this exact central session and unchanged prepared identity.

    Authorization is never cached: consuming the new one-use handoff still
    checks account, membership, trial and current release. The backend session
    is probed before reuse; a missing or expired session takes the normal path.
    """
    account=onboarding.identity._account(session)
    if existing.central_session!=session or account['id']!=existing.claims['account_id']:
        return None
    member=onboarding.identity._membership(account['id'],existing.claims['tenant_id'])
    if member['role']!=existing.claims['role']:return None
    row=onboarding.db.execute("SELECT snapshot FROM preparation_jobs WHERE id=? AND status='ready_local'",(existing.claims['job_id'],)).fetchone()
    if not row or json.loads(row['snapshot'])!=existing.snapshot:return None
    try:
        result=_rpc(existing.opener,existing.base,'/web/session/get_session_info',{})
        if result.get('uid')!=existing.uid:return None
    except (IdentityError,OSError,urllib.error.URLError,ValueError,KeyError):
        return None
    claims=onboarding.consume_handoff(session,ticket)
    if any(claims[key]!=existing.claims[key] for key in ('account_id','tenant_id','role','job_id')):
        raise IdentityError('El acceso cambió; vuelve a entrar a tu espacio.')
    return BackendSession(onboarding,session,claims,existing.snapshot,existing.opener,existing.base,existing.uid)
