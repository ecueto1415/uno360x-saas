"""Private queue worker, no HTTP listener, no public registration or SMTP."""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.shared_adapter import SharedHostAdapter,CapacityUnavailable
from control.identity import IdentityService
from control.onboarding import Onboarding
STATE=Path('/var/lib/uno360x-saas/control')

def pending_jobs(db,initial):
 states="('queued','running','failed','ready_local')" if initial else "('queued')"
 expired=''
 params=()
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
  expired=' AND NOT EXISTS (SELECT 1 FROM trial_workspaces t WHERE t.tenant_id=p.tenant_id AND t.expires IS NOT NULL AND t.expires<=?)'
  params=(time.time(),)
 return [r[0] for r in db.execute('SELECT p.id FROM preparation_jobs p WHERE p.status IN '+states+expired+' ORDER BY p.updated',params)]
def main():
 os.umask(0o077);adapter=SharedHostAdapter();STATE.mkdir(mode=0o700,exist_ok=True)
 service=IdentityService(STATE/'control.sqlite3',lambda notice:None);jobs=Onboarding(service)
 initial=True
 try:
  while True:
   if service.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_workspaces'").fetchone():
    for expired in service.db.execute("SELECT p.snapshot FROM preparation_jobs p JOIN trial_workspaces t ON p.tenant_id=t.tenant_id WHERE t.expires IS NOT NULL AND t.expires<=?",(time.time(),)).fetchall():
     try:adapter.stop_expired(json.loads(expired[0]))
     except Exception:print('expired_compute_cleanup_pending',flush=True)
   queue=pending_jobs(service.db,initial)
   for job in queue:
    try:jobs.run(job,adapter);print(job+' ready_private',flush=True)
    except CapacityUnavailable:
     with service.db:service.db.execute("UPDATE preparation_jobs SET current_step='capacity' WHERE status='queued' AND (current_step IS NULL OR current_step='capacity')")
     break
    except Exception:print(job+' preparation_failed_review_private_state',flush=True)
   initial=False;time.sleep(3)
 finally:service.close()
if __name__=='__main__':main()
