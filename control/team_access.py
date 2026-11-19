"""Tenant-scoped team administration rendered by the trusted workspace gateway."""
import hmac
import re
from urllib.parse import parse_qs, urlsplit

from .access_broker import _rpc
from .identity import IdentityError, IdentityService, email_key
from .identity_http import csrf_for

from .team_views import PATH, invitation_page, removal_page, user_page, users_page, workspace_shell
PROFILE = re.compile(rb'(<div class="ux-profile">[^<]*(?:<(?!/?div\b)[^>]*>[^<]*)*<div>.*?</div>)(</div>)', re.S)
GEAR = b'''<details class="ux-team-settings" style="position:relative;flex:none"><summary title="Ajustes de usuarios" aria-label="Ajustes de usuarios"
 style="display:inline-grid;cursor:pointer;list-style:none;place-items:center;width:36px;height:36px;flex:none;border:1px solid #dce4ed;border-radius:9px;background:white;color:#12877c">
 <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M10 2h4l.6 3 2 .9 2.7-1.5 2.3 2.3-1.5 2.7.9 2 3 .6v3l-3 .6-.9 2 1.5 2.7-2.3 2.3-2.7-1.5-2 .9-.6 2h-4l-.6-2-2-.9-2.7 1.5-2.3-2.3 1.5-2.7-.9-2-3-.6v-3l3-.6.9-2-1.5-2.7 2.3-2.3L7.4 6l2-.9z" transform="translate(1 0) scale(.89)"/><circle cx="12" cy="12" r="3"/></svg></summary>
 <div style="position:absolute;right:0;top:calc(100% + 8px);z-index:50;min-width:182px;padding:5px;border:1px solid #dce4ed;border-radius:9px;background:white;box-shadow:0 8px 24px #18283f24">
  <a href="/__team" style="display:block;padding:8px 10px;color:#18283f;white-space:nowrap">Usuarios y permisos</a>
  <a href="/__team?view=invite" style="display:block;padding:8px 10px;color:#11786f;white-space:nowrap">Invitar empleado</a>
 </div></details>'''


def allowed(handle):
    return handle.backend.claims['role'] in ('owner', 'admin')


PAYROLL_LINK = b'<a href="/odoo/payroll-receipts" title="Recibos de n&#243;mina" style="color:#11786f;font-weight:650">N&#243;mina</a>'
PAYROLL_CONTRACTS_LINK = b'<a href="/odoo/payroll-contracts" title="Contratos y salarios" style="color:#11786f;font-weight:650">Salarios</a>'


def decorate(handle, path, status, headers, body):
    route = urlsplit(path).path
    workspace_page = route.startswith(('/uno360x-', '/uno360x/'))
    native_page = route == '/web' or route == '/odoo' or route.startswith('/odoo/')
    if (status == 200 and (workspace_page or native_page)
            and any(k.lower()=='content-type' and v.startswith('text/html') for k,v in headers)
            and PROFILE.search(body)):
        additions = GEAR if allowed(handle) else b''
        if route.startswith('/uno360x-') and 'payroll' in handle.backend.claims.get('work_permissions',()):
            additions += PAYROLL_LINK + PAYROLL_CONTRACTS_LINK
        if additions:
            body = PROFILE.sub(lambda match: match[1]+additions+match[2],body,count=1)
            headers = [(k,v) for k,v in headers if k.lower() not in ('etag','last-modified')]
    return status, headers, body


def employees(handle, search='', employee_id=None):
    domain = [('active','=',True),('user_id','=',False)]
    if employee_id is not None:
        domain.append(('id','=',employee_id))
    elif search:
        domain.append(('name','ilike',search))
    backend = handle.backend
    with handle.lock:
        return _rpc(backend.opener,backend.base,'/web/dataset/call_kw/hr.employee/search_read',
                    {'model':'hr.employee','method':'search_read','args':[domain],
                     'kwargs':{'fields':['name','work_email'],'limit':50,'order':'name,id'}})


def send_invitation(manager, handle, identity, employee_id, role="member", work_permissions=None, business=None):
    rows = employees(handle,employee_id=employee_id)
    if len(rows)!=1:
        raise IdentityError('Este empleado ya tiene usuario o no esta disponible.')
    email = email_key(rows[0]['work_email'])
    manager.validate(handle,identity)
    options = {} if work_permissions is None else {'work_permissions':work_permissions}
    if business is not None:
        options['business'] = business
    identity.invite(handle.backend.central_session,handle.tenant,email,role,employee_id=employee_id,**options)


def user_rows(handle, identity):
    tenant = handle.tenant
    active = identity.members(handle.backend.central_session,tenant)
    for row in active:
        draft = identity.db.execute('SELECT name FROM trial_signup_drafts WHERE account_id=?',(row['id'],)).fetchone()
        row.update(name=draft['name'] if draft and draft['name'] else row['email'],status='active')
    tables = {r[0] for r in identity.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('employee_invites','employee_memberships')")}
    links = {}
    if 'employee_memberships' in tables:
        links = dict(identity.db.execute('SELECT account_id,employee_id FROM employee_memberships WHERE tenant_id=?',(tenant,)))
    pending = []
    if 'employee_invites' in tables:
        active_emails = {row['email'] for row in active}
        for row in identity.db.execute("""
            SELECT t.email,t.role,e.employee_id FROM identity_tokens t JOIN employee_invites e ON e.token_digest=t.digest AND e.tenant_id=t.tenant_id
            WHERE t.tenant_id=? AND t.purpose='invite' AND t.used=0 AND t.expires>? ORDER BY t.email
        """,(tenant,identity.clock())):
            if row['email'] not in active_emails:
                pending.append(dict(id=row['employee_id'],name=row['email'],email=row['email'],role=row['role'],status='pending'))
    employee_ids = sorted(set(links.values()) | {row['id'] for row in pending})
    names = {}
    if employee_ids:
        backend = handle.backend
        try:
            with handle.lock:
                records = _rpc(backend.opener,backend.base,'/web/dataset/call_kw/hr.employee/search_read',
                               {'model':'hr.employee','method':'search_read','args':[[('id','in',employee_ids)]],
                                'kwargs':{'fields':['name'],'limit':len(employee_ids)}})
            names = {row['id']:row['name'] for row in records}
        except IdentityError:
            pass
    for row in active:
        row['name'] = names.get(links.get(row['id']),row['name'])
    for row in pending:
        row['name'] = names.get(row['id'],row['name'])
    return sorted(active+pending,key=lambda row:(row['status'],row['name'].casefold()))


def can_remove(handle, row):
    actor = handle.backend.claims
    return row['id']!=actor['account_id'] and row['role']!='owner' and (actor['role']=='owner' or row['role']=='member')


def reply_screen(handler, handle, status, content):
    manager = handler.server.manager
    upstream_status, headers, workspace = manager.forward(handle,'GET','/uno360x-resumen',dict(handler.headers),b'')
    if upstream_status==200:
        _,_,workspace = decorate(handle,'/uno360x-resumen',upstream_status,headers,workspace)
        content = workspace_shell(workspace,content)
    handler.reply(status,content,[('Content-Type','text/html; charset=utf-8')])


def dispatch(handler, handle, url):
    manager = handler.server.manager
    identity = manager.identity()
    try:
        manager.validate(handle,identity)
        if not allowed(handle):
            handler.reply(403)
            return
        csrf = csrf_for(handle.token)
        if handler.command == 'POST':
            if handler.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded' or handler.headers.get('Transfer-Encoding'):
                handler.reply(400)
                return
            try:
                size = int(handler.headers.get('Content-Length','0'))
                if not 1 <= size <= 1024:
                    raise ValueError()
                data = parse_qs(handler.rfile.read(size).decode(),strict_parsing=True,max_num_fields=11)
                business_fields = set(IdentityService.business_areas)
                grant = {'csrf','user','grant'} <= set(data) <= {'csrf','user','grant','areas','hr','payroll','business'} | business_fields
                invitation_fields = {'csrf','employee','role'}
                invite_areas = invitation_fields < set(data) <= invitation_fields | {'areas','hr','payroll','business'} | business_fields
                if (business_fields & set(data) and 'business' not in data
                        or {'hr','payroll'} & set(data) and 'areas' not in data):
                    raise ValueError()
                if any(data[key] != ['1'] for key in (business_fields | {'grant','areas','business','hr','payroll'}) & set(data)):
                    raise ValueError()
                if (not grant and not invite_areas and set(data) not in ({'csrf','employee'},{'csrf','employee','role'},{'csrf','remove'},{'csrf','delete'},{'csrf','user','role'})) or any(len(v)!=1 for v in data.values()):
                    raise ValueError()
                edit = 'user' in data
                role = data.get('role',['member'])[0]
                if role not in ('member','admin'):
                    raise ValueError()
                delete = 'delete' in data
                target = data.get('user',data.get('delete',data.get('remove',[''])))[0]
                if 'remove' in data or delete or edit:
                    if not re.fullmatch('[a-f0-9]{32}',target) or target==handle.backend.claims['account_id']:
                        raise ValueError()
                else:
                    employee_id = int(data['employee'][0])
                    if not 0 < employee_id <= 2147483647:
                        raise ValueError()
            except (ValueError,UnicodeError):
                handler.reply(400)
                return
            if not hmac.compare_digest(data['csrf'][0],csrf):
                handler.reply(403)
                return
            try:
                business = tuple(key for key in IdentityService.business_areas if key in data) if 'business' in data else None
                if grant:
                    options = {'hr':'hr' in data,'payroll':'payroll' in data} if 'areas' in data else {}
                    identity.set_work_permissions(handle.backend.central_session,handle.tenant,target,business=business,**options)
                elif edit:
                    identity.change_role(handle.backend.central_session,handle.tenant,target,role)
                elif delete:
                    identity.delete_unused_member(handle.backend.central_session,handle.tenant,target)
                elif target:
                    identity.remove_member(handle.backend.central_session,handle.tenant,target)
                else:
                    areas = (data.get('hr')==['1'],data.get('payroll')==['1']) if invite_areas and 'areas' in data else None
                    send_invitation(manager,handle,identity,employee_id,role,areas,business if role=='member' else None)
            except (IdentityError,ValueError) as error:
                reply_screen(handler,handle,409,users_page(user_rows(handle,identity),csrf,'','all',str(error)))
                return
            handler.reply(303,headers=[('Location',PATH+('?changed=1' if edit else '?deleted=1' if delete else '?removed=1' if target else '?sent=1'))])
            return
        if handler.command not in ('GET','HEAD'):
            handler.reply(405)
            return
        try:
            query = parse_qs(url.query,max_num_fields=5)
        except ValueError:
            handler.reply(400)
            return
        search = query.get('q',[''])[0][:100].strip()
        if query.get('view')==['invite']:
            raw_id = query.get('employee',[''])[0]
            selected = None
            notice = ''
            try:
                if raw_id:
                    if not raw_id.isascii() or not raw_id.isdigit() or not 0 < int(raw_id) <= 2147483647:
                        handler.reply(400)
                        return
                    selected = next(iter(employees(handle,employee_id=int(raw_id))),None)
                    if selected is None:
                        notice = 'Este empleado ya tiene usuario o no está disponible.'
                rows = [] if selected else employees(handle,search)
            except IdentityError:
                rows = []
                notice = 'El directorio de empleados no está disponible para tu plan o permisos.'
            owner = handle.backend.claims['role']=='owner'
            can_grant_areas = owner and 'uno360x_payroll_hr' in handle.backend.snapshot['installation']['addons']
            reply_screen(handler,handle,200,invitation_page(rows,selected,csrf,search,notice,owner,can_grant_areas,True))
            return
        rows = user_rows(handle,identity)
        if 'user' in query or 'remove' in query or 'delete' in query:
            target = query.get('delete',query.get('remove',query.get('user')))[0]
            row = next((row for row in rows if row['status']=='active' and row['id']==target),None)
            if not row:
                handler.reply(404)
                return
            may_remove = can_remove(handle,row)
            may_delete = may_remove and row['role']=='member' and not identity.member_has_used_space(handle.tenant,row['id'])
            if ('remove' in query and not may_remove) or ('delete' in query and not may_delete):
                handler.reply(403)
                return
            may_edit = handle.backend.claims['role']=='owner' and row['role']!='owner'
            areas = identity.work_permissions(handle.tenant,row['id'],row['role'])
            if row['role']=='member' and 'scoped' not in areas:
                areas += ('sales',)
            has_payroll = 'uno360x_payroll_hr' in handle.backend.snapshot['installation']['addons']
            content = removal_page(row,csrf,delete='delete' in query) if 'remove' in query or 'delete' in query else user_page(
                row,may_remove,may_delete,csrf,may_edit,areas,include_business=True,include_payroll=has_payroll,can_edit_business=row['role']=='member')
        else:
            status = query.get('status',['all'])[0]
            if status not in ('all','active','pending'):
                status = 'all'
            term = search.casefold()
            rows = [row for row in rows if (status=='all' or row['status']==status)
                    and (term in row['name'].casefold() or term in row['email'].casefold())]
            sent = query.get('sent')==['1']
            removed = query.get('removed')==['1']
            deleted = query.get('deleted')==['1']
            changed = query.get('changed')==['1']
            notice = 'Nivel de acceso actualizado.' if changed else 'Usuario eliminado de esta empresa.' if deleted else 'Acceso retirado.' if removed else ('Invitación enviada al correo laboral.' if sent else '')
            content = users_page(rows,csrf,search,status,notice,sent or removed or deleted or changed,handle.backend.claims['role']=='owner')
        reply_screen(handler,handle,200,content)
    finally:
        identity.close()
