import io
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from control import expense_chat as chat
from control.identity import IdentityError
from support_center.expense_processor import schema


class Identity:
    def close(self): pass


class Manager:
    def __init__(self): self.valid=True; self.validations=0
    def identity(self): return Identity()
    def validate(self,handle,identity):
        self.validations+=1
        if not self.valid: raise IdentityError('Revoked')


class Opener:
    def __init__(self): self.calls=[]
    def open(self,request,timeout):
        params=json.loads(request.data)['params'];self.calls.append(params)
        result={'capture_options':{'enabled':True,'user_id':17},
                'capture_history':[],
                'capture_draft':{'status':'draft','id':42,'comprobante':'B0100000001',
                                 'moneda':'DOP','total':118,'pendientes':'Revisar'}}[params['method']]
        return io.BytesIO(json.dumps({'result':result}).encode())


class ExpenseGatewayTests(unittest.TestCase):
    def setUp(self):
        self.manager=Manager()
        self.opener=Opener()
        self.handle=SimpleNamespace(token='fictional-handle',tenant='tenant-a',
            lock=threading.Lock(),backend=SimpleNamespace(base='http://127.0.0.1:19000',
                uid=17,opener=self.opener))
        self.data={'filename':'factura.png','image':'ZmFrZQ==','message':'Registra en borrador'}
        self.result={'datos':{'rnc':'131000000'},'faltantes':[]}

    def test_fixed_user_rpc_no_client_context_or_tenant(self):
        result=chat.submit(self.manager,self.handle,self.data,lambda v:self.result)
        self.assertEqual(result['draft']['id'],42)
        self.assertEqual(self.opener.calls[1]['method'],'capture_draft')
        self.assertEqual(self.opener.calls[1]['kwargs'],{})
        self.assertEqual(self.opener.calls[1]['args'][0],'factura.png')
        self.assertGreaterEqual(self.manager.validations,6)
        with self.assertRaises(ValueError):
            chat.submit(self.manager,self.handle,dict(self.data,tenant='tenant-b'),lambda v:self.result)

    def test_revoked_during_ai_cannot_write(self):
        def processor(value):
            self.manager.valid=False
            return self.result
        with self.assertRaises(IdentityError):
            chat.submit(self.manager,self.handle,self.data,processor)
        self.assertEqual(len(self.opener.calls),1)

    def test_unclear_photo_does_not_create_draft(self):
        result=chat.submit(self.manager,self.handle,self.data,
            lambda v:{'datos':{},'faltantes':['Confirmar NCF ilegible']})
        self.assertIn('NCF',result['reply'])
        self.assertNotIn('draft',result)
        self.assertNotIn('capture_draft',[c['method'] for c in self.opener.calls])

    def test_identity_mismatch_and_method_allowlist(self):
        self.handle.backend.uid=18
        with self.assertRaises(ValueError):
            chat.submit(self.manager,self.handle,self.data,lambda v:self.result)
        with self.assertRaises(ValueError):
            chat.rpc(self.manager,self.handle,'action_post',[42])

    def test_csrf_bound_to_handle_and_strict_extraction(self):
        first=chat.csrf(self.handle);self.handle.token='another'
        self.assertNotEqual(first,chat.csrf(self.handle))
        self.assertFalse(schema()['additionalProperties'])
        self.assertFalse(schema()['properties']['datos']['additionalProperties'])

    def test_no_write_if_processor_fails(self):
        def failed(value): raise RuntimeError('Unavailable')
        with self.assertRaises(RuntimeError):
            chat.submit(self.manager,self.handle,self.data,failed)
        self.assertEqual([c['method'] for c in self.opener.calls],['capture_options'])


if __name__=='__main__': unittest.main()
