import sqlite3,time,unittest
from deployment.run_shared_worker import pending_jobs

class WorkerQueueTests(unittest.TestCase):
 def test_restart_does_not_reactivate_expired_compute(self):
  db=sqlite3.connect(':memory:')
  db.executescript('CREATE TABLE preparation_jobs(id TEXT,tenant_id TEXT,status TEXT,updated REAL); CREATE TABLE trial_workspaces(tenant_id TEXT,expires REAL);')
  db.executemany('INSERT INTO preparation_jobs VALUES (?,?,?,?)',[('expired','a','ready_local',1),('active','b','ready_local',2),('queued','c','queued',3)])
  db.executemany('INSERT INTO trial_workspaces VALUES (?,?)',[('a',time.time()-1),('b',time.time()+3600),('c',None)])
  self.assertEqual(pending_jobs(db,True),['active','queued'])
  self.assertEqual(pending_jobs(db,False),['queued'])
  db.close()
