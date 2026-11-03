import unittest,tempfile,sqlite3,pathlib,copy
from admin_console.storage import increase,overlay,QuotaError,Conflict,GB
class StorageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=sqlite3.connect(pathlib.Path(self.tmp.name)/'state.db');self.db.row_factory=sqlite3.Row;self.now=2000000000;self.tenant='a'*32
  self.snapshot={'generated':self.now,'clients':[{'id':self.tenant,'quota_bytes':5*GB,'storage_bytes':4*GB}],'server':{'disk_available':100*GB}}
  self.data={'tenant_id':self.tenant,'quota_gb':10,'expected_bytes':5*GB,'request_id':'b'*32,'reason':'Customer requested expansion'}
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def apply(self,data=None,snapshot=None):return increase(self.db,copy.deepcopy(snapshot or self.snapshot),data or self.data,'owner@example.test',self.now)
 def test_persistent_increase_history_and_idempotent_retry(self):
  self.assertEqual(self.apply()['quota_bytes'],10*GB);self.assertTrue(self.apply()['duplicate'])
  data=overlay(self.db,copy.deepcopy(self.snapshot));self.assertEqual(data['clients'][0]['quota_bytes'],10*GB);h=data['clients'][0]['quota_history'];self.assertEqual(len(h),1);self.assertEqual(h[0]['previous_bytes'],5*GB);self.assertEqual(h[0]['actor'],'owner@example.test')
  self.db.close();self.db=sqlite3.connect(pathlib.Path(self.tmp.name)/'state.db');self.db.row_factory=sqlite3.Row;self.assertEqual(overlay(self.db,copy.deepcopy(self.snapshot))['clients'][0]['quota_bytes'],10*GB)
 def test_stale_reused_request_and_decrease_rejected(self):
  self.apply()
  for changes in [{'quota_gb':20},{'request_id':'c'*32,'quota_gb':20}]:
   with self.assertRaises(Conflict):self.apply(dict(self.data,**changes))
  with self.assertRaises(QuotaError):self.apply(dict(self.data,request_id='d'*32,quota_gb=5,expected_bytes=10*GB))
 def test_capacity_reserve_other_assignments_stale_snapshot_and_foreign_tenant(self):
  small=copy.deepcopy(self.snapshot);small['server']['disk_available']=12*GB
  for snap in [small,dict(self.snapshot,generated=self.now-181)]:
   with self.assertRaises(QuotaError):self.apply(snapshot=snap)
  with self.assertRaises(QuotaError):self.apply(dict(self.data,tenant_id='f'*32))
  self.assertEqual(self.db.execute('SELECT count(*) FROM storage_changes').fetchone()[0],0)
 def test_validation_rejects_non_integer_and_below_current_usage(self):
  for value in [True,5.5,'10',1001,4]:
   with self.assertRaises(QuotaError):self.apply(dict(self.data,quota_gb=value))
  snap=copy.deepcopy(self.snapshot);snap['clients'][0]['storage_bytes']=11*GB
  with self.assertRaises(QuotaError):self.apply(snapshot=snap)
if __name__=='__main__':unittest.main()
