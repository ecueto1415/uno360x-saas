"""Narrow, root-run rollout of the restaurant pilot and its SaaS gateway hook.

Does not update Odoo modules, databases, tenant containers or fiscal services.
Requires a staged source directory and an independently verified Node runtime.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

def run(*args):return subprocess.check_output(args,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    stage=Path(sys.argv[1]).resolve()
    assert stage.is_dir() and stage.is_relative_to('/srv/uno360x-saas/restaurant-releases')
    source=Path('/srv/uno360x-saas/https-pilot-current').resolve()
    gateway=source/'control/gateway.py'
    backup=Path('/var/backups/uno360x-restaurant')/time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True,mode=0o700)
    shutil.copy2(gateway,backup/'gateway.py')
    profile=pwd.getpwnam('uno360x-saas')
    state=Path('/var/lib/uno360x-saas/restaurant');state.mkdir(mode=0o700,exist_ok=True)
    os.chown(state,profile.pw_uid,profile.pw_gid)
    key=state/'proxy.key'
    if not key.exists():key.write_text(secrets.token_hex(48)+'\n');key.chmod(0o600);os.chown(key,profile.pw_uid,profile.pw_gid)
    runtime=Path('/opt/uno360x-pos-runtime/node-v24.11.1-linux-x64/bin/node');assert runtime.is_file()
    before={'outsolutech_pid':run('systemctl','show','odoo18.service','-p','MainPID','--value'),
            'gateway_sha256':sha(gateway)}
    # Proof that fiscal implementation and all three fiscal service units stay unchanged.
    fiscal_paths=list(source.glob('addons/uno360x_ecf_core/**/*.py'))
    before['fiscal_hashes']={str(p):sha(p) for p in fiscal_paths}
    (backup/'before.json').write_text(json.dumps(before,indent=2))
    plugin=source/'control/restaurant.py'
    if plugin.exists():shutil.copy2(plugin,backup/'restaurant.py')
    shutil.copy2(stage/'control/restaurant.py',plugin)
    original=gateway.read_text()
    patched=original
    if 'from . import restaurant' not in patched:
        anchor='            url = urllib.parse.urlsplit(self.path)\n'
        assert patched.count(anchor)==1
        patched=patched.replace(anchor,'            from . import restaurant\n'+anchor+
            "            if url.path == restaurant.PATH or url.path.startswith(restaurant.PATH + '/'):\n                restaurant.dispatch(self,handle,url)\n                return\n")
        anchor='            status,headers,body = brand_workspace_title(self.path,status,headers,body)\n'
        assert patched.count(anchor)==1
        patched=patched.replace(anchor,anchor+'            status,headers,body = restaurant.decorate(self.path,status,headers,body)\n')
    compile(patched,str(gateway),'exec');compile(plugin.read_text(),str(plugin),'exec')
    temp=gateway.with_suffix('.restaurant-next');temp.write_text(patched);shutil.copymode(gateway,temp);os.replace(temp,gateway)
    current=Path('/srv/uno360x-saas/restaurant-current')
    if current.is_symlink():(backup/'previous-release.txt').write_text(str(current.resolve()))
    nextlink=current.with_name('restaurant-next')
    if nextlink.is_symlink():nextlink.unlink()
    nextlink.symlink_to(stage);os.replace(nextlink,current)
    service=Path('/etc/systemd/system/uno360x-restaurant.service')
    if service.exists():shutil.copy2(service,backup/service.name)
    service.write_text('''[Unit]
Description=UNO360X restaurant isolated pilot
After=network.target
[Service]
User=uno360x-saas
Group=uno360x-saas
WorkingDirectory=/srv/uno360x-saas/restaurant-current
ExecStart=/opt/uno360x-pos-runtime/node-v24.11.1-linux-x64/bin/node /srv/uno360x-saas/restaurant-current/pos-pilot/server.mjs
Environment=POS_PORT=18248
Environment=POS_DB=/var/lib/uno360x-saas/restaurant/pilot.sqlite
Environment=POS_PROXY_KEY=/var/lib/uno360x-saas/restaurant/proxy.key
Restart=on-failure
RestartSec=3
UMask=0077
MemoryMax=384M
CPUQuota=50%
TasksMax=48
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/uno360x-saas/restaurant
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
''')
    try:
        run('systemctl','daemon-reload');run('systemctl','enable','--now','uno360x-restaurant.service')
        run('systemctl','restart','uno360x-restaurant.service')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for i in range(25):
            try:
                opener.open('http://127.0.0.1:18248/api/state',timeout=2)
            except urllib.error.HTTPError as error:
                if error.code==403:break
                raise
            except urllib.error.URLError:time.sleep(.2)
        else:raise RuntimeError('POS did not start')
        if patched!=original:run('systemctl','restart','uno360x-saas-pilot.service')
        assert run('systemctl','is-active','uno360x-saas-pilot.service')=='active'
        assert before['outsolutech_pid']==run('systemctl','show','odoo18.service','-p','MainPID','--value')
        assert all(sha(Path(p))==value for p,value in before['fiscal_hashes'].items())
    except BaseException:
        shutil.copy2(backup/'gateway.py',gateway)
        run('systemctl','restart','uno360x-saas-pilot.service')
        run('systemctl','stop','uno360x-restaurant.service')
        raise
    print(json.dumps({'release':str(stage),'backup':str(backup),'outsolutech_pid_unchanged':True,'fiscal_code_unchanged':True,'pos_service':run('systemctl','is-active','uno360x-restaurant.service')},indent=2))

if __name__=='__main__':main()
