"""Private broker adapter. Tenant HTTP is published to host loopback only."""
import json
from deployment.shared_adapter import SharedHostAdapter
from deployment.https_pilot import checked_origin
class PilotAdapter(SharedHostAdapter):
 def backend(self,s):
  n=self.names(s);self.check_container(n['app'],s)
  proxy=n['prefix']+'-proxy'
  if not self.exists('container',proxy):
   self.run('run','-d','--name',proxy,'--network',n['network'],*self.label_args(s),
    '--cpus','0.1','--memory','64m','--pids-limit','48','--read-only','--cap-drop','all',
    '--security-opt','no-new-privileges','-p','127.0.0.1:18190:18069',
    '-v',str(self.root/'deployment'/'tenant_socket_proxy.py')+':/proxy.py:ro',
    '--entrypoint','python3',self.images['odoo:18.0'],'/proxy.py',n['app'])
  info=self.inspect(proxy)
  if not all(info['Config']['Labels'].get(k)==v for k,v in self.labels(s).items()):raise RuntimeError('Foreign proxy')
  if info['Image'].removeprefix('sha256:')!=self.images['odoo:18.0'].removeprefix('sha256:'):raise RuntimeError('Unexpected proxy image')
  if set(info['NetworkSettings']['Networks'])!={n['network']}:raise RuntimeError('Unexpected proxy network')
  ports=info['HostConfig']['PortBindings']
  if ports!={'18069/tcp':[{'HostIp':'127.0.0.1','HostPort':'18190'}]}:raise RuntimeError('Unexpected proxy publication')
  if not info['State']['Running']:self.run('start',proxy)
  return 'http://127.0.0.1:18190'
 def configure_company(self,s,profile,origin):
  checked_origin(origin)
  super().configure_company(s,profile,'http://127.0.0.1:18184')
  self.shell(s,"env['ir.config_parameter'].sudo().set_param('web.base.url',%r);env.cr.commit();print('UNO360X_OK')"%origin)
