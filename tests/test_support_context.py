import contextlib
import io
import json
import threading
from types import SimpleNamespace
import unittest
from control.support_context import capture
from control.identity import IdentityError

class ContextTests(unittest.TestCase):
 def setup_capture(self,result=None,error=None,role='owner'):
  calls=[]
  class Opener:
   def open(self,request,timeout):
    calls.append((request,timeout))
    if error:raise error
    return contextlib.closing(io.BytesIO(json.dumps({'result':result}).encode()))
  handle=SimpleNamespace(tenant='tenant-a',token='secret-not-to-copy',lock=threading.Lock(),backend=SimpleNamespace(
   base='http://127.0.0.1:1111',uid=77,opener=Opener(),claims={'role':role,'account_id':'alice'}))
  closed=[];checks=[]
  manager=SimpleNamespace(identity=lambda:SimpleNamespace(close=lambda:closed.append(True)),validate=lambda h,i:checks.append(h.tenant))
  return handle,manager,calls,checks,closed
 def test_only_fixed_read_method_and_session_identity(self):
  h,m,calls,checks,closed=self.setup_capture({'version':'support-readonly-v1','user_id':77,'features':{}})
  result=capture(m,h)
  self.assertTrue(result['verified']);self.assertEqual(['tenant-a','tenant-a'],checks)
  request,timeout=calls[0];params=json.loads(request.data)['params']
  self.assertEqual('support_diagnostics',params['method']);self.assertEqual([],params['args']);self.assertEqual({},params['kwargs'])
  self.assertEqual(6,timeout);self.assertNotIn(h.token,json.dumps(result));self.assertEqual([True],closed)
 def test_mismatched_identity_and_failed_backend_not_verified(self):
  for result,error in [({'version':'support-readonly-v1','user_id':88,'features':{}},None),(None,TimeoutError())]:
   h,m,*_=self.setup_capture(result,error)
   self.assertFalse(capture(m,h)['verified'])
 def test_permission_revocation_cannot_be_swallowed(self):
  h,m,*_=self.setup_capture()
  def denied(*args):raise IdentityError('revoked')
  m.validate=denied
  with self.assertRaises(IdentityError):capture(m,h)
 def test_member_is_not_given_user_administration(self):
  h,m,*_=self.setup_capture({'version':'support-readonly-v1','user_id':77,'features':{}},role='member')
  result=capture(m,h)
  self.assertFalse(result['diagnostics']['features']['users']['available'])
  self.assertIsNone(result['diagnostics']['features']['users']['route'])
  self.assertFalse(result['diagnostics']['features']['subscription']['available'])
  self.assertIsNone(result['diagnostics']['features']['subscription']['route'])

if __name__=='__main__':unittest.main()
