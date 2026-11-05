"""Private queue worker, no HTTP listener, no public registration or SMTP."""
import json,os,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.shared_adapter import SharedHostAdapter,CapacityUnavailable
from control.identity import IdentityService
from control.onboarding import Onboarding
from deployment.admission_status import publish as publish_admission
STATE=Path('/var/lib/uno360x-saas/control')

def pending_jobs(db,initial):
 states="('queued','running','failed','ready_local')" if initial else "('queued')"
 expired=''
 params=()
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
  expired=' AND NOT EXISTS (SELECT 1 FROM trial_workspaces t WHERE t.tenant_id=p.tenant_id AND t.expires IS NOT NULL AND t.expires<=?)'
  params=(time.time(),)
 return [r[0] for r in db.execute('SELECT p.id FROM preparation_jobs p WHERE p.status IN '+states+expired+' ORDER BY p.updated',params)]
MAX_PREPARATIONS=10

def prepare_job(job):
 # Odoo bootstrap buffers and SQLite connections are private to each task.
 service=None
 try:
  service=IdentityService(STATE/'control.sqlite3',lambda notice:None)
  adapter=SharedHostAdapter()
  Onboarding(service).run(job,adapter)
  return job,'ready_private'
 except CapacityUnavailable:return job,'capacity'
 except Exception:return job,'preparation_failed_review_private_state'
 finally:
  if service is not None:service.close()

class PreparationRunner:
 def __init__(self,process=prepare_job):
  self.process=process;self.pool=ThreadPoolExecutor(max_workers=MAX_PREPARATIONS);self.inflight={}
 def submit(self,queue):
  submitted=[]
  for job in queue:
   if job in self.inflight:continue
   if len(self.inflight)>=MAX_PREPARATIONS:break
   self.inflight[job]=self.pool.submit(self.process,job);submitted.append(job)
  return submitted
 def collect(self):
  results=[]
  for job,future in list(self.inflight.items()):
   if not future.done():continue
   del self.inflight[job]
   try:results.append(future.result())
   except Exception:results.append((job,'preparation_failed_review_private_state'))
  return results
 def close(self):self.pool.shutdown(wait=True)

def main():
 os.umask(0o077);adapter=SharedHostAdapter();STATE.mkdir(mode=0o700,exist_ok=True)
 service=IdentityService(STATE/'control.sqlite3',lambda notice:None);runner=PreparationRunner()
 initial_queue=pending_jobs(service.db,True);next_expiration_sweep=0;next_admission_check=0;retry_after=0
 try:
  while True:
   for job,result in runner.collect():
    if result=='capacity':
     retry_after=time.monotonic()+5
     with service.db:service.db.execute("UPDATE preparation_jobs SET current_step='capacity' WHERE id=? AND status='queued'",(job,))
    else:print(job+' '+result,flush=True)
   if time.monotonic()>=next_admission_check:
    next_admission_check=time.monotonic()+5
    try:publish_admission(adapter)
    except Exception:print('admission_check_pending',flush=True)
   if time.monotonic()>=next_expiration_sweep and service.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
    next_expiration_sweep=time.monotonic()+60
    for expired in service.db.execute("SELECT p.snapshot FROM preparation_jobs p JOIN trial_workspaces t ON p.tenant_id=t.tenant_id WHERE t.expires IS NOT NULL AND t.expires<=?",(time.time(),)).fetchall():
     try:adapter.stop_expired(json.loads(expired[0]))
     except Exception:print('expired_compute_cleanup_pending',flush=True)
   if time.monotonic()>=retry_after:
    submitted=runner.submit(initial_queue+pending_jobs(service.db,False))
    initial_queue=[job for job in initial_queue if job not in submitted]
   time.sleep(1)
 finally:runner.close();service.close()
if __name__=='__main__':main()
