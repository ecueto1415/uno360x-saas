"""Root-owned read-only exporter. Publishes no credentials or business documents."""
import os,pathlib,subprocess,sqlite3,json,time,re,shutil,tempfile,pwd,datetime,gzip

STATE=pathlib.Path('/var/lib/uno360x-admin-export');CONTROL=pathlib.Path('/var/lib/uno360x-saas/control/control.sqlite3')
def cpu_counts():
 row=pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:];v=list(map(int,row));return {'total':sum(v[:8]),'idle':v[3]+v[4],'steal':v[7]}
def command(args,timeout=12):return subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=True).stdout
def podman(*args):return command(['runuser','-u','uno360x-saas','--','env','XDG_RUNTIME_DIR=/run/user/996','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/996/bus','podman',*args],20)
def tree_size(path):
 total=0
 if not path.is_dir() or path.is_symlink():return None
 for root,dirs,files in os.walk(path,followlinks=False):
  dirs[:]=[d for d in dirs if not (pathlib.Path(root)/d).is_symlink()]
  for file in files:
   f=pathlib.Path(root)/file
   try:
    if not f.is_symlink() and f.is_file():total+=f.stat().st_size
   except FileNotFoundError:pass
 return total
def antivirus():
 import importlib.util
 spec=importlib.util.spec_from_file_location('uno360x_av_history','/usr/local/lib/uno360x-antivirus/history.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 review_file=pathlib.Path('/var/lib/uno360x-antivirus/reviews.json');reviews=json.loads(review_file.read_text()) if review_file.exists() else {}
 history,_=module.collect('/var/log/uno360x-antivirus',reviews=reviews)
 p=pathlib.Path('/var/lib/uno360x-antivirus/latest.json');latest=json.loads(p.read_text()) if p.exists() else None
 if latest:latest={k:v for k,v in latest.items() if k in ('started','finished','mode','automatic_deletion','status','elapsed_seconds','infected_files','internal_scanner_errors')}
 sigs=[f.stat().st_mtime for name in ['daily.cld','daily.cvd'] if (f:=pathlib.Path('/var/lib/clamav')/name).exists()]
 nxt=command(['systemctl','show','uno360x-antivirus-scan.timer','-p','NextElapseUSecRealtime','--value']).strip()
 try:next_epoch=datetime.datetime.strptime(nxt,'%a %Y-%m-%d %H:%M:%S %Z').replace(tzinfo=datetime.timezone.utc).timestamp()
 except ValueError:next_epoch=None
 history=list({r['started']:r for r in history}.values());history.sort(key=lambda r:r['started'],reverse=True)
 return {'latest':latest,'history':history,'retention_days':30,'signatures_updated':max(sigs) if sigs else None,'next_scan':nxt,'next_scan_epoch':next_epoch,'mode':'detection_only'}
def export():
 now=time.time();previous=STATE/'cpu.json';current=cpu_counts();prior=json.loads(previous.read_text()) if previous.exists() else None
 if not prior:
  prior=current;time.sleep(.25);current=cpu_counts()
 total=current['total']-prior['total'];used=(100*(total-(current['idle']-prior['idle'])-(current['steal']-prior['steal']))/total) if total>0 else None
 previous.write_text(json.dumps(current));previous.chmod(0o600)
 mem={k:int(v.split()[0])*1024 for k,v in [l.split(':',1) for l in pathlib.Path('/proc/meminfo').read_text().splitlines()]}
 disk=shutil.disk_usage('/var/lib/uno360x-saas')
 d=sqlite3.connect('file:'+str(CONTROL)+'?mode=ro',uri=True);d.row_factory=sqlite3.Row
 query='''SELECT t.id,t.slug,t.hostname,t.modules,w.name,w.created,w.started,w.expires,w.country,w.currency,a.email,a.verified,a.active,
 j.status AS preparation_status,j.current_step,j.updated AS preparation_updated,
 (SELECT count(*) FROM memberships m JOIN accounts ac ON ac.id=m.account_id WHERE m.tenant_id=t.id AND m.active=1 AND ac.active=1) AS members
 FROM tenants t JOIN memberships m ON m.tenant_id=t.id AND m.role='owner'
 JOIN accounts a ON a.id=m.account_id LEFT JOIN trial_workspaces w ON w.tenant_id=t.id
 LEFT JOIN preparation_jobs j ON j.tenant_id=t.id ORDER BY w.created DESC'''
 clients=[]
 for row in d.execute(query):
  r=dict(row)
  if not re.fullmatch('[a-f0-9]{32}',r['id']):continue
  if r['email'].lower().endswith(('.test','.invalid','.localhost','.example')):continue
  r['modules']=json.loads(r['modules']);r['quota_bytes']=5_000_000_000;r['quota_enforced']=False
  r['days_remaining']=max(0,int((r['expires']-now+86399)//86400)) if r['expires'] else None
  r['status']='inactive' if not r['active'] else 'failed' if r['preparation_status']=='failed' else 'preparing' if r['preparation_status']!='ready_local' else 'expired' if r['expires'] and r['expires']<=now else 'trial' if r['expires'] else 'existing'
  role='tenant_'+r['id'];container='uno360x-pilot-'+r['id']+'-db';size=None;binding=None
  inventory=pathlib.Path('/var/lib/uno360x-saas/shared-postgres/inventory.sqlite3')
  if inventory.exists():
   with sqlite3.connect('file:'+str(inventory)+'?mode=ro',uri=True) as pool:
    pool.row_factory=sqlite3.Row;found=pool.execute('SELECT * FROM reserve_bindings WHERE tenant_id=?',(r['id'],)).fetchone()
    if found:binding=dict(found)
  if binding:
   role=binding['database_name'];container='uno360x-shared-postgres-v1'
   if not re.fullmatch('tenant_[a-f0-9]{32}',role):raise ValueError('Invalid shared database')
  try:
   inspect=json.loads(podman('inspect',container))[0]
   if binding:
    if inspect['Config']['Labels'].get('uno360x.environment')!='shared-postgres-reserve' or inspect['Config']['Labels'].get('uno360x.managed')!='uno360x-saas':raise ValueError('Foreign shared container')
   elif inspect['Config']['Labels'].get('uno360x.tenant')!=r['id']:raise ValueError('Foreign container')
   if inspect['State']['Running']:
    size=int(podman('exec','-u','postgres',container,'psql','-U','postgres' if binding else role,'-d',role,'-Atc','BEGIN READ ONLY; SELECT pg_database_size(current_database()); COMMIT;').splitlines()[1])
  except Exception:pass
  volume=binding['files_volume'] if binding else 'uno360x-pilot-'+r['id']+'-odoodata'
  if not re.fullmatch(r'uno360x-(?:pilot-[a-f0-9]{32}-odoodata|reserve-[a-f0-9]{32}-files)',volume):raise ValueError('Invalid files volume')
  files=pathlib.Path('/var/lib/uno360x-saas/.local/share/containers/storage/volumes')/volume/'_data'/'filestore'
  r['files_bytes']=tree_size(files);r['database_bytes']=size;r['storage_bytes']=(size+r['files_bytes']) if size is not None and r['files_bytes'] is not None else None
  clients.append(r)
 events=[]
 allowed={r['id'] for r in clients}
 for event in d.execute('SELECT event,tenant_id,occurred FROM identity_audit ORDER BY id DESC LIMIT 300'):
  if event['tenant_id'] in allowed:events.append(dict(event))
 d.close()
 value={'generated':now,'clients':clients,'events':events[:60],'server':{'cpu_percent':round(max(0,min(100,used)),1) if used is not None else None,'cpus':os.cpu_count(),'memory_total':mem['MemTotal'],'memory_available':mem['MemAvailable'],'memory_used':mem['MemTotal']-mem['MemAvailable'],'disk_total':disk.total,'disk_used':disk.used,'disk_available':disk.free,'load':list(os.getloadavg())},'antivirus':antivirus()}
 fd,temp=tempfile.mkstemp(prefix='.snapshot-',dir=STATE)
 try:
  with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False)
  os.chown(temp,0,pwd.getpwnam('uno360x-admin').pw_gid);os.chmod(temp,0o640);os.replace(temp,STATE/'snapshot.json')
 finally:
  if os.path.exists(temp):os.unlink(temp)

if __name__=='__main__':export()
