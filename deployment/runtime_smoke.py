"""Rootless container proof on the authorized VM; no Odoo/PG database started."""
import json,os,pathlib,pwd,subprocess
assert os.geteuid()==0 and pathlib.Path('/etc/uno360x-saas/staging-policy.json').exists()
uid=pwd.getpwnam('uno360x-saas').pw_uid
base=['runuser','-u','uno360x-saas','--','env','XDG_RUNTIME_DIR=/run/user/'+str(uid),'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(uid)+'/bus','podman']
def call(args):return subprocess.run(base+args,cwd='/var/lib/uno360x-saas',capture_output=True,text=True,check=True).stdout
info=json.loads(call(['info','--format','json']));assert info['host']['security']['rootless']
image='docker.io/library/postgres@sha256:1beaa3084eee2676f20a9cd9928f0bf2c5bf674f8e49f81017912183d377c61c'
print('Pulling pinned official image for private runtime proof...',flush=True)
call(['pull',image])
output=call(['run','--rm','--name','uno360x-runtime-probe','--label','uno360x.environment=runtime-validation','--network','none','--read-only','--cap-drop','all','--security-opt','no-new-privileges','--memory','128m','--cpus','0.25','--pids-limit','32','--entrypoint','/bin/sh',image,'-c','test ! -r /etc/odoo18.conf && test ! -d /opt/odoo18 && echo UNO360X_PRIVATE_CONTAINER_OK'])
assert 'UNO360X_PRIVATE_CONTAINER_OK' in output
assert not json.loads(call(['ps','--format','json']))
report={'rootless':True,'runtime_user':'uno360x-saas','cgroup_version':info['host']['cgroupVersion'],'graph_root':info['store']['graphRoot'],'official_image_digest':image,'network':'none','ports_published':False,'production_paths_mounted':False,'read_only_container':True,'capabilities_dropped':True,'probe_passed':True,'probe_removed':True,'tenant_provisioning_not_yet_deployed':True}
pathlib.Path('/etc/uno360x-saas/runtime-smoke.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
