import io
from datetime import date
from decimal import Decimal, InvalidOperation

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request, content_disposition
from odoo.tools.misc import format_amount
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from werkzeug.exceptions import Forbidden, NotFound

from .areas import AreaWorkspace

PATH = '/uno360x/finanzas/cheques'


class ChequeWorkspace(AreaWorkspace):
    def _context(self):
        if not request.env.user.has_group('account.group_account_manager'):
            raise Forbidden()
        values = self._service()._area_values('billing')
        values.update(page_key='billing', cheque_url=PATH)
        return request.env['uno360x.bank.cheque'], values

    def _cheque(self, model, cheque_id):
        cheque = model.search([('id', '=', cheque_id)], limit=1)
        if not cheque:
            raise NotFound()
        return cheque

    def _journals(self):
        return request.env['account.journal'].search([
            ('company_id', '=', request.env.company.id), ('type', '=', 'bank')
        ])

    def _amount(self, cheque):
        return format_amount(request.env, cheque.amount, cheque.currency_id)

    @http.route(PATH, type='http', auth='user', methods=['GET'])
    def cheque_list(self, q='', status='', journal='', page='1', **kw):
        model, values = self._context()
        domain = []
        if journal.isascii() and journal.isdigit() and len(journal) < 11:
            domain.append(('journal_id', '=', int(journal)))
        if status in ('draft', 'issued', 'void'):
            domain.append(('state', '=', status))
        if q.strip():
            domain += ['|', ('number', 'ilike', q.strip()[:100]), ('beneficiary', 'ilike', q.strip()[:100])]
        page = min(int(page), 10000) if page.isascii() and page.isdigit() and 0 < len(page) < 8 else 1
        page = max(page, 1)
        items = model.search(domain, limit=51, offset=(page - 1) * 50)
        from urllib.parse import urlencode
        values.update(cheques=items[:50], journals=self._journals(), q=q, journal=journal, status=status,
                      amount_display=self._amount, page=page, has_more=len(items) > 50,
                      filter_url=PATH + '?' + urlencode(dict(q=q, journal=journal, status=status)))
        return self._render('uno360x_workspace.cheque_list', values)

    @http.route([PATH + '/nuevo', PATH + '/<int:cheque_id>'], type='http', auth='user', methods=['GET', 'POST'])
    def cheque_form(self, cheque_id=None, **kw):
        model, values = self._context()
        cheque = self._cheque(model, cheque_id) if cheque_id else model
        journals = self._journals()
        values.update(cheque=cheque, journals=journals, today=fields.Date.context_today(model),
                      data={}, error='', amount_display=self._amount,
                      bills=request.env['account.move'].search([
                          ('company_id', '=', request.env.company.id), ('move_type', '=', 'in_invoice'),
                          ('state', '=', 'posted'), ('payment_state', 'not in', ['paid', 'reversed']),
                      ], limit=100, order='invoice_date desc, id desc'))
        if request.httprequest.method == 'POST':
            values['data'] = kw
            try:
                with request.env.cr.savepoint():
                    journal = journals.filtered(lambda item: str(item.id) == kw.get('journal_id'))
                    entered = Decimal(kw.get('amount', ''))
                    if not journal or not entered.is_finite() or not 0 < entered < 10**12:
                        raise UserError('Selecciona el banco e introduce un monto válido.')
                    amount = journal.uno_cheque_currency_id.round(float(entered))
                    bill = values['bills'].filtered(lambda item: str(item.id) == kw.get('bill_id'))
                    if kw.get('bill_id') and not bill and cheque.bill_id and str(cheque.bill_id.id) == kw['bill_id']:
                        bill = cheque.bill_id
                    if kw.get('bill_id') and not bill:
                        raise UserError('Selecciona una factura disponible.')
                    data = dict(journal_id=journal.id, beneficiary=kw.get('beneficiary', '').strip()[:120],
                                amount=amount, date=date.fromisoformat(kw.get('date', '')),
                                memo=kw.get('memo', '').strip()[:150], bill_id=bill.id or False)
                    if cheque:
                        cheque.write(data)
                    else:
                        cheque = model.create(data)
                suffix = '/vista' if kw.get('step') == 'preview' else ''
                return request.redirect(f'{PATH}/{cheque.id}{suffix}', code=303)
            except (UserError, ValueError, InvalidOperation) as error:
                values['error'] = str(error) if isinstance(error, UserError) else 'Revisa la fecha y el monto.'
        return self._render('uno360x_workspace.cheque_form', values)

    @http.route(PATH + '/<int:cheque_id>/vista', type='http', auth='user', methods=['GET', 'POST'])
    def cheque_preview(self, cheque_id, number='', **kw):
        model, values = self._context()
        cheque = self._cheque(model, cheque_id)
        error = ''
        if request.httprequest.method == 'POST':
            try:
                with request.env.cr.savepoint():
                    if kw.get('step') == 'void':
                        cheque._void(kw.get('reason', ''))
                        return request.redirect(f'{PATH}/{cheque.id}', code=303)
                    cheque._lock()
                    self._print_document(cheque, False)
                    cheque._issue(number.strip())
                return request.redirect(f'{PATH}/{cheque.id}/vista?emitido=1', code=303)
            except UserError as exc:
                error = str(exc)
        values.update(bank_action=request.env.ref('uno360x_workspace.cheque_bank_action').id, cheque=cheque, number=number, error=error, amount_display=self._amount,
                      amount_words=cheque._amount_words(), just_issued=kw.get('emitido') == '1')
        return self._render('uno360x_workspace.cheque_preview', values)

    @http.route(PATH + '/<int:cheque_id>/impresion.pdf', type='http', auth='user', methods=['GET'])
    def cheque_pdf(self, cheque_id, prueba='', **kw):
        model, _ = self._context()
        cheque = self._cheque(model, cheque_id)
        sample = prueba == '1'
        if cheque.state == 'void' or (cheque.state != 'issued' and not sample):
            raise Forbidden()
        try:
            document = self._print_document(cheque, sample)
        except UserError as exc:
            return request.make_response(str(exc), headers=[('Content-Type', 'text/plain; charset=utf-8')], status=422)
        return request.make_response(document, headers=[
            ('Content-Type', 'application/pdf'), ('Cache-Control', 'no-store'),
            ('Content-Disposition', content_disposition('prueba-cheque.pdf' if sample else f'cheque-{cheque.number}.pdf', 'inline')),
        ])

    def _print_document(self, cheque, sample):
        profile = cheque.journal_id
        width = profile.uno_cheque_width or 216
        height = profile.uno_cheque_height or 279
        data = io.BytesIO()
        pdf = canvas.Canvas(data, pagesize=(width * mm, height * mm))
        pdf.setTitle('Prueba de alineación' if sample else 'Cheque ' + (cheque.number or ''))
        def place(key, label, right=False):
            x = profile['uno_cheque_' + key + '_x'] + profile.uno_cheque_x
            y = profile['uno_cheque_' + key + '_y'] + profile.uno_cheque_y
            amount_x = profile.uno_cheque_amount_x + profile.uno_cheque_x
            usable = x - 3 if right else width - x - 3
            if key == 'beneficiary':
                usable = min(usable, amount_x - x - 45)
            if usable <= 0 or not 0 < y < height:
                raise UserError('Ajusta la posición de los campos en el formato del banco.')
            text_width = pdf.stringWidth(label, 'Helvetica', 11)
            size = min(11, 11 * usable * mm / max(text_width, 1))
            if size < 7:
                raise UserError('Un dato es demasiado largo para el formato del banco. Ajusta el formato antes de emitir.')
            pdf.setFont('Helvetica', size)
            render = pdf.drawRightString if right else pdf.drawString
            render(x * mm, (height - y) * mm, label)

        place('date', cheque.date.strftime('%d/%m/%Y'), True)
        place('beneficiary', cheque.beneficiary)
        place('amount', self._amount(cheque).replace(chr(160), ' '), True)
        place('words', cheque._amount_words())
        if sample:
            pdf.setFillColorRGB(.65, .15, .15)
            pdf.setFont('Helvetica-Bold', 12)
            pdf.drawCentredString(width * mm / 2, (height - 6) * mm, 'PRUEBA DE ALINEACIÓN')
        pdf.save()
        return data.getvalue()
