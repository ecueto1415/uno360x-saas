import concurrent.futures,pathlib,tempfile,threading,time,unittest
from unittest.mock import patch
from deployment.reserve_pool import Pool,NETWORK,LABELS,validate_shared_networks

class SharedCatalogTests(unittest.TestCase):
 def test_shared_catalog_reconciliation_is_exclusive_between_threads(self):
  with tempfile.TemporaryDirectory() as temp,patch('deployment.reserve_pool.BASE',pathlib.Path(temp)):
   pool=object.__new__(Pool);lock=threading.Lock();state={'active':0,'peak':0,'calls':0}
   def reconcile():
    with lock:state['active']+=1;state['peak']=max(state['peak'],state['active']);state['calls']+=1
    time.sleep(.025)
    with lock:state['active']-=1
   pool._ensure_locked=reconcile
   with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:list(executor.map(lambda _:pool.ensure(),range(10)))
   self.assertEqual(state['peak'],1);self.assertEqual(state['calls'],10)
 def test_bulk_inspection_preserves_private_network_and_ownership_guards(self):
  name='uno360x-pilot-'+'a'*32+'-net';management={'name':NETWORK,'internal':True,'labels':LABELS};tenant={'name':name,'internal':True,'labels':{'uno360x.environment':'private-pilot'}}
  validate_shared_networks([NETWORK,name],[management,tenant])
  for values in ([management],[management,dict(tenant,internal=False)],[management,dict(tenant,labels={})],[management,tenant,tenant],[management,dict(tenant,name='foreign')]):
   with self.assertRaises(RuntimeError):validate_shared_networks([NETWORK,name],values)
