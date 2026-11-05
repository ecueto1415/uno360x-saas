import concurrent.futures,threading,unittest,urllib.request
from http.server import BaseHTTPRequestHandler
from deployment.https_pilot import HTTPSIdentityServer,BoundedHTTPServer

class ParallelEntryCapacityTests(unittest.TestCase):
 def test_ten_slow_entries_leave_capacity_for_progress_and_health(self):
  gate=threading.Event();ten=threading.Event();lock=threading.Lock();state={'started':0}
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    with lock:
     state['started']+=1
     if state['started']==10:ten.set()
    gate.wait(5);self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
   def do_GET(self):self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
  server=object.__new__(HTTPSIdentityServer);BoundedHTTPServer.__init__(server,('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(server.server_port)
  def enter(_):
   with urllib.request.urlopen(urllib.request.Request(url,data=b'{}'),timeout=8) as r:return r.status
  try:
   with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures=[executor.submit(enter,i) for i in range(10)]
    try:
     self.assertTrue(ten.wait(3))
     with urllib.request.urlopen(url,timeout=2) as r:self.assertEqual(r.status,200)
    finally:gate.set()
    self.assertTrue(all(f.result()==200 for f in futures))
  finally:gate.set();server.shutdown();server.server_close();thread.join(2)
