"""Install only signed-index Podman candidate packages, without OS upgrade."""
import hashlib,json,os,pathlib,re,shutil,subprocess,urllib.request
assert os.geteuid()==0 and pathlib.Path('/etc/uno360x-saas/staging-policy.json').exists()
def call(args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT)
before=call(['systemctl','show','odoo18','-p','MainPID','--value']).strip()
plan=call(['apt-get','--simulate','--no-upgrade','install','podman'])
assert '0 upgraded,' in plan and '0 to remove' in plan
names=re.findall(r'^Inst ([a-z0-9+-]+) ',plan,re.M)
allowed={'aardvark-dns','buildah','catatonit','conmon','containernetworking-plugins','crun','fuse-overlayfs','golang-github-containers-common','golang-github-containers-image','libslirp0','libsubid4','libyajl2','netavark','passt','podman','slirp4netns','uidmap'}
assert set(names)<=allowed and 'podman' in names
manifest=[]
for name in names:
 info=call(['apt-cache','show','--no-all-versions',name]);fields={}
 for line in info.splitlines():
  if ': ' in line and not line.startswith(' '):
   k,v=line.split(': ',1);fields.setdefault(k,v)
 relative=fields['Filename'];assert relative.startswith('pool/') and '..' not in relative
 expected=fields['SHA256'];assert re.fullmatch('[a-f0-9]{64}',expected)
 target=pathlib.Path('/var/cache/apt/archives')/relative.rsplit('/',1)[1]
 if not target.exists() or hashlib.file_digest(target.open('rb'),'sha256').hexdigest()!=expected:
  url='https://old-releases.ubuntu.com/ubuntu/'+relative
  with urllib.request.urlopen(url,timeout=45) as response:raw=response.read()
  assert hashlib.sha256(raw).hexdigest()==expected
  temporary=target.with_suffix('.verified-part');temporary.write_bytes(raw);temporary.replace(target)
 apt_name=name+'_'+fields['Version'].replace(':','%3a')+'_'+fields['Architecture']+'.deb'
 apt_target=target.parent/apt_name
 if apt_target!=target:shutil.copyfile(target,apt_target)
 manifest.append({'package':name,'version':fields['Version'],'sha256':expected})
print('VERIFIED_PACKAGES '+json.dumps(manifest),flush=True)
env=dict(os.environ,DEBIAN_FRONTEND='noninteractive',NEEDRESTART_MODE='l')
p=subprocess.run(['apt-get','-y','--no-download','--no-upgrade','install','podman'],env=env,capture_output=True,text=True)
pathlib.Path('/etc/uno360x-saas/runtime-install.log').write_text(p.stdout+'\n'+p.stderr)
assert p.returncode==0,'Review private runtime-install.log'
assert call(['systemctl','show','odoo18','-p','MainPID','--value']).strip()==before
report={'podman_version':call(['podman','--version']).strip(),'packages':manifest,'os_upgrade':False,'operational_odoo_restarted':False,'public_ports_added':False}
pathlib.Path('/etc/uno360x-saas/runtime-install.json').write_text(json.dumps(report,indent=2))
print('PRIVATE_RUNTIME_INSTALLED '+json.dumps(report),flush=True)
