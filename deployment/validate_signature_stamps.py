import base64,json
from io import BytesIO
from pathlib import Path
from PIL import Image,ImageDraw
from odoo.exceptions import AccessError,UserError
assert env.cr.dbname!='Outsolutech_prueba'
base=env(context=dict(env.context,tracking_disable=True,mail_create_nosubscribe=True,no_reset_password=True))
company=base.company
old=company.uno360x_signature_stamp
im=Image.new('RGB',(600,220),'white');draw=ImageDraw.Draw(im)
draw.rectangle((10,10,590,210),outline='#568875',width=5)
draw.text((45,75),'FIRMA Y SELLO - PRUEBA SIN VALIDEZ',fill='#245341',font_size=24)
bio=BytesIO();im.save(bio,format='PNG')
company.sudo().write({'uno360x_signature_stamp':base64.b64encode(bio.getvalue())})
assert company.uno360x_signature_stamp
partner=base['res.partner'].create({'name':'QA Firma y sello SIN VALIDEZ'})
quote=base['sale.order'].create({'partner_id':partner.id,'company_id':company.id,
 'order_line':[(0,0,{'name':'Servicio ficticio sin validez','product_uom_qty':1,'price_unit':100})]})
out=Path('/tmp/uno-signature-validation');out.mkdir(exist_ok=True)
report=base.ref('sale.action_report_saleorder').with_context(report_pdf_no_attachment=True)
html,_=report._render_qweb_html(report.report_name,quote.ids)
assert b'Firma y sello' in html
pdf,_=report._render_qweb_pdf(report.report_name,quote.ids)
(out/'cotizacion-prueba.pdf').write_bytes(pdf)
invoice=base['account.move'].create({'move_type':'out_invoice','partner_id':partner.id,
 'company_id':company.id,'invoice_line_ids':[(0,0,{'name':'Servicio ficticio SIN VALIDEZ','quantity':1,'price_unit':100})]})
report=base.ref('account.account_invoices').with_context(report_pdf_no_attachment=True)
html,_=report._render_qweb_html(report.report_name,invoice.ids)
assert b'Firma y sello' in html
pdf,_=report._render_qweb_pdf(report.report_name,invoice.ids)
(out/'factura-borrador-prueba.pdf').write_bytes(pdf)
accepted=base['account.move'].search([('move_type','in',['out_invoice','out_refund']),('company_id','=',company.id)],limit=50).filtered(lambda m:m._uno360x_invoice_accepted_issue())[:1]
original_layout=company.uno360x_document_layout
for layout in ('standard','boxed','striped','bold'):
 company.uno360x_document_layout=layout
 html,_=report._render_qweb_html(report.report_name,invoice.ids)
 assert b'alt="Firma y sello"' in html,layout
company.uno360x_document_layout=original_layout
if accepted:
 html,_=report._render_qweb_html(report.report_name,accepted.ids)
 from lxml import html as lh
 tree=lh.fromstring(html)
 block=tree.xpath('//table[contains(@class,"ux-document-fiscal-signature")]')
 assert len(block)==1
 assert block[0].xpath('.//tr/td[1]//img[contains(@alt,"DGII")]')
 assert block[0].xpath('.//tr/td[2]//img[@alt="Firma y sello"]')
 pdf,_=report._render_qweb_pdf(report.report_name,accepted.ids)
 (out/'factura-fiscal-vista-prueba.pdf').write_bytes(pdf)
 print('FISCAL_QR_LEFT_SIGNATURE_RIGHT_OK',flush=True)
sales=base['res.users'].with_context(no_reset_password=True).create({
 'name':'QA Stamp permissions','login':'qa_stamp_permissions_20261119','email':False,
 'company_id':company.id,'company_ids':[(6,0,[company.id])],
 'groups_id':[(6,0,[base.ref('base.group_user').id,base.ref('sales_team.group_sale_salesman').id])]})
try:company.with_user(sales).write({'uno360x_signature_stamp':False})
except AccessError:pass
else:raise AssertionError('Unauthorized signature write')
company.sudo().write({'uno360x_signature_stamp':False})
html,_=report._render_qweb_html(report.report_name,invoice.ids)
assert b'alt="Firma y sello"' not in html
env.cr.rollback()
assert company.uno360x_signature_stamp==old
assert not base['res.partner'].search_count([('name','=','QA Firma y sello SIN VALIDEZ')])
print('SIGNATURE_REPORTS_AND_PERMISSIONS_OK_ROLLED_BACK',flush=True)

