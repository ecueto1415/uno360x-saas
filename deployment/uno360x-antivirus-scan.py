#!/usr/bin/python3
import pathlib,subprocess,datetime,json,os,sys,re,fcntl,time,resource
STATE=pathlib.Path('/var/lib/uno360x-antivirus'); LOGS=pathlib.Path('/var/log/uno360x-antivirus'); DB=pathlib.Path('/var/lib/clamav')
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4)))
report={'started':now.isoformat(),'mode':'detection_only','automatic_deletion':False}
def finish(status,code,**extra):
 report.update(status=status,finished=datetime.datetime.now(datetime.timezone.utc).isoformat(),**extra)
 p=STATE/'latest.json'; tmp=p.with_suffix('.new'); tmp.write_text(json.dumps(report,indent=2)); tmp.chmod(0o640); tmp.replace(p)
 print(json.dumps(report),flush=True)
 if code:
  subprocess.run(['/usr/bin/logger','-p','authpriv.alert','-t','uno360x-antivirus','--','Antivirus status='+status+'; review '+str(p)])
 raise SystemExit(code)

def scan_targets():
 targets=['/opt/odoo18','/opt/jenifer-directa','/opt/jenifer-updates','/usr/local/bin','/usr/local/sbin','/usr/local/lib/uno360x','/usr/lib/systemd/system','/etc/cron.d','/etc/systemd/system','/tmp','/var/tmp','/home/linuxuser','/srv/uno360x-saas/releases','/srv/uno360x-saas/runtime']
 saas=pathlib.Path('/var/lib/uno360x-saas')
 storage=saas/'.local/share/containers/storage'
 # Scan Odoo attachments/addons, never PostgreSQL volumes or container images.
 candidates=list((storage/'volumes').glob('uno360x-pilot-*-odoodata/_data'))
 candidates += list((storage/'overlay').glob('*/diff/tmp'))
 candidates += list((storage/'overlay').glob('*/diff/var/tmp'))
 candidates += [saas/'uploads',saas/'tmp']
 for p in candidates:
  if p.is_dir() and not p.is_symlink() and p.resolve().is_relative_to(saas.resolve()):
   targets.append(str(p))
 targets=[p for p in targets if pathlib.Path(p).exists() and not pathlib.Path(p).is_symlink()]
 targets += [str(p) for p in pathlib.Path('/usr/lib').glob('.*') if p.is_file() and not p.is_symlink()]
 return list(dict.fromkeys(targets))

if '--show-plan' in sys.argv:
 print(json.dumps({'mode':'detection_only','automatic_deletion':False,'targets':scan_targets(),'postgresql_volumes_included':False,'sessions_and_credentials_excluded':True},indent=2))
 raise SystemExit(0)

if '--manual' not in sys.argv and not 1<=now.hour<5: finish('skipped_outside_night_window',0)
lock=open('/run/uno360x-clamav/operation.lock','a')
try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: finish('skipped_signature_update_running',0)
mem={k:int(v.split()[0]) for k,v in [l.split(':',1) for l in pathlib.Path('/proc/meminfo').read_text().splitlines()]}
if mem['MemAvailable']<4*1024*1024: finish('skipped_insufficient_memory',0,available_mib=mem['MemAvailable']//1024)
updates=[p for name in ['daily.cvd','daily.cld'] if (p:=DB/name).is_file()]
if not updates or (datetime.datetime.now().timestamp()-max(p.stat().st_mtime for p in updates))>48*3600: finish('error_signatures_missing_or_stale',2)
targets=scan_targets()
log=LOGS/('scan-'+now.strftime('%Y%m%d-%H%M%S')+'.log')
command=['/usr/local/bin/clamscan','--tempdir=/var/lib/uno360x-antivirus/tmp','--database=/var/lib/clamav','--official-db-only=yes','--recursive=yes','--infected','--follow-dir-symlinks=0','--follow-file-symlinks=0','--max-filesize=50M','--max-scansize=100M','--max-recursion=16',r'--exclude-dir=/\.git(/|$)',r'--exclude-dir=/\.(ssh|codex|cache)(/|$)',r'--exclude-dir=/sessions(/|$)',r'--exclude=\.(p12|pfx|pem|key)$','--exclude=/home/linuxuser/credentials.txt',r'--exclude-dir=/var/lib/uno360x-saas/(control|tenants)(/|$)',r'--exclude-dir=/var/lib/uno360x-saas/\.local/share/containers/storage/volumes/[^/]*-pgdata(/|$)']+targets
report.update(log=str(log),targets=targets)
started=time.monotonic()
try:
 with log.open('w') as output:
  result=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,timeout=6600,env={**os.environ,'LC_ALL':'C'})
 usage=resource.getrusage(resource.RUSAGE_CHILDREN)
 report.update(elapsed_seconds=round(time.monotonic()-started,2),peak_scanner_rss_mib=round(usage.ru_maxrss/1024,1),scanner_cpu_seconds=round(usage.ru_utime+usage.ru_stime,2))
 text=log.read_text(errors='replace')
 scan_errors=len(re.findall(r'LibClamAV Error:',text))
 report['internal_scanner_errors']=scan_errors
 for label,key in [('Data scanned','data_scanned_mib'),('Data read','data_read_mib')]:
  match=re.search(label+r':\s*([0-9.]+) MB',text)
  if match: report[key]=float(match[1])
 if scan_errors: finish('scan_error',2,scanner_exit_code=result.returncode)
 count=re.search(r'Infected files:\s*(\d+)',text)
 if result.returncode==0: finish('completed_no_detections',0,infected_files=int(count[1]) if count else 0)
 if result.returncode==1: finish('detections_require_review',1,infected_files=int(count[1]) if count else None)
 finish('scan_error',2,scanner_exit_code=result.returncode)
except subprocess.TimeoutExpired: finish('scan_time_limit',2)
except Exception as error: finish('scan_error',2,error_type=type(error).__name__)

