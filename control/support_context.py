"""One fixed read-only RPC, with the exact browser user's session and current tenant."""
import json
import time
import urllib.request
from .identity import IdentityError

def capture(manager, handle):
    identity=manager.identity()
    try:
        manager.validate(handle,identity)
        body=json.dumps({'jsonrpc':'2.0','method':'call','id':1,'params':{
            'model':'uno360x.workspace','method':'support_diagnostics','args':[],'kwargs':{}}}).encode()
        request=urllib.request.Request(handle.backend.base+'/web/dataset/call_kw/uno360x.workspace/support_diagnostics',
            data=body,headers={'Content-Type':'application/json','X-UNO360X-Bridge':'1'})
        with handle.lock:
            with handle.backend.opener.open(request,timeout=6) as response:
                raw=response.read(65537)
        manager.validate(handle,identity)
        if len(raw)>65536:
            raise ValueError('Diagnostic size')
        data=json.loads(raw)
        result=data.get('result')
        if not isinstance(result,dict) or result.get('version')!='support-readonly-v1' or result.get('user_id')!=handle.backend.uid:
            raise ValueError('Diagnostic identity or version')
        # No account/session secrets are included in this snapshot or passed to AI.
        result['features']['users']={
            'installed':True,'available':handle.backend.claims.get('role') in ('owner','admin'),
            'path':'Engranaje junto a tu nombre → Usuarios y permisos','route':'/__team',
            'steps':'El administrador puede invitar empleados y asignar áreas. No es necesario modificar los permisos técnicos de Odoo.'}
        if not result['features']['users']['available']:
            result['features']['users'].update(route=None,steps='Solicita al administrador de la empresa los cambios de usuarios y permisos.')
        result['access']={'role':handle.backend.claims.get('role'),
                          'areas':list(handle.backend.claims.get('work_permissions',()))}
        return {'verified':True,'captured':time.time(),'diagnostics':result}
    except IdentityError:
        raise
    except Exception:
        # A slow/unavailable diagnostic cannot drop the actual support request.
        return {'verified':False,'reason':'No se pudo consultar la configuración con los permisos de esta sesión. No afirmar que está verificada.'}
    finally:
        identity.close()
