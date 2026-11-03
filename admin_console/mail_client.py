"""Local Unix transport; SMTP secrets remain outside the admin account."""
import socket,json

def send_code(code):
 if not isinstance(code,str) or len(code)!=6 or not code.isdigit():raise ValueError('Invalid code')
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
  client.settimeout(25);client.connect('/run/uno360x-admin-mail/send.sock');client.sendall(json.dumps({'code':code}).encode()+b'\n');reply=client.recv(128)
  if reply!=b'accepted\n':raise RuntimeError('Mail unavailable')
