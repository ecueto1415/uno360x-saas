"""SMTP relay dedicated to one admin recipient, authenticated by Unix peer UID.
No public listener, arbitrary recipients, links, subjects or HTML accepted.
"""
import socketserver,socket,struct,pwd,os,json,smtplib,ssl,time,collections
from pathlib import Path
from email.message import EmailMessage
OWNER='ecueto@outsolutech.com'
SOCKET='/run/uno360x-admin-mail/send.sock'
CONFIG=Path('/var/lib/uno360x-saas/control/mail-resend.json')

class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  self.request.settimeout(5)
  _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
  if uid!=pwd.getpwnam('uno360x-admin').pw_uid:return
  try:
   data=json.loads(self.rfile.readline(128));code=data.get('code')
   if set(data)!={'code'} or not isinstance(code,str) or len(code)!=6 or not code.isdigit():raise ValueError()
   now=time.monotonic()
   while self.server.sent and now-self.server.sent[0]>900:self.server.sent.popleft()
   if len(self.server.sent)>=5:raise ValueError()
   self.server.sent.append(now)
   config=json.loads(CONFIG.read_text());assert config['independent_saas_mailbox'] is True
   assert (config['security'],config['port']) in [('ssl',465),('starttls',587)]
   assert config['from_address'].endswith('@uno360x.com')
   message=EmailMessage();message['From']=config['from_address'];message['To']=OWNER;message['Subject']='Tu código de acceso a UNO360X Admin'
   message.set_content('Tu código de verificación es: '+code+'\n\nVence en 10 minutos y solo puede utilizarse una vez.\nSi no solicitaste acceso al panel de administración, ignora este correo.\n\nUNO360X\n')
   ctx=ssl.create_default_context()
   transport=smtplib.SMTP_SSL(config['host'],465,timeout=20,context=ctx) if config['security']=='ssl' else smtplib.SMTP(config['host'],587,timeout=20)
   with transport as client:
    if config['security']=='starttls':client.ehlo();client.starttls(context=ctx);client.ehlo()
    client.login(config['username'],config['password']);client.send_message(message)
   self.wfile.write(b'accepted\n')
  except Exception:self.wfile.write(b'unavailable\n')

if __name__=='__main__':
 os.umask(0o007)
 p=Path(SOCKET)
 if p.exists():p.unlink()
 with socketserver.UnixStreamServer(SOCKET,Handler) as server:
  p.chmod(0o660);server.sent=collections.deque();server.serve_forever()
