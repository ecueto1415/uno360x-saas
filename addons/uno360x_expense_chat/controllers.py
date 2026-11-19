from odoo import http
from odoo.http import request
from odoo.addons.uno360x_workspace.controllers.workspace import WorkspaceController


class ExpenseChat(WorkspaceController):
    @http.route('/uno360x/jenifer/gastos', type='http', auth='user', methods=['GET'])
    def expense_chat(self, **kwargs):
        request.env['uno360x.expense.capture']._guard()
        ctx = self._service()._workspace_context()
        ctx.update(page_key='billing')
        return self._render('uno360x_expense_chat.page', ctx)
