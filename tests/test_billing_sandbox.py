import hashlib,hmac,json,secrets,tempfile,unittest
from pathlib import Path
from control.identity import IdentityService
from control.billing_sandbox import SandboxBilling

class BillingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.mail=[];self.now=2000000000
        self.identity=IdentityService(Path(self.tmp.name)/'control.sqlite3',self.mail.append,clock=lambda:self.now)
        self.identity.register('owner@example.test');self.identity.complete_registration(self.mail[-1]['token'],'Clave ficticia billing 2026')
        self.session=self.identity.login('owner@example.test','Clave ficticia billing 2026')['session']
        self.tenant=self.identity.create_company(self.session,'billing-ficticio',['jenifer_ai'],'one')['id']
        self.key=secrets.token_bytes(32)
        self.billing=SandboxBilling(self.identity,self.key,{'currency':'DOP','prices':{'business_base':10000,'jenifer_ai':5000}})
    def tearDown(self):self.identity.close();self.tmp.cleanup()
    def event(self,cid,status='paid',event_id='fixture-1',**changes):
        data={'event_id':event_id,'checkout_id':cid,'status':status,'amount_minor':15000,'currency':'DOP','period_seconds':3600,'sandbox':True};data.update(changes)
        body=json.dumps(data,sort_keys=True).encode();return body,hmac.new(self.key,body,hashlib.sha256).hexdigest()
    def test_no_pricebook_means_no_checkout_and_no_real_charge(self):
        service=SandboxBilling(self.identity,self.key)
        self.assertEqual(service.quote(self.session,self.tenant)['price_status'],'undefined')
        with self.assertRaises(ValueError):service.checkout(self.session,self.tenant,'one')
    def test_idempotent_checkout_event_and_expiry(self):
        first=self.billing.checkout(self.session,self.tenant,'one')
        self.assertEqual(first,self.billing.checkout(self.session,self.tenant,'one'))
        body,sig=self.event(first['checkout_id']);self.billing.receive(body,sig)
        self.assertTrue(self.billing.receive(body,sig)['duplicate'])
        self.assertTrue(self.billing.entitlement(self.session,self.tenant)['sandbox_subscription_active'])
        self.assertFalse(self.billing.entitlement(self.session,self.tenant)['production_access_enabled'])
        self.now+=3600
        self.assertFalse(self.billing.entitlement(self.session,self.tenant)['sandbox_subscription_active'])
    def test_signature_amount_currency_and_real_flag_rejected(self):
        cid=self.billing.checkout(self.session,self.tenant,'one')['checkout_id']
        body,sig=self.event(cid)
        with self.assertRaises(ValueError):self.billing.receive(body,'0'*64)
        for changes in [{'amount_minor':1},{'currency':'USD'},{'sandbox':False}]:
            body,sig=self.event(cid,**changes)
            with self.assertRaises(ValueError):self.billing.receive(body,sig)
    def test_refund_cannot_be_reactivated_by_late_paid_event(self):
        cid=self.billing.checkout(self.session,self.tenant,'one')['checkout_id']
        for status,eid in [('paid','1'),('refunded','2'),('paid','3')]:self.billing.receive(*self.event(cid,status,eid))
        self.assertFalse(self.billing.entitlement(self.session,self.tenant)['sandbox_subscription_active'])
