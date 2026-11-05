import contextlib,pathlib,tempfile,unittest
from unittest.mock import patch
from control.reserve_store import ReserveStore
from deployment.reserve_pool import Pool,profiles

class ReserveBatchTests(unittest.TestCase):
 def test_each_pass_prepares_at_most_five_and_latch_continues_to_fifty(self):
  with tempfile.TemporaryDirectory() as temp:
   store=ReserveStore(pathlib.Path(temp)/'inventory.sqlite3');profile={'fingerprint':'a'*64}
   def make(modules,profile):
    slot=store.start_slot(profile,modules);store.mark_ready(slot);return slot
   for _ in range(40):make([],profile)
   pool=object.__new__(Pool);pool.store=store;pool.builder_lock=lambda:contextlib.nullcontext();pool.ensure=lambda:None;pool.prune_retired=lambda:None;pool.create_slot=make
   with patch('deployment.reserve_pool.profiles',return_value=[([],profile,50)]),patch('deployment.reserve_pool.host_memory_available',return_value=4*1024**3):
    pool.replenish();self.assertEqual(store.counts()['ready'],45);self.assertTrue(store.refill_needed())
    pool.replenish();self.assertEqual(store.counts()['ready'],50);self.assertFalse(store.refill_needed())
    pool.replenish();self.assertEqual(store.counts()['ready'],50)
   store.close()
 def test_fifty_ready_profiles_include_twenty_base_spaces(self):
  wanted=profiles();self.assertEqual(sum(w for _,_,w in wanted),50);self.assertEqual(next(w for modules,_,w in wanted if not modules),20);self.assertEqual(len(wanted),8)
