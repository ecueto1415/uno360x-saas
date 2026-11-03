"""Fixed TCP tunnel inside an isolated tenant network; no HTTP credentials logged."""
import re,select,socket,socketserver,sys
TARGET=sys.argv[1]
if not re.fullmatch(r'uno360x-(?:pilot|bench)-[a-f0-9]{32}-app',TARGET):raise ValueError('Invalid target')
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  upstream=None
  try:
   upstream=socket.create_connection((TARGET,8069),timeout=10)
   self.request.settimeout(30);upstream.settimeout(30)
   while True:
    ready,_,_=select.select([self.request,upstream],[],[],60)
    if not ready:return
    for source in ready:
     data=source.recv(65536)
     if not data:return
     (upstream if source is self.request else self.request).sendall(data)
  except OSError:pass
  finally:
   if upstream:upstream.close()
class Server(socketserver.ThreadingTCPServer):
 allow_reuse_address=True
 daemon_threads=True
Server(('0.0.0.0',18069),Handler).serve_forever()
