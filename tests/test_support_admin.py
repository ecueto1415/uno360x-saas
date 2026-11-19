from pathlib import Path
from unittest.mock import patch
from tests.test_admin_console import OwnerHTTPTests
from support_center.store import Store

class SupportAdminTests(OwnerHTTPTests):
 def setUp(self):
  super().setUp()
  self.path=Path(self.tmp.name)/'support.sqlite3'
  s=Store(self.path);s.initialize()
  self.case=s.send('tenant-a','alice',{'body':'Consulta ficticia','request_id':'a'*32})
  s.close()
  self.patch=patch('admin_console.server.SupportStore',lambda:Store(self.path));self.patch.start()
 def tearDown(self):
  self.patch.stop();super().tearDown()
 def test_owner_support_read_reply_requires_auth_and_csrf(self):
  self.assertEqual(401,self.request('/api/support')[0])
  self.activate();self.csrf=self.request('/api/session')[2]['csrf_token']
  self.assertEqual(1,len(self.request('/api/support')[2]['cases']))
  self.assertEqual('alice',self.request('/api/support?case_id='+self.case)[2]['selected']['account'])
  good=self.csrf;self.csrf='bad'
  payload={'case_id':self.case,'action':'reply','body':'Respuesta ficticia del equipo','request_id':'b'*32}
  self.assertEqual(403,self.request('/api/support',payload)[0]);self.csrf=good
  self.assertEqual(403,self.request('/api/support',payload,origin='https://evil.example')[0])
  self.assertEqual(200,self.request('/api/support',payload)[0])
  self.assertEqual(200,self.request('/api/support',payload)[0])
  value=self.request('/api/support?case_id='+self.case)[2]
  self.assertEqual(2,len(value['messages']));self.assertEqual('team',value['messages'][-1]['role'])
  self.assertEqual(400,self.request('/api/support?case_id='+('f'*32))[0])
