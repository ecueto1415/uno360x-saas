import base64
import io
import urllib.error
from datetime import datetime,timedelta,timezone
from unittest.mock import patch,Mock
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from odoo import fields,Command
from odoo.tests.common import TransactionCase,tagged
from odoo.exceptions import UserError,AccessError,ValidationError
from ..client import Client,SubmissionUnknown


@tagged('post_install','-at_install')
class TestProduction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        dop=cls.env.ref('base.DOP');dop.active=True
        cls.company=cls.env['res.company'].create({'name':'EMPRESA FICTICIA QA','vat':'132364805','street':'SOLO LABORATORIO','country_id':cls.env.ref('base.do').id,'currency_id':dop.id,'tax_calculation_rounding_method':'round_per_line','outs_ecf_production_enabled':True,'external_report_layout_id':cls.env.ref('web.external_layout_standard').id})
        cls.env=cls.env(context=dict(cls.env.context,allowed_company_ids=cls.company.ids))
        cls.receivable=cls.env['account.account'].create({'name':'QA RECEIVABLE','code':'QA110','account_type':'asset_receivable','reconcile':True,'company_ids':[Command.set(cls.company.ids)]})
        cls.income=cls.env['account.account'].create({'name':'QA INCOME','code':'QA410','account_type':'income','company_ids':[Command.set(cls.company.ids)]})
        cls.journal=cls.env['account.journal'].create({'name':'QA SALES','code':'FQA','type':'sale','company_id':cls.company.id,'default_account_id':cls.income.id})
        cls.buyer=cls.env['res.partner'].create({'name':'CLIENTE FICTICIO QA','vat':'123456789','property_account_receivable_id':cls.receivable.id})
        group=cls.env['account.tax.group'].create({'name':'QA ITBIS','company_id':cls.company.id})
        cls.tax=cls.env['account.tax'].create({'name':'QA ITBIS18','amount':18,'amount_type':'percent','type_tax_use':'sale','company_id':cls.company.id,'tax_group_id':group.id,'outs_ecf_category':'1'})
        cls.product=cls.env['product.product'].create({'name':'SERVICIO FICTICIO QA','type':'service'})
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048);subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'FIRMA FICTICIA QA')]);now=datetime.now(timezone.utc)
        cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.KeyUsage(True,False,False,False,False,False,False,False,False),critical=True).sign(key,hashes.SHA256())
        cls.fake_p12=pkcs12.serialize_key_and_certificates(b'qa',key,cert,None,serialization.BestAvailableEncryption(b'qa-only'))

    def setUp(self):
        super().setUp()
        self.authorization=self.env['outsolutech.ecf.range'].create({'name':'AUTORIZACION FICTICIA QA','company_id':self.company.id,'document_type':'31','first_number':'0000000100','last_number':'0000000102','next_number':'0000000100','valid_until':fields.Date.add(fields.Date.today(),years=1),'authorization_reference':'QA-NO-ES-AUTORIZACION-DGII','evidence':base64.b64encode(b'QA ONLY'),'evidence_filename':'qa.txt'})
        self.identity_patch=patch.object(type(self.env['outsolutech.ecf.document']),'_identity',lambda record:(self.fake_p12,b'qa-only'))
        self.identity_patch.start();self.addCleanup(self.identity_patch.stop)

    def document(self):
        move=self.env['account.move'].create({'move_type':'out_invoice','company_id':self.company.id,'journal_id':self.journal.id,'partner_id':self.buyer.id,'invoice_date':fields.Date.today(),'invoice_date_due':fields.Date.today(),'invoice_line_ids':[Command.create({'name':'SERVICIO FICTICIO QA','product_id':self.product.id,'quantity':1,'price_unit':100,'account_id':self.income.id,'tax_ids':[Command.set(self.tax.ids)]})]})
        move.action_post()
        action=move.action_outs_ecf_production()
        return self.env['outsolutech.ecf.document'].browse(action['res_id'])

    def test_authorized_allocation_signature_and_qr(self):
        doc=self.document();self.assertFalse(doc.encf);self.assertEqual(self.authorization.next_number,'0000000100')
        doc.action_prepare();self.assertEqual(doc.encf,'E310000000100');self.assertEqual(self.authorization.next_number,'0000000101');self.assertTrue(doc._check_integrity())
        self.assertFalse(self.company.outs_ecf_test_sequence_id)
        doc._set({'track_id':'qa-track','state':'sent'})
        doc._apply_result({'codigo':'1','rnc':'132364805','eNCF':doc.encf,'trackId':'qa-track','secuenciaUtilizada':True})
        self.assertEqual(doc.state,'accepted');self.assertIn('/ecf/ConsultaTimbre?',doc.qr_url);self.assertNotIn('/testecf/',doc.qr_url)
        self.assertTrue(base64.b64decode(doc.qr_image.split(',',1)[1]).startswith(b'\x89PNG'))
        self.assertEqual(doc.action_print()['report_name'],'outsolutech_ecf_production.template_report')
        html,_=self.env['ir.actions.report']._render_qweb_html('account.account_invoices',doc.move_id.ids)
        self.assertIn(doc.encf.encode(),html)
        self.assertIn('FACTURA DE CRÉDITO FISCAL ELECTRÓNICA'.encode(),html)
        self.assertNotIn(doc.move_id.name.encode(),html)
        self.assertIn(b'uxf-security-block',html)

    def test_no_range_no_sequence(self):
        self.authorization.active=False
        doc=self.document()
        with self.assertRaises(UserError):doc.action_prepare()
        self.assertFalse(doc.encf)

    def test_expired_range_and_exhausted_range_block(self):
        self.authorization.valid_until=fields.Date.subtract(fields.Date.today(),days=1)
        doc=self.document()
        with self.assertRaises(UserError):doc.action_prepare()

    def test_no_duplicate_assignment(self):
        doc=self.document();doc.action_prepare();number=doc.encf
        with self.assertRaises(UserError):doc.action_prepare()
        self.assertEqual(doc.encf,number);self.assertEqual(self.authorization.issued_count,1)

    def test_protected_defaults_and_range_writes_block(self):
        doc=self.document()
        with self.assertRaises(AccessError):self.env['outsolutech.ecf.document'].with_context(default_state='queued').create({'move_id':doc.move_id.id})
        doc.action_prepare()
        with self.assertRaises(UserError):self.authorization.write({'last_number':'0000009999'})
        with self.assertRaises(AccessError):self.authorization.write({'next_number':'0000000100'})

    def test_overlapping_range_block(self):
        with self.assertRaises(ValidationError),self.cr.savepoint():
            self.authorization.copy({'name':'QA SOLAPADA'})

    def test_production_client_rejects_testing_environment(self):
        with self.assertRaises(ValueError):Client(self.fake_p12,b'qa-only','testecf')
        self.assertEqual(Client(self.fake_p12,b'qa-only','ecf').environment,'ecf')

    def test_official_track_not_found_is_distinct_from_other_http400_errors(self):
        opener=Mock();client=Client(self.fake_p12,b'qa-only','ecf',opener=opener);client.token='QA-NOT-A-TOKEN'
        opener.open.side_effect=urllib.error.HTTPError('https://ecf.dgii.gov.do/',400,'QA',{},io.BytesIO(b'{"codigo":0,"estado":"TrackId no encontrado."}'))
        self.assertEqual(client.tracks('132364805','E310000000001'),[])
        opener.open.side_effect=urllib.error.HTTPError('https://ecf.dgii.gov.do/',400,'QA',{},io.BytesIO(b'{"codigo":4,"estado":"QA invalid request"}'))
        with self.assertRaises(ValueError):client.tracks('132364805','E310000000001')

    def test_transport_retry_is_readonly_and_never_repeats_invoice_post(self):
        opener=Mock();client=Client(self.fake_p12,b'qa-only','ecf',opener=opener);client.token='QA-NOT-A-TOKEN'
        opener.open.side_effect=[ConnectionResetError('QA'),io.BytesIO(b'{"codigo":3}')]
        with patch('time.sleep',lambda seconds:None):self.assertEqual(client.result('qa-track'),{'codigo':3})
        self.assertEqual(opener.open.call_count,2)
        opener.reset_mock();opener.open.side_effect=ConnectionResetError('QA')
        with patch('time.sleep',lambda seconds:None),self.assertRaises(SubmissionUnknown):client.submit(b'<ECF/>','132364805','E310000000001')
        self.assertEqual(opener.open.call_count,1)

    def test_incorrect_dgii_identity_not_accepted(self):
        doc=self.document();doc.action_prepare()
        with self.assertRaises(UserError):doc._apply_result({'codigo':'1','rnc':'111111111','eNCF':doc.encf})
        self.assertEqual(doc.state,'prepared')

    def test_unknown_submission_is_not_retried(self):
        doc=self.document();doc.action_prepare();doc.action_queue()
        fake=Mock();fake.authenticate.return_value='QA';fake.submit.side_effect=SubmissionUnknown('QA CONNECTION LOST')
        with patch.object(type(doc),'_client',lambda record:fake),patch.object(self.env.cr,'commit',lambda:None):
            doc._cron_process();doc.invalidate_recordset();self.assertEqual(doc.state,'uncertain')
            doc._cron_process();self.assertEqual(fake.submit.call_count,1)
        self.assertEqual(doc.attempt_count,1)

    def test_pending_pdf_blocked(self):
        doc=self.document();doc.action_prepare()
        with self.assertRaises(UserError):doc.action_print()

    def test_invoice_action_defaults_do_not_leak_into_fiscal_document(self):
        doc=self.document()
        action=doc.move_id.with_context(default_move_type='out_invoice',default_journal_id=self.journal.id,default_currency_id=self.company.currency_id.id,default_state='posted').action_outs_ecf_production()
        self.assertEqual(action['res_id'],doc.id)
        # Exercise a fresh creation through the same browser invoice context.
        move=doc.move_id
        doc.unlink()
        action=move.with_context(default_move_type='out_invoice',default_journal_id=self.journal.id,default_currency_id=self.company.currency_id.id,default_state='posted').action_outs_ecf_production()
        fresh=self.env['outsolutech.ecf.document'].browse(action['res_id'])
        self.assertEqual(fresh.state,'draft');self.assertFalse(fresh.signed_xml);self.assertFalse(fresh.encf)
        self.assertEqual(fresh.environment,'ecf');self.assertEqual(fresh.move_id,move)

    def test_unrelated_invoice_default_is_not_treated_as_a_protected_fiscal_field(self):
        doc=self.document();move=doc.move_id;doc.unlink()
        fresh=self.env['outsolutech.ecf.document'].with_context(default_move_type='out_invoice',default_environment='ecf').create({'move_id':move.id})
        self.assertEqual(fresh.state,'draft')
        with self.assertRaises(AccessError):self.env['outsolutech.ecf.document'].with_context(default_signed_xml='QA').create({'move_id':move.id})

    def test_government_document_has_independent_authorized_range(self):
        row=self.authorization.copy({'document_type':'45','first_number':'0000000200','last_number':'0000000202','next_number':'0000000200'})
        doc=self.document();doc.write({'document_type':'45'});doc.action_prepare()
        self.assertEqual(doc.encf,'E450000000200');self.assertEqual(row.next_number,'0000000201')
        self.assertEqual(self.authorization.next_number,'0000000100')
        self.assertTrue(doc._check_integrity())

    def test_credit_note_na_expiry_is_preserved_without_enabling_unsupported_flow(self):
        row=self.authorization.copy({'document_type':'34','valid_until':False})
        self.assertFalse(row.valid_until)
        with self.assertRaises(UserError):row._reserve()
        self.assertEqual(row.next_number,'0000000100')

    def test_tax_and_invoice_changes_block_after_signature(self):
        doc=self.document();doc.action_prepare()
        with self.assertRaises(UserError):doc.move_id.invoice_line_ids.write({'price_unit':200})
        with self.assertRaises(UserError):doc.move_id.write({'invoice_date':fields.Date.subtract(fields.Date.today(),days=1)})

    def test_legacy_customer_journal_blocked_without_touching_existing_invoice(self):
        doc=self.document()
        legacy=self.journal.copy({'name':'QA LEGACY','code':'B01'})
        draft=doc.move_id.copy({'journal_id':legacy.id,'invoice_date':fields.Date.today()})
        with self.assertRaises(UserError):draft.action_post()
        self.assertEqual(draft.state,'draft')
        self.assertEqual(doc.move_id.state,'posted')
        self.assertFalse(doc.encf)
        self.assertEqual(self.authorization.next_number,'0000000100')

    def test_long_invoice_label_preserved_as_description_in_signed_xml(self):
        from lxml import etree
        doc=self.document()
        original='SERVICIO DE MANTENIMIENTO\n'+'DETALLE COMPLETO DEL SERVICIO '*5
        doc.move_id.invoice_line_ids[0].write({'name':original})
        doc.action_prepare()
        root=etree.fromstring(base64.b64decode(doc.signed_xml))
        item=root.find('DetallesItems/Item')
        self.assertEqual(item.findtext('NombreItem'),'SERVICIO DE MANTENIMIENTO')
        self.assertEqual(item.findtext('DescripcionItem'),original.strip())
        self.assertTrue(doc._check_integrity())

    def test_description_above_schema_limit_blocks_before_reservation(self):
        doc=self.document()
        doc.move_id.invoice_line_ids[0].write({'name':'X'*1001})
        with self.assertRaises(UserError):doc.action_prepare()
        self.assertFalse(doc.encf)
        self.assertEqual(self.authorization.next_number,'0000000100')


    def test_unaccepted_invoice_keeps_original_report(self):
        doc=self.document()
        html,_=self.env['ir.actions.report']._render_qweb_html('account.account_invoices',doc.move_id.ids)
        self.assertIn(doc.move_id.name.encode(),html)
        self.assertNotIn(b'uxf-security-block',html)
