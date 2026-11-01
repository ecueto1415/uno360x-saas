import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from control.container_adapter import ContainerAdapter
class ContainerBoundaryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.state=Path(self.tmp.name)/'tenants'
  self.a=ContainerAdapter(self.state,{'postgres:16':'a'*64,'odoo:18.0':'b'*64},Path(self.tmp.name),'private-pilot','uno360x-pilot-')
  self.s={'tenant_id':'c'*32,'mode':'local_laboratory','installation':{'fingerprint':'d'*64}}
 def tearDown(self):self.tmp.cleanup()
 def test_native_production_names_and_traversal_are_rejected(self):
  for tid in ['Outsolutech_prueba','OUTSOLUTECH','../etc','c'*31]:
   with self.assertRaises(ValueError):self.a.names(dict(self.s,tenant_id=tid))
 def test_foreign_container_is_never_started_or_modified(self):
  self.a.inspect=Mock(return_value={'Config':{'Labels':{'uno360x.environment':'production'}}})
  self.a.run=Mock()
  with self.assertRaises(RuntimeError):self.a.check_container('foreign',self.s)
  self.a.run.assert_not_called()
 def test_published_port_rejected_even_with_valid_labels(self):
  n=self.a.names(self.s)
  self.a.inspect=Mock(return_value={'Config':{'Labels':self.a.labels(self.s)},'Image':'b'*64,'NetworkSettings':{'Networks':{n['network']:{}},'Ports':{'8069/tcp':[{'HostPort':'8069'}]}}})
  with self.assertRaises(RuntimeError):self.a.check_container(n['app'],self.s)
 @unittest.skipUnless(os.name=='posix','Linux lock semantics')
 def test_single_pilot_capacity_blocks_a_second_identity(self):
  from deployment.shared_adapter import SharedHostAdapter
  adapter=SharedHostAdapter.__new__(SharedHostAdapter)
  adapter.state=self.state
  with adapter.lock('a'*32):pass
  with self.assertRaises(RuntimeError):
   with adapter.lock('b'*32):pass
  self.assertFalse((self.state/('b'*32)).exists())

 def test_version_update_keeps_owned_resources_and_rejects_other_tenants(self):
  updated=dict(self.s,installation={'fingerprint':'e'*64},resource_fingerprint='d'*64)
  self.assertEqual(self.a.labels(updated),self.a.labels(self.s))
  other=dict(updated,tenant_id='f'*32)
  self.assertNotEqual(self.a.labels(other),self.a.labels(updated))

 @unittest.skipUnless(os.name=='posix','Linux admission locking')
 def test_two_slots_queue_third_without_blocking_existing_tenant(self):
  from deployment.shared_adapter import SharedHostAdapter,CapacityUnavailable
  adapter=SharedHostAdapter.__new__(SharedHostAdapter);adapter.state=self.state;adapter.max_active=2
  with adapter.lock('a'*32):
   with adapter.lock('b'*32):pass
  with adapter.lock('a'*32):pass
  with self.assertRaises(CapacityUnavailable):
   with adapter.lock('c'*32):pass
  self.assertFalse((self.state/('c'*32)).exists())
