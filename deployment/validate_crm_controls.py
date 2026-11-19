"""Run in an isolated Odoo shell with a candidate controller, always rollback.

Set candidate_crm_source before executing. No fiscal operation, mail send or commit.
"""
from types import SimpleNamespace
import json
from odoo.http import Response

assert env.cr.dbname!='Outsolutech_prueba'
base=env(context=dict(env.context,tracking_disable=True,mail_create_nosubscribe=True,no_reset_password=True))
owner=base['res.users'].search([('uno360x_account_id','!=',False),('active','=',True)]).filtered(
    lambda u:u.has_group('sales_team.group_sale_manager'))[:1]
assert owner,'No SaaS CRM administrator'
namespace={'__name__':'odoo.addons.uno360x_workspace.controllers.crm_candidate',
           '__package__':'odoo.addons.uno360x_workspace.controllers'}
exec(compile(candidate_crm_source,'candidate_crm.py','exec'),namespace)
current=base(user=owner.id)
namespace['request']=SimpleNamespace(env=current,httprequest=SimpleNamespace(method='POST'),redirect=lambda url,code=303:Response(status=code,headers={'Location':url}))
controller=namespace['CrmWorkspace']()
controller._crm_context=lambda:(None,{})
controller._render=lambda template,values:Response(str(values.get('crm_error','')),status=400)
owners=controller._crm_owners()
assert owner.id in owners.ids
assert controller._crm_owner(str(owner.id),owners)==owner.id
assert controller._crm_owner('0',owners) is False
for value in ('bad','999999999'):
    try:controller._crm_owner(value,owners)
    except namespace['UserError']:pass
    else:raise AssertionError('Invalid owner accepted')
sales=base['res.users'].with_context(no_reset_password=True).create({
 'name':'QA CRM permissions rollback','login':'qa_crm_permissions_rollback_20261119',
 'email':False,'company_id':base.company.id,'company_ids':[(6,0,[base.company.id])],
 'groups_id':[(6,0,[base.ref('base.group_user').id,base.ref('sales_team.group_sale_salesman').id])]})
team=current['crm.team'].create({'name':'QA CRM controls rollback','company_id':current.company.id,'use_opportunities':True})
shared=current['crm.stage'].search([('team_id','=',False)])
result=controller.crm_manage(flow=str(team.id),mode='stage',name='QA Etapa rollback',after='0')
assert result.status_code==303
assert current['crm.stage'].search_count([('team_id','=',team.id),('name','=','QA Etapa rollback')])==1
assert current['ir.config_parameter'].sudo().get_param('uno360x.crm.include_global.%s.%s'%(current.company.id,team.id))=='1'
result=controller.crm_manage(flow=str(team.id),mode='stage',name='QA Etapa rollback',after='0')
assert result.status_code==400 and result.get_data()
assert current['crm.stage'].search_count([('team_id','=',team.id),('name','=','QA Etapa rollback')])==1
result=controller.crm_opportunity(flow=str(team.id),name='QA Oportunidad rollback',user_id=str(sales.id))
assert result.status_code==303
lead=current['crm.lead'].search([('name','=','QA Oportunidad rollback'),('team_id','=',team.id)])
assert len(lead)==1 and lead.user_id==sales and lead.company_id==current.company
result=controller.crm_record(lead.id,user_id='0')
assert result.status_code==303
assert not lead.user_id and lead.company_id==current.company
result=controller.crm_record(lead.id,user_id=str(owner.id))
assert result.status_code==303
assert lead.user_id==owner and lead.company_id==current.company
namespace['request'].env=base(user=sales.id)
self_owners=controller._crm_owners()
assert self_owners.ids==sales.ids
try:controller._crm_owner(str(owner.id),self_owners)
except namespace['UserError']:pass
else:raise AssertionError('Salesperson could select another owner')
try:controller.crm_manage(flow=str(team.id),mode='stage',name='Forbidden stage')
except namespace['Forbidden']:pass
else:raise AssertionError('Salesperson could manage stages')
env.cr.rollback()
assert not env['crm.lead'].search_count([('name','=','QA Oportunidad rollback')])
assert not env['crm.team'].search_count([('name','=','QA CRM controls rollback')])
print('CRM_CONTROL_TESTS_OK',json.dumps({'responsible_assignment':True,'unassign_preserves_company':True,'reassign_preserves_company':True,'cross_user_guard':True,'stage_create':True,'duplicate_guard':True,'salesperson_stage_denied':True,'rolled_back':True}),flush=True)
