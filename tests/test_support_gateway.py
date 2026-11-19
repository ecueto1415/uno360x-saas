import json
from pathlib import Path
from unittest.mock import patch
from tests.test_gateway import GatewayTests
from support_center.store import Store

class SupportGatewayTests(GatewayTests):
    def setUp(self):
        super().setUp()
        self.support_path=Path(self.tmp.name)/'support.sqlite3'
        s=Store(self.support_path);s.initialize();s.close()
        self.patch=patch('control.support.Store',lambda:Store(self.support_path));self.patch.start()
    def tearDown(self):
        self.patch.stop();super().tearDown()
    def test_support_auth_origin_csrf_and_idempotent_submission(self):
        self.assertEqual(401,self.request('/__support')[0])
        self.enter()
        status,_,body=self.request('/__support');self.assertEqual(200,status)
        token=json.loads(body)['csrf_token']
        headers={'Origin':self.server.origin,'Content-Type':'application/json','X-CSRF-Token':token}
        message=json.dumps({'body':'Consulta ficticia de inventario','request_id':'a'*32}).encode()
        self.assertEqual(403,self.request('/__support','POST',message,dict(headers,Origin='https://evil.example'))[0])
        self.assertEqual(403,self.request('/__support','POST',message,dict(headers,**{'X-CSRF-Token':'bad'}))[0])
        status,_,result=self.request('/__support','POST',message,headers);self.assertEqual(200,status)
        case=json.loads(result)['selected']['id']
        self.assertEqual(200,self.request('/__support','POST',message,headers)[0])
        s=Store(self.support_path)
        try:self.assertEqual(1,len(s.messages(case)))
        finally:s.close()
        self.assertEqual(400,self.request('/__support?case_id='+('f'*32))[0])
        self.assertEqual(400,self.request('/__support?tenant=forged')[0])
        self.assertEqual(200,self.request('/__support/chat.js?v=1')[0])
        self.assertEqual(404,self.request('/__support/worker.py')[0])
        self.assertEqual(405,self.request('/__support','DELETE',headers={'Origin':self.server.origin})[0])
