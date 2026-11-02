"""A normal web-client burst must not evict its menu request or starve login."""
import concurrent.futures,threading,time,unittest,urllib.request
from http.server import BaseHTTPRequestHandler
from deployment.https_pilot import BoundedHTTPServer

class BurstTests(unittest.TestCase):
 def test_browser_asset_burst_and_identity_have_independent_capacity(self):
  entered=0;lock=threading.Lock();ready=threading.Event();release=threading.Event()
  class Slow(BaseHTTPRequestHandler):
   def do_GET(self):
    nonlocal entered
    with lock:
     entered+=1
     if entered==10:ready.set()
    release.wait(5);self.send_response(200);self.end_headers();self.wfile.write(b'ok')
   def log_message(self,*a):pass
  class Fast(Slow):
   def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'ok')
  app=BoundedHTTPServer(('127.0.0.1',0),Slow);identity=BoundedHTTPServer(('127.0.0.1',0),Fast)
  for server in (app,identity):threading.Thread(target=server.serve_forever,daemon=True).start()
  def get(server):
   with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port),timeout=8) as response:return response.status
  try:
   with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    requests=[pool.submit(get,app) for _ in range(10)]
    self.assertTrue(ready.wait(4),'normal browser request burst was rejected')
    self.assertEqual(get(identity),200)
    release.set();self.assertEqual([f.result() for f in requests],[200]*10)
  finally:
   release.set()
   for server in (app,identity):server.shutdown();server.server_close()
