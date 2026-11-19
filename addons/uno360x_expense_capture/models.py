import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from psycopg2 import IntegrityError
from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError
from .photo import inspect_photo, read_photo
ACCOUNTANTS = 'account.group_account_user,account.group_account_manager'


def amount(value):
    if isinstance(value, bool):
        raise UserError('Importe inválido.')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise UserError('Importe inválido.') from None
    if not result.is_finite() or result < 0:
        raise UserError('Importe inválido.')
    return result


class Move(models.Model):
    _inherit = 'account.move'
    if hasattr(models, 'Constraint'):
        _photo_hash_company_unique = models.Constraint(
            'UNIQUE(company_id, uno_photo_hash)', 'Esta foto ya está registrada en la empresa.')
        _photo_ncf_partner_unique = models.Constraint(
            'UNIQUE(company_id, partner_id, uno_photo_source_ncf)', 'Este comprobante ya está registrado para el proveedor.')
    else:
        _sql_constraints = [
            ('photo_hash_company_unique', 'UNIQUE(company_id, uno_photo_hash)', 'Esta foto ya está registrada en la empresa.'),
            ('photo_ncf_partner_unique', 'UNIQUE(company_id, partner_id, uno_photo_source_ncf)', 'Este comprobante ya está registrado para el proveedor.'),
        ]
    uno_photo_hash = fields.Char(copy=False, readonly=True, index=True,
                                  groups=ACCOUNTANTS)
    uno_photo_pending = fields.Text(copy=False, readonly=True,
                                     groups=ACCOUNTANTS)
    uno_photo_expense_type = fields.Selection(
        [(f'{i:02}', label) for i, label in enumerate([
            'Gastos de personal', 'Trabajos, suministros y servicios', 'Arrendamientos',
            'Activos fijos', 'Representación', 'Otras deducciones admitidas',
            'Gastos financieros', 'Gastos extraordinarios', 'Costo de venta',
            'Adquisiciones de activos', 'Seguros'], 1)],
        string='Clasificación del gasto capturado', copy=False, groups=ACCOUNTANTS)
    uno_photo_source_ncf = fields.Char('Comprobante de la foto', copy=False, readonly=True,
                                        groups=ACCOUNTANTS)

    def _uno_photo_number(self):
        self.ensure_one()
        if self.uno_photo_source_ncf:
            return self.uno_photo_source_ncf
        if hasattr(self, '_uno606_number') and self.env.user.has_group('account.group_account_user'):
            return self._uno606_number()
        return str(self.uno_photo_source_ncf or self.ref or '').strip().upper()


class Capture(models.AbstractModel):
    _name = 'uno360x.expense.capture'
    _description = 'Borradores de gastos desde fotos con permisos del solicitante'

    def _guard(self):
        if self.env.su or not any(self.env.user.has_group(g) for g in ACCOUNTANTS.split(',')):
            raise AccessError('Solo contabilidad autorizada puede preparar gastos desde fotos.')
        self.env['account.move'].check_access('create')

    @api.model
    def _read(self, filename, raw):
        self._guard()
        try:
            result = read_photo(filename, raw)
        except ValueError as error:
            raise UserError(str(error)) from None
        result.update(self.capture_options())
        result['advertencia'] += ' El OCR puede confundir 0/O y 1/I. Si el NCF no es inequívoco, pide confirmar ese dato.'
        return result

    @api.model
    def capture_options(self):
        self._guard()
        taxes = self.env['account.tax'].search([
            ('company_id', '=', self.env.company.id), ('type_tax_use', '=', 'purchase'),
            ('active', '=', True)])
        return {'enabled': True, 'company_id': self.env.company.id, 'user_id': self.env.uid,
            'today': str(fields.Date.context_today(self)),
            'monedas': self.env['res.currency'].search([('active','=',True)]).mapped('name'),
            'impuestos_disponibles': [{
            'id': t.id, 'nombre': t.name, 'importe': t.amount,
            'tipo': t.amount_type, 'incluido': t.price_include,
            'rol_606': t.uno606_role if 'uno606_role' in t._fields and self.env.user.has_group('account.group_account_user') else None} for t in taxes]}

    @api.model
    def capture_draft(self, filename, image, data):
        self._guard()
        import base64
        if not isinstance(image, str) or len(image) > 2_700_000 or not isinstance(data, dict):
            raise UserError('Adjunta una foto de hasta 2 MB.')
        try:
            raw = base64.b64decode(image, validate=True)
        except (ValueError, TypeError):
            raise UserError('Foto inválida.') from None
        return self._prepare(filename, raw, data)

    @api.model
    def capture_history(self):
        self._guard()
        moves = self.env['account.move'].search([
            ('company_id','=',self.env.company.id), ('create_uid','=',self.env.uid),
            ('uno_photo_hash','!=',False), ('move_type','=','in_invoice')],
            order='id desc', limit=30)
        return [self._result(m, 'existing') for m in moves]

    @api.model
    def _prepare(self, filename, raw, data):
        self._guard()
        try:
            checksum = inspect_photo(filename, raw)
        except ValueError as error:
            raise UserError(str(error)) from None
        company = self.env.company
        # One lock per company serializes fiscal/hash duplicate checks across photos.
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s,%s)', (60619, company.id))
        moves = self.env['account.move']
        existing = moves.search([('company_id', '=', company.id),
                                 ('uno_photo_hash', '=', checksum)], limit=1)
        if existing:
            return self._result(existing, 'existing')
        required = ['rnc', 'ncf', 'fecha', 'moneda', 'total', 'itbis', 'lineas']
        missing = [k for k in required if k not in data or data[k] is None or data[k] == '']
        if missing:
            return {'status': 'needs_data', 'faltan': missing, 'creado': False}
        rnc = re.sub(r'[ -]', '', str(data['rnc']))
        ncf = str(data['ncf']).strip().upper()
        if not re.fullmatch(r'\d{9}|\d{11}', rnc):
            raise UserError('RNC/cédula ilegible o incompleto; verifica la foto.')
        # Supplier credit/debit notes and informal receipts require their own workflow.
        if not re.fullmatch(r'(?:B01\d{8}|E31\d{10})', ncf):
            raise UserError('Esta fase admite facturas de compra B01 y E31. Otros comprobantes necesitan revisión contable.')
        partners = self.env['res.partner'].search([
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ('parent_id', '=', False), ('active', '=', True),
            '|', ('vat', 'ilike', rnc), ('vat', 'ilike', rnc[:3])])
        partners = partners.filtered(lambda p: re.sub(r'[ -]', '', str(p.vat or '')) == rnc)
        if len(partners) != 1:
            return {'status': 'needs_supplier', 'rnc': rnc, 'coincidencias': len(partners), 'creado': False}
        partner = partners
        # Compare through the shared 606 resolver, including legacy localization fields.
        candidates = moves.search([('company_id', '=', company.id),
            ('partner_id', 'child_of', partner.id), ('move_type', 'in', ['in_invoice', 'in_refund'])])
        duplicate = candidates.filtered(lambda m: m._uno_photo_number() == ncf)
        if duplicate:
            return self._result(duplicate[:1], 'existing')
        try:
            issued = fields.Date.to_date(data['fecha'])
        except (TypeError, ValueError):
            raise UserError('Fecha ilegible; usa la fecha de la factura en AAAA-MM-DD.') from None
        if not issued or issued > fields.Date.today():
            raise UserError('Verifica la fecha de emisión.')
        currency = self.env['res.currency'].search([('name', '=', data['moneda']),
                                                     ('active', '=', True)], limit=1)
        if not currency:
            raise UserError('Moneda no configurada; no se presume DOP.')
        journals = self.env['account.journal'].search([
            ('company_id', '=', company.id), ('type', '=', 'purchase')], limit=2)
        if len(journals) != 1:
            return {'status': 'needs_configuration', 'faltan': ['Diario de compras único/configurado'], 'creado': False}
        rows = data['lineas']
        if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
            raise UserError('Envía de 1 a 50 partidas de una sola factura.')
        lines = []
        pending = ['Revisar imagen, clasificación fiscal, impuestos y retenciones antes de confirmar.']
        for row in rows:
            name = str(row.get('descripcion') or '').strip()
            qty, price = amount(row.get('cantidad')), amount(row.get('precio'))
            if not name or len(name) > 1000 or qty <= 0:
                raise UserError('Falta descripción/cantidad legible de una partida.')
            nature = row.get('naturaleza')
            if nature not in ('goods', 'services'):
                nature = False
                pending.append('Clasificar partida como bien o servicio.')
            tax_ids = row.get('impuestos')
            if not isinstance(tax_ids, list) or any(type(i) is not int for i in tax_ids):
                raise UserError('Selecciona los impuestos reales configurados; no se presume ITBIS.')
            taxes = self.env['account.tax'].browse(tax_ids).exists()
            taxes.check_access('read')
            if len(taxes) != len(set(tax_ids)) or any(
                t.company_id != company or t.type_tax_use != 'purchase' or not t.active or
                t.amount_type != 'percent' or t.price_include or t.amount < 0 or
                (t.uno606_role not in ('vat', 'exempt') if 'uno606_role' in t._fields and self.env.user.has_group('account.group_account_user')
                 else t.amount not in (0, 16, 18)) for t in taxes):
                raise UserError('Impuesto no compatible con esta captura. Contabilidad debe revisar retenciones y otros impuestos.')
            values = {'name': name, 'quantity': float(qty),
                'price_unit': float(price), 'tax_ids': [Command.set(taxes.ids)]}
            if 'uno606_nature' in self.env['account.move.line']._fields and self.env.user.has_group('account.group_account_user'):
                values['uno606_nature'] = nature
            lines.append(Command.create(values))
        expense = data.get('tipo_gasto') or False
        if expense and expense not in dict(moves._fields['uno_photo_expense_type'].selection):
            raise UserError('Tipo de gasto 606 inválido.')
        if not expense:
            pending.append('Seleccionar tipo de gasto 606.')
        # No payment form/date, retention or paid state is inferred from a photograph.
        try:
            with self.env.cr.savepoint():
                values = {
                    'company_id': company.id, 'move_type': 'in_invoice',
                    'partner_id': partner.id, 'ref': ncf, 'uno_photo_source_ncf': ncf,
                    'journal_id': journals.id, 'currency_id': currency.id,
                    'invoice_date': issued, 'invoice_line_ids': lines,
                    'uno_photo_expense_type': expense,
                    'uno_photo_hash': checksum, 'uno_photo_pending': '\n'.join(dict.fromkeys(pending))}
                if 'uno606_ncf' in moves._fields and self.env.user.has_group('account.group_account_user'):
                    values.update(uno606_ncf=ncf, uno606_expense_type=expense, uno606_reviewed=False)
                move = moves.with_context(default_move_type='in_invoice').create(values)
                if abs(Decimal(str(move.amount_total)) - amount(data['total'])) > Decimal('0.01') or abs(
                    Decimal(str(move.amount_tax)) - amount(data['itbis'])) > Decimal('0.01'):
                    raise UserError('Los totales/ITBIS no cuadran con la foto. No se creó el gasto.')
                self.env['ir.attachment'].create({'name': Path(filename).name[:150],
                    'raw': raw, 'res_model': 'account.move', 'res_id': move.id})
                return self._result(move, 'draft')
        except IntegrityError as error:
            if error.pgcode == '23505' and 'photo_' in (error.diag.constraint_name or ''):
                raise UserError('Otra solicitud ya está registrando esta foto o comprobante. No se duplicó; consulta el borrador existente antes de reintentar.') from None
            raise

    def _result(self, move, status):
        move.check_access('read')
        return {'status': status, 'id': move.id, 'estado': move.state,
                'comprobante': move._uno_photo_number(), 'total': move.amount_total,
                'moneda': move.currency_id.name, 'pendientes': move.uno_photo_pending or '',
                'url': '/web#id=%s&model=account.move&view_type=form' % move.id,
                'nota': 'Borrador pendiente de revisión; no equivale a gasto presentado en 606 ni a pago.'}
