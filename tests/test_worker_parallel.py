import threading,time,unittest
from deployment.run_shared_worker import PreparationRunner

class WorkerParallelTests(unittest.TestCase):
 def test_new_arrivals_fill_free_slots_and_twenty_jobs_run_once_at_most_ten_at_a_time(self):
  lock=threading.Lock();gate=threading.Event();three=threading.Event();ten=threading.Event();state={'active':0,'peak':0};seen=[];results=[]
  def work(job):
   with lock:
    state['active']+=1;state['peak']=max(state['peak'],state['active']);seen.append(job)
    if state['active']==3:three.set()
    if state['active']==10:ten.set()
   if not gate.wait(5):raise RuntimeError('Preparations did not overlap')
   with lock:state['active']-=1
   return job,'ready_private'
  runner=PreparationRunner(work)
  try:
   self.assertEqual(len(runner.submit(range(3))),3);self.assertTrue(three.wait(3))
   self.assertEqual(len(runner.submit(range(20))),7);self.assertTrue(ten.wait(3));self.assertEqual(len(seen),10);self.assertEqual(runner.submit(range(20)),[])
   gate.set();deadline=time.monotonic()+4
   while len(results)<20 and time.monotonic()<deadline:
    results.extend(runner.collect());runner.submit(job for job in range(20) if job not in {j for j,_ in results});time.sleep(.005)
   self.assertEqual(sorted(seen),list(range(20)));self.assertEqual(len(results),20);self.assertEqual(state['peak'],10)
  finally:gate.set();runner.close()
 def test_failure_of_one_task_does_not_abort_other_companies(self):
  def work(job):
   if job==0:raise RuntimeError('failed task')
   return job,'ready_private'
  runner=PreparationRunner(work)
  try:
   runner.submit(range(3));results=[];deadline=time.monotonic()+3
   while len(results)<3 and time.monotonic()<deadline:results.extend(runner.collect());time.sleep(.005)
   self.assertEqual(dict(results),{0:'preparation_failed_review_private_state',1:'ready_private',2:'ready_private'})
  finally:runner.close()
