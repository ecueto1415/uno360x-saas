import base64
import calendar
from collections import defaultdict
from datetime import date
from markupsafe import Markup, escape

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError, UserError
from .engine import build, export_txt, NCF, tax_id

ACCOUNTANTS = 'account.group_account_user'
EXPENSES = [(f'{n:02}', label) for n,label in enumerate([
    'Gastos de personal', 'Trabajos, suministros y servicios', 'Arrendamientos',
    'Activos fijos', 'Representación', 'Otras deducciones admitidas',
    'Gastos financieros', 'Gastos extraordinarios', 'Costo de venta',
    'Adquisiciones de activos', 'Seguros'], 1)]
PAYMENTS = [('01','Efectivo'),('02','Cheque / transferencia / depósito'),
            ('03','Tarjeta'),('04','Compra a crédito'),('05','Permuta'),
            ('06','Nota de crédito'),('07','Mixto')]
ISR = [(f'{n:02}',label) for n,label in enumerate([
    'Alquileres','Honorarios por servicios','Otras rentas','Rentas presuntas',
    'Intereses a personas jurídicas residentes','Intereses a personas físicas residentes',
    'Proveedores del Estado','Juegos telefónicos','Ganadería de carne bovina'],1)]
TAX_ROLES = [('vat','ITBIS facturado'),('vat_withheld','ITBIS retenido'),
             ('isr_withheld','ISR retenido'),('isc','Selectivo al consumo'),
             ('other','Otros impuestos/tasas'),('tip','Propina legal'),('exempt','Exento / tasa cero')]


def accountant(env, company):
    if (not env.su and not env.user.has_group(ACCOUNTANTS)) or company not in env.companies:
        raise AccessError('Solo contabilidad autorizada puede consultar el 606 de sus empresas.')


class Tax(models.Model):
    _inherit = 'account.tax'
    uno606_role = fields.Selection(TAX_ROLES, string='Clasificación Formato 606', groups=ACCOUNTANTS)

    def _uno606_role(self):
        self.ensure_one()
        self.check_access('read')
        if self.uno606_role: return self.uno606_role
        # Legacy classification fields may be manager-only. Read only these
        # configuration values after checking the caller's access to this tax;
        # invoice/payment/report records retain the caller's own permissions.
        if 'uno360x_ecf_retention' in self._fields and self.sudo().uno360x_ecf_retention:
            return {'itbis':'vat_withheld','isr':'isr_withheld'}.get(self.sudo().uno360x_ecf_retention)
        if 'outs_ecf_category' in self._fields and self.sudo().outs_ecf_category:
            return 'exempt' if self.sudo().outs_ecf_category in ('3','4') else 'vat'
        return False


class Journal(models.Model):
    _inherit = 'account.journal'
    uno606_payment_form = fields.Selection(PAYMENTS, string='Forma de pago 606', groups=ACCOUNTANTS)


class MoveLine(models.Model):
    _inherit = 'account.move.line'
    uno606_nature = fields.Selection([('goods','Bienes'),('services','Servicios')],
                                    string='Bien/servicio 606', groups=ACCOUNTANTS, copy=True)


class Move(models.Model):
    _inherit = 'account.move'
    uno606_ncf = fields.Char('NCF/e-NCF de compra (606)', copy=False, groups=ACCOUNTANTS)
    uno606_modified = fields.Char('NCF modificado (606)', copy=False, groups=ACCOUNTANTS)
    uno606_original_reported = fields.Boolean('Original reportado previamente en el 606', copy=False, groups=ACCOUNTANTS)
    uno606_expense_type = fields.Selection(EXPENSES, string='Tipo de gasto 606', groups=ACCOUNTANTS)
    uno606_reviewed = fields.Boolean('Datos fiscales 606 revisados', copy=False, groups=ACCOUNTANTS)
    uno606_proportional = fields.Monetary('ITBIS sujeto a proporcionalidad', currency_field='company_currency_id', groups=ACCOUNTANTS)
    uno606_cost_vat = fields.Monetary('ITBIS llevado al costo', currency_field='company_currency_id', groups=ACCOUNTANTS)
    uno606_events = fields.One2many('uno360x.606.payment', 'move_id', string='Pagos y retenciones 606', groups=ACCOUNTANTS, copy=False)

    def _uno606_number(self):
        self.ensure_one()
        candidates = [self[name] for name in ('l10n_latam_document_number','ncf','uno606_ncf','ref') if name in self._fields and self[name]]
        return next((str(v).strip().upper() for v in candidates if NCF.fullmatch(str(v).strip().upper())), str(self.uno606_ncf or self.ref or '').strip().upper())

    def _uno606_entry(self, period):
        self.ensure_one()
        accountant(self.env, self.company_id)
        errors, amounts = [], defaultdict(float)
        sign = -1 if self.move_type == 'in_refund' else 1
        for line in self.invoice_line_ids.filtered(lambda l:l.display_type == 'product'):
            nature = line.uno606_nature
            if not nature and line.product_id:
                nature = 'services' if line.product_id.type == 'service' else 'goods'
            if not nature: errors.append(('Bienes/servicios', 'Clasifica la línea: ' + (line.name or str(line.id))))
            else: amounts[nature] += sign * line.balance
        potential_retention = False
        for line in self.line_ids.filtered('tax_line_id'):
            role = line.tax_line_id._uno606_role()
            if not role: errors.append(('Impuesto', 'Clasifica para 606: ' + line.tax_line_id.name))
            elif role in ('vat_withheld','isr_withheld'):
                potential_retention = True
            elif role != 'exempt': amounts[role] += sign * line.balance
        for tax in self.invoice_line_ids.tax_ids:
            if tax.amount == 0 and not tax._uno606_role():
                errors.append(('Impuesto', 'Confirma la clasificación de tasa cero/exento: ' + tax.name))
        if self.company_currency_id.name != 'DOP': errors.append(('Moneda', 'La moneda contable debe ser DOP; no se convierte con una tasa implícita.'))
        events = self.uno606_events.filtered(lambda e:e.date.strftime('%Y%m') == period)
        if any(e.state != 'reviewed' for e in events): errors.append(('Pagos', 'Hay pagos/retenciones sin revisar.'))
        paid = max(events.mapped('date')) if events else False
        forms = set(events.mapped('payment_form'))
        form = next(iter(forms)) if len(forms) == 1 else '07' if forms else '04'
        isr_types = set(events.filtered(lambda e:e.isr_amount).mapped('isr_type'))
        if len(isr_types) > 1: errors.append(('Tipo retención ISR', 'Más de un tipo ISR en el mismo NCF/período; requiere revisión contable.'))
        # Payment detail is explicit and checked against reconciliation, never guessed from an invoice label.
        for event in events:
            errors.extend(event._validation_errors())
        if self.invoice_date and self.invoice_date.strftime('%Y%m') == period:
            payable = self.line_ids.filtered(lambda l:l.account_id.account_type=='liability_payable')
            partials = payable.matched_debit_ids | payable.matched_credit_ids
            has_reconciliation = any(
                counterpart.move_id != self and counterpart.move_id.move_type == 'entry'
                for partial in partials for counterpart in (partial.debit_move_id,partial.credit_move_id)
            )
            if has_reconciliation and not self.uno606_events:
                errors.append(('Pagos', 'Completa y revisa los pagos/compensaciones históricos del comprobante.'))
            if potential_retention and has_reconciliation and not self.uno606_events:
                errors.append(('Retenciones', 'Confirma la fecha y retenciones efectivamente pagadas.'))
        original = self.reversed_entry_id
        if original and (original.company_id != self.company_id or original.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id):
            errors.append(('Factura original', 'La empresa/proveedor de la nota y su factura original no coinciden.'))
        if original and original.invoice_date and self.invoice_date and original.invoice_date > self.invoice_date:
            errors.append(('Factura original', 'La factura original es posterior a la nota.'))
        number = self._uno606_number()
        known_numbers = {str(self[name]).strip().upper() for name in
            ('l10n_latam_document_number','ncf','uno606_ncf','ref')
            if name in self._fields and self[name] and NCF.fullmatch(str(self[name]).strip().upper())}
        if len(known_numbers) > 1:
            errors.append(('NCF/e-NCF', 'Los campos fiscales y Referencia contienen comprobantes distintos; corrige la discrepancia.'))
        if self.move_type == 'in_refund': form = '06'
        entry = dict(move_id=self.id, source=self.display_name, supplier=self.partner_id.commercial_partner_id.vat,
            ncf=number, expense=(self['expense_type'] if 'expense_type' in self._fields else False) or self.uno606_expense_type,
            modified=original._uno606_number() if original else self.uno606_modified or '',
            issued=str(self.invoice_date) if self.invoice_date else '', paid=str(paid) if paid else '',
            services=round(amounts['services'],2), goods=round(amounts['goods'],2),
            total=round(sign*sum(self.invoice_line_ids.filtered(lambda l:l.display_type=='product').mapped('balance')),2),
            vat=round(amounts['vat'],2), vat_withheld=round(sum(events.mapped('vat_amount')),2),
            proportional=self.uno606_proportional, cost_vat=self.uno606_cost_vat,
            advance=round(amounts['vat']-self.uno606_cost_vat,2), vat_perceived=0,
            isr_type=next(iter(isr_types)) if len(isr_types)==1 else '',
            isr_withheld=round(sum(events.mapped('isr_amount')),2), isr_perceived=0,
            isc=round(amounts['isc'],2), other=round(amounts['other'],2), tip=round(amounts['tip'],2),
            payment_form=form, credit=self.move_type=='in_refund', reviewed=self.uno606_reviewed,
            original_reported=self.uno606_original_reported, errors=errors)
        # Special foreign-payment self-issued vouchers use the reporting company's identifier.
        if number.startswith(('B13','E43','B17','E47')): entry['supplier'] = self.company_id.vat
        return entry


class Payment(models.Model):
    _name = 'uno360x.606.payment'
    _description = 'Pago y retenciones revisados del 606'
    _check_company_auto = True
    _order = 'date,id'
    move_id = fields.Many2one('account.move', required=True, ondelete='cascade', check_company=True, index=True)
    company_id = fields.Many2one(related='move_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date('Fecha de pago', required=True)
    payment_id = fields.Many2one('account.payment', string='Pago contable', check_company=True)
    reference = fields.Char('Referencia / evidencia histórica', required=True)
    payment_form = fields.Selection(PAYMENTS, string='Forma de pago', required=True)
    amount = fields.Monetary('Importe liquidado en DOP', required=True)
    vat_amount = fields.Monetary('ITBIS retenido pagado')
    isr_amount = fields.Monetary('ISR retenido pagado')
    isr_type = fields.Selection(ISR, string='Tipo de retención ISR')
    state = fields.Selection([('draft','Por revisar'),('reviewed','Revisado')], required=True, default='draft')

    @api.onchange('payment_id')
    def _onchange_payment(self):
        if self.payment_id:
            payment=self.payment_id
            self.date=payment.date
            self.reference=payment.name
            self.payment_form=payment.journal_id.uno606_payment_form or False
            payable=payment.move_id.line_ids.filtered(lambda line:line.account_id.account_type=='liability_payable')
            self.amount=abs(sum(payable.mapped('balance')))
            self.state='draft'

    def _validation_errors(self):
        self.ensure_one()
        problems=[]
        if self.amount <= 0 or self.vat_amount < 0 or self.isr_amount < 0:
            problems.append(('Pago', 'Importes de pago/retención inválidos.'))
        if self.move_id.invoice_date and self.date < self.move_id.invoice_date:
            problems.append(('Fecha pago','El pago es anterior al comprobante.'))
        if self.vat_amount+self.isr_amount > self.amount:
            problems.append(('Retenciones','Las retenciones superan el pago.'))
        if bool(self.isr_amount) != bool(self.isr_type):
            problems.append(('Tipo ISR','Completa conjuntamente tipo e importe ISR.'))
        if self.payment_id:
            payment=self.payment_id
            if payment.company_id != self.company_id or payment.date != self.date:
                problems.append(('Pago contable','La empresa o fecha no coincide.'))
            # Odoo's reconciled invoice relations preserve the accounting evidence.
            invoices = payment.reconciled_bill_ids if 'reconciled_bill_ids' in payment._fields else self.env['account.move']
            if self.move_id not in invoices:
                problems.append(('Pago contable','El pago seleccionado no está conciliado con esta factura.'))
        if self.search_count([('id','!=',self.id),('move_id','=',self.move_id.id),('date','=',self.date),('reference','=',self.reference)]):
            problems.append(('Pago duplicado','Ya existe la misma referencia para esta factura y fecha.'))
        return problems

    @api.constrains('move_id','payment_id','date','amount','vat_amount','isr_amount','isr_type','state')
    def _check_fiscal(self):
        for record in self:
            accountant(self.env,record.company_id)
            if record.move_id.move_type not in ('in_invoice','in_refund'):
                raise ValidationError('El 606 corresponde a documentos de proveedores.')
            if record.state=='reviewed':
                errors=record._validation_errors()
                if errors: raise ValidationError('\n'.join(message for _,message in errors))


class Report(models.TransientModel):
    _name = 'uno360x.606.report'
    _description = 'Borrador Formato 606 DGII'
    company_id = fields.Many2one('res.company', required=True, default=lambda s:s.env.company)
    month = fields.Selection([(f'{n:02}',str(n)) for n in range(1,13)], required=True, default=lambda s:fields.Date.today().strftime('%m'))
    year = fields.Integer(required=True, default=lambda s:fields.Date.today().year)
    preview = fields.Html('Comprobantes, totales y errores', readonly=True, sanitize=True)
    file_data = fields.Binary(readonly=True, attachment=False)
    filename = fields.Char(readonly=True)

    def _result(self):
        self.ensure_one(); accountant(self.env,self.company_id)
        try:
            start=date(self.year,int(self.month),1)
            end=date(self.year,int(self.month),calendar.monthrange(self.year,int(self.month))[1])
        except (ValueError,TypeError): raise UserError('Selecciona un mes y año válidos.') from None
        moves=self.env['account.move'].with_company(self.company_id).search([
            ('company_id','=',self.company_id.id),('move_type','in',['in_invoice','in_refund']),
            ('state','=','posted'),'|',
            '&',('invoice_date','>=',start),('invoice_date','<=',end),
            '&',('invoice_date','=',False),'&',('date','>=',start),('date','<=',end)])
        events=self.env['uno360x.606.payment'].search([('company_id','=',self.company_id.id),
            ('date','>=',start),('date','<=',end),'|',('vat_amount','>',0),('isr_amount','>',0)])
        moves |= events.move_id.filtered(lambda m:m.state=='posted' and m.invoice_date and m.invoice_date < start)
        entries=[]
        all_moves=self.env['account.move'].with_company(self.company_id).search([
            ('company_id','=',self.company_id.id),('move_type','in',['in_invoice','in_refund']),('state','=','posted')])
        duplicate_map=defaultdict(list)
        for move in all_moves:
            number=move._uno606_number()
            if number: duplicate_map[(move.partner_id.commercial_partner_id.id,number)].append(move.id)
        for move in moves.sorted(lambda m:(m.invoice_date or date.min,m.id)):
            entry=move._uno606_entry(f'{self.year:04}{self.month}')
            duplicates=duplicate_map[(move.partner_id.commercial_partner_id.id,entry['ncf'])]
            if len(duplicates)>1: entry['errors'].append(('NCF duplicado','Comprobante repetido en facturas: '+', '.join(map(str,duplicates))))
            entries.append(entry)
        return build(self.company_id.vat,f'{self.year:04}{self.month}',entries)

    def action_preview(self):
        result=self._result()
        output=Markup('<h3>EN PRUEBAS · Requiere confirmación de contabilidad</h3><p>Archivo para carga manual. No se envía a la DGII desde aquí.</p>')
        unclassified_tax=any(p['field']=='Impuesto' for p in result['errors'])
        totals=[result['totals'].get(k,'0.00') for k in ('total','vat','vat_withheld','isr_withheld')]
        if unclassified_tax: totals[1]='Pendiente de clasificar'
        output+=Markup('<p>Registros: %s · Neto facturado DOP: %s · ITBIS: %s · ITBIS retenido: %s · ISR retenido: %s</p>') % tuple(escape(v) for v in [len(result['rows'])]+totals)
        issues=Markup('')
        if result['errors']:
            issues+=Markup('<h4>Corrige estos errores antes de exportar</h4><ul>')
            for problem in result['errors']:
                source=escape(problem['source'])
                if problem.get('move_id'):
                    source=Markup('<a href="/odoo/account.move/%s" target="_blank">%s</a>') % (problem['move_id'],source)
                issues+=Markup('<li>%s · <strong>%s</strong>: %s</li>') % (source,escape(problem['field']),escape(problem['message']))
            issues+=Markup('</ul>')
        else: output+=Markup('<p>Sin errores locales. Pendiente cotejo contable y prevalidación oficial.</p>')
        output+=Markup('<div style="overflow-x:auto"><table class="table table-sm"><thead><tr>')
        columns=[('source','Factura'),('supplier','RNC'),('ncf','NCF/e-NCF'),('modified','Modificado'),('issued','Emisión'),('paid','Pago'),('expense','Gasto'),('total','Base DOP'),('vat','ITBIS'),('vat_withheld','ITBIS retenido'),('isr_withheld','ISR retenido'),('payment_form','Forma de pago'),('retention_only','Solo retenciones')]
        for _,label in columns: output+=Markup('<th>%s</th>') % label
        output+=Markup('</tr></thead><tbody>')
        for row in result['rows']:
            output+=Markup('<tr>')
            for key,_ in columns:
                value=row.get(key)
                if key=='retention_only': value='Sí' if value else 'No'
                elif key=='payment_form': value=dict(PAYMENTS).get(value,value)
                elif key in ('issued','paid') and value:
                    value=f'{value[6:8]}/{value[4:6]}/{value[:4]}'
                elif value is False or value is None or value=='': value='—'
                if key=='vat' and any(p.get('move_id')==row.get('move_id') and p['field']=='Impuesto' for p in result['errors']):value='Por revisar'
                output+=Markup('<td>%s</td>') % escape(str(value))
            output+=Markup('</tr>')
        output+=Markup('</tbody></table></div>')
        output+=issues
        self.write({'preview':output,'file_data':False,'filename':False})
        return {'type':'ir.actions.act_window','res_model':self._name,'res_id':self.id,'view_mode':'form','target':'current'}

    def action_download(self):
        # Always rebuild from authorized source records. Never export edited preview/JSON.
        result=self._result()
        if result['errors']: raise UserError('Hay errores fiscales. Pulsa Revisar borrador y corrige las facturas indicadas.')
        data=export_txt(result)
        filename=f"DGII_F_606_{result['issuer']}_{result['period']}.TXT"
        self.write({'file_data':base64.b64encode(data),'filename':filename})
        return {'type':'ir.actions.act_url','url':f'/web/content/{self._name}/{self.id}/file_data/{filename}?download=true','target':'download'}
