import pathlib,tempfile,unittest
from types import SimpleNamespace
from deployment.admission_status import publish

class DisabledAdmissionTests(unittest.TestCase):
 def test_open_admission_does_not_scan_existing_tenant_runtimes(self):
  def forbidden(*args):raise AssertionError('Admission disabled; do not scan all runtimes')
  adapter=SimpleNamespace(enforce_admission=False,max_active=None,has_headroom=forbidden)
  with tempfile.TemporaryDirectory() as temp:
   result=publish(adapter,pathlib.Path(temp)/'status.json');self.assertTrue(result['can_prepare'])
