import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from control import restaurant
from control.identity import IdentityError

class Backend:
    uid=7
    opener=None
    base='http://127.0.0.1:9999'
    def rpc(self,model,method,args,kwargs):
        if method=='has_group':
            return args[0][0] in (7,8) and (args[1].endswith('group_pos_user') or args[0][0]==7)
        if method=='read':return [{'name':'Responsable','company_id':[3,'Restaurante piloto']}]
        if method=='search_read':
            assert ('company_ids','in',[3]) in args[0]
            return [{'id':7,'name':'Responsable'},{'id':8,'name':'Camarero'},{'id':9,'name':'Contabilidad'}]
        raise AssertionError((model,method,args,kwargs))
class Manager:
    def identity(self):return SimpleNamespace(close=lambda:None)
    def validate(self,handle,identity):
        if not handle.active:raise IdentityError('closed')

class RestaurantGatewayTest(unittest.TestCase):
    def test_verified_company_and_pos_staff_only(self):
        restaurant._staff_cache.clear()
        h=SimpleNamespace(tenant='a'*32,backend=Backend(),lock=threading.Lock(),active=True)
        with patch.object(restaurant,'_rpc',side_effect=lambda opener,base,path,p:h.backend.rpc(p['model'],p['method'],p['args'],p['kwargs'])):
            result=restaurant.claims(Manager(),h)
        self.assertEqual(result['scope'],'a'*32+':company-3')
        self.assertEqual(result['role'],'supervisor')
        self.assertEqual([p['id'] for p in result['staff']],['7','8'])
        h.active=False
        with self.assertRaises(IdentityError):restaurant.claims(Manager(),h)

    def test_non_pos_user_denied(self):
        backend=Backend();backend.uid=9
        h=SimpleNamespace(tenant='b'*32,backend=backend,lock=threading.Lock(),active=True)
        with patch.object(restaurant,'_rpc',side_effect=lambda opener,base,path,p:h.backend.rpc(p['model'],p['method'],p['args'],p['kwargs'])):
            with self.assertRaises(IdentityError):restaurant.claims(Manager(),h)

if __name__=='__main__':unittest.main()
