import base64
import re
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden

from .certificate_input import certificate_password
from .workspace import WorkspaceController, can_manage_company


class FiscalAssistantController(WorkspaceController):
    @http.route('/uno360x-mi-empresa/facturacion-electronica', type='http', auth='user',
                methods=['GET', 'POST'], csrf=True)
    def fiscal_assistant(self, **_):
        service = self._service()
        if not can_manage_company(request.env.user):
            raise Forbidden()
        context = service._workspace_context()
        context.update(page_key='my_company', certificate_error='', certificate_details=None)
        company = request.env.company
        registration_model = request.env['uno360x.fiscal.registration'].sudo()
        registration = registration_model.search([('company_id', '=', company.id)], limit=1)
        tax_id = re.sub(r'[\s-]', '', company.vat or '')
        context.update(
            registration=registration if registration.tax_id == tax_id else registration_model,
            registration_error='', registration_saved=_.get('registry_saved') == '1',
            company_tax_id=tax_id, company_legal_name=company.sudo().uno360x_fiscal_legal_name or company.name,
        )
        if request.httprequest.method == 'POST' and request.httprequest.form.get('operation') == 'registry':
            try:
                self._save_registration(company, registration_model, tax_id)
            except ValueError as error:
                context['registration_error'] = str(error)
            else:
                return request.redirect('/uno360x-mi-empresa/facturacion-electronica?registry_saved=1#registro-rnc', code=303)
        elif request.httprequest.method == 'POST':
            try:
                context['certificate_details'] = self._check_certificate()
            except ValueError as error:
                context['certificate_error'] = str(error)
        return self._render('uno360x_workspace.fiscal_assistant', context)

    @staticmethod
    def _save_registration(company, registrations, tax_id):
        form = request.httprequest.form
        registered_rnc = re.sub(r'[\s-]', '', form.get('registered_rnc', ''))
        if not re.fullmatch(r'(?:[0-9]{9}|[0-9]{11})', tax_id) or registered_rnc != tax_id:
            raise ValueError('El RNC o la cédula del registro debe coincidir con el dato en Mi empresa.')
        address = ' '.join(form.get('fiscal_address', '').split())
        legal_name = ' '.join(form.get('legal_name', '').split())
        if not 1 <= len(legal_name) <= 200 or not 1 <= len(address) <= 500:
            raise ValueError('Escribe la razón social y la dirección que figuran en el registro.')
        if form.get('confirmed') != '1':
            raise ValueError('Confirma que comparaste los datos con el registro del RNC.')
        upload = request.httprequest.files.get('rnc_document')
        if not upload or not upload.filename.lower().endswith('.pdf'):
            raise ValueError('Selecciona el registro del RNC en formato PDF.')
        contents = upload.stream.read(5_000_001)
        if len(contents) > 5_000_000 or not contents.startswith(b'%PDF-'):
            raise ValueError('Carga un PDF válido de hasta 5 MB.')
        request.env.cr.execute('UPDATE res_company SET id = id WHERE id = %s', [company.id])
        current = registrations.search([('company_id', '=', company.id)], limit=1)
        values = {
            'company_id': company.id, 'tax_id': tax_id, 'legal_name': legal_name,
            'fiscal_address': address, 'document': base64.b64encode(contents),
            'confirmed_by': request.env.uid,
        }
        if current:
            current.write(values)
        else:
            registrations.create(values)

    @staticmethod
    def _check_certificate():
        files = request.httprequest.files
        certificate = files.get('certificate')
        if not certificate or not certificate.filename.lower().endswith(('.p12', '.pfx')):
            raise ValueError('Selecciona un certificado .p12 o .pfx.')
        contents = certificate.stream.read(5_000_001)
        if not contents or len(contents) > 5_000_000:
            raise ValueError('El certificado debe pesar hasta 5 MB.')
        credentials = files.get('credentials')
        if not credentials or not credentials.filename.lower().endswith('.txt'):
            raise ValueError('Adjunta el archivo credentials.txt del certificado.')
        try:
            password = certificate_password(credentials.stream.read(8193))
        except UnicodeError:
            raise ValueError('No se pudo leer credentials.txt. Adjunta el archivo original del certificado.') from None
        try:
            key, cert, _ = pkcs12.load_key_and_certificates(contents, password.encode('utf-8'))
        except ValueError:
            raise ValueError('No se pudo abrir el certificado con la clave indicada.') from None
        if not isinstance(key, rsa.RSAPrivateKey) or cert is None or key.key_size < 2048:
            raise ValueError('El archivo debe contener un certificado de firma RSA y su clave privada.')
        start = getattr(cert, 'not_valid_before_utc', None)
        end = getattr(cert, 'not_valid_after_utc', None)
        if start is None:
            start = cert.not_valid_before.replace(tzinfo=timezone.utc)
            end = cert.not_valid_after.replace(tzinfo=timezone.utc)
        if not start <= datetime.now(timezone.utc) <= end:
            raise ValueError('El certificado está vencido o aún no está vigente.')
        try:
            can_sign = cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature
        except x509.ExtensionNotFound:
            can_sign = False
        if not can_sign or key.public_key().public_numbers() != cert.public_key().public_numbers():
            raise ValueError('El certificado no es apto para firmar con la clave incluida.')
        return {'expires': end.date().isoformat(), 'fingerprint': cert.fingerprint(hashes.SHA256()).hex()}
