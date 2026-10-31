from pathlib import Path
from odoo import fields,models
from odoo.exceptions import AccessDenied
from .protocol import verify


class BridgeNonce(models.Model):
    _name='uno360x.auth.nonce'
    _description='Accesos de un uso de UNO360X'
    nonce=fields.Char(required=True,index=True)
    expires=fields.Float(required=True)
    _sql_constraints=[('nonce_unique','unique(nonce)','Acceso ya utilizado.')]
    # No ACL: only authentication code may access this technical ledger via sudo.


class Users(models.Model):
    _inherit='res.users'
    uno360x_account_id=fields.Char(readonly=True,copy=False,index=True,groups='base.group_system')
    _sql_constraints=[('uno360x_account_unique','unique(uno360x_account_id)','Identidad de acceso duplicada.')]

    def _check_credentials(self, credential, user_agent_env):
        if credential.get('type')!='uno360x_bridge':
            return super()._check_credentials(credential,user_agent_env)
        self.ensure_one()
        try:
            identity=self.env['uno360x.tenant.identity'].sudo().search([],limit=2)
            if len(identity)!=1 or not self.sudo().uno360x_account_id:raise ValueError()
            key=Path('/run/uno360x/bridge.key').read_bytes()
            data=verify(key,credential.get('password'),identity.tenant_id,self.login)
            if data['sub']!=self.sudo().uno360x_account_id:raise ValueError()
            # Unique insert is atomic even under concurrent replay attempts.
            with self.env.cr.savepoint():
                self.env['uno360x.auth.nonce'].sudo().create({'nonce':data['jti'],'expires':data['exp']})
        except Exception:
            raise AccessDenied() from None
        return {'uid':self.id,'auth_method':'uno360x_bridge','mfa':'default'}
