import pathlib,tempfile,json,unittest
from unittest.mock import Mock
from control.container_adapter import ContainerAdapter

class RuntimeIdentityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.a=ContainerAdapter.__new__(ContainerAdapter);self.a.state=self.root;self.a.root=self.root;self.a.environment='qa';self.a.prefix='qa-';self.a.images={}
  self.s={'tenant_id':'a'*32,'hostname':'qa.uno360x.com','mode':'local_laboratory','installation':{'fingerprint':'b'*64}}
  self.n=self.a.names(self.s);self.n['directory'].mkdir();self.a.exists=Mock(return_value=False);self.a.sql=Mock(return_value='0');self.a.run=Mock();self.a.check_container=Mock()
 def tearDown(self):self.tmp.cleanup()
 def marker(self): (self.n['directory']/'installed.json').write_text(json.dumps({'fingerprint':'b'*64,'template':'verified-template'}))
 def test_existing_or_cold_instances_never_receive_first_owner_bootstrap(self):
  setup=Mock();self.assertFalse(self.a.runtime_identity(self.s,setup));self.marker();self.a.exists.return_value=True
  self.assertFalse(self.a.runtime_identity(self.s,setup));setup.assert_not_called();self.a.run.assert_not_called()
 def test_existing_business_identity_is_rejected_before_launch(self):
  self.marker();self.a.sql.return_value='1'
  with self.assertRaises(RuntimeError):self.a.runtime_identity(self.s,Mock())
  self.a.run.assert_not_called()
 def test_capture_failure_does_not_leave_replayable_partial_script(self):
  self.marker()
  def broken():self.a.shell(self.s,'sensitive private payload');raise ValueError('fail')
  with self.assertRaises(ValueError):self.a.runtime_identity(self.s,broken)
  self.assertFalse((self.n['directory']/'initial-owner.json').exists());self.assertFalse(hasattr(self.a,'_startup_scripts'));self.a.run.assert_not_called()
 def test_retry_cannot_reuse_another_identity_or_release(self):
  p=self.n['directory']/'initial-owner.json';p.write_text(json.dumps({'tenant_id':'c'*32,'hostname':self.s['hostname'],'fingerprint':'b'*64,'script':'must never run'}))
  with self.assertRaises(RuntimeError):self.a.runtime_identity(self.s,Mock())
  self.a.run.assert_not_called()
 def test_database_startup_failure_restores_the_normal_cpu_budget(self):
  self.a.images={'postgres:16':'b'*64};self.a.volume=Mock();self.a.check_container=Mock();self.a.exists=Mock(side_effect=[False,True]);self.a.startup_database_cpus='0.75';self.a.database_limits=['--cpus','0.25','--memory','192m']
  def run(*args,**kwargs):
   if args[0]=='exec':raise RuntimeError('readiness probe failed')
   return Mock(returncode=0,stdout='')
  self.a.run=Mock(side_effect=run)
  with self.assertRaises(RuntimeError):self.a.database(self.s)
  self.a.run.assert_called_with('update','--cpus','0.25',self.n['database'])
  self.assertEqual(self.a.database_limits[1],'0.25')
 def test_current_identity_does_not_reapply_initial_company_settings(self):
  self.a.sql.return_value=self.s['tenant_id']+'|'+self.s['hostname']+'\noperator_'+self.s['tenant_id']+'\n0';self.a.shell=Mock()
  self.a.identity(self.s)
  self.a.shell.assert_not_called()
if __name__=='__main__':unittest.main()
