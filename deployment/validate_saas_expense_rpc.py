"""Isolated SaaS QA only. Public RPC methods retain the real actor's permissions."""
import base64
import io
import json
from PIL import Image,ImageDraw,ImageFont
from odoo import fields
from odoo.exceptions import AccessError

assert env.cr.dbname==expected_qa_database and env.cr.dbname!='Outsolutech_prueba'
base=env(context=dict(env.context,tracking_disable=True,mail_create_nosubscribe=True,no_reset_password=True))
company=base.company
def actor(name,groups):
    return base['res.users'].create({'name':name,'login':name,'company_id':company.id,
        'company_ids':[(6,0,[company.id])],'groups_id':[(6,0,[base.ref('base.group_user').id]+[base.ref(g).id for g in groups])]})
manager=actor('qa_saas_photo_manager',['account.group_account_manager'])
other=actor('qa_saas_photo_other',['account.group_account_manager'])
staff=actor('qa_saas_photo_staff',[])
admin=base(user=manager.id,su=False)
service=admin['uno360x.expense.capture']
assert service.capture_options()['user_id']==manager.id
for method,args in [('capture_options',[]),('capture_history',[])]:
    try:
        with env.cr.savepoint():getattr(service.with_user(staff),method)(*args)
    except AccessError:pass
    else:raise AssertionError('Staff must not have access')
account=base['account.account'].search([('company_ids','in',company.id),('account_type','=','expense')],limit=1)
journal=base['account.journal'].search([('company_id','=',company.id),('type','=','purchase')])
assert account and len(journal)==1
journal.default_account_id=account
partner=base['res.partner'].create({'name':'QA SaaS foto ficticia','vat':'131000000','company_id':company.id})
img=Image.new('RGB',(1400,650),'white')
draw=ImageDraw.Draw(img);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',34)
draw.multiline_text((25,25),'FACTURA DE PROVEEDOR\nRNC 131000000\nNCF B0199999971\nFECHA '+str(fields.Date.today())+'\nSERVICIO QA 100.00\nITBIS 0.00\nTOTAL 100.00',fill='black',font=font,spacing=15)
buffer=io.BytesIO();img.save(buffer,format='PNG');raw=buffer.getvalue()
encoded=base64.b64encode(raw).decode()
data={'rnc':partner.vat,'ncf':'B0199999971','fecha':str(fields.Date.today()),'moneda':'DOP',
      'total':100,'itbis':0,'tipo_gasto':'02','lineas':[{'descripcion':'Servicio QA ficticio','cantidad':1,'precio':100,'impuestos':[],'naturaleza':'services'}]}
first=service.capture_draft('factura.png',encoded,data)
assert first['status']=='draft'
second=service.capture_draft('repetida.png',encoded,data)
assert second['id']==first['id'] and second['status']=='existing'
assert len(service.capture_history())==1
assert service.with_user(other).capture_history()==[]
move=admin['account.move'].browse(first['id'])
assert move.state=='draft' and not move.sudo().uno606_reviewed
assert base['ir.attachment'].search_count([('res_model','=','account.move'),('res_id','=',move.id)])==1
foreign=base['res.company'].create({'name':'QA otra compañía gastos','currency_id':company.currency_id.id})
try:
    with env.cr.savepoint():
        service.with_context(allowed_company_ids=[foreign.id]).capture_options()
except AccessError:pass
else:raise AssertionError('Foreign company must not be selected')

# Render the real page, without JavaScript authentication, as a read-only design snapshot.
from types import SimpleNamespace
from pathlib import Path
request=SimpleNamespace(env=admin,httprequest=SimpleNamespace(path='/uno360x/jenifer/gastos'),
                        csrf_token=lambda:'qa-not-a-session')
ctx=admin['uno360x.workspace']._workspace_context()
ctx.update(page_key='billing',request=request,csrf='qa-not-a-session')
page=admin['ir.ui.view'].with_context(minimal_qcontext=True)._render_template('uno360x_expense_chat.page',ctx)
out=Path('/var/lib/odoo/expense-preview');out.mkdir(exist_ok=True)
(out/'page.html').write_bytes(page if isinstance(page,bytes) else str(page).encode())
(out/'fixture.png').write_bytes(raw)
(out/'options.json').write_text(json.dumps(service.capture_options()))
(out/'data.json').write_text(json.dumps(data))
env.cr.rollback()
assert not env['res.partner'].search_count([('name','=','QA SaaS foto ficticia')])
print('SAAS_EXPENSE_RPC_VALIDATED_ROLLED_BACK')

