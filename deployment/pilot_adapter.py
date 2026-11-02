"""Private broker adapter. Tenant HTTP is published to host loopback only."""
import json,socket,time,urllib.request,urllib.error
from deployment.shared_adapter import SharedHostAdapter
from deployment.https_pilot import checked_origin
class PilotAdapter(SharedHostAdapter):
 def wait_backend(self,port):
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  base='http://127.0.0.1:'+str(port)
  for _ in range(30):
   try:
    with opener.open(base+'/web/login',timeout=2) as response:
     if response.status==200:return base
   except (OSError,urllib.error.URLError):pass
   time.sleep(0.2)
  raise RuntimeError('Private application proxy is not ready')
 def access_backend(self,s):
  # One fresh metadata snapshot per entry; no cross-request inspection cache.
  # The same ownership/image/network/port checks below still inspect every item.
  n=self.names(s);expected={n['app'],n['database'],n['prefix']+'-proxy'}
  result=self.run('inspect',*sorted(expected),check=False);inspected=None
  if result.returncode==0:
   try:
    items=json.loads(result.stdout)
    if isinstance(items,list) and len(items)==3:
     found={item['Name'].lstrip('/'):item for item in items}
     if set(found)==expected:inspected=found
   except (ValueError,KeyError,TypeError,AttributeError):pass
  self.validate_runtime(s,inspected=inspected)
  return self.backend(s,inspected=inspected)
 def backend(self,s,inspected=None):
  import fcntl
  with (self.state/'proxy-ports.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   return self._backend_locked(s,inspected)
 def _backend_locked(self,s,inspected=None):
  inspected=inspected or {}
  n=self.names(s);self.check_container(n['app'],s,info=inspected.get(n['app']))
  proxy=n['prefix']+'-proxy'
  port_file=n['directory']/'proxy-port'
  if port_file.is_symlink():raise RuntimeError('Unexpected proxy state')
  if port_file.exists():port=int(port_file.read_text())
  elif proxy in inspected or self.exists('container',proxy):
   info=inspected.get(proxy) or self.inspect(proxy)
   if not all(info['Config']['Labels'].get(k)==v for k,v in self.labels(s).items()):raise RuntimeError('Foreign proxy')
   binding=info['HostConfig']['PortBindings'].get('18069/tcp',[])
   if len(binding)!=1 or binding[0]['HostIp']!='127.0.0.1':raise RuntimeError('Invalid proxy publication')
   port=int(binding[0]['HostPort']);self.protected(port_file,str(port))
  else:
   port=None
   for candidate in range(18190,18230):
    probe=socket.socket()
    try:probe.bind(('127.0.0.1',candidate));port=candidate;break
    except OSError:pass
    finally:probe.close()
   if port is None:raise RuntimeError('No loopback proxy slot')
   self.protected(port_file,str(port))
  if not 18190<=port<18230:raise RuntimeError('Invalid private proxy port')
  if proxy not in inspected and not self.exists('container',proxy):
   self.run('run','-d','--name',proxy,'--network',n['network'],*self.label_args(s),
    '--cpus','0.1','--memory','32m','--pids-limit','48','--read-only','--cap-drop','all',
    '--security-opt','no-new-privileges','-p','127.0.0.1:%s:18069'%port,
    '-v',str(self.root/'deployment'/'tenant_socket_proxy.py')+':/proxy.py:ro',
    '--entrypoint','python3',self.images['odoo:18.0'],'/proxy.py',n['app'])
  info=inspected.get(proxy) or self.inspect(proxy)
  if not all(info['Config']['Labels'].get(k)==v for k,v in self.labels(s).items()):raise RuntimeError('Foreign proxy')
  if info['Image'].removeprefix('sha256:')!=self.images['odoo:18.0'].removeprefix('sha256:'):raise RuntimeError('Unexpected proxy image')
  if set(info['NetworkSettings']['Networks'])!={n['network']}:raise RuntimeError('Unexpected proxy network')
  ports=info['HostConfig']['PortBindings']
  if ports!={'18069/tcp':[{'HostIp':'127.0.0.1','HostPort':str(port)}]}:raise RuntimeError('Unexpected proxy publication')
  if not info['State']['Running']:self.run('start',proxy)
  return self.wait_backend(port)
 def configure_company(self,s,profile,origin):
  checked_origin(origin)
  super().configure_company(s,profile,'http://127.0.0.1:18184')
  self.shell(s,"env['ir.config_parameter'].sudo().set_param('web.base.url',%r);env.cr.commit();print('UNO360X_OK')"%origin)
