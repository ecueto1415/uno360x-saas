import unittest
from contextlib import nullcontext
from unittest.mock import Mock
from control.shared_database import SharedDatabaseMixin

class SharedDatabaseTests(unittest.TestCase):
 def test_expiring_one_company_never_stops_the_shared_database(self):
  a=SharedDatabaseMixin();a.shared_binding=Mock(return_value={'database_name':'tenant_'+'a'*32});a.lock=lambda tid:nullcontext()
  a.names=lambda s:{'app':'owned-app','prefix':'owned','database':'shared-postgres'};a.exists=Mock(return_value=True);a.labels=lambda s:{'owner':'expected'}
  a.inspect=Mock(return_value={'Config':{'Labels':{'owner':'expected'}},'State':{'Running':True}});a.run=Mock()
  self.assertTrue(a.stop_shared_expired({'tenant_id':'a'*32}));self.assertEqual([c.args for c in a.run.call_args_list],[('stop','owned-app'),('stop','owned-proxy')])
 def test_expiration_rejects_a_foreign_application(self):
  a=SharedDatabaseMixin();a.shared_binding=Mock(return_value={'database_name':'tenant_'+'a'*32});a.lock=lambda tid:nullcontext();a.names=lambda s:{'app':'foreign','prefix':'owned'};a.exists=Mock(return_value=True);a.labels=lambda s:{'owner':'expected'};a.inspect=Mock(return_value={'Config':{'Labels':{'owner':'other'}},'State':{'Running':True}});a.run=Mock()
  with self.assertRaises(RuntimeError):a.stop_shared_expired({'tenant_id':'a'*32})
  a.run.assert_not_called()
if __name__=='__main__':unittest.main()
