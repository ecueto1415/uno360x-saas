import concurrent.futures,http.client,http.cookies,json,os,pathlib,resource,secrets,sqlite3,statistics,sys,tempfile,threading,time,urllib.request,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import pwd
if os.geteuid()==0 or pwd.getpwuid(os.geteuid()).pw_name!='uno360x-saas':raise RuntimeError('Run exclusively as the unprivileged SaaS account')
from deployment.https_pilot import HTTPSIdentityServer
from control.identity import IdentityService,dummy_password_hash
from control.trials import Trials
from control.onboarding import Onboarding
os.umask(0o077)
N=10;origin='https://cuenta.uno360x.com';mail={};mail_lock=threading.Lock();metrics_lock=threading.Lock();latencies={};stop=threading.Event();samples=[]
def sink(item):
 with mail_lock:mail[item['email']]=item['token']
def memory():
 d={}
 for l in pathlib.Path('/proc/meminfo').read_text().splitlines():
  if l.startswith(('MemAvailable:','MemTotal:')):d[l.split(':')[0]]=int(l.split()[1])*1024
 return d
def cpu():
 vals=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:9]));return sum(vals),vals[3]+vals[4]
def monitor():
 while not stop.wait(.1):
  samples.append(memory()['MemAvailable'])
def health():
 result={}
 for name,url,host in [('native','http://127.0.0.1:8069/web/login?db=Outsolutech_prueba',None),('signup','http://127.0.0.1:18183/health','cuenta.uno360x.com')]:
  try:
   req=urllib.request.Request(url,headers={'Host':host} if host else {})
   with urllib.request.urlopen(req,timeout=5) as r:result[name]=r.status
  except Exception as e:result[name]=type(e).__name__
 return result
before_health=health();before_mem=memory();before_pid=subprocess.check_output(['systemctl','show','odoo18','-p','MainPID','--value'],text=True).strip()
with tempfile.TemporaryDirectory(prefix='uno360x-signup-burst-',dir='/var/lib/uno360x-saas') as tmp:
 dbpath=pathlib.Path(tmp)/'identity.sqlite3';bootstrap=IdentityService(dbpath,sink);Trials(bootstrap);Onboarding(bootstrap);bootstrap.close();dummy_password_hash()
 server=HTTPSIdentityServer(0,dbpath,sink,None,origin,[],'https://piloto.uno360x.com',public_signup=True)
 thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.05),daemon=True);thread.start();barrier=threading.Barrier(N)
 def client(i):
  email='load-'+secrets.token_hex(4)+'@example.com';password=secrets.token_urlsafe(24);cookie='';csrf='';stage='initial'
  def request(path,data):
   nonlocal cookie,csrf,stage
   stage=path;barrier.wait(timeout=30)
   conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=20)
   headers={'Host':'cuenta.uno360x.com','Origin':origin,'Content-Type':'application/json','X-CSRF-Token':csrf}
   if cookie:headers['Cookie']=cookie
   start=time.monotonic()
   try:
    conn.request('POST',path,json.dumps(data).encode(),headers);r=conn.getresponse();body=json.loads(r.read());duration=time.monotonic()-start
    if r.getheader('Set-Cookie'):
     jar=http.cookies.SimpleCookie();jar.load(r.getheader('Set-Cookie'));cookie='; '.join(k+'='+v.value for k,v in jar.items())
    with metrics_lock:latencies.setdefault(path,[]).append({'http':r.status,'seconds':duration})
    if r.status!=200:raise RuntimeError('HTTP '+str(r.status))
    return body
   finally:conn.close()
  try:
   request('/trial/register',{'name':'EMPRESA FICTICIA '+str(i),'email':email,'modules':[],'consent':True,'consent_version':'public-trial-v1'})
   with mail_lock:token=mail[email]
   request('/verify',{'token':token,'password':password})
   result=request('/login',{'email':email,'password':password});csrf=result['csrf_token']
   data={'name':'EMPRESA FICTICIA '+str(i),'country':'DO','currency':'DOP','modules':[]}
   co=request('/trial/create',data)
   state=request('/trial/status',{'tenant_id':co['tenant_id']})
   again=request('/trial/create',data)
   assert again['tenant_id']==co['tenant_id'] and not state['local_ready'] and state['started'] is None
   return {'client':i,'ok':True,'status':state['status'],'duplicate_prevented':True}
  except Exception as e:
   barrier.abort();return {'client':i,'ok':False,'stage':stage,'error':type(e).__name__+': '+str(e)[:100]}
 try:
  cpu_before=cpu();usage_before=resource.getrusage(resource.RUSAGE_SELF);start=time.monotonic();monitor_thread=threading.Thread(target=monitor,daemon=True);monitor_thread.start()
  with concurrent.futures.ThreadPoolExecutor(max_workers=N) as pool:results=list(pool.map(client,range(1,N+1)))
  elapsed=time.monotonic()-start;usage_after=resource.getrusage(resource.RUSAGE_SELF);cpu_after=cpu();stop.set();monitor_thread.join()
  c=sqlite3.connect(dbpath);counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('accounts','tenants','trial_workspaces','preparation_jobs')};verified=c.execute('SELECT count(*) FROM accounts WHERE verified=1').fetchone()[0];c.close()
 finally:server.shutdown();server.server_close();thread.join();stop.set()
after_health=health();after_pid=subprocess.check_output(['systemctl','show','odoo18','-p','MainPID','--value'],text=True).strip()
phases={}
for name,items in latencies.items():
 vals=sorted(x['seconds'] for x in items);phases[name]={'requests':len(vals),'http_codes':{str(code):sum(x['http']==code for x in items) for code in set(x['http'] for x in items)},'mean_seconds':round(statistics.mean(vals),3),'max_seconds':round(max(vals),3)}
used_cpu=(usage_after.ru_utime+usage_after.ru_stime)-(usage_before.ru_utime+usage_before.ru_stime)
total=cpu_after[0]-cpu_before[0];idle=cpu_after[1]-cpu_before[1]
report={'clients':N,'concurrent_registration':True,'scope':'Same VM and deployed HTTP identity code, isolated temporary database and in-memory mail; no real email, Cloudflare/TLS load or Odoo tenant provisioning','successes':sum(x['ok'] for x in results),'elapsed_seconds':round(elapsed,3),'counts':counts,'verified_accounts':verified,'phases':phases,'results':results,'resources':{'process_peak_rss_mib':round(usage_after.ru_maxrss/1024,1),'process_cpu_seconds':round(used_cpu,3),'process_mean_one_core_percent':round(100*used_cpu/elapsed,1),'host_cpu_mean_percent':round(100*(total-idle)/total,1) if total else 0,'host_available_before_mib':round(before_mem['MemAvailable']/1024**2,1),'host_available_min_mib':round(min(samples or [before_mem['MemAvailable']])/1024**2,1)},'health_before':before_health,'health_after':after_health,'native_pid_unchanged':before_pid==after_pid,'real_customer_database_touched':False,'fictitious_state_removed':True,'email_delivery':'captured locally, not sent'}
p=pathlib.Path('/var/lib/uno360x-saas/signup-burst-10-result.json');p.write_text(json.dumps(report,indent=2));print(json.dumps(report))


if report['successes'] != N:raise SystemExit(1)
