from base64 import b64decode, b64encode
from datetime import datetime
from urllib.parse import urlencode

from lxml import etree

from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'


    def _uno360x_invoice_accepted_issue(self):
        self.ensure_one()
        self.check_access('read')
        model = 'uno360x.ecf.issue'
        if model not in self.env.registry:
            return False
        return self.env[model].sudo().search([
            ('move_id', '=', self.id), ('company_id', '=', self.company_id.id),
            ('state', 'in', ('accepted', 'conditional')), ('signed_xml', '!=', False),
        ], limit=1)

    def _ux_accepted_ecf_number(self):
        if len(self) == 1 and isinstance(self.id, int):
            issue = self._uno360x_invoice_accepted_issue()
            if issue:
                return issue.encf
        return super()._ux_accepted_ecf_number()

    def _get_report_base_filename(self):
        if len(self) == 1:
            issue = self._uno360x_invoice_accepted_issue()
            if issue and issue.encf:
                return issue.encf
        return super()._get_report_base_filename()

    def _get_invoice_legal_documents(self, filetype, allow_fallback=False):
        if filetype == 'pdf' and self._uno360x_invoice_accepted_issue():
            report = self.env.ref('account.account_invoices').with_context(
                report_pdf_no_attachment=True,
            )
            content, report_type = report._render_qweb_pdf(report.report_name, self.ids)
            return {
                'filename': self._get_invoice_report_filename(),
                'filetype': 'application/pdf',
                'content': content,
            }
        return super()._get_invoice_legal_documents(filetype, allow_fallback=allow_fallback)

    def _get_invoice_report_filename(self, extension='pdf'):
        issue = self._uno360x_invoice_accepted_issue()
        if issue and issue.encf:
            return f'{issue.encf}.{extension}'
        return super()._get_invoice_report_filename(extension=extension)

    def _uno360x_production_stamp(self):
        self.ensure_one()
        self.check_access('read')
        issue = self._uno360x_invoice_accepted_issue()
        if not issue:
            return {}
        try:
            raw = b64decode(issue.signed_xml, validate=True)
            xml = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True))
            encf = xml.findtext('Encabezado/IdDoc/eNCF')
            issuer = xml.findtext('Encabezado/Emisor/RNCEmisor')
            total = xml.findtext('Encabezado/Totales/MontoTotal')
            signed_at = xml.findtext('FechaHoraFirma')
            issue_date = xml.findtext('Encabezado/Emisor/FechaEmision')
            if (xml.tag != 'ECF' or xml.getroottree().docinfo.doctype or
                    encf != issue.encf or issuer != (self.company_id.vat or '').replace('-', '').replace(' ', '') or
                    not all((total, signed_at, issue_date))):
                return {}
            signature = xml.findtext('{http://www.w3.org/2000/09/xmldsig#}Signature/{http://www.w3.org/2000/09/xmldsig#}SignatureValue') or ''
            code = ''.join(signature.split())[:6]
            if len(code) != 6:
                return {}
        except (ValueError, etree.XMLSyntaxError):
            return {}
        from urllib.parse import urlencode, quote
        params = dict(RncEmisor=issuer, ENCF=encf, MontoTotal=total, CodigoSeguridad=code)
        if issue.signed_summary:
            url = 'https://fc.dgii.gov.do/ecf/ConsultaTimbreFC'
        else:
            url = 'https://ecf.dgii.gov.do/ecf/ConsultaTimbre'
            params.update(FechaEmision=issue_date, FechaFirma=signed_at)
            buyer = xml.findtext('Encabezado/Comprador/RNCComprador')
            if buyer:
                params['RncComprador'] = buyer
        qr = self.env['ir.actions.report'].barcode('QR', url + '?' + urlencode(params, quote_via=quote),
                                                    width=360, height=360, quiet=1)
        return dict(encf=encf, code=code, signed_at=signed_at, qr=b64encode(qr),
                    valid_until=xml.findtext('Encabezado/IdDoc/FechaVencimientoSecuencia'))

    def _uno360x_modern_stamp(self):
        self.ensure_one()
        self.check_access('read')
        production = self._uno360x_production_stamp()
        if production:
            return dict(production, production=True)
        model = 'uno360x.ecf.certification.request'
        if model not in self.env.registry:
            return {}
        document = self.env[model].sudo().search([
            ('move_id', '=', self.id), ('company_id', '=', self.company_id.id),
            ('signed_xml', '!=', False),
            ('state', 'in', ('submitted', 'accepted', 'conditional')),
        ], order='id desc', limit=1)
        if not document:
            return {}
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
            xml = etree.fromstring(b64decode(document.signed_xml, validate=True), parser)
            if xml.tag != 'ECF' or xml.getroottree().docinfo.doctype:
                return {}
            encf = xml.findtext('Encabezado/IdDoc/eNCF')
            signature = xml.findtext('{http://www.w3.org/2000/09/xmldsig#}Signature/{http://www.w3.org/2000/09/xmldsig#}SignatureValue')
            signed_at = xml.findtext('FechaHoraFirma')
            issuer = xml.findtext('Encabezado/Emisor/RNCEmisor')
            issue_date = xml.findtext('Encabezado/Emisor/FechaEmision')
            total = xml.findtext('Encabezado/Totales/MontoTotal')
            if (encf != document.encf or issuer != self.company_id.vat
                    or not all((encf, signature, signed_at, issuer, issue_date, total))):
                return {}
            datetime.strptime(signed_at, '%d-%m-%Y %H:%M:%S')
            code = ''.join(signature.split())[:6]
            if len(code) != 6:
                return {}
            buyer = xml.findtext('Encabezado/Comprador/RNCComprador')
            params = {'RncEmisor': issuer}
            if buyer:
                params['RncComprador'] = buyer
            params.update(ENCF=encf, FechaEmision=issue_date, MontoTotal=total,
                          FechaFirma=signed_at, CodigoSeguridad=code)
            url = 'https://ecf.dgii.gov.do/certecf/ConsultaTimbre?' + urlencode(params)
            return {
                'encf': encf,
                'code': code,
                'signed_at': signed_at,
                'valid_until': xml.findtext('Encabezado/IdDoc/FechaVencimientoSecuencia'),
                'qr': b64encode(self.env['ir.actions.report'].barcode(
                    'QR', url, width=360, height=360, quiet=1)),
            }
        except (ValueError, etree.XMLSyntaxError):
            return {}
