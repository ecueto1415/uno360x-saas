from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied


class BridgeController(http.Controller):
    @http.route('/uno360x/bridge/login',type='json',auth='public',methods=['POST'],csrf=False)
    def login(self, login=None, assertion=None):
        # A cross-origin HTML form cannot supply this JSON/custom-header flow.
        # The trusted local broker never supplies an arbitrary callback URL.
        if request.httprequest.headers.get('X-UNO360X-Bridge')!='1':raise AccessDenied()
        origin=request.httprequest.headers.get('Origin')
        if origin and origin!=request.httprequest.url_root.rstrip('/'):raise AccessDenied()
        if not isinstance(login,str) or not isinstance(assertion,str):raise AccessDenied()
        auth=request.session.authenticate(request.db,{'login':login,'password':assertion,'type':'uno360x_bridge'})
        return {'authenticated':bool(request.session.uid),'uid':auth['uid'],
                'mfa_required':not bool(request.session.uid)}
