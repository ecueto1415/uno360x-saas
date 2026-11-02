import unittest
from pathlib import Path
from unittest.mock import Mock
from control.container_adapter import ContainerAdapter

class UserSyncTests(unittest.TestCase):
 def adapter(self,current):
  a=object.__new__(ContainerAdapter);a._user_is_current=Mock(return_value=current);a.shell=Mock(return_value='UNO360X_OK');return a
 def payload(self):
  return {'tenant_id':'a'*32,'installation':{'addons':{}}},{'tenant_id':'a'*32,'account_id':'b'*32,'email':'fixture@example.test','role':'owner'}
 def test_current_user_avoids_the_expensive_shell(self):
  a=self.adapter(True);s,c=self.payload();a.sync_user(s,c);a.shell.assert_not_called()
  self.assertNotIn('base.group_system',a._user_is_current.call_args.args[2])
 def test_missing_or_drifted_user_still_uses_full_orm_sync(self):
  a=self.adapter(False);s,c=self.payload();a.sync_user(s,c);a.shell.assert_called_once()
 def test_foreign_identity_never_reaches_probe_or_shell(self):
  a=self.adapter(True);s,c=self.payload();c['tenant_id']='c'*32
  with self.assertRaises(RuntimeError):a.sync_user(s,c)
  a._user_is_current.assert_not_called();a.shell.assert_not_called()

 def test_batched_container_metadata_still_rejects_foreign_or_published_resources(self):
  import copy
  a=object.__new__(ContainerAdapter);a.state=Path('/fictional-test');a.prefix='fixture-';a.environment='test';a.images={'odoo:18.0':'app-image','postgres:16':'db-image'}
  s={'tenant_id':'a'*32,'mode':'local_laboratory','installation':{'fingerprint':'release'}}
  name=a.names(s)['app'];info={'Config':{'Labels':a.labels(s)},'Image':'app-image','NetworkSettings':{'Networks':{a.names(s)['network']:{}},'Ports':{}}}
  a.inspect=Mock(side_effect=AssertionError('Metadata should already be supplied'))
  self.assertIs(a.check_container(name,s,info=info),info)
  foreign=copy.deepcopy(info);foreign['Config']['Labels']['uno360x.tenant']='b'*32
  with self.assertRaises(RuntimeError):a.check_container(name,s,info=foreign)
  published=copy.deepcopy(info);published['NetworkSettings']['Ports']={'8069/tcp':[{'HostIp':'0.0.0.0','HostPort':'8069'}]}
  with self.assertRaises(RuntimeError):a.check_container(name,s,info=published)
