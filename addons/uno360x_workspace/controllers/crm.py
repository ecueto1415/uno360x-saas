from urllib.parse import urlencode

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.osv import expression
from odoo.tools.misc import format_amount
from werkzeug.exceptions import Forbidden, NotFound

from .areas import AreaWorkspace


CRM_URL = '/uno360x/area/crm'


class CrmWorkspace(AreaWorkspace):
    def _crm_context(self):
        service = self._service()
        values = service._workspace_context()
        if not service._area_available('crm', values):
            raise NotFound()
        values['page_key'] = 'crm'
        return service, values

    def _crm_teams(self):
        return request.env['crm.team'].search([
            ('company_id', 'in', [False, request.env.company.id]),
            ('use_opportunities', '=', True),
        ])

    def _crm_url(self, **params):
        return CRM_URL + ('?' + urlencode(params) if params else '')

    def _crm_team(self, teams, value):
        try:
            return teams.filtered_domain([('id', '=', int(value))])[:1]
        except (ValueError, TypeError):
            return teams[:0]

    @http.route()
    def area(self, key, q='', **kw):
        if key != 'crm':
            return super().area(key, q=q, **kw)
        service, values = self._crm_context()
        env = request.env
        teams = self._crm_teams()
        team = self._crm_team(teams, kw.get('flow'))
        if kw.get('new') == '1':
            return self._opportunity_form(values, teams, team)
        values['crm_saved'] = kw.get('saved') == '1'
        stage_model = env['crm.stage']
        lead_model = env['crm.lead']
        action = service._area_action('crm', values)
        action_url = '/odoo/action-%s' % action.id if action else ''
        q = str(q or '').strip()[:100]
        domain = [('type', '=', 'opportunity'), ('company_id', '=', env.company.id)]
        if team:
            domain.append(('team_id', '=', team.id))
        if q:
            domain = expression.AND([domain, ['|', ('name', 'ilike', q),
                                              ('partner_id.name', 'ilike', q)]])
        stages_domain = ['|', ('team_id', '=', False), ('team_id', 'in', team.ids if team else teams.ids)]
        params = {'q': q}
        if team:
            params['flow'] = team.id
        list_mode = kw.get('view') == 'list'
        values.update(crm_view_list=self._crm_url(**params, view='list'),
                      crm_view_board=self._crm_url(**params))
        if list_mode:
            if str(kw.get('only_stage', '')).isdigit():
                params['only_stage'] = int(kw['only_stage'])
                domain.append(('stage_id', '=', params['only_stage'] or False))
            try:
                page = max(1, min(10000, int(kw.get('page', 1))))
            except (ValueError, TypeError):
                page = 1
            rows = lead_model.search(domain, offset=(page - 1) * 40, limit=41)
            currency = env.company.currency_id
            values.update(crm_rows=[{
                'id': lead.id, 'title': lead.name, 'client': lead.partner_id.name or lead.partner_name,
                'stage': lead.stage_id.name or _('Sin etapa'),
                'amount': format_amount(env, lead.expected_revenue, currency),
            } for lead in rows[:40]], crm_previous=self._crm_url(**params, view='list', page=page - 1) if page > 1 else '',
                crm_next=self._crm_url(**params, view='list', page=page + 1) if len(rows) > 40 else '')
        groups = [] if list_mode else lead_model._read_group(domain, ['stage_id'], ['__count', 'expected_revenue:sum'])
        totals = {stage.id: (count, amount) for stage, count, amount in groups}
        stages = stage_model.search(stages_domain)
        if team and any(stages.mapped('team_id')):
            stages = stages.filtered(lambda stage: stage.team_id or stage.id in totals)
        stages |= stage_model.browse([sid for sid in totals if sid])
        columns = []
        currency = env.company.currency_id
        for stage in stages.sorted(lambda stage: (stage.sequence, stage.name, stage.id)):
            columns.append((stage.id, stage.name))
        if False in totals:
            columns.append((False, _('Sin etapa')))
        try:
            selected_stage = int(kw.get('stage', ''))
        except (ValueError, TypeError):
            selected_stage = None
        if selected_stage not in {int(sid) for sid, name in columns}:
            selected_stage = int(columns[0][0]) if columns else None
        cards = []
        for sid, title in columns:
            count, total = totals.get(sid, (0, 0))
            leads = lead_model.search(domain + [('stage_id', '=', sid)], limit=24) if count else lead_model.browse()
            cards.append({
                'id': int(sid), 'title': title, 'count': count,
                'total': format_amount(env, total, currency), 'more': self._crm_url(**params, view='list', only_stage=int(sid)) if count > len(leads) else '',
                'leads': [{
                    'id': lead.id, 'client': lead.partner_id.name or lead.partner_name,
                    'title': lead.name, 'amount': format_amount(env, lead.expected_revenue, currency),
                    'activity': lead.activity_summary or lead.activity_type_id.name,
                    'deadline': lead.activity_date_deadline,
                } for lead in leads],
            })
        create_url = self._crm_url(**params, new=1)
        values.update(crm_teams=teams, crm_team=team, crm_query=q, crm_columns=cards,
                      crm_stage=selected_stage, crm_native=action_url, crm_create=create_url,
                      crm_can_create=lead_model.has_access('create'),
                      crm_manager=env.user.has_group('sales_team.group_sale_manager'),
                      crm_list=kw.get('view') == 'list')
        return self._render('uno360x_workspace.crm_board', values)

    def _opportunity_form(self, values, teams, team, entry=None, error=''):
        if not request.env['crm.lead'].has_access('create'):
            raise Forbidden()
        values.update(crm_teams=teams, crm_team=team, crm_entry=entry or {},
                      crm_error=error, crm_back=self._crm_url(**({'flow': team.id} if team else {})))
        return self._render('uno360x_workspace.crm_new', values)

    @http.route('/uno360x/area/crm/opportunity', type='http', auth='user', methods=['POST'], csrf=True)
    def crm_opportunity(self, flow=None, name='', **kw):
        _, values = self._crm_context()
        teams = self._crm_teams()
        team = self._crm_team(teams, flow)
        env = request.env
        leads = env['crm.lead']
        if not leads.has_access('create'):
            raise Forbidden()
        entry = {'name': str(name or '').strip()[:160]}
        for field, size in (('partner_name', 120), ('email_from', 160), ('phone', 60)):
            entry[field] = str(kw.get(field) or '').strip()[:size]
        if not entry['name'] or (flow and not team):
            msg = _('Escribe el nombre de la oportunidad.') if not entry['name'] else _('Selecciona un flujo disponible.')
            return self._opportunity_form(values, teams, team, entry, msg)
        data = dict(entry, type='opportunity', company_id=env.company.id)
        if team:
            data['team_id'] = team.id
            stage = env['crm.stage'].search([('team_id', '=', team.id)], limit=1)
            if stage:
                data['stage_id'] = stage.id
        try:
            with env.cr.savepoint():
                leads.create(data)
        except AccessError:
            raise Forbidden() from None
        except UserError as exc:
            return self._opportunity_form(values, teams, team, entry, str(exc))
        return request.redirect(self._crm_url(saved=1, **({'flow': team.id} if team else {})), code=303)

    @http.route('/uno360x/area/crm/record/<int:record_id>', type='http', auth='user',
                methods=['GET', 'POST'], csrf=True)
    def crm_record(self, record_id, edit='', saved='', **kw):
        _, values = self._crm_context()
        env = request.env
        lead = env['crm.lead'].search([
            ('id', '=', record_id), ('type', '=', 'opportunity'),
            ('company_id', '=', env.company.id),
        ], limit=1)
        if not lead:
            raise NotFound()
        can_edit = lead.has_access('write')
        posting = request.httprequest.method == 'POST'
        editing = posting or edit == '1'
        if editing and not can_edit:
            raise Forbidden()
        url = CRM_URL + '/record/%s' % lead.id
        stages = env['crm.stage'].search(['|', ('team_id', '=', False),
                                               ('team_id', '=', lead.team_id.id or False)])
        fields = {'name': 160, 'partner_name': 120, 'email_from': 160, 'phone': 60}
        entry = {field: lead[field] or '' for field in fields}
        stage_id = lead.stage_id.id or 0
        error = ''
        if posting:
            entry = {field: str(kw.get(field, entry[field]) or '').strip()[:size]
                     for field, size in fields.items()}
            try:
                next_stage = int(kw.get('stage_id', stage_id))
                if not entry['name']:
                    raise UserError(_('Escribe el nombre de la oportunidad.'))
                if next_stage != stage_id and next_stage not in stages.ids:
                    raise UserError(_('Selecciona una etapa de este flujo.'))
                changes = {field: value for field, value in entry.items()
                           if value != (lead[field] or '')}
                if next_stage != stage_id:
                    changes['stage_id'] = next_stage
                with env.cr.savepoint():
                    if changes:
                        lead.write(changes)
                return request.redirect(url + '?saved=1', code=303)
            except AccessError:
                raise Forbidden() from None
            except UserError as exc:
                error = str(exc)
            except (ValueError, TypeError):
                error = _('Selecciona una etapa válida.')
        quote_action = env.ref('uno360x_workspace.crm_to_quote')
        quote_url = ('/odoo/action-%s?active_id=%s' % (quote_action.id, lead.id)
                     if env['sale.order'].has_access('create') else '')
        values.update(
            crm_quote_url=quote_url, crm_record=lead, crm_can_edit=can_edit, crm_editing=editing,
            crm_saved=saved == '1' and not editing, crm_stages=stages,
            crm_entry=entry, crm_selected_stage=stage_id, crm_error=error,
            crm_detail_amount=format_amount(env, lead.expected_revenue, lead.company_currency),
            crm_record_url=url,
            crm_back=self._crm_url(**({'flow': lead.team_id.id} if lead.team_id else {})),
        )
        return self._render('uno360x_workspace.crm_record', values)

    @http.route('/uno360x/area/crm/manage', type='http', auth='user', methods=['GET', 'POST'], csrf=True)
    def crm_manage(self, flow=None, mode='', name='', stages='', after=None, edit=None, **kw):
        _, values = self._crm_context()
        env = request.env
        if not env.user.has_group('sales_team.group_sale_manager'):
            raise Forbidden()
        teams = self._crm_teams()
        team = self._crm_team(teams, flow)
        stage_model = env['crm.stage']
        specific = stage_model.search([('team_id', '=', team.id)]) if team else stage_model.browse()
        edit_stage = self._crm_team(specific, edit)
        error = ''
        crm_after = self._crm_team(specific - edit_stage, after)
        if edit_stage and after is None:
            index = list(specific).index(edit_stage)
            crm_after = specific[index - 1] if index else specific[:0]
        if request.httprequest.method == 'POST':
            try:
                with env.cr.savepoint():
                    clean_name = str(name or '').strip()[:100]
                    if not clean_name:
                        raise UserError(_('Escribe un nombre.'))
                    if mode == 'flow':
                        names = [line.strip()[:100] for line in str(stages or '')[:2200].splitlines() if line.strip()]
                        if not names or len(names) > 20 or len(set(n.casefold() for n in names)) != len(names):
                            raise UserError(_('Escribe entre 1 y 20 etapas con nombres distintos.'))
                        team = env['crm.team'].create({'name': clean_name, 'company_id': env.company.id,
                                                       'use_opportunities': True})
                        stage_model.create([{'name': n, 'team_id': team.id, 'sequence': i * 10}
                                            for i, n in enumerate(names)])
                        return request.redirect(self._crm_url(flow=team.id), code=303)
                    if mode != 'stage' or not team:
                        raise UserError(_('Selecciona un flujo.'))
                    if edit and not edit_stage:
                        raise UserError(_('La etapa ya no está disponible en este flujo.'))
                    remaining = specific - edit_stage
                    preceding = self._crm_team(remaining, after)
                    if after not in (None, '', '0') and not preceding:
                        raise UserError(_('Selecciona una posición válida.'))
                    if any(stage.name.casefold() == clean_name.casefold() for stage in remaining):
                        raise UserError(_('Ya existe una etapa con ese nombre en este flujo.'))
                    if edit_stage:
                        edit_stage.write({'name': clean_name})
                        stage = edit_stage
                    else:
                        stage = stage_model.create({'name': clean_name, 'team_id': team.id})
                    order = list(remaining)
                    order.insert(order.index(preceding) + 1 if preceding else 0, stage)
                    for index, item in enumerate(order):
                        if item.sequence != index * 10:
                            item.sequence = index * 10
                    return request.redirect(self._crm_url(flow=team.id), code=303)
            except AccessError:
                raise Forbidden() from None
            except UserError as exc:
                error = exc.args[0]
        values.update(crm_teams=teams, crm_team=team, crm_specific=specific,
                      crm_edit=edit_stage, crm_after=crm_after, crm_error=error, crm_name=name, crm_stages=stages,
                      crm_mode=mode or ('stage' if team else 'flow'),
                      crm_back=self._crm_url(**({'flow': team.id} if team else {})))
        return self._render('uno360x_workspace.crm_manage', values)
