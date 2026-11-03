import unittest
from contextlib import contextmanager
from unittest.mock import Mock
from deployment.reserve_pool import Pool

class ReserveClaimTests(unittest.TestCase):
 def test_customer_can_take_a_completed_space_while_the_builder_keeps_working(self):
  pool=Pool.__new__(Pool);binding={'tenant_id':'a'*32,'database_name':'tenant_'+'b'*32};pool.store=Mock();pool.store.claim.side_effect=[None,binding];pool.create_slot=Mock()
  @contextmanager
  def busy(wait=True):raise BlockingIOError();yield
  pool.builder_lock=busy
  self.assertEqual(pool.claim({'tenant_id':'a'*32,'installation':{'fingerprint':'c'*64,'addons':{}}}),binding);pool.create_slot.assert_not_called()
if __name__=='__main__':unittest.main()
