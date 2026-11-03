import unittest,tempfile,pathlib,tarfile,io,json,os
from unittest.mock import Mock,patch
from control.template_cache import cache_key,verified_cache,checksum,RECIPE
from control.template_install import TemplateInstallMixin
from control.container_adapter import ContainerAdapter
class CacheTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.profile={'fingerprint':'a'*64};self.images={'odoo:18.0':'b'*64,'postgres:16':'c'*64}
 def tearDown(self):self.tmp.cleanup()
 def seed(self,unsafe=False):
  key=cache_key(self.profile,self.images);p=self.root/'ready'/key;p.mkdir(parents=True)
  (p/'database.dump').write_bytes(b'fake pristine dump')
  with tarfile.open(p/'files.tar','w') as f:
   m=tarfile.TarInfo('../escape' if unsafe else 'file');m.size=1;f.addfile(m,io.BytesIO(b'x'))
  (p/'manifest.json').write_text(json.dumps({'key':key,'recipe':RECIPE,'fingerprint':self.profile['fingerprint'],'images':self.images,'pristine':True,'sha256':{n:checksum(p/n) for n in ('database.dump','files.tar')}}));return p
 def test_missing_versioned_and_verified_cache(self):
  self.assertIsNone(verified_cache(self.profile,self.images,self.root));p=self.seed();self.assertEqual(verified_cache(self.profile,self.images,self.root),p)
  self.assertNotEqual(cache_key(self.profile,self.images),cache_key({'fingerprint':'d'*64},self.images))
  (p/'database.dump').write_bytes(b'changed')
  with self.assertRaises(RuntimeError):verified_cache(self.profile,self.images,self.root)
 def test_unsafe_archive_rejected(self):
  self.seed(True)
  with self.assertRaises(RuntimeError):verified_cache(self.profile,self.images,self.root)
 def test_nonempty_owned_db_is_never_overwritten_without_restore_journal(self):
  class Fake(TemplateInstallMixin):pass
  a=Fake();a.images=self.images;a.root=self.root;a.exists=Mock(return_value=False);a.check_container=Mock();a.volume=Mock();a.run=Mock();a.sql=Mock(return_value='1');a.names=lambda s:{'directory':self.root,'init':'init','database':'db','files':'files'}
  with patch('control.template_install.verified_cache',return_value=self.root):
   with self.assertRaises(RuntimeError):a.installation({'installation':self.profile})
  a.run.assert_not_called()
 def test_identity_batch_executes_one_shell_and_discards_on_error(self):
  a=ContainerAdapter(self.root/'state',self.images,self.root,'qa','qa-');a.names=Mock(return_value={'directory':self.root});a.common=Mock(return_value=[]);a.run=Mock(return_value=Mock(returncode=0,stdout='UNO360X_OK'))
  with a.batch_shell({}):a.shell({},'first');a.shell({},'second')
  self.assertEqual(a.run.call_count,1);self.assertEqual(a.run.call_args.kwargs['input'],'first\nsecond')
  a.run.reset_mock()
  with self.assertRaises(ValueError):
   with a.batch_shell({}):a.shell({},'not applied');raise ValueError()
  a.run.assert_not_called()
class AdmissionAndReadinessTests(unittest.TestCase):
 def test_open_admission_preserves_existing_companies_and_reserves_peak_memory(self):
  from deployment.shared_adapter import SharedHostAdapter
  a=SharedHostAdapter.__new__(SharedHostAdapter);a._allocated=Mock(return_value=2)
  values={'memory.max':str(3*1024**3),'memory.current':str(1024**3),'cpu.max':'150000 100000','meminfo':'MemTotal: 8000000 kB\nMemAvailable: 4000000 kB\n'}
  def read(p,*args,**kwargs):return values[p.name]
  with patch.object(pathlib.Path,'read_text',new=read),patch('os.cpu_count',return_value=4):
   self.assertTrue(a.has_headroom('new'))
   a._allocated.return_value=3;self.assertFalse(a.has_headroom('new'))
   values['memory.max']=str(4*1024**3);values['meminfo']='MemTotal: 16000000 kB\nMemAvailable: 4000000 kB\n';self.assertTrue(a.has_headroom('new'))
   values['memory.max']='max';self.assertFalse(a.has_headroom('new'))
 def test_capacity_queue_does_not_create_or_stop_resources(self):
  from deployment.shared_adapter import SharedHostAdapter,CapacityUnavailable
  with tempfile.TemporaryDirectory() as tmp:
   a=SharedHostAdapter.__new__(SharedHostAdapter);a.state=pathlib.Path(tmp);a.max_active=None;a.has_headroom=Mock(return_value=False);a.run=Mock()
   with self.assertRaises(CapacityUnavailable):
    with a.lock('a'*32):pass
   a.run.assert_not_called();self.assertFalse((a.state/('a'*32)).exists())
 def test_database_probe_waits_for_final_server_and_real_database(self):
  with tempfile.TemporaryDirectory() as tmp:
   a=ContainerAdapter(pathlib.Path(tmp),{'postgres:16':'b'*64,'odoo:18.0':'c'*64},pathlib.Path(tmp),'qa','qa-')
   s={'tenant_id':'a'*32,'mode':'local_laboratory','installation':{'fingerprint':'d'*64}}
   a.names(s)['directory'].mkdir();a.volume=Mock();a.exists=Mock(return_value=False);probes=[]
   def run(*args,**kwargs):
    if args[0]=='exec':probes.append(args);return Mock(returncode=0,stdout='bootstrap accepting' if len(probes)==1 else '1')
    return Mock(returncode=0,stdout='')
   a.run=Mock(side_effect=run)
   with patch('time.sleep'):a.database(s)
   self.assertEqual(len(probes),2);self.assertIn('/proc/1/comm',probes[0][-1])

if __name__=='__main__':unittest.main()
