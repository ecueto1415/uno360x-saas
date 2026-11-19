"""Native isolated clone only; no fiscal posting, emails or payment calls."""
import io
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from PIL import Image, ImageDraw, ImageFont
from odoo import api, fields
from odoo.exceptions import AccessError, UserError

assert env.cr.dbname == 'uno_photo_native_20261119'
env.cr.execute('SHOW port'); assert env.cr.fetchone()[0] == '18192'
base = env(context=dict(env.context, tracking_disable=True, no_vat_validation=True,
                         mail_create_nosubscribe=True, no_reset_password=True))
admin = base(user=2, su=False)
assert admin.user.has_group('account.group_account_user')
company = admin.company
assert not admin['ir.module.module'].search_count([('name','=','uno360x_dgii_606'),('state','=','installed')])
partner = admin['res.partner'].create({'name':'QA FOTO GASTO FICTICIO NO VALIDO',
    'vat':'131000000', 'company_id':company.id})
taxes = admin['account.tax'].search([('company_id','=',company.id),('type_tax_use','=','purchase'),
    ('active','=',True),('amount_type','=','percent'),('amount','=',18)])
assert taxes
tax = taxes.filtered(lambda t:'serv' not in t.name.lower() and 'cost' not in t.name.lower()
                     and 'imp.' not in t.name.lower())[:1]
assert tax

def photo(extra=''):
    image=Image.new('RGB',(1500,650),'white')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',35)
    draw.multiline_text((25,25),'FACTURA FICTICIA QA - NO VALIDA\nRNC: 131000000\nNCF: B0199999901\nFECHA: '+str(fields.Date.today())+
        '\nSERVICIO QA 100.00\nITBIS 18.00\nTOTAL 118.00\n'+extra,fill='black',font=font,spacing=15)
    result=io.BytesIO();image.save(result,format='PNG');return result.getvalue()

data={'rnc':partner.vat,'ncf':'B0199999901','fecha':str(fields.Date.today()),
    'moneda':'DOP','total':118,'itbis':18,'tipo_gasto':'02',
    'lineas':[{'descripcion':'PRUEBA FICTICIA NO VALIDA - Servicio QA','cantidad':1,
        'precio':100,'impuestos':[tax.id],'naturaleza':'services'}]}
service=admin['uno360x.expense.capture']
raw=photo()
assert '118.00' in service._read('factura.png',raw)['texto_ocr']
first=service._prepare('factura.png',raw,data)
assert first['status']=='draft',first
move=admin['account.move'].browse(first['id'])
assert move.move_type=='in_invoice' and move.state=='draft'
assert move.uno_photo_source_ncf==data['ncf'] and move.ref==data['ncf']
assert move.uno_photo_expense_type=='02' and move.amount_total==118
assert service._prepare('foto-repetida.png',raw,data)['id']==move.id
assert service._prepare('otra-foto.png',photo('OTRA FOTO'),data)['id']==move.id
assert admin['ir.attachment'].search_count([('res_model','=','account.move'),('res_id','=',move.id)])==1

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
stage=Path('/var/lib/uno360x-expense-stage-20261119/candidate')
commerce=load('native_qa_commerce',stage/'comercio_jenifer.py')
worker=load('native_qa_worker',stage/'worker.py')
agent=load('native_qa_agent',stage/'agente_jenifer.py')
assert {'leer_factura_gasto','preparar_gasto_desde_foto'} <= {t['name'] for t in agent.commerce_tools()}
files={'archivo_1':('factura.png',raw)}
lookup=set()
def commercial(name,args):
    call=commerce.Commerce(admin,worker,0,0,'Registra este gasto en borrador',files)
    call.lookups=lookup
    return call.execute(name,args)
commercial('leer_factura_gasto',{'archivo_id':'archivo_1'})
assert commercial('preparar_gasto_desde_foto',{'archivo_id':'archivo_1','datos_json':json.dumps(data)})['id']==move.id

# Verify worker whitelist/dispatch using its real loop, deterministic model output.
class QAAgent:
    def commerce_tools(self): return agent.commerce_tools()
    def payment_tools(self): return []
    def run_agent(self,text,settings,execute,**kwargs):
        assert execute('leer_factura_gasto',{'archivo_id':'archivo_1'})['texto_ocr']
        result=execute('preparar_gasto_desde_foto',{'archivo_id':'archivo_1','datos_json':json.dumps(data)})
        assert result['status']=='existing' and result['id']==move.id
        return {'answer':'Borrador existente, sin duplicar.','trace':[]}
worker.agent_engine=lambda:QAAgent()
worker.approved_extensions=lambda:({},[])
worker.knowledge_engine=lambda:SimpleNamespace(search=lambda *a,**k:{'excerpts':[]})
outcome=worker.run_internal_agent('Registra el gasto',{},lambda q:{},lambda term:None,
    can_act=True,commerce=commercial)
assert 'sin duplicar' in outcome['body_html']

# Actual model smoke with only the two accounting tools and fictional data.
if globals().get('run_live_model'):
    import os
    agent.tools=lambda can_act:[]
    prompt=('Registra esta factura ficticia de laboratorio en borrador. Archivo actual archivo_1. '
        'Datos confirmados por el usuario contra la foto: '+json.dumps(data)+
        '. Lee la foto y usa preparar_gasto_desde_foto. No confirmes ni pagues. '
        'Si ya existe devuelve el enlace del borrador existente. No pidas repetir la orden.')
    live=agent.run_agent(prompt,{k:os.environ[k] for k in ('OPENAI_API_KEY','OPENAI_MODEL') if os.environ.get(k)},
        commercial,can_act=True,extra_tools=agent.commerce_tools()[:2],cueto_private=True)
    names=[t['name'] for t in live['trace']]
    assert 'leer_factura_gasto' in names and 'preparar_gasto_desde_foto' in names,live
    print('LIVE_MODEL_TOOLS',json.dumps(names))
    print('LIVE_MODEL_ANSWER',live['answer'][:1000])
assert admin['account.move'].search_count([('company_id','=',company.id),('ref','=',data['ncf'])])==1
assert move.state=='draft'
env.cr.rollback()
assert not env['res.partner'].search_count([('name','=','QA FOTO GASTO FICTICIO NO VALIDO')])
print('NATIVE_EXPENSE_CHAT_VALIDATED_ROLLED_BACK')
