"""Publish only the isolated restaurant release plus its read-only public-menu route.
No Odoo/gateway updates; preserve all fiscal locations and current tenant data.
"""
from pathlib import Path
import subprocess,sys,time,os,shutil,json

def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT).strip()
base=Path('/srv/uno360x-saas/restaurant-releases').resolve()
stage=Path(sys.argv[1]).resolve();assert stage.is_relative_to(base) and stage.is_dir()
link=Path('/srv/uno360x-saas/restaurant-current');old=link.resolve()
conf=Path('/etc/nginx/sites-available/uno360x-saas-pilot');original=conf.read_text()
assert 'server_name piloto.uno360x.com;' in original
backup=Path('/var/backups/uno360x-restaurant')/('public-menu-'+time.strftime('%Y%m%d-%H%M%S'));backup.mkdir(parents=True,mode=0o700)
shutil.copy2(conf,backup/'nginx-pilot.conf');(backup/'previous-release.txt').write_text(str(old))
before=run('systemctl','show','odoo18.service','-p','MainPID','--value')
fiscal=run('ss','-ltnp','sport = :18198')
location='''
 # UNO360X public digital menu: read-only, no SaaS session or private API forwarding.
 location ^~ /menu-pos/ {
  limit_except GET HEAD { deny all; }
  proxy_pass http://127.0.0.1:18248;
  proxy_set_header Host piloto.uno360x.com;
  proxy_set_header Cookie "";
  proxy_set_header Authorization "";
  proxy_set_header X-UNO-POS-Proof "";
  proxy_connect_timeout 3s;
  proxy_read_timeout 10s;
  proxy_buffering on;
  proxy_max_temp_file_size 0;
 }
'''
anchor=' server_name piloto.uno360x.com;\n'
assert original.count(anchor)==1
patched=original if 'location ^~ /menu-pos/' in original else original.replace(anchor,anchor+location,1)
try:
 subprocess.run(['python3',str(stage/'deployment/update_restaurant_split.py'),str(stage)],check=True)
 tmp=conf.with_suffix('.menu-next');tmp.write_text(patched);shutil.copymode(conf,tmp);os.replace(tmp,conf)
 run('nginx','-t');run('systemctl','reload','nginx')
 assert run('systemctl','show','odoo18.service','-p','MainPID','--value')==before
 assert run('ss','-ltnp','sport = :18198')==fiscal
 assert run('systemctl','is-active','uno360x-restaurant.service')=='active'
 print(json.dumps({'public_menu_route':'active','backup':str(backup),'outsolutech_unchanged':True,'incivi_fiscal_unchanged':True,'gateway_restart':False}))
except BaseException:
 shutil.copy2(backup/'nginx-pilot.conf',conf);run('nginx','-t');run('systemctl','reload','nginx')
 nextlink=link.with_name('restaurant-public-menu-rollback');assert not nextlink.exists();nextlink.symlink_to(old);os.replace(nextlink,link)
 run('systemctl','restart','uno360x-restaurant.service');raise
