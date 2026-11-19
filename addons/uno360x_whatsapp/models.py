import hashlib
import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import format_amount

from .protocol import phone, template_payload


def require_collector(env):
    if not (env.su or env.user.has_group('uno360x_whatsapp.group_collection_user') or env.user.has_group('account.group_account_manager')):
        raise AccessError('Tu usuario no tiene permiso para gestionar recordatorios de cobro.')
    if not env['uno360x.workspace']._work_area_allowed('billing'):
        raise AccessError('El área de facturación no está habilitada para tu usuario.')


def require_manager(env):
    if not (env.su or env.user.has_group('account.group_account_manager')):
        raise AccessError('Solo el administrador de contabilidad puede configurar WhatsApp.')


class Connection(models.Model):
    _name='uno360x.wa.connection'
    _description='Número de WhatsApp de la empresa (laboratorio)'
    company_id=fields.Many2one('res.company',required=True,default=lambda s:s.env.company,index=True)
    display_phone=fields.Char('Número de la empresa, pendiente de verificar')
    template_name=fields.Char(default='uno360x_aviso_factura',required=True)
    language=fields.Selection([('es','Español'),('es_ES','Español ES'),('es_MX','Español MX'),('en_US','English')],default='es',required=True)
    _sql_constraints=[('company_unique','unique(company_id)','Ya existe una configuración para esta empresa.')]

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            if set(vals)-{'company_id','display_phone','template_name','language'} or vals.get('company_id',self.env.company.id)!=self.env.company.id:
                raise AccessError('Configura únicamente el número de la empresa activa.')
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        if set(vals)-{'display_phone','template_name','language'} or any(c.company_id!=self.env.company for c in self):
            raise AccessError('Configura únicamente el número de la empresa activa.')
        return super().write(vals)

    @api.constrains('display_phone','template_name','language')
    def _check_config(self):
        for record in self:
            try:
                if record.display_phone: phone(record.display_phone)
                template_payload('+18095550101',record.template_name,record.language,['prueba']*6)
            except ValueError as exc: raise ValidationError(str(exc)) from None


class Consent(models.Model):
    _name='uno360x.wa.consent'
    _description='Autorización de recordatorios por empresa y cliente'
    _check_company_auto=True
    company_id=fields.Many2one('res.company',required=True,default=lambda s:s.env.company,index=True)
    partner_id=fields.Many2one('res.partner',required=True,ondelete='restrict',check_company=True,index=True)
    recipient=fields.Char('WhatsApp del contacto de pagos',required=True)
    state=fields.Selection([('unknown','Sin autorización'),('granted','Autorizado'),('revoked','No contactar')],required=True,default='unknown')
    evidence=fields.Char('Cómo y cuándo autorizó el cliente')
    recorded_by=fields.Many2one('res.users',readonly=True)
    recorded_at=fields.Datetime(readonly=True)
    _sql_constraints=[('company_partner_unique','unique(company_id,partner_id)','Ya existe un contacto de pagos para este cliente en esta empresa.')]

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            if set(vals)-{'company_id','partner_id','recipient','state','evidence'} or vals.get('company_id',self.env.company.id)!=self.env.company.id:
                raise AccessError('Usa la configuración del cliente de la empresa activa.')
            partner=self.env['res.partner'].browse(vals.get('partner_id')).exists()
            partner.check_access('read')
            if not partner or partner!=partner.commercial_partner_id:
                raise ValidationError('Selecciona el cliente principal de la factura.')
            vals.update(recorded_by=self.env.uid,recorded_at=fields.Datetime.now())
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        if set(vals)-{'recipient','state','evidence'} or any(c.company_id!=self.env.company for c in self):
            raise AccessError('Usa la configuración del cliente de la empresa activa.')
        if 'recipient' in vals and vals.get('state')=='granted':
            changed=any(phone(vals['recipient'])!=phone(c.recipient) for c in self)
            if changed and (not (vals.get('evidence') or '').strip() or any(vals.get('evidence')==c.evidence for c in self)):
                raise UserError('El nuevo número requiere una nueva evidencia de autorización.')
        if 'recipient' in vals and 'state' not in vals:
            vals=dict(vals,state='unknown',evidence=False)
        vals=dict(vals,recorded_by=self.env.uid,recorded_at=fields.Datetime.now())
        return super().write(vals)

    @api.constrains('recipient','state','evidence','company_id','partner_id')
    def _check_consent(self):
        for record in self:
            try: phone(record.recipient)
            except ValueError as exc: raise ValidationError(str(exc)) from None
            if record.state=='granted' and not (record.evidence or '').strip():
                raise ValidationError('Indica la evidencia de autorización antes de habilitar recordatorios.')
            if record.partner_id.company_id and record.partner_id.company_id!=record.company_id:
                raise ValidationError('El contacto pertenece a otra empresa.')


class Reminder(models.Model):
    _name='uno360x.wa.reminder'
    _description='Borrador de recordatorio de cobro WhatsApp'
    _check_company_auto=True
    _order='id desc'
    company_id=fields.Many2one('res.company',required=True,index=True)
    move_id=fields.Many2one('account.move',required=True,check_company=True,ondelete='restrict')
    consent_id=fields.Many2one('uno360x.wa.consent',required=True,check_company=True,ondelete='restrict')
    collection_day=fields.Date(required=True)
    state=fields.Selection([('prepared','Borrador'),('simulated','Simulado: no enviado'),('blocked','Bloqueado')],required=True,readonly=True)
    document_number=fields.Char(readonly=True)
    recipient=fields.Char(readonly=True)
    body=fields.Text(readonly=True)
    payload=fields.Text(readonly=True,groups='account.group_account_manager,uno360x_whatsapp.group_collection_user')
    reason=fields.Char(readonly=True)
    prepared_by=fields.Many2one('res.users',readonly=True)
    simulated_by=fields.Many2one('res.users',readonly=True)
    simulated_at=fields.Datetime(readonly=True)
    _sql_constraints=[('daily_reminder_unique','unique(company_id,move_id,consent_id,collection_day)','Ya existe un aviso para esta factura y contacto en esta fecha.')]

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        if not self.env.su:
            invoice_query=self.env['account.move']._search([])
            domain=list(domain)+[('move_id','in',invoice_query)]
        return super()._search(domain,offset=offset,limit=limit,order=order)

    def check_access(self, operation):
        result=super().check_access(operation)
        if self and not self.env.su:
            # Elevated read is limited to the foreign-key metadata; invoice
            # authorization is checked again with the caller's actual env.
            self.sudo().mapped('move_id').with_env(self.env).check_access('read')
        return result

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError('Prepara el aviso desde la factura, después de validar su saldo y destinatario.')

    def write(self, vals):
        raise AccessError('El historial solo cambia mediante las acciones del recordatorio.')

    @api.model
    def _snapshot(self, move, consent):
        require_collector(self.env)
        move.check_access('read');consent.check_access('read')
        if not move or not consent or move.company_id!=self.env.company or consent.company_id!=move.company_id:
            raise AccessError('La factura y el contacto deben pertenecer a la empresa activa.')
        if move.move_type!='out_invoice' or move.state!='posted':
            raise UserError('Solo se preparan recordatorios de facturas de cliente confirmadas.')
        if move.payment_state in ('paid','reversed') or move.currency_id.is_zero(move.amount_residual) or move.amount_residual<0:
            raise UserError('Esta factura ya no tiene un saldo pendiente de cobro.')
        if 'uno360x_full_credit_encf' in move._fields and move.uno360x_full_credit_encf:
            raise UserError('La factura fue anulada con nota de crédito electrónica.')
        if consent.partner_id!=move.partner_id.commercial_partner_id or consent.state!='granted':
            raise UserError('El cliente no ha autorizado recordatorios de esta empresa o pidió no ser contactado.')
        connection=self.env['uno360x.wa.connection'].search([('company_id','=',move.company_id.id)],limit=1)
        number=move._ux_accepted_ecf_number() if hasattr(move,'_ux_accepted_ecf_number') else False
        number=number or move.name
        amount=format_amount(self.env,move.amount_residual,move.currency_id)
        due=move.invoice_date_due.strftime('%d/%m/%Y') if move.invoice_date_due else 'Sin vencimiento registrado'
        parameters=[move.company_id.name,move.partner_id.commercial_partner_id.name,number,move.currency_id.name,f'{move.amount_residual:.2f}',due]
        parameters=[' '.join(p.split())[:500] for p in parameters]
        payload=template_payload(consent.recipient,connection.template_name if connection else 'uno360x_aviso_factura',connection.language if connection else 'es',parameters)
        body=f'Hola, {parameters[1]}. {parameters[0]} te recuerda el saldo pendiente de la factura {number}: {amount}. Vencimiento: {due}. Si necesitas revisar el pago, responde a este mensaje. Gracias.'
        return {'document_number':number,'recipient':phone(consent.recipient),'body':body,'payload':json.dumps(payload,ensure_ascii=False)}

    @api.model
    def _prepare(self, move, consent):
        values=self._snapshot(move,consent)
        company_tz=self.env.company.partner_id.tz or 'America/Santo_Domingo'
        today=fields.Date.context_today(self.with_context(tz=company_tz))
        key=f'{self.env.company.id}:{move.id}:{consent.id}:{today}'
        lock=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big',signed=True)
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)',[lock])
        existing=self.search([('company_id','=',self.env.company.id),('move_id','=',move.id),('consent_id','=',consent.id),('collection_day','=',today)],limit=1)
        if existing:return existing
        return super(Reminder,self).create(dict(values,company_id=self.env.company.id,move_id=move.id,consent_id=consent.id,collection_day=today,state='prepared',prepared_by=self.env.uid))

    def _simulate(self):
        self.ensure_one();require_collector(self.env);self.check_access('write')
        if self.company_id!=self.env.company:raise AccessError('Selecciona la empresa del recordatorio.')
        self.env.cr.execute('SELECT id FROM uno360x_wa_reminder WHERE id=%s FOR UPDATE',[self.id])
        self.invalidate_recordset()
        if self.state!='prepared':return self
        self.move_id.invalidate_recordset();self.consent_id.invalidate_recordset()
        try:values=self._snapshot(self.move_id,self.consent_id)
        except (UserError,AccessError) as exc:
            super(Reminder,self).write({'state':'blocked','reason':str(exc)[:300]})
            return self
        super(Reminder,self).write(dict(values,state='simulated',reason='Simulación local. No se contactó a Meta ni al cliente.',simulated_by=self.env.uid,simulated_at=fields.Datetime.now()))
        return self
