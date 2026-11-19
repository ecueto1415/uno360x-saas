"""Execute with Odoo shell ONLY on the isolated clone, never live Outsolutech.

No network/fiscal submissions, no email. All test accounting records rolled back.
"""
from pathlib import Path
import json
from odoo.exceptions import AccessError, UserError
assert env.cr.dbname == 'Outsolutech_prueba'
env.cr.execute('show port')
assert env.cr.fetchone()[0] == '18192', 'This is NOT the isolated 606 PostgreSQL'
base=env(context=dict(env.context,tracking_disable=True,mail_create_nosubscribe=True,no_reset_password=True))
company=base.company
partner=base['res.partner'].create({'name':'QA 606 PROVEEDOR FICTICIO','vat':'130052433'})
account=base['account.account'].search([('account_type','=','expense'),('company_ids','in',company.id)],limit=1)
assert account
vat=base['account.tax'].create({'name':'QA 606 ITBIS 18','amount':18,'type_tax_use':'purchase','company_id':company.id,'uno606_role':'vat'})
def bill(number,when,kind='in_invoice',original=False):
    vals={'partner_id':partner.id,'company_id':company.id,'move_type':kind,'invoice_date':when,
          'date':when,'uno606_ncf':number,'uno606_expense_type':'02',
          'invoice_line_ids':[(0,0,{'name':'QA 606 servicio ficticio','account_id':account.id,
                                  'quantity':1,'price_unit':1000,'tax_ids':[(6,0,vat.ids)],'uno606_nature':'services'})]}
    if original:vals['reversed_entry_id']=original.id
    move=base['account.move'].create(vals)
    move.action_post()
    move.uno606_reviewed=True
    return move
b=bill('B0100999901','2026-11-04')
e=bill('E310000999901','2026-11-05')
nc=bill('E340000999901','2026-11-06','in_refund',e)
older=bill('B0100999902','2026-10-04')
event=base['uno360x.606.payment'].create({'move_id':older.id,'date':'2026-11-10',
    'reference':'QA 606 RETENCIONES SIMULADAS','payment_form':'02','amount':1180,
    'vat_amount':54,'isr_type':'02','isr_amount':100,'state':'reviewed'})
entries=[m._uno606_entry('202611') for m in (b,e,nc,older)]
from odoo.addons.uno360x_dgii_606.engine import build,export_txt
r=build(company.vat,'202611',entries)
assert not r['errors'],r['errors']
assert r['totals']['total']=='1000.00',r['totals']
assert r['totals']['vat_withheld']=='54.00'
txt=export_txt(r)
assert len(txt.decode().splitlines())==5
Path('/var/lib/uno360x-606-lab/DGII_F_606_PRUEBA_202611.TXT').write_bytes(txt)
wizard=base['uno360x.606.report'].create({'company_id':company.id,'month':'11','year':2026})
result=wizard._result()
assert all(row['move_id'] in base['account.move'].search([('company_id','=',company.id)]).ids for row in result['rows'])
assert b.id in [row['move_id'] for row in result['rows']]
assert older.id in [row['move_id'] for row in result['rows']]
wizard.action_preview()
assert 'B0100999901' in str(wizard.preview)
# Existing historical invoices have missing NCF/classifications: must block, not invent.
if result['errors']:
    try:wizard.action_download()
    except UserError:pass
    else:raise AssertionError('Historical missing data export was allowed')
else:
    wizard.action_download()
    assert wizard.file_data and wizard.filename.endswith('_202611.TXT')
duplicate=bill('B0100999901','2026-11-07')
assert any(p['field']=='NCF duplicado' and p.get('move_id')==b.id for p in wizard._result()['errors'])
missing=bill('B0100999903','2026-11-07');missing.uno606_expense_type=False;missing.uno606_reviewed=False
assert any(p['field']=='Tipo de gasto' and p.get('move_id')==missing.id for p in wizard._result()['errors'])
try:wizard.action_download()
except UserError:pass
else:raise AssertionError('Export with missing data was allowed')
paid_bill=bill('B0100999904','2026-11-08')
bank=base['account.journal'].search([('company_id','=',company.id),('type','=','bank')],limit=1)
if not bank: bank=base['account.journal'].create({'name':'QA606 Banco ficticio','code':'QA606','type':'bank','company_id':company.id})
bank.uno606_payment_form='02'
register=base['account.payment.register'].with_context(active_model='account.move',active_ids=paid_bill.ids).create({'journal_id':bank.id,'payment_date':'2026-11-12','amount':1180})
payment=register._create_payments()
assert len(payment)==1
payment_event=base['uno360x.606.payment'].new({'move_id':paid_bill.id,'payment_id':payment.id})
payment_event._onchange_payment()
assert payment_event.date==payment.date and payment_event.payment_form=='02'
payment_event=base['uno360x.606.payment'].create({'move_id':paid_bill.id,'payment_id':payment.id,
    'date':'2026-11-12','reference':payment.name,'payment_form':'02','amount':1180,'state':'reviewed'})
assert not payment_event._validation_errors()
assert not paid_bill._uno606_entry('202611')['errors']
sales=base['res.users'].with_context(no_reset_password=True).create({'name':'QA606 Ventas',
    'login':'qa606salesrollback','company_id':company.id,'company_ids':[(6,0,[company.id])],
    'groups_id':[(6,0,[base.ref('base.group_user').id,base.ref('sales_team.group_sale_salesman').id])]})
try:base['uno360x.606.report'].with_user(sales).create({'company_id':company.id,'month':'11','year':2026})
except AccessError:pass
else:raise AssertionError('Sales could access 606')
other=base['res.company'].create({'name':'QA606 Empresa aislada','currency_id':company.currency_id.id,'vat':'132364805'})
try:wizard.with_user(sales).action_download()
except AccessError:pass
else:raise AssertionError('Unauthorized export')
owner=base['res.users'].with_context(no_reset_password=True).create({'name':'QA606 Contabilidad',
    'login':'qa606accountantrollback','company_id':company.id,'company_ids':[(6,0,[company.id])],
    'groups_id':[(6,0,[base.ref('base.group_user').id,base.ref('account.group_account_user').id])]})
normal_report=base['uno360x.606.report'].with_user(owner).create({'company_id':company.id,'month':'11','year':2026})
normal_report.action_preview()
assert normal_report.preview and '>False<' not in str(normal_report.preview)
assert str(normal_report.preview).index('<table') < str(normal_report.preview).index('Corrige estos errores')
if 'outs_ecf_category' in vat._fields:
    vat.write({'uno606_role':False,'outs_ecf_category':'1'})
    assert vat.with_user(owner)._uno606_role()=='vat'
    vat.uno606_role='vat'
foreign=base['uno360x.606.report'].new({'company_id':other.id,'month':'11','year':2026})
try:foreign.with_user(owner)._result()
except AccessError:pass
else:raise AssertionError('Cross-company access was allowed')
result_summary={'synthetic_cases':4,'b_and_e':True,'credit_note':True,'later_retention':True,
    'missing_data_blocked':True,'duplicates_blocked':True,'sales_denied':True,'company_isolation':True,
    'reconciled_payment_checked':True,'historical_errors':len(result['errors']),'historical_rows':len(result['rows']),
    'official_prevalidator':'pending','accounting_comparison':'pending'}
env.cr.rollback()
assert not env['res.partner'].search_count([('name','=','QA 606 PROVEEDOR FICTICIO')])
Path('/var/lib/uno360x-606-lab/validation.json').write_text(json.dumps(result_summary,indent=2))
print('606_LAB_VALIDATED_ROLLED_BACK',json.dumps(result_summary))
