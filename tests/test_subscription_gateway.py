from urllib.parse import urlencode
from unittest.mock import patch
from control.subscription_store import Subscription
from control.subscription import token
from tests.test_gateway import GatewayTests

class SubscriptionGatewayTests(GatewayTests):
 def test_subscription_uses_same_gateway_auth_and_rejects_employee_direct_access(self):
  ledger=Subscription(self.identity);ledger.initialize()
  self.assertEqual(401,self.request('/uno360x-suscripcion')[0])
  self.enter()
  handle=next(iter(self.manager.handles.values()))
  shell=b'<html><head><title>App</title></head><body><div class="ux-page"><header>UNO360X</header>OLD<footer class="ux-footer">Company</footer></div></body></html>'
  forward=self.manager.forward
  with patch.object(self.manager,'forward',return_value=(200,[('Content-Type','text/html')],shell)):
   status,_,body=self.request('/uno360x-suscripcion');self.assertEqual(200,status);self.assertIn(b'Suscripci',body)
  message=urlencode({'csrf':token(handle),'operation':'preferences','method':'transfer','email':'billing@example.test'}).encode()
  headers={'Origin':self.server.origin,'Content-Type':'application/x-www-form-urlencoded'}
  self.assertEqual(403,self.request('/uno360x-suscripcion','POST',message,dict(headers,Origin='https://evil.example'))[0])
  self.assertEqual(303,self.request('/uno360x-suscripcion?tab=payment','POST',message,headers)[0])
  self.assertEqual('billing@example.test',ledger.overview(self.session,self.tid)['preferences']['email'])
  account=self.identity._account(self.session)
  with self.identity.db:self.identity.db.execute("UPDATE memberships SET role='member' WHERE account_id=? AND tenant_id=?",(account['id'],self.tid))
  handle.backend.claims.update(role='member',work_permissions=self.identity.work_permissions(self.tid,account['id'],'member'))
  for route in ['/uno360x-suscripcion','/uno360x-suscripcion?tab=history','/__subscription/style.css']:
   self.assertEqual(403,self.request(route)[0])
  self.assertEqual(403,self.request('/uno360x-suscripcion','POST',message,headers)[0])
  # The rest of the employee's workspace remains available.
  self.assertEqual(200,self.request('/odoo')[0])
