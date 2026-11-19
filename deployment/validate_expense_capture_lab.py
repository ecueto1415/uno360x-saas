"""Isolated QA only; fictitious data and every accounting change rolls back."""
import io
import json
from PIL import Image, ImageDraw, ImageFont
from odoo import fields
from odoo.exceptions import AccessError, UserError

assert env.cr.dbname == expected_qa_database and env.cr.dbname != 'Outsolutech_prueba'
base = env(context=dict(env.context, tracking_disable=True,
                        mail_create_nosubscribe=True, no_reset_password=True))
company = base.company
assert not company.uno360x_ecf_enabled
manager = base['res.users'].create({'name': 'QA Contabilidad fotos',
    'login': 'qa_expense_photo', 'company_id': company.id,
    'company_ids': [(6, 0, [company.id])],
    'groups_id': [(6, 0, [base.ref('base.group_user').id,
                          base.ref('account.group_account_manager').id, base.ref('account.group_account_user').id])]})
staff = base['res.users'].create({'name': 'QA Sin contabilidad',
    'login': 'qa_expense_photo_denied', 'company_id': company.id,
    'company_ids': [(6, 0, [company.id])],
    'groups_id': [(6, 0, [base.ref('base.group_user').id])]})
admin = base(user=manager.id, su=False)
service = admin['uno360x.expense.capture']
partner = base['res.partner'].create({'name': 'QA Suplidor ficticio fotos',
                                     'vat': '131000000', 'company_id': company.id})
tax = base['account.tax'].create({'name': 'QA ITBIS compra foto 18%',
    'company_id': company.id, 'amount': 18, 'type_tax_use': 'purchase',
    'amount_type': 'percent', 'uno606_role': 'vat'})
expense = base['account.account'].search([
    ('company_ids', 'in', company.id), ('account_type', '=', 'expense')], limit=1)
assert expense
journals = base['account.journal'].search([
    ('company_id', '=', company.id), ('type', '=', 'purchase')])
assert len(journals) == 1
journals.default_account_id = expense

def photo(extra=''):
    image = Image.new('RGB', (1400, 600), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 36)
    draw.multiline_text((30, 30), 'FACTURA QA FICTICIA - NO VALIDA\nRNC 131000000\nB0100009991\nSERVICIO 100.00\nITBIS 18.00\nTOTAL 118.00\n'+extra,
                        fill='black', font=font, spacing=15)
    out = io.BytesIO(); image.save(out, format='PNG')
    return out.getvalue()

raw = photo()
ocr = service._read('factura-qa.png', raw)
assert '118.00' in ocr['texto_ocr'] and '131000000' in ocr['texto_ocr'], ocr
data = {'rnc': partner.vat, 'ncf': 'B0100009991', 'fecha': str(fields.Date.today()),
    'moneda': company.currency_id.name, 'total': 118, 'itbis': 18, 'tipo_gasto': '',
    'lineas': [{'descripcion': 'Servicio ficticio QA', 'cantidad': 1, 'precio': 100,
                'impuestos': [tax.id], 'naturaleza': 'services'}]}

def rejected(fn, kind=UserError):
    try:
        with env.cr.savepoint(): fn()
    except kind: return
    raise AssertionError('Should reject')

rejected(lambda: service.with_user(staff)._read('factura.png', raw), AccessError)
rejected(lambda: service.with_user(staff)._prepare('factura.png', raw, data), AccessError)
rejected(lambda: service._read('falsa.png', b'not an image'))
result = service._prepare('factura-qa.png', raw, data)
assert result['status'] == 'draft', result
move = admin['account.move'].browse(result['id'])
assert move.state == 'draft' and not move.uno606_reviewed
assert move.uno606_ncf == data['ncf'] and not move.uno606_expense_type
assert move.amount_total == 118 and move.amount_tax == 18
assert move.uno606_events == base['uno360x.606.payment']
assert base['ir.attachment'].search_count([
    ('res_model', '=', 'account.move'), ('res_id', '=', move.id)]) == 1
assert service._prepare('reintento.png', raw, data)['id'] == move.id
assert service._prepare('segunda-foto.png', photo('OTRA FOTO'), data)['id'] == move.id
changed = dict(data, ncf='B0100009992', total=130)
before = admin['account.move'].search_count([])
rejected(lambda: service._prepare('error.png', photo('ERROR TOTAL'), changed))
assert admin['account.move'].search_count([]) == before
missing = dict(data); missing.pop('ncf')
assert service._prepare('sin-numero.png', photo('SIN NCF'), missing)['status'] == 'needs_data'
unknown = dict(data, rnc='999999999')
assert service._prepare('sin-proveedor.png', photo('OTRO RNC'), unknown)['status'] == 'needs_supplier'
rejected(lambda: service._prepare('nota.png', photo('NOTA'), dict(data, ncf='E340000000001')))
another = base['res.company'].create({'name': 'QA Otra empresa fotos', 'currency_id': company.currency_id.id})
foreign_group = base['account.tax.group'].create({'name': 'QA Grupo otra empresa', 'company_id': another.id})
foreign = base['account.tax'].create({'name': 'QA Impuesto otra empresa',
    'company_id': another.id, 'tax_group_id': foreign_group.id, 'country_id': tax.country_id.id,
    'amount': 18, 'type_tax_use': 'purchase'})
bad = json.loads(json.dumps(data)); bad['ncf'] = 'B0100009993'
bad['lineas'][0]['impuestos'] = [foreign.id]
rejected(lambda: service._prepare('otra-empresa.png', photo('OTRA EMPRESA'), bad), (AccessError, UserError))
assert move.state == 'draft' and move.amount_residual == move.amount_total
import importlib.util
from types import SimpleNamespace
from pathlib import Path
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result
agent = module('qa_agent', '/mnt/expense-source/jenifer-runtime/agente_jenifer.py')
commerce = module('qa_commerce', '/mnt/expense-source/jenifer-runtime/comercio_jenifer.py')
bridge = module('qa_expense_bridge', '/mnt/expense-source/integrations/jenifer/expense_bridge.py')
bridge.install(agent, commerce.Commerce)
assert len([t for t in agent.commerce_tools() if t['name'] == 'leer_factura_gasto']) == 1
files = {'archivo_1': ('factura.png', photo('PRUEBA HERRAMIENTAS'))}
first = commerce.Commerce(admin, SimpleNamespace(), 1, 1, 'Registra el gasto adjunto', files)
first.execute('leer_factura_gasto', {'archivo_id': 'archivo_1'})
next_call = commerce.Commerce(admin, SimpleNamespace(), 1, 1, 'Registra el gasto adjunto', files)
next_call.lookups = first.lookups
e31 = dict(data, ncf='E310000009991')
tool_result = next_call.execute('preparar_gasto_desde_foto',
    {'archivo_id': 'archivo_1', 'datos_json': json.dumps(e31)})
assert tool_result['status'] == 'draft' and tool_result['comprobante'] == e31['ncf']
env.cr.rollback()
assert not env['res.partner'].search_count([('name', '=', 'QA Suplidor ficticio fotos')])
print('EXPENSE_PHOTO_LAB_VALIDATED_ROLLED_BACK', json.dumps({
    'ocr_real': True, 'draft': True, 'original_attached': True,
    'no_duplicates_hash_or_ncf': True, 'unreadable_or_missing': True,
    'totals_mismatch_rollback': True, 'role_and_company_isolation': True,
    'not_posted_paid_or_submitted': True, 'actual_jenifer_commerce_adapter': True}))



