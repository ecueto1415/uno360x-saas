import base64
import hashlib
import json
import re
from urllib.parse import urlencode, quote
from lxml import etree
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.outsolutech_ecf_flujo.builder import build_invoice, validate_signed
from .crypto import sign_xml, load_identity, verify_xml
from .client import Client
from .production_trust import validate_certificate

RNC = '132364805'
CERTIFICATE = '5187cb95c492e1d726cf3a69e0c597e1c88a898841a0e49d8cc3805fed660944'


def preserve_history(records):
    if records:
        raise UserError('Conserve el modulo y el historial fiscal de produccion.')


class Company(models.Model):
    _inherit = 'res.company'
    outs_ecf_production_enabled = fields.Boolean(string='Emision e-CF productiva habilitada', groups='account.group_account_manager', copy=False)
    outs_ecf_range_ids = fields.One2many('outsolutech.ecf.range','company_id',string='Autorizaciones e-NCF',groups='account.group_account_manager')

    def action_outs_ecf_production_connection(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError('Acceso exclusivo a responsables de contabilidad.')
        if re.sub(r'\D','',self.vat or '') != RNC:
            raise UserError('Este certificado corresponde exclusivamente a OUTSOLUTECH.')
        from pathlib import Path
        directory=Path('/etc/odoo18/ecf-pruebas')
        p12=(directory/'identity.p12').read_bytes();password=(directory/'password').read_bytes()
        _,certificate=load_identity(p12,password)
        from cryptography.hazmat.primitives import hashes
        if certificate.fingerprint(hashes.SHA256()).hex()!=CERTIFICATE:
            raise UserError('El certificado no corresponde a la identidad autorizada.')
        validate_certificate(certificate,'/etc/uno360x-dgii-production/trust')
        try: expiry=Client(p12,password,'ecf').authenticate()
        except ValueError as error:raise UserError(str(error)) from None
        return {'type':'ir.actions.client','tag':'display_notification','params':{'title':'Conexion DGII produccion correcta','message':'Certificado autenticado. Vigencia de sesion: %s. No se envio ninguna factura.'%expiry,'type':'success','sticky':True}}


class Range(models.Model):
    _name = 'outsolutech.ecf.range'
    _description = 'Autorizacion de secuencias e-NCF productivas'
    _order = 'valid_until,id'
    _check_company_auto = True
    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company',required=True,default=lambda self:self.env.company,ondelete='restrict')
    document_type = fields.Selection([('31','Credito fiscal E31'),('33','Nota de debito E33'),('34','Nota de credito E34'),('43','Gastos menores E43'),('44','Regimenes especiales E44'),('45','Gubernamental E45')],required=True,default='31')
    first_number = fields.Char(string='Desde (10 digitos)',required=True)
    last_number = fields.Char(string='Hasta (10 digitos)',required=True)
    next_number = fields.Char(string='Siguiente (10 digitos)',required=True)
    valid_until = fields.Date(string='Fecha de vencimiento autorizada',help='Sin fecha solo cuando la autorizacion DGII de E34 indica N/A.')
    authorization_reference = fields.Char(string='Solicitud o autorizacion DGII',required=True)
    evidence = fields.Binary(string='Constancia de autorizacion OFV',attachment=True,required=True)
    evidence_filename = fields.Char()
    active = fields.Boolean(default=True)
    issued_count = fields.Integer(readonly=True,default=0)

    @api.constrains('first_number','last_number','next_number','company_id','document_type','valid_until')
    def _check_range(self):
        for row in self:
            self.env.cr.execute('SELECT pg_advisory_xact_lock(%s,%s)',(18431,row.company_id.id*100+int(row.document_type)))
            if re.sub(r'\D','',row.company_id.vat or '') != RNC:
                raise ValidationError('Autorizacion exclusiva de OUTSOLUTECH.')
            if not row.valid_until and row.document_type!='34':
                raise ValidationError('Este tipo requiere fecha de vencimiento autorizada.')
            numbers=(row.first_number,row.last_number,row.next_number)
            if any(not re.fullmatch(r'\d{10}',str(n or '')) for n in numbers[:2]) or not re.fullmatch(r'\d{10}|10000000000',str(numbers[2] or '')):
                raise ValidationError('Ingrese secuencias numericas de diez digitos.')
            first,last,nxt=map(int,numbers)
            if not 1<=first<=last<=9999999999 or not first<=nxt<=last+1:
                raise ValidationError('Rango de secuencias incoherente.')
            others=self.with_context(active_test=False).search([('company_id','=',row.company_id.id),('document_type','=',row.document_type),('id','!=',row.id)])
            if any(first<=int(other.last_number) and last>=int(other.first_number) for other in others):
                raise ValidationError('La autorizacion se solapa con otra secuencia registrada.')

    def write(self, vals):
        if {'issued_count','next_number'}.intersection(vals):
            raise AccessError('La secuencia siguiente se actualiza exclusivamente al reservar un e-NCF.')
        if set(vals)-{'active','name'} and any(row.issued_count for row in self):
            raise UserError('Una autorizacion utilizada no puede modificarse; registre otra autorizacion.')
        return super().write(vals)

    def unlink(self):
        if any(row.issued_count for row in self):raise UserError('Conserve las autorizaciones utilizadas.')
        return super().unlink()

    def _reserve(self):
        self.ensure_one()
        if self.document_type not in ('31','45'):
            raise UserError('Autorizacion registrada; el flujo XML de este tipo aun no esta habilitado.')
        self.env.cr.execute('SELECT id FROM outsolutech_ecf_range WHERE id=%s FOR UPDATE',(self.id,))
        self.invalidate_recordset()
        if not self.active or self.valid_until < fields.Date.context_today(self):
            raise UserError('La autorizacion e-NCF no esta vigente.')
        nxt=int(self.next_number)
        if nxt>int(self.last_number):raise UserError('La autorizacion e-NCF esta agotada. Registre otra autorizacion OFV.')
        # Keep the final exhausted value representable even at the absolute limit.
        following=str(nxt+1).zfill(10)
        super(Range,self).write({'next_number':following,'issued_count':self.issued_count+1})
        return 'E'+self.document_type+str(nxt).zfill(10)


class Move(models.Model):
    _inherit = 'account.move'
    outs_ecf_production_enabled = fields.Boolean(related='company_id.outs_ecf_production_enabled')

    def _outs_ecf_production_report(self):
        self.ensure_one();self.check_access('read')
        if self.company_id not in self.env.companies:
            raise AccessError('Seleccione la empresa de la factura.')
        return self.env['outsolutech.ecf.document'].sudo().search([('move_id','=',self.id),('environment','=','ecf'),('state','in',['accepted','conditional'])],limit=1)

    def action_outs_ecf_production(self):
        self.ensure_one();self.check_access('read')
        if not self.company_id.outs_ecf_production_enabled:
            raise UserError('Complete la habilitacion de produccion y sus autorizaciones e-NCF.')
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError('Acceso exclusivo a responsables de contabilidad.')
        docs=self.env['outsolutech.ecf.document'].search([('move_id','=',self.id)],limit=1)
        if docs and docs.environment!='ecf':
            raise UserError('Esta factura tiene un expediente de prueba. No se convierte a produccion.')
        if not docs:
            # Invoice actions carry defaults for account.move (move_type,
            # journal, currency, etc.). Do not apply them to a fiscal document.
            context={key:value for key,value in self.env.context.items() if not key.startswith('default_')}
            context['default_environment']='ecf'
            docs=self.env['outsolutech.ecf.document'].with_context(context).create({'move_id':self.id})
        return {'type':'ir.actions.act_window','res_model':docs._name,'res_id':docs.id,'views':[(self.env.ref('outsolutech_ecf_production.document_form').id,'form')],'target':'current'}


class Document(models.Model):
    _inherit = 'outsolutech.ecf.document'
    environment = fields.Selection(selection_add=[('ecf','Produccion fiscal')],ondelete={'ecf':preserve_history})
    state = fields.Selection(selection_add=[('accepted','Aceptado por DGII'),('conditional','Aceptado condicional por DGII')])
    production_range_id = fields.Many2one('outsolutech.ecf.range',readonly=True,copy=False,ondelete='restrict',check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        permitted={'move_id','income_type','payment_type','document_type','environment'}
        if any(key.startswith('default_') and key[8:] in self._fields and key[8:] not in permitted for key in self.env.context):
            raise AccessError('No se permite establecer datos fiscales protegidos mediante valores predeterminados.')
        docs=super().create(vals_list)
        if any(d.environment=='ecf' and (d.state!='draft' or d.encf or d.signed_xml or d.track_id or d.production_range_id) for d in docs):
            raise AccessError('El expediente productivo debe comenzar vacio y pendiente de preparar.')
        return docs

    def _guard(self):
        super()._guard()
        if any(doc.environment=='ecf' and not doc.company_id.outs_ecf_production_enabled for doc in self):
            raise UserError('Emision productiva deshabilitada para esta empresa.')

    def _production_range(self):
        self.ensure_one()
        if self.production_range_id:
            if self.production_range_id.company_id!=self.company_id or self.production_range_id.document_type!=self.document_type:
                raise UserError('La autorizacion no corresponde a esta empresa y tipo de comprobante.')
            return self.production_range_id
        ranges=self.env['outsolutech.ecf.range'].search([('company_id','=',self.company_id.id),('document_type','=',self.document_type),('valid_until','>=',fields.Date.context_today(self))])
        for row in ranges:
            if int(row.next_number)<=int(row.last_number):return row
        raise UserError('No hay secuencias e-NCF autorizadas y vigentes para este tipo. Registre la constancia de OFV.')

    def _data(self):
        data=super()._data()
        if self.environment=='ecf':data['test_expiry']=str(self._production_range().valid_until)
        return data

    def _identity(self):
        p12,password=super()._identity()
        if self.environment=='ecf':
            _,certificate=load_identity(p12,password)
            from cryptography.hazmat.primitives import hashes
            if certificate.fingerprint(hashes.SHA256()).hex()!=CERTIFICATE:
                raise UserError('Certificado distinto a la identidad productiva autorizada.')
            validate_certificate(certificate,'/etc/uno360x-dgii-production/trust')
        return p12,password

    def _client(self):
        if self.environment!='ecf':return super()._client()
        self._guard();p12,password=self._identity()
        return Client(p12,password,'ecf')

    def action_authenticate(self):
        if self.environment!='ecf':return super().action_authenticate()
        self.ensure_one();self._guard()
        try:expiry=self._client().authenticate()
        except ValueError as error:raise UserError(str(error)) from None
        self._set({'authentication_expiry':expiry})
        return {'type':'ir.actions.client','tag':'display_notification','params':{'title':'Conexion DGII produccion correcta','message':'Certificado autenticado. No se envio una factura.','type':'success','sticky':True}}

    def action_prepare(self):
        if self.environment!='ecf':return super().action_prepare()
        self.ensure_one();self._guard()
        self.env.cr.execute('SELECT id FROM outsolutech_ecf_document WHERE id=%s FOR UPDATE',(self.id,));self.invalidate_recordset()
        if self.state!='draft':raise UserError('El e-NCF ya esta preparado; no se reasigna.')
        self.env.cr.execute('SELECT id FROM account_move WHERE id=%s FOR UPDATE',(self.move_id.id,));self.move_id.invalidate_recordset();self.move_id.invoice_line_ids.invalidate_recordset()
        self.env.cr.execute('SELECT id FROM res_company WHERE id=%s FOR UPDATE',(self.company_id.id,))
        row=self._production_range();data=self._data();p12,password=self._identity()
        try:
            validate_signed(sign_xml(build_invoice(data,'E'+self.document_type+'0000000001'),p12,password))
            encf=row._reserve();signed=sign_xml(build_invoice(data,encf),p12,password);validate_signed(signed)
        except ValueError as error:raise UserError(str(error)) from None
        root=etree.fromstring(signed);snapshot=json.dumps(data,ensure_ascii=False,sort_keys=True)
        self._set({'name':encf+' - PRODUCCION','production_range_id':row.id,'encf':encf,'signed_xml':base64.b64encode(signed),'xml_filename':RNC+encf+'.xml','snapshot_json':snapshot,'snapshot_hash':hashlib.sha256(snapshot.encode()).hexdigest(),'signed_hash':hashlib.sha256(signed).hexdigest(),'signature_time':root.findtext('FechaHoraFirma'),'security_code':root.findtext('{http://www.w3.org/2000/09/xmldsig#}Signature/{http://www.w3.org/2000/09/xmldsig#}SignatureValue')[:6],'state':'prepared','result_text':'XML productivo firmado y validado. Pendiente de envio a DGII.'})

    def _check_integrity(self):
        signed=super()._check_integrity()
        if self.environment=='ecf':
            p12,password=self._identity();_,certificate=load_identity(p12,password)
            verify_xml(signed,certificate)
            row=self.production_range_id
            if not row or not row.valid_until or row.valid_until<fields.Date.context_today(self) or not self.encf or self.encf[:3]!='E'+row.document_type or not int(row.first_number)<=int(self.encf[3:])<=int(row.last_number):
                raise UserError('El e-NCF no corresponde a una autorizacion productiva vigente.')
        return signed

    def action_queue(self):
        result=super().action_queue()
        if self.environment=='ecf':self._set({'result_text':'En cola de produccion. Se enviara una sola vez a DGII y se consultara su resultado.'})
        return result

    @api.model
    def _cron_process(self):
        # The inherited worker selects via SQL; include ORM changes that may
        # have been enqueued within the current transaction before that query.
        self.flush_model(['state','write_date'])
        return super()._cron_process()

    @api.depends('snapshot_json','encf','security_code','signature_time','state','environment')
    def _compute_qr(self):
        super()._compute_qr()
        for doc in self.filtered(lambda d:d.environment=='ecf' and d.qr_url):
            doc.qr_url=doc.qr_url.replace('/testecf/','/ecf/')
            doc.qr_image='/report/barcode/?barcode_type=QR&value='+quote(doc.qr_url,safe='')+'&width=220&height=220'

    def action_print(self):
        if self.environment!='ecf':return super().action_print()
        self.ensure_one();self._guard()
        if self.state not in ('accepted','conditional'):
            raise UserError('Espere la aceptacion de DGII para imprimir la representacion fiscal.')
        return self.env.ref('outsolutech_ecf_production.report_production').report_action(self)
