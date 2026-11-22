"""Update only the isolated restaurant service; no Odoo or gateway mutation."""
from pathlib import Path
import subprocess,sys,shutil,sqlite3,json,time,os,urllib.request,hashlib
def run(*args):return subprocess.check_output(args,text=True).strip()
base=Path('/srv/uno360x-saas/restaurant-releases').resolve()
stage=Path(sys.argv[1]).resolve();assert stage.is_relative_to(base) and stage.is_dir()
current=Path('/srv/uno360x-saas/restaurant-current');old=current.resolve();assert old.is_relative_to(base)
stamp=time.strftime('%Y%m%d-%H%M%S');backup=Path('/var/backups/uno360x-restaurant')/('split-'+stamp);backup.mkdir(mode=0o700,parents=True)
before=run('systemctl','show','odoo18.service','-p','MainPID','--value')
fiscal=run('ss','-ltnp','sport = :18198')
(backup/'previous-release.txt').write_text(str(old))
source=sqlite3.connect('file:/var/lib/uno360x-saas/restaurant/pilot.sqlite?mode=ro',uri=True)
source.execute('PRAGMA query_only=ON');dest=sqlite3.connect(backup/'pilot.sqlite');source.backup(dest);dest.close();source.close()
nextlink=current.with_name('restaurant-split-next');assert not nextlink.exists()
nextlink.symlink_to(stage);os.replace(nextlink,current)
run('systemctl','restart','uno360x-restaurant.service')
try:
 for attempt in range(15):
  try:
   with urllib.request.urlopen('http://127.0.0.1:18248/') as r:assert b'UNO360X POS' in r.read()
   break
  except OSError:time.sleep(.3)
 else:raise RuntimeError('Restaurant health check failed')
 assert run('systemctl','show','odoo18.service','-p','MainPID','--value')==before
 assert run('ss','-ltnp','sport = :18198')==fiscal
 print(json.dumps({'restaurant':'active','release':str(stage),'outsolutech_pid_unchanged':True,'incivi_fiscal_listener_unchanged':True,'backup':str(backup)}))
except Exception:
 nextlink.symlink_to(old);os.replace(nextlink,current);run('systemctl','restart','uno360x-restaurant.service');raise
