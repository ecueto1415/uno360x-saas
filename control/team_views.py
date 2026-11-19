"""Views for the workspace users and invitation screens."""
from html import escape
import re
from urllib.parse import urlencode

PATH = '/__team'
ROLES = {'owner':'Propietario','admin':'Administrador','member':'Empleado'}


def link(**params):
    return PATH + ('?' + urlencode(params) if params else '')


def invite_button(employee_id, csrf, text, secondary=False, level=''):
    return (f'<form method="post" action="{PATH}"><input type="hidden" name="csrf" value="{escape(csrf)}">'
            f'<input type="hidden" name="employee" value="{employee_id}">{level}<button class="{"secondary" if secondary else "button"}">'
            f'{escape(text)}</button></form>')


def shell(content, notice='', success=False):
    feedback = f'<p class="feedback {"success" if success else "error"}" role="status">{escape(notice)}</p>' if notice else ''
    return f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Usuarios | UNO360X</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#f1f5f9;color:#18283f;font:15px/1.6 system-ui,sans-serif}}
    main{{max-width:1120px;margin:28px auto;padding:0 16px}}header{{background:#101e35;color:white;border-radius:16px 16px 0 0;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px}}
    header strong{{font-size:23px;letter-spacing:-.6px}}header span{{color:#32d2bf}}header a{{color:#c3e6df}}
    section{{background:white;padding:26px;border:1px solid #dbe5ed;border-radius:0 0 16px 16px}}
    h1,h2,p{{margin:0 0 12px}}h1{{font-size:27px;line-height:1.25}}h2{{font-size:18px}}
    a{{color:#11786f;text-decoration:none}}a:hover{{text-decoration:underline}}small,.muted,.crumb{{color:#52647a}}
    .crumb{{font-size:12px;margin-bottom:17px}}.heading,.filters,.actions{{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}}
    .filters{{justify-content:flex-start;margin:18px 0}}.actions{{justify-content:flex-start;margin-top:18px}}
    form{{margin:0}}input,button,select{{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid #dbe5ed}}input{{max-width:100%}}
    .button,.secondary{{display:inline-block;padding:8px 13px;border-radius:8px;font-size:13px;font-weight:650;cursor:pointer;text-decoration:none}}
    .button{{background:#11786f;border:1px solid #11786f;color:white}}.secondary{{background:white;border:1px solid #dbe5ed;color:#11786f}}
    .pill{{display:inline-block;border-radius:20px;background:#edf2f7;color:#52647a;padding:4px 10px;font-size:12px;white-space:nowrap}}
    .pill.current,.active{{background:#e1f4ee;color:#11786f}}.pending{{background:#fff2d6;color:#765315}}
    .table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;text-align:left}}th{{background:#f1f5f9;color:#52647a;font-size:12px}}
    td,th{{padding:12px}}td{{border-bottom:1px solid #dbe5ed}}td:first-child small{{display:block;overflow-wrap:anywhere}}
    .form-grid{{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:20px}}
    .card,.aside{{border-radius:12px;padding:20px}}.card{{border:1px solid #dbe5ed}}.aside{{background:#f1f5f9}}
    .field{{background:#f1f5f9;border:1px solid #dbe5ed;border-radius:8px;padding:9px 12px;margin:6px 0 14px;overflow-wrap:anywhere}}
    .feedback{{padding:10px 13px;border-radius:8px}}.success{{background:#e1f4ee;color:#075d51}}.error{{background:#fff0ed;color:#8c2222}}
    .candidates{{list-style:none;padding:0}}.candidates li{{padding:9px 0;border-bottom:1px solid #dbe5ed}}
    .access-form{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;align-items:start}}
    .access-options{{background:#f1f5f9;border:0;border-radius:14px;margin:0;padding:20px;min-width:0}}
    .invite-access:has(input[value="admin"]:checked) .commercial-check{{display:none}}
    .access-options fieldset{{padding:0;margin:0;border:0;min-width:0}}
    .access-options button{{margin-top:12px}}
    .access-options h2{{font-size:20px}}.access-check{{display:flex;align-items:center;gap:9px;min-height:31px}}
    .access-check input,.role-card input{{margin:0;accent-color:#11786f}}
    .role-card{{display:block;padding:12px 16px;border:1px solid #dbe5ed;border-radius:11px;margin:8px 0;cursor:pointer}}
    .role-card:has(input:checked){{background:#e1f4ee;border-color:#e1f4ee;color:#11786f}}
    .role-card small{{display:block;margin-top:4px}}
    @media(max-width:650px){{main{{margin:12px auto}}section{{padding:16px}}.form-grid,.access-form{{grid-template-columns:1fr}}td,th{{padding:8px}}.heading{{align-items:flex-start}}}}
    </style><main><header><strong>UNO<span>360X</span></strong><a href="/uno360x-resumen">Volver a mi empresa</a></header>
    <section>{feedback}{content}</section></main></html>'''.encode()


def users_page(rows, csrf, search, status, notice='', success=False, can_invite_admin=False):
    tabs = ''.join(f'<a class="pill {"current" if key==status else ""}" href="{escape(link(status=key,q=search))}">{label}</a>'
                   for key,label in (('all','Todos'),('active','Activos'),('pending','Invitados')))
    records = []
    for row in rows:
        active = row['status']=='active'
        name, email = escape(row['name']), escape(row['email'])
        label = 'Activo' if active else 'Invitado'
        if active:
            action = f'<a href="{escape(link(user=row["id"]))}">Ver usuario y permisos</a>'
        elif row['role']!='admin':
            action = invite_button(row['id'],csrf,'Reenviar invitación',True)
        elif can_invite_admin:
            level = '<input type="hidden" name="role" value="admin">'
            action = invite_button(row['id'],csrf,'Reenviar invitación',True,level)
        else:
            action = ''
        records.append(f'<tr><td><strong>{name}</strong><small>{email}</small></td><td>{ROLES[row["role"]]}</td>'
                       f'<td><span class="pill {row["status"]}">{label}</span></td><td>{action}</td></tr>')
    content = f'''<div class="crumb">Ajustes / Usuarios</div><div class="heading">
    <div><h1>Usuarios</h1><p class="muted">Consulta quién tiene acceso y quién aún debe aceptar su invitación.</p></div>
    <a class="button" href="{link(view='invite')}">+ Invitar empleado</a></div><div class="filters">
    <form method="get" action="{PATH}"><input type="hidden" name="status" value="{status}">
    <input type="search" name="q" maxlength="100" value="{escape(search)}" placeholder="Buscar por nombre o correo" aria-label="Buscar por nombre o correo">
    <button class="secondary">Buscar</button></form>{tabs}</div>
    <div class="table-wrap"><table><thead><tr><th>EMPLEADO</th><th>ACCESO</th><th>ESTADO</th><th>ACCIÓN</th></tr></thead>
    <tbody>{''.join(records) or '<tr><td colspan="4">No hay usuarios que coincidan.</td></tr>'}</tbody></table></div>'''
    if len(rows)==1 and rows[0]['role']=='owner' and not search and status=='all':
        content += ('<p class="muted" style="margin-top:18px">Solo está registrada la cuenta propietaria. '
                    f'<a href="{link(view="invite")}">Invita a un empleado</a> para asignarle permisos.</p>')
    return shell(content,notice,success)


def invitation_page(rows, selected, csrf, search, notice='', can_invite_admin=False, can_grant_areas=False, can_grant_business=False):
    options = ''.join(f'<li><a href="{escape(link(view="invite",employee=row["id"]))}">{escape(row["name"])}</a>'
                      f' <small>{escape(row["work_email"] or "Sin correo laboral")}</small></li>' for row in rows)
    if selected:
        email = selected['work_email']
        identity = f'<p class="muted"><strong>{escape(selected["name"])}</strong> &middot; {escape(email or "Sin correo laboral")}</p>'
        change = f'<a href="{link(view="invite")}">Cambiar empleado</a>'
        if not email:
            return shell(f'<h1>Invitar empleado</h1>{identity}<p>Completa el correo laboral en la ficha del empleado.</p>{change}',notice)
        levels = role_options('member') if can_invite_admin else '<input type="hidden" name="role" value="member"><h2>Nivel de acceso</h2><p><strong>Empleado</strong></p>'
        areas = ''
        if can_grant_areas or can_grant_business:
            business = '<input type="hidden" name="business" value="1">' if can_grant_business else ''
            payroll = '<input type="hidden" name="areas" value="1">' if can_grant_areas else ''
            areas = (f'<fieldset class="access-options" aria-labelledby="invite-areas"><h2 id="invite-areas">Áreas permitidas</h2>{business}{payroll}'
                     '<p class="muted">Selecciona las áreas del empleado.</p>'
                     + area_controls((),can_grant_areas,can_grant_business)
                     + '<p class="muted">La lista depende del plan de la empresa.</p></fieldset>')
        return shell(f'''<div class="crumb"><a href="{PATH}">Ajustes / Usuarios</a> / Invitar empleado</div>
        <h1>Invitar empleado</h1>{identity}
        <form method="post" action="{PATH}" class="access-form invite-access">
        <input type="hidden" name="csrf" value="{escape(csrf)}">
        <input type="hidden" name="employee" value="{selected['id']}">
        <div>{levels}<div class="actions"><button class="button">Enviar invitación</button>
        <a class="secondary" href="{PATH}">Cancelar</a>{change}</div>
        <p class="muted" style="margin-top:18px">Solo el propietario puede nombrar administradores.</p></div>{areas}</form>''',notice)
    else:
        empty = '<li>No hay empleados disponibles.</li>'
        if can_grant_areas and not search and not notice:
            empty = ('<li>Todavía no hay empleados activos sin usuario. '
                     '<a href="/uno360x-empleados">Abrir Empleados</a> para registrar a la persona y su correo laboral.</li>')
        form = f'''<form method="get" action="{PATH}"><input type="hidden" name="view" value="invite">
        <label for="employee-search"><strong>Empleado sin usuario</strong></label><p></p>
        <input id="employee-search" type="search" name="q" maxlength="100" value="{escape(search)}" placeholder="Buscar empleado por nombre">
        <button class="secondary">Buscar</button></form>
        <ul class="candidates">{options or empty}</ul>'''
    return shell(f'''<div class="crumb"><a href="{PATH}">Ajustes / Usuarios</a> / Invitar empleado</div>
    <div class="form-grid"><div class="card"><h1>Invitar empleado</h1>{form}</div>
    <aside class="aside"><h2>Después de enviar</h2><ol><li>Verás el estado Invitado en Usuarios.</li>
    <li>El empleado abre el enlace de su correo.</li><li>Al aceptar, puede entrar a la empresa.</li></ol>
    <p class="muted">Si falta el correo laboral, complétalo en la ficha de empleado.</p></aside></div>''',notice)


def role_options(current):
    choices = (('member','Empleado','Trabaja en las áreas que le habilites.'),
               ('admin','Administrador de empresa','Gestiona el equipo y los ajustes de su empresa.'))
    return '<h2>Nivel de acceso</h2>' + ''.join(
        f'<label class="role-card"><input type="radio" name="role" value="{key}" {"checked" if key==current else ""}>'
        f' <strong>{label}</strong><small>{detail}</small></label>' for key,label,detail in choices)


BUSINESS_AREAS = (('pos','Punto de venta'),('sales','Ventas y CRM'),('inventory','Inventario'),('billing','Facturación'))
PAYROLL_AREAS = (('hr','Recursos Humanos'),('payroll','Nómina'))


def area_controls(areas, include_payroll=True, include_business=False):
    choices = (BUSINESS_AREAS if include_business else ()) + (PAYROLL_AREAS if include_payroll else ())
    return ''.join(f'<label class="access-check{" commercial-check" if (key,label) in BUSINESS_AREAS else ""}"><input type="checkbox" name="{key}" value="1" {"checked" if key in areas else ""}> {label}</label>'
                   for key,label in choices)


def user_page(row, can_remove=False, can_delete=False, csrf='', can_edit=False, areas=None, include_business=False, include_payroll=None, can_edit_business=None):
    remove = f'<a class="secondary" href="{escape(link(remove=row["id"]))}">Quitar acceso</a>' if can_remove else ''
    delete = f'<a class="secondary" href="{escape(link(delete=row["id"]))}">Eliminar usuario</a>' if can_delete else ''
    role = row['role']
    fields = (f'<input type="hidden" name="csrf" value="{escape(csrf)}">'
              f'<input type="hidden" name="user" value="{escape(row["id"])}">')
    levels = (f'<form method="post" action="{PATH}">{fields}{role_options(role)}'
              '<button class="button">Guardar nivel</button></form>') if can_edit else (
              f'<h2>Nivel de acceso</h2><div class="role-card"><strong>{ROLES[role]}</strong></div>')
    if include_payroll is None:
        include_payroll = areas is not None
    if can_edit_business is None:
        can_edit_business = can_edit
    business_editable = include_business and can_edit_business and role=='member'
    payroll_editable = include_payroll and can_edit
    selected = areas or ()
    if include_business and role!='member':
        selected = (*selected,*(key for key,_ in BUSINESS_AREAS))
    permissions = ''
    if payroll_editable or business_editable:
        business = '<input type="hidden" name="business" value="1">' if business_editable else ''
        payroll = '<input type="hidden" name="areas" value="1">' if payroll_editable else ''
        permissions += (f'<form method="post" action="{PATH}">{fields}'
                        f'<input type="hidden" name="grant" value="1">{business}{payroll}'
                        f'{area_controls(selected,payroll_editable,business_editable)}'
                        '<button class="button">Guardar permisos</button></form>')
    readonly = area_controls(selected,include_payroll and not payroll_editable,include_business and not business_editable)
    if readonly:
        permissions += f'<fieldset disabled aria-label="Permisos de solo lectura">{readonly}</fieldset>'
    if role=='owner' and permissions:
        permissions += (f'<p class="muted">La cuenta propietaria tiene acceso a estas áreas. '
                        f'<a href="{link(view="invite")}">Invita a un empleado</a> para elegir sus permisos.</p>')
    if not permissions:
        permissions = '<p class="muted">No hay áreas disponibles para este plan.</p>'
    return shell(f'''<div class="crumb"><a href="{PATH}">Ajustes / Usuarios</a> / Ver usuario y permisos</div>
    <h1>Usuario y permisos</h1>
    <p class="muted"><strong>{escape(row['name'])}</strong> &middot; {escape(row['email'])} <span class="pill active">Activo</span></p>
    <div class="access-form"><div>{levels}
    <div class="actions">{remove}{delete}<a href="{PATH}">Volver a Usuarios</a></div></div>
    <aside class="access-options" aria-labelledby="user-areas"><h2 id="user-areas">Áreas permitidas</h2>{permissions}</aside></div>''')


def workspace_shell(workspace, screen):
    page = workspace.find(b'<div class="ux-page">')
    header = workspace.find(b'</header>',page) if page>=0 else -1
    footer = workspace.find(b'<footer class="ux-footer"',header) if header>=0 else -1
    styles = re.search(rb'<style>(.*?)</style>',screen,re.S)
    content = re.search(rb'<section>(.*?)</section></main>',screen,re.S)
    if footer<0 or not styles or not content:
        return screen

    def scope(match):
        selector = match[1].strip()
        if selector.startswith(b'@'):
            return selector+b'{'
        return b','.join(b'#uno-team-screen '+item.strip() for item in selector.split(b','))+b'{'

    css = re.sub(rb'(?:^|(?<=[{}]))([^{}]+)\{',scope,styles[1])
    embedded = b'<style>'+css+b'</style><div id="uno-team-screen"><section>'+content[1]+b'</section></div>'
    return workspace[:header+9]+embedded+workspace[footer:]


def removal_page(row, csrf, delete=False):
    target = escape(row['id'])
    title = 'Eliminar usuario' if delete else 'Quitar acceso'
    field = 'delete' if delete else 'remove'
    detail = ('El usuario se eliminará de esta empresa. Los accesos a otras empresas se conservan.' if delete
              else 'Su actividad anterior se conserva. Su cuenta UNO360X puede seguir usándose en otras empresas.')
    return shell(f'''<div class="crumb"><a href="{PATH}">Ajustes / Usuarios</a></div>
    <h1>{title}</h1><p><strong>{escape(row['name'])}</strong> dejará de poder entrar a esta empresa.</p>
    <p class="muted">{detail}</p>
    <div class="actions"><form method="post" action="{PATH}">
    <input type="hidden" name="csrf" value="{escape(csrf)}"><input type="hidden" name="{field}" value="{target}">
    <button class="button" type="submit">Confirmar</button></form>
    <a class="secondary" href="{escape(link(user=row['id']))}">Cancelar</a></div>''')


