"""Approved subscription layout, inserted into the existing UNO360X shell."""
from datetime import datetime
from html import escape as e
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import re
import uuid

PATH='/uno360x-suscripcion'
ASSET='/__subscription'

def money(value,currency):return ('US$' if currency=='USD' else 'RD$')+f'{value/100:,.2f}'
def date(value):return datetime.fromtimestamp(value,ZoneInfo('America/Santo_Domingo')).strftime('%d/%m/%Y') if value is not None else 'Por configurar'
def link(**query):return PATH+('?' + urlencode(query) if query else '')
def pill(text,kind='good'):return f'<span class="sb-pill {kind}">{e(text)}</span>'

def rows(records):
    if not records:return '<p class="sb-empty">Todavía no tienes facturas de suscripción. Aquí aparecerán cuando UNO360X las emita.</p>'
    return '<div class="sb-table"><table><thead><tr><th>FECHA</th><th>FACTURA</th><th>IMPORTE</th><th>ESTADO</th><th>DOCUMENTO</th></tr></thead><tbody>'+''.join(
        f'<tr><td data-label="Fecha">{date(r["issued"])}</td><td data-label="Factura">{e(r["number"])}</td><td data-label="Importe"><strong>{money(r["total_minor"],r["currency"])}</strong></td>'
        f'<td data-label="Estado">{pill("Pagada" if r["state"]=="paid" else "Anulada" if r["state"]=="void" else "Pendiente de verificación" if r["awaiting_review"] else "Pendiente","good" if r["state"]=="paid" else "neutral" if r["state"]=="void" else "pending")}</td>'
        f'<td data-label="Documento"><a href="{link(pdf=r["id"])}">Descargar PDF</a></td></tr>' for r in records)+'</tbody></table></div>'

def screen(data,records,csrf,tab='summary',notice='',year='',state='',query='',error=False):
    pref,terms=data['preferences'],data['terms']
    tabs=''.join(f'<a class="{"active" if tab==key else ""}" href="{link(tab=key)}" {"aria-current=page" if tab==key else ""}>{label}</a>' for key,label in [('summary','Resumen'),('payment','Método de pago'),('history','Historial')])
    intro=f'''<div id="uno-subscription"><p class="sb-crumb">MI EMPRESA / SUSCRIPCIÓN</p><div class="sb-heading"><div><h1>Suscripción</h1><p>Tu plan, tus pagos y tus facturas en un solo lugar.</p></div>{pill('Solo administrador')}</div><nav class="sb-tabs" aria-label="Suscripción">{tabs}</nav>'''
    feedback=f'<p class="sb-feedback {"error" if error else ""}" role="{"alert" if error else "status"}">{e(notice)}</p>' if notice else ''
    if tab=='summary':
        mods={'payroll_hr':'Nómina y Recursos Humanos','jenifer_ai':'Jenifer IA','projects_services':'Proyectos y Servicios'}
        extras=''.join(f'<li>{e(mods.get(m,m))}</li>' for m in data['modules'] if m in mods)
        state_label='Prueba activa hasta '+date(data['trial_expires']) if data['trial_expires'] else 'Activa · sin vencimiento de prueba'
        price=money(terms['amount_minor'],terms['currency']) if terms else 'Por configurar'
        content=f'''<div class="sb-grid"><article class="sb-card"><div class="sb-between"><small>TU PLAN ACTUAL</small>{pill(state_label)}</div><h2>Base Empresarial</h2><p class="sb-price">{price}<small>{' / mes' if terms else ' Tarifa de la suscripción'}</small></p><p>CRM, ventas, inventario y facturación electrónica según la habilitación de tu empresa.</p><ul>{extras}</ul><a class="sb-button" href="/uno360x-ayuda">Solicitar cambio</a></article><article class="sb-card"><small>PRÓXIMO PAGO</small><h2>{date(terms['next_due']) if terms else 'Por configurar'}</h2><p>{price}</p><hr><p>Método de pago</p><strong>{'Transferencia bancaria' if pref['method']=='transfer' else 'Sin seleccionar'}</strong><p><a href="{link(tab='payment')}">Gestionar método de pago</a></p></article></div><article class="sb-card"><div class="sb-between"><h2>Facturas recientes</h2><a href="{link(tab='history')}">Ver historial</a></div>{rows(records[:3])}</article><p class="sb-hint">Tu condición actual se conserva. No hay cargos automáticos ni cambios de plan al guardar preferencias.</p>'''
    elif tab=='history':
        options=''.join(f'<option value="{key}" {"selected" if state==key else ""}>{label}</option>' for key,label in [('','Todos los estados'),('pending','Pendiente'),('paid','Pagada'),('void','Anulada')])
        content=f'''<form class="sb-filters" method="get" action="{PATH}"><input type="hidden" name="tab" value="history"><label>Año<input name="year" placeholder="Todos" inputmode="numeric" maxlength="4" value="{e(year)}"></label><label>Estado<select name="state">{options}</select></label><label>Buscar factura<input name="q" maxlength="80" value="{e(query)}" placeholder="Número de factura"></label><button class="sb-button">Filtrar</button></form><article class="sb-card">{rows(records)}</article>'''
    else:
        pending=[r for r in records if r['state']=='pending']
        options=''.join(f'<option value="{r["id"]}">{e(r["number"])} · {money(r["total_minor"],r["currency"])}</option>' for r in pending)
        transfer=f'''<form method="post" action="{link(tab='payment')}" enctype="multipart/form-data" class="sb-proof"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="operation" value="transfer"><input type="hidden" name="request_id" value="{uuid.uuid4().hex}"><label>Factura pendiente<select name="invoice" required>{options}</select></label><label>Referencia de la transferencia<input name="reference" maxlength="100" required></label><label>Comprobante (PDF, JPG o PNG, hasta 3 MB)<input type="file" name="proof" accept="application/pdf,image/jpeg,image/png" required></label><button class="sb-button primary">Enviar comprobante</button></form>''' if pending else '<p class="sb-hint">No tienes facturas pendientes para reportar un pago.</p>'
        content=f'''<form method="post" action="{link(tab='payment')}"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="operation" value="preferences"><div class="sb-grid"><article class="sb-card"><h2>Cómo pagar tu suscripción</h2><label class="sb-method"><input type="radio" name="method" value="transfer" required {"checked" if pref['method']=='transfer' else ''}><span><strong>Transferencia bancaria</strong><small>Envía el comprobante para revisión.</small></span></label><div class="sb-method disabled"><span><strong>Tarjeta de crédito o débito</strong><small>Pendiente de conexión con el proveedor de pagos. No ingreses números de tarjeta en UNO360X.</small></span></div></article><article class="sb-card"><h2>Datos para tus facturas</h2><p>Razón social y RNC</p><strong>Tomados de Mi empresa</strong><p><a href="/uno360x-mi-empresa">Ver datos de la empresa</a></p><label>Correo de facturación<input name="email" type="email" maxlength="254" autocomplete="email" value="{e(pref['email'])}" required></label><button class="sb-button primary">Guardar cambios</button></article></div></form><article class="sb-card"><h2>Pagar por transferencia</h2><p>Utiliza los datos bancarios indicados en tu factura de suscripción. El comprobante quedará pendiente de verificación; enviarlo no confirma el pago.</p>{transfer}</article>'''
    return (intro+feedback+content+'</div>').encode()

def embed(workspace,content):
    page=workspace.find(b'<div class="ux-page">')
    header=workspace.find(b'</header>',page) if page>=0 else -1
    footer=workspace.find(b'<footer class="ux-footer"',header) if header>=0 else -1
    if footer<0:raise ValueError('No se pudo cargar el menú de la empresa.')
    body=workspace[:header+9]+content+workspace[footer:]
    body=re.sub(rb'<title>.*?</title>',b'<title>Suscripci&#243;n | UNO360X</title>',body,count=1)
    return body.replace(b'</head>',b'<link rel="stylesheet" href="/__subscription/style.css?v=1"></head>',1)
