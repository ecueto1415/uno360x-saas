from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from werkzeug.exceptions import Forbidden

from .workspace import WorkspaceController, can_manage_company
from ..models.fiscal_sequence import DOCUMENT_TYPES


class FiscalSequenceController(WorkspaceController):
    @http.route('/uno360x-mi-empresa/secuencias', type='http', auth='user',
                methods=['GET', 'POST'], csrf=True)
    def fiscal_sequences(self, add='', saved='', **params):
        service = self._service()
        user = request.env.user
        if not can_manage_company(user):
            raise Forbidden()
        company = request.env.company
        ranges = request.env['uno360x.fiscal.sequence.request'].sudo()
        fields = ('document_type', 'authorization', 'first_encf', 'last_encf', 'next_encf', 'expires')
        form = {key: params.get(key, '') for key in fields}
        error = ''
        if request.httprequest.method == 'POST':
            try:
                with request.env.cr.savepoint():
                    ranges._submit_range(company, user, form)
            except UserError as exc:
                error = str(exc)
            else:
                return request.redirect('/uno360x-mi-empresa/secuencias?saved=1', code=303)
        context = service._workspace_context()
        context.update(
            page_key='my_company', ranges=ranges.search([('company_id', '=', company.id)]),
            document_types=DOCUMENT_TYPES, labels=dict(DOCUMENT_TYPES), form=form,
            form_open=add == '1' or bool(error), form_error=error, range_saved=saved == '1',
        )
        return self._render('uno360x_workspace.fiscal_sequences', context)
