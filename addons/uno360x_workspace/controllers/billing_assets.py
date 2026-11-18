from werkzeug.wrappers import Response
from odoo import http
from odoo.http import request
from ..billing_assets import billing_asset


class BillingAssets(http.Controller):
    @http.route('/uno360x_workspace/billing-assets/<string:kind>/<string:version>',
                type='http', auth='public', methods=['GET'])
    def billing_asset(self, kind, version, **kwargs):
        if kind not in ('css', 'js'):
            return request.not_found()
        digest, content = billing_asset(kind)
        current = '%s.%s' % (digest, kind)
        if version != current:
            return request.redirect(
                '/uno360x_workspace/billing-assets/%s/%s' % (kind, current), code=302
            )
        content_type = 'text/css; charset=utf-8' if kind == 'css' else 'application/javascript; charset=utf-8'
        response = Response(content, content_type=content_type, headers={
            'Cache-Control': 'public, max-age=31536000, immutable',
            'X-Content-Type-Options': 'nosniff',
        })
        response.set_etag(digest)
        return response.make_conditional(request.httprequest)
