import unittest
from types import SimpleNamespace
from deployment.runtime_bootstrap import isolate_bus_database

class RuntimeBusIsolationTests(unittest.TestCase):
 def test_notifications_use_only_own_database_and_preserve_options(self):
  calls=[]
  db=SimpleNamespace(db_connect=lambda *a,**kw:calls.append((a,kw)))
  own="tenant_"+"a"*32
  isolate_bus_database(db,own)
  db.db_connect("postgres",allow_uri=True)
  db.db_connect(own)
  db.db_connect("tenant_"+"b"*32)
  self.assertEqual(calls,[((own,),{"allow_uri":True}),((own,),{}),(("tenant_"+"b"*32,),{})])
 def test_invalid_target_does_not_change_connection_function(self):
  for target in ("postgres","Outsolutech_prueba","tenant_a",["tenant_"+"a"*32],None):
   db=SimpleNamespace(db_connect=object());original=db.db_connect
   with self.assertRaises(ValueError):isolate_bus_database(db,target)
   self.assertIs(db.db_connect,original)
