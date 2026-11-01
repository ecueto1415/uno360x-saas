"""Read-only prelaunch endpoint. No accounts, passwords, provisioning or mail."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
PAGE=b'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>UNO360X</title><style>body{font:18px Arial,sans-serif;background:#f2f6f7;color:#1b3546;margin:0;padding:12vh 8vw}main{max-width:650px;margin:auto}h1{color:#12877c}a{color:#12877c}</style><main><h1>UNO360X</h1><h2>Estamos preparando tu espacio.</h2><p>El registro de la prueba gratis estar&aacute; disponible pr&oacute;ximamente.</p><p><a href="/prueba-saas">Ver el recorrido de prueba</a> &middot; <a href="/">Volver al inicio</a></p></main></html>'''
def public_signup_enabled():
 try:return json.loads(Path('/etc/uno360x-saas/https-pilot.json').read_text()).get('public_signup') is True
 except (OSError,ValueError):return False

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,body,kind):
  self.send_response(status)
  for k,v in [('Content-Type',kind),('Content-Length',str(len(body))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY'),('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")]:self.send_header(k,v)
  self.end_headers()
  if self.command!='HEAD':self.wfile.write(body)
 def do_GET(self):
  if self.path in ['/estado','/health']:
   self.reply(200,json.dumps({'status':'available' if public_signup_enabled() else 'preparing','signup_enabled':public_signup_enabled()}).encode(),'application/json');return
  if self.path=='/':self.reply(200,PAGE,'text/html; charset=utf-8');return
  self.reply(404,b'Not found','text/plain')
 def do_POST(self):self.reply(503,b'Registro no habilitado.','text/plain; charset=utf-8');self.close_connection=True
 do_HEAD=do_GET
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',18082),Handler).serve_forever()
