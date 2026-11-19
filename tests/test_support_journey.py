"""Complete HTTP path: customer → worker → human queue → owner → customer."""
import json
from unittest.mock import patch
from tests.test_support_gateway import SupportGatewayTests
from tests.test_admin_console import OwnerHTTPTests
from support_center.store import Store
from support_center.worker import run

class SupportJourneyTests(SupportGatewayTests):
 def test_complete_customer_ai_human_owner_response(self):
  self.enter()
  token=json.loads(self.request('/__support')[2])['csrf_token']
  headers={'Origin':self.server.origin,'Content-Type':'application/json','X-CSRF-Token':token}
  data=json.dumps({'body':'QA: ¿Dónde está el informe de faltantes?','request_id':'1'*32}).encode()
  status,_,body=self.request('/__support','POST',data,headers);self.assertEqual(200,status)
  case=json.loads(body)['selected']['id']
  calls=[]
  def responder(settings,history,context):
   calls.append(history)
   return {'reply':'En Inventario → Informe de faltantes.','topic':'inventory','human':False}
  run({},self.support_path,responder,budget=.1)
  value=json.loads(self.request('/__support?case_id='+case)[2])
  self.assertEqual('assistant',value['messages'][-1]['role']);self.assertEqual(1,len(calls))
  status,_,body=self.request('/__support','POST',json.dumps({'case_id':case,'handoff':True}).encode(),headers)
  self.assertEqual(200,status);self.assertEqual(1,json.loads(body)['selected']['human'])
  owner=OwnerHTTPTests('test_no_anonymous_data_or_path_traversal');owner.setUp()
  try:
   with patch('admin_console.server.SupportStore',lambda:Store(self.support_path)):
    owner.activate();owner.csrf=owner.request('/api/session')[2]['csrf_token']
    listing=owner.request('/api/support')[2]
    self.assertEqual(self.tid,listing['cases'][0]['tenant'])
    self.assertEqual(case,listing['cases'][0]['id'])
    reply={'case_id':case,'action':'reply','body':'QA equipo: recibimos tu consulta y te ayudamos.','request_id':'2'*32}
    self.assertEqual(200,owner.request('/api/support',reply)[0])
    self.assertEqual(200,owner.request('/api/support',reply)[0])
    value=json.loads(self.request('/__support?case_id='+case)[2])
    self.assertEqual(3,len(value['messages']));self.assertEqual('team',value['messages'][-1]['role'])
    self.assertEqual(reply['body'],value['messages'][-1]['body'])
    follow=json.dumps({'case_id':case,'body':'Gracias, espero al equipo.','request_id':'3'*32}).encode()
    self.assertEqual(200,self.request('/__support','POST',follow,headers)[0])
    run({},self.support_path,responder,budget=.1)
    self.assertEqual(1,len(calls),'AI must stop after handoff')
  finally:owner.tearDown()
