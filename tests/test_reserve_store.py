import pathlib,tempfile,unittest,uuid,sqlite3
from control.reserve_store import ReserveStore

class ReserveStoreTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.temp.name)/'inventory.sqlite3';self.store=ReserveStore(self.path);self.profile={'fingerprint':'a'*64}
 def tearDown(self):self.store.close();self.temp.cleanup()
 def fill(self,count):
  for _ in range(count):slot=self.store.start_slot(self.profile,[]);self.store.mark_ready(slot)
 def test_refill_starts_at_forty_and_stops_at_fifty(self):
  self.assertTrue(self.store.refill_needed());self.fill(50);self.assertFalse(self.store.refill_needed())
  for _ in range(9):self.store.claim(uuid.uuid4().hex,self.profile['fingerprint'])
  self.assertEqual(self.store.counts()['ready'],41);self.assertFalse(self.store.refill_needed())
  self.store.claim(uuid.uuid4().hex,self.profile['fingerprint']);self.assertTrue(self.store.refill_needed())
  self.fill(5);self.assertTrue(self.store.refill_needed());self.fill(5);self.assertFalse(self.store.refill_needed())
 def test_assignment_is_idempotent_and_never_reuses_a_client(self):
  self.fill(2);tenant=uuid.uuid4().hex;a=self.store.claim(tenant,self.profile['fingerprint']);b=self.store.claim(tenant,self.profile['fingerprint'])
  self.assertEqual(a,b);other=self.store.claim(uuid.uuid4().hex,self.profile['fingerprint']);self.assertNotEqual(a['database_name'],other['database_name']);self.assertEqual(self.store.counts()['ready'] if 'ready' in self.store.counts() else 0,0)
 def test_different_product_is_not_assigned_and_retirement_keeps_assigned_data(self):
  self.fill(2);self.assertIsNone(self.store.claim(uuid.uuid4().hex,'b'*64));tenant=uuid.uuid4().hex;binding=self.store.claim(tenant,self.profile['fingerprint'])
  self.store.retire_old_ready({'b'*64});self.assertEqual(self.store.counts()['retired'],1);self.assertEqual(self.store.binding(tenant),binding)
 def test_refill_remains_active_when_spaces_are_consumed_during_the_build(self):
  self.fill(40);self.assertTrue(self.store.refill_needed());self.fill(5);self.store.claim(uuid.uuid4().hex,self.profile['fingerprint']);self.assertTrue(self.store.refill_needed());self.fill(6);self.assertFalse(self.store.refill_needed())
if __name__=='__main__':unittest.main()
