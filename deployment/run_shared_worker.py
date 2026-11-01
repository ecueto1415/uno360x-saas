"""Private queue worker, no HTTP listener, no public registration or SMTP."""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment.shared_adapter import SharedHostAdapter
from control.identity import IdentityService
from control.onboarding import Onboarding
STATE=Path('/var/lib/uno360x-saas/control')
def main():
 os.umask(0o077);adapter=SharedHostAdapter();STATE.mkdir(mode=0o700,exist_ok=True)
 service=IdentityService(STATE/'control.sqlite3',lambda notice:None);jobs=Onboarding(service)
 initial=True
 try:
  while True:
   states="('queued','running','failed','ready_local')" if initial else "('queued')"
   queue=[r[0] for r in service.db.execute('SELECT id FROM preparation_jobs WHERE status IN '+states+' ORDER BY updated')]
   for job in queue:
    try:jobs.run(job,adapter);print(job+' ready_private',flush=True)
    except Exception:print(job+' preparation_failed_review_private_state',flush=True)
   initial=False;time.sleep(3)
 finally:service.close()
if __name__=='__main__':main()
