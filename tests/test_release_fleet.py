import json,pathlib,sqlite3,tempfile,unittest
from deployment.release_fleet import active_tenants,queued_rebases,reviewed_transition

class FleetReleaseTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.executescript('CREATE TABLE tenants(id TEXT,modules TEXT);CREATE TABLE preparation_jobs(id TEXT,tenant_id TEXT,status TEXT,updated REAL,fingerprint TEXT,snapshot TEXT);CREATE TABLE trial_workspaces(tenant_id TEXT,expires REAL);CREATE TABLE preparation_steps(job_id TEXT,step TEXT);')
  self.old={'fingerprint':'old','addons':{'uno360x_workspace':'1','uno360x_base':'1'}};self.new={'fingerprint':'new','addons':{'uno360x_workspace':'2','uno360x_base':'1'}}
 def tearDown(self):self.db.close()
 def add(self,tid,status,expires):
  self.db.execute('INSERT INTO tenants VALUES (?,?)',(tid,'[]'));self.db.execute('INSERT INTO preparation_jobs VALUES (?,?,?,?,?,?)',('job-'+tid,tid,status,1,'old',json.dumps({'tenant_id':tid,'installation':self.old,'company_profile':{'name':'Preserved'}})));self.db.execute('INSERT INTO trial_workspaces VALUES (?,?)',(tid,expires))
 def test_fleet_discovers_all_active_companies_without_a_hardcoded_list(self):
  self.add('active','ready_local',200);self.add('expired','ready_local',50);self.add('no-trial','ready_local',None);self.add('queued','queued',None)
  self.assertEqual({r['tenant_id'] for r in active_tenants(self.db,100)},{'active','no-trial'})
 def test_reviewed_visual_change_cannot_enable_or_change_business_modules(self):
  reviewed_transition(self.old,self.new)
  with self.assertRaises(RuntimeError):reviewed_transition(self.old,{'addons':dict(self.new['addons'],uno360x_payroll_hr='1')})
  with self.assertRaises(RuntimeError):reviewed_transition(self.old,{'addons':dict(self.new['addons'],uno360x_base='2')})
 def test_only_unallocated_queued_requests_are_rebased_without_duplicates(self):
  self.add('queued','queued',None)
  with tempfile.TemporaryDirectory() as folder:
   state=pathlib.Path(folder);result=queued_rebases(self.db,state,lambda modules:self.new)
   self.assertEqual(len(result),1);snapshot,job=result[0];self.assertEqual(snapshot['company_profile']['name'],'Preserved');self.assertEqual(job,'job-queued')
   self.assertEqual(self.db.execute('SELECT fingerprint FROM preparation_jobs').fetchone()[0],'old','Planning must not mutate the request')
   (state/'queued').mkdir()
   with self.assertRaises(RuntimeError):queued_rebases(self.db,state,lambda modules:self.new)
if __name__=='__main__':unittest.main()
