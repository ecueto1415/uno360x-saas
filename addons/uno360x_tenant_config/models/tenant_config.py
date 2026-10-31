import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenantIdentity(models.Model):
    _name = 'uno360x.tenant.identity'
    _description = 'Identidad SaaS de la instancia'

    tenant_id = fields.Char(required=True, readonly=True, copy=False)
    hostname = fields.Char(required=True, readonly=True, copy=False)
    singleton_key = fields.Integer(default=1, required=True, readonly=True)
    _sql_constraints = [
        ('one_identity', 'unique(singleton_key)', 'Solo una identidad por instancia.'),
        ('fixed_key', 'CHECK(singleton_key = 1)', 'Identidad de instancia inválida.'),
    ]

    @api.constrains('tenant_id', 'hostname')
    def _check_identity(self):
        for rec in self:
            if not re.fullmatch(r'[a-f0-9]{32}', rec.tenant_id or ''):
                raise ValidationError('Identificador SaaS inválido.')
            if not re.fullmatch(r'[a-z][a-z0-9-]{1,38}[a-z0-9]\.uno360x\.com', rec.hostname or ''):
                raise ValidationError('Dominio SaaS inválido.')


class CompanyFiscalSetup(models.Model):
    _inherit = 'res.company'

    uno360x_ecf_setup_state = fields.Selection([
        ('not_started', 'Sin configurar'),
        ('pending_validation', 'Pendiente de validación'),
        ('blocked', 'Bloqueado'),
    ], default='not_started', readonly=True, copy=False,
       groups='base.group_system')
    # No active state or emission switch until a real adapter verifies the gates.
    # Never store certificates/passwords as ordinary fields or public attachments.
