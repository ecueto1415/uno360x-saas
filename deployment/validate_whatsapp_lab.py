"""SaaS QA only. Caller supplies expected_qa_database. All business fixtures rollback.

This tests local preparation, never Meta, DGII, SMS, email or a customer's number.
"""
import json
from datetime import timedelta
from unittest.mock import patch
from odoo import fields
from odoo.exceptions import AccessError,UserError,ValidationError

assert env.cr.dbname==expected_qa_database and env.cr.dbname!='Outsolutech_prueba'
base=env(context=dict(env.context,tracking_disable=True,mail_create_nosubscribe=True,no_reset_password=True))
company=base.company
assert not company.uno360x_ecf_enabled
company.name='QA WhatsApp · Empresa A'
group=base.ref('uno360x_whatsapp.group_collection_user')
def user(login,groups):
    return base['res.users'].create({'name':login,'login':login,'company_id':company.id,'company_ids':[(6,0,[company.id])],
        'groups_id':[(6,0,[base.ref('base.group_user').id]+[base.ref(g).id for g in groups])]})
manager=user('qa_wa_manager',['account.group_account_manager'])
collector=user('qa_wa_collector',['uno360x_whatsapp.group_collection_user','account.group_account_invoice'])
sales=user('qa_wa_sales',['sales_team.group_sale_salesman'])
wa_only=user('qa_wa_without_invoice_rights',['uno360x_whatsapp.group_collection_user'])
staff=base(user=collector.id);admin=base(user=manager.id)
partner=base['res.partner'].create({'name':'Cliente ficticio WhatsApp'})
account=base['account.account'].search([('account_type','=','income'),('company_ids','in',company.id)],limit=1)
assert account
def invoice():
    move=base['account.move'].create({'move_type':'out_invoice','partner_id':partner.id,'company_id':company.id,
        'invoice_date':fields.Date.today()-timedelta(days=10),'invoice_date_due':fields.Date.today()-timedelta(days=3),
        'invoice_line_ids':[(0,0,{'name':'Servicio de demostración sin valor fiscal','account_id':account.id,'quantity':1,'price_unit':100,'tax_ids':[(5,0,0)]})]})
    move.action_post()
    return move
def denied(fn,kind=AccessError):
    try:
        with env.cr.savepoint():fn()
    except kind:return
    raise AssertionError('Operation should have been rejected')

connection=admin['uno360x.wa.connection'].create({'display_phone':'+18095550102'})
denied(lambda:staff['uno360x.wa.connection'].create({'display_phone':'+18095550103'}))
denied(lambda:connection.with_user(collector).write({'display_phone':'+18095550103'}))
denied(lambda:admin['uno360x.wa.consent'].create({'partner_id':partner.id,'recipient':'+18095550101','state':'granted'}),ValidationError)
consent=admin['uno360x.wa.consent'].create({'partner_id':partner.id,'recipient':'+18095550101'})
move=invoice()
reminders=staff['uno360x.wa.reminder']
denied(lambda:reminders._prepare(move.with_user(collector),consent.with_user(collector)),UserError)
consent.write({'state':'granted','evidence':'Autorización ficticia, solo QA'})
denied(lambda:base(user=sales.id)['uno360x.wa.reminder']._prepare(move,consent))
denied(lambda:base(user=wa_only.id)['uno360x.wa.reminder']._prepare(move.with_user(wa_only),consent.with_user(wa_only)))
denied(lambda:reminders.create({'company_id':company.id,'move_id':move.id,'state':'simulated'}))
first=reminders._prepare(move.with_user(collector),consent.with_user(collector))
second=reminders._prepare(move.with_user(collector),consent.with_user(collector))
assert first.id==second.id and reminders.search_count([('move_id','=',move.id)])==1
assert reminders.with_context(tz='Pacific/Auckland')._prepare(move.with_user(collector),consent.with_user(collector)).id==first.id
assert reminders.with_context(tz='America/Los_Angeles')._prepare(move.with_user(collector),consent.with_user(collector)).id==first.id
denied(lambda:first.write({'state':'simulated'}))
first._simulate();at=first.simulated_at
assert first.state=='simulated' and 'No se contactó a Meta' in first.reason
first._simulate();assert first.simulated_at==at
denied(lambda:consent.with_user(collector).write({'state':'granted','evidence':'forged'}))

# Fiscal number presentation is mocked in memory: no sequence is reserved or emitted.
with patch.object(type(move),'_ux_accepted_ecf_number',return_value='E310000000001'):
    data=reminders._snapshot(move.with_user(collector),consent.with_user(collector))
    assert data['document_number']=='E310000000001' and 'E310000000001' in data['body']

bank=base['account.journal'].search([('company_id','=',company.id),('type','=','bank')],limit=1)
if not bank:bank=base['account.journal'].create({'name':'QA WhatsApp banco ficticio','code':'QAWA','type':'bank'})
def pay(move,amount):
    wizard=base['account.payment.register'].with_context(active_model='account.move',active_ids=move.ids).create({'journal_id':bank.id,'payment_date':fields.Date.today(),'amount':amount})
    wizard._create_payments();move.invalidate_recordset()
partial=invoice();pending=reminders._prepare(partial.with_user(collector),consent.with_user(collector))
pay(partial,30);pending._simulate()
assert json.loads(pending.sudo().payload)['template']['components'][0]['parameters'][4]['text']=='70.00'
paid=invoice();pending=reminders._prepare(paid.with_user(collector),consent.with_user(collector))
pay(paid,100);pending._simulate();assert pending.state=='blocked'
draft=base['account.move'].create({'move_type':'out_invoice','partner_id':partner.id})
denied(lambda:reminders._prepare(draft.with_user(collector),consent.with_user(collector)),UserError)
cancelled=invoice();pending=reminders._prepare(cancelled.with_user(collector),consent.with_user(collector))
cancelled.button_draft();cancelled.button_cancel();pending._simulate();assert pending.state=='blocked'
credited=invoice();pending=reminders._prepare(credited.with_user(collector),consent.with_user(collector))
credit=credited._reverse_moves(default_values_list=[{'date':fields.Date.today(),'invoice_date':fields.Date.today()}],cancel=True)
pending._simulate();assert pending.state=='blocked'
denied(lambda:reminders._prepare(credit.with_user(collector),consent.with_user(collector)),UserError)
revoked=invoice();pending=reminders._prepare(revoked.with_user(collector),consent.with_user(collector))
consent.write({'state':'revoked'});pending._simulate();assert pending.state=='blocked'
consent.write({'state':'granted','evidence':'Nueva autorización ficticia'})
denied(lambda:consent.write({'recipient':'+18095550104','state':'granted','evidence':'Nueva autorización ficticia'}),UserError)
consent.write({'recipient':'+18095550104'});assert consent.state=='unknown'
consent.write({'state':'granted','evidence':'Autorización del nuevo número ficticio'})

other=base['res.company'].create({'name':'QA WhatsApp · Empresa B','currency_id':company.currency_id.id})
foreign_consent=base['uno360x.wa.consent'].with_company(other).create({'partner_id':partner.id,'recipient':'+18095550105','state':'granted','evidence':'Empresa B ficticia'})
denied(lambda:reminders._snapshot(move.with_user(collector),foreign_consent.with_user(collector)))
assert not staff['uno360x.wa.consent'].search_count([('id','=',foreign_consent.id)])
denied(lambda:admin['uno360x.wa.connection'].create({'company_id':other.id}))

# Existing invoice record rules must also protect the message body.
base['ir.rule'].create({'name':'QA WhatsApp invoice restriction','model_id':base.ref('account.model_account_move').id,
    'domain_force':"[('id','!=',%s)] if user.id==%s else []"%(move.id,collector.id)})
denied(lambda:first.with_user(collector).read(['body']))

result={'duplicate_preparation':'one record','double_simulation':'one event','paid_invoice':'blocked',
 'cancelled_invoice':'blocked','credited_invoice':'blocked','draft_invoice':'blocked',
 'revoked_consent':'blocked','number_change':'requires new consent','partial_payment':'current balance 70.00',
 'other_company':'denied','invoice_record_rules':'respected','configuration_by_collector':'denied',
 'fiscal_number':'displayed from mocked existing number; no fiscal issuance',
 'provider_network_calls':0,'real_messages_sent':0}
if globals().get('export_whatsapp_views'):
    from types import SimpleNamespace
    from pathlib import Path
    from odoo.addons.uno360x_whatsapp import controllers as wa_controller
    output=Path('/var/lib/odoo/whatsapp-preview');output.mkdir(exist_ok=True)
    req=SimpleNamespace(env=admin,httprequest=SimpleNamespace(method='GET'))
    wa_controller.request=req
    controller=wa_controller.WhatsAppWorkspace()
    controller._service=lambda:admin['uno360x.workspace']
    def render(template,values):
        return admin['ir.ui.view'].with_context(minimal_qcontext=True)._render_template(template,dict(values,csrf='qa-preview-not-a-session',request=req))
    controller._render=render
    def save_page(name,response):
        text=response.get_data(as_text=True) if hasattr(response,'get_data') else str(response)
        assert '<html' in text
        (output/name).write_text(text)
    demo=invoice()
    def fiscal_demo_number(record):return 'E31'+f'{record.id:010d}'
    with patch.object(type(move),'_ux_accepted_ecf_number',fiscal_demo_number):
        preview=admin['uno360x.wa.reminder']._prepare(demo.with_user(manager),consent.with_user(manager))
        save_page('home.html',controller.wa_home())
        save_page('review.html',controller.wa_invoice(demo.id))
        save_page('configuration.html',controller.wa_configuration())
        save_page('customer.html',controller.wa_customer(partner.id))
        preview._simulate()
        save_page('reminder.html',controller.wa_reminder(preview.id))
    print('WHATSAPP_VIEWS_RENDERED',5)
env.cr.rollback()
assert not env['res.partner'].search_count([('name','=','Cliente ficticio WhatsApp')])
print('WHATSAPP_LAB_VALIDATED_ROLLED_BACK',json.dumps(result,ensure_ascii=False))
