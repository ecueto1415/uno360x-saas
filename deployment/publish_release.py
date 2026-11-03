"""One reviewed release -> every active SaaS tenant, with resumable progress.

Root is used only for existing SaaS service/source-link management. Tenant
database work and tests run as uno360x-saas. Native Odoo is never managed.
Default: read-only plan. --apply publishes this immutable candidate source.
"""
import argparse,fcntl,hashlib,json,os,pathlib,sqlite3,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE=pathlib.Path('/srv/uno360x-saas')
LINKS=('master-current','worker-current','https-pilot-current')

def saas(command,**kwargs):
 return subprocess.run(['runuser','-u','uno360x-saas','--','env','XDG_RUNTIME_DIR=/run/user/996','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/996/bus',*command],cwd='/var/lib/uno360x-saas',**kwargs)

def native_guard():
 return {'pid':subprocess.check_output(['systemctl','show','odoo18','-p','MainPID','--value'],text=True).strip(),'config_sha256':hashlib.sha256(pathlib.Path('/etc/odoo18.conf').read_bytes()).hexdigest()}

def main():
 p=argparse.ArgumentParser();p.add_argument('--release',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 if os.geteuid()!=0:raise RuntimeError('Root coordinator required; tenant work remains unprivileged')
 if not ROOT.is_relative_to((BASE/'releases').resolve()) or ROOT.name!='source':raise RuntimeError('Use an immutable candidate release directory')
 command=['python3',str(ROOT/'deployment/release_fleet.py'),'--release',a.release]
 if not a.apply:raise SystemExit(saas(command).returncode)
 os.umask(0o077)
 with pathlib.Path('/run/lock/uno360x-saas-release.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  before=native_guard();old={n:str((BASE/n).resolve()) for n in LINKS}
  db=sqlite3.connect('file:/var/lib/uno360x-saas/control/control.sqlite3?mode=ro',uri=True)
  if db.execute("SELECT 1 FROM preparation_jobs WHERE status='running'").fetchone():raise RuntimeError('Wait for the current creation to finish')
  db.close()
  # Keep identity and customer applications available during sequential staging.
  subprocess.run(['systemctl','stop','uno360x-saas-worker'],check=True)
  if saas(command+['--apply']).returncode:
   raise RuntimeError('Rollout paused for review; gateway remains up, worker remains paused, progress and backups retained')
  subprocess.run(['systemctl','stop','uno360x-saas-pilot'],check=True)
  if saas(command+['--finalize']).returncode:
   raise RuntimeError('Atomic publication needs review; do not start the old gateway against partially published profiles')
  for name in LINKS:
   temporary=BASE/(name+'.next');temporary.unlink(missing_ok=True);temporary.symlink_to(ROOT);temporary.replace(BASE/name)
  subprocess.run(['systemctl','start','uno360x-saas-pilot','uno360x-saas-worker'],check=True)
  for service in ('uno360x-saas-pilot','uno360x-saas-worker'):
   subprocess.run(['systemctl','is-active','--quiet',service],check=True)
  after=native_guard();assert before==after,'Native Odoo changed during the SaaS publication'
  record={'release':a.release,'source':str(ROOT),'previous_links':old,'published_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'native_odoo_unchanged':True}
  pathlib.Path('/var/lib/uno360x-saas/published-release.json').write_text(json.dumps(record))
  print(json.dumps(record),flush=True)
if __name__=='__main__':main()
