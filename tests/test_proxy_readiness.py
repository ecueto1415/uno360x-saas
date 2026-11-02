import unittest,urllib.error
from unittest.mock import Mock,patch
from deployment.pilot_adapter import PilotAdapter

class ProxyReadinessTests(unittest.TestCase):
 def test_cold_proxy_is_retried_before_first_bridge_login(self):
  response=Mock();response.status=200;response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
  opener=Mock();opener.open.side_effect=[urllib.error.URLError('connection refused'),response]
  with patch('deployment.pilot_adapter.urllib.request.build_opener',return_value=opener),patch('deployment.pilot_adapter.time.sleep'):
   self.assertEqual(PilotAdapter.wait_backend(object(),18191),'http://127.0.0.1:18191')
  self.assertEqual(opener.open.call_count,2)
 def test_unavailable_proxy_never_returns_a_ready_backend(self):
  opener=Mock();opener.open.side_effect=urllib.error.URLError('connection refused')
  with patch('deployment.pilot_adapter.urllib.request.build_opener',return_value=opener),patch('deployment.pilot_adapter.time.sleep'):
   with self.assertRaises(RuntimeError):PilotAdapter.wait_backend(object(),18191)
  self.assertEqual(opener.open.call_count,30)
