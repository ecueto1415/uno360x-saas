import unittest
from control.shared_database import shared_database_host

class PrivateEndpointTests(unittest.TestCase):
 def test_each_company_uses_the_verified_address_on_its_own_network(self):
  info={'NetworkSettings':{'Networks':{'one':{'IPAddress':'10.89.1.2'},'two':{'IPAddress':'10.89.2.2'}}}}
  self.assertEqual(shared_database_host(info,'one'),'10.89.1.2');self.assertEqual(shared_database_host(info,'two'),'10.89.2.2')
 def test_public_loopback_missing_or_invalid_endpoints_are_rejected(self):
  for value in ('8.8.8.8','127.0.0.1','0.0.0.0','::1','host.invalid',None):
   with self.assertRaises(RuntimeError):shared_database_host({'NetworkSettings':{'Networks':{'one':{'IPAddress':value}}}},'one')
  with self.assertRaises(RuntimeError):shared_database_host({'NetworkSettings':{'Networks':{}}},'one')
