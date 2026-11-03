"""Isolated owner authentication. No Odoo credentials or tenant memberships."""
import base64,hashlib,hmac,json,secrets,sqlite3,struct,time
from functools import lru_cache
from pathlib import Path
from cryptography.fernet import Fernet

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def password_hash(password):
 if not isinstance(password,str) or not 12<=len(password)<=128:raise ValueError('La contraseña debe tener de 12 a 128 caracteres.')
 salt=secrets.token_hex(16);value=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,dklen=32)
 return 'scrypt$16384$8$1$'+salt+'$'+value.hex()
def password_matches(password,encoded):
 if not isinstance(password,str) or len(password)>128:return False
 try:
  algorithm,n,r,p,salt,expected=encoded.split('$')
  if (algorithm,n,r,p)!=('scrypt','16384','8','1'):return False
  actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,dklen=32).hex()
  return hmac.compare_digest(actual,expected)
 except (ValueError,TypeError):return False
@lru_cache(maxsize=1)
def dummy_password_hash():return password_hash(secrets.token_urlsafe(24))

class Denied(ValueError):pass
class Limited(Denied):pass

def otp(secret,counter):
 key=base64.b32decode(secret+'='*((8-len(secret)%8)%8))
 value=hmac.new(key,struct.pack('>Q',counter),hashlib.sha1).digest();offset=value[-1]&15
 return str((struct.unpack('>I',value[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)

def csrf(token):return hmac.new(token.encode(),b'uno360x-owner-csrf',hashlib.sha256).hexdigest()

class Auth:
 def __init__(self,state,owner,clock=time.time,factor="totp",delivery=None):
  if factor not in ("totp","email"):raise ValueError("Unsupported authentication factor")
  self.factor=factor;self.delivery=delivery
  self.state=Path(state);self.state.mkdir(mode=0o700,parents=True,exist_ok=True);self.owner=owner;self.clock=clock
  key=self.state/'mfa.key'
  if not key.exists():
   import os
   fd=os.open(key,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
   with os.fdopen(fd,'wb') as out:out.write(Fernet.generate_key())
  self.cipher=Fernet(key.read_bytes());self.db=sqlite3.connect(self.state/'auth.sqlite3',timeout=5);self.db.row_factory=sqlite3.Row
  self.db.executescript('''
   PRAGMA journal_mode=WAL;
   CREATE TABLE IF NOT EXISTS owner(email TEXT PRIMARY KEY,password TEXT NOT NULL,secret BLOB NOT NULL,last_counter INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS enrollment(digest TEXT PRIMARY KEY,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0,secret BLOB);
   CREATE TABLE IF NOT EXISTS challenges(digest TEXT PRIMARY KEY,expires REAL NOT NULL,agent TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,expires REAL NOT NULL,last_seen REAL NOT NULL,agent TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS recovery(digest TEXT PRIMARY KEY,used INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS limits(bucket TEXT PRIMARY KEY,started REAL NOT NULL,count INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS email_codes(challenge TEXT PRIMARY KEY,code TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,used INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event TEXT NOT NULL,occurred REAL NOT NULL);
  ''')
  (self.state/'auth.sqlite3').chmod(0o600)
 def close(self):self.db.close()
 def audit(self,event):self.db.execute('INSERT INTO audit(event,occurred) VALUES (?,?)',(event,self.clock()))
 def allow(self,bucket,maximum=5,window=900):
  key=digest(bucket);now=self.clock()
  with self.db:
   self.db.execute('BEGIN IMMEDIATE');r=self.db.execute('SELECT * FROM limits WHERE bucket=?',(key,)).fetchone()
   if not r or now>=r['started']+window:self.db.execute('INSERT OR REPLACE INTO limits VALUES (?,?,1)',(key,now));return
   self.db.execute('UPDATE limits SET count=count+1 WHERE bucket=?',(key,))
   denied=r['count']>=maximum
  if denied:raise Limited('Demasiados intentos. Espera unos minutos.')
 def new_enrollment(self):
  if self.db.execute('SELECT 1 FROM owner').fetchone():raise Denied('El administrador ya está configurado.')
  token=secrets.token_urlsafe(32)
  with self.db:
   self.db.execute('DELETE FROM enrollment');self.db.execute('INSERT INTO enrollment(digest,expires) VALUES (?,?)',(digest(token),self.clock()+86400));self.audit('activation_issued')
  return token
 def start_enrollment(self,token,ip):
  self.allow('activation:'+ip,10)
  if not isinstance(token,str) or len(token)>128:raise Denied('Enlace inválido o vencido.')
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   row=self.db.execute('SELECT * FROM enrollment WHERE digest=? AND used=0 AND expires>?',(digest(token),self.clock())).fetchone()
   if not row or self.db.execute('SELECT 1 FROM owner').fetchone():raise Denied('Enlace inválido o vencido.')
  if self.factor=='email':
   self.issue_email(token,'activation',ip);return {'email':self.owner,'factor':'email','expires_seconds':600}
  with self.db:
   secret=self.cipher.decrypt(row['secret']).decode() if row['secret'] else base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
   self.db.execute('UPDATE enrollment SET secret=? WHERE digest=?',(self.cipher.encrypt(secret.encode()),digest(token)))
  return {'email':self.owner,'secret':secret}
 def finish_enrollment(self,token,password,code,agent,ip):
  self.allow('activate-finish:'+ip)
  encoded=password_hash(password)
  if self.factor=='email':self.check_email(token,'activation',code)
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   row=self.db.execute('SELECT * FROM enrollment WHERE digest=? AND used=0 AND expires>?',(digest(token),self.clock())).fetchone()
   if not row or (self.factor=='totp' and not row['secret']) or self.db.execute('SELECT 1 FROM owner').fetchone():raise Denied('Enlace inválido o vencido.')
   if self.factor=='totp':
    secret=self.cipher.decrypt(row['secret']).decode();counter=self.valid_counter(secret,code,-1);stored_secret=row['secret']
   else:counter=-1;stored_secret=self.cipher.encrypt(b'')
   self.db.execute('INSERT INTO owner VALUES (?,?,?,?)',(self.owner,encoded,stored_secret,counter));self.db.execute('UPDATE enrollment SET used=1,secret=NULL')
   codes=[secrets.token_hex(6) for _ in range(8)] if self.factor=='totp' else []
   self.db.executemany('INSERT INTO recovery(digest) VALUES (?)',[(digest(c),) for c in codes]);session=self.create_session(agent);self.audit('owner_activated')
  return session,codes
 def valid_counter(self,secret,code,last):
  if not isinstance(code,str) or len(code)!=6 or not code.isdigit():raise Denied('Código de verificación inválido.')
  current=int(self.clock()//30)
  for counter in (current,current-1,current+1):
   if counter>last and hmac.compare_digest(otp(secret,counter),code):return counter
  raise Denied('Código incorrecto, vencido o ya utilizado.')
 def login(self,email,password,agent,ip):
  self.allow('login-ip:'+ip,10);self.allow('login-owner',8)
  row=self.db.execute('SELECT * FROM owner WHERE email=?',(self.owner,)).fetchone()
  matched=password_matches(password,row['password'] if row else dummy_password_hash())
  if not row or not matched or not isinstance(email,str) or email.strip().lower()!=self.owner:
   with self.db:self.audit('login_failed')
   raise Denied('Correo o contraseña incorrectos.')
  token=secrets.token_urlsafe(32)
  with self.db:
   self.db.execute('DELETE FROM challenges WHERE expires<=?',(self.clock(),));self.db.execute('INSERT INTO challenges VALUES (?,?,?)',(digest(token),self.clock()+(600 if self.factor=='email' else 300),digest(agent)));self.audit('password_verified')
  if self.factor=='email':self.issue_email(token,'login',ip)
  return token
 def mfa(self,challenge,code,agent,ip):
  self.allow('mfa:'+ip)
  if self.factor=='email':return self.email_session(challenge,code,agent,ip)
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   row=self.db.execute('SELECT * FROM challenges WHERE digest=? AND expires>? AND agent=?',(digest(challenge),self.clock(),digest(agent))).fetchone()
   owner=self.db.execute('SELECT * FROM owner WHERE email=?',(self.owner,)).fetchone()
   if not row or not owner:raise Denied('Vuelve a iniciar sesión.')
   if isinstance(code,str) and len(code)==12:
    recovery=self.db.execute('SELECT * FROM recovery WHERE digest=? AND used=0',(digest(code.strip().lower()),)).fetchone()
    if not recovery:raise Denied('Código de recuperación inválido.')
    self.db.execute('UPDATE recovery SET used=1 WHERE digest=?',(recovery['digest'],));self.db.execute('DELETE FROM sessions');self.audit('recovery_used')
   else:
    secret=self.cipher.decrypt(owner['secret']).decode();counter=self.valid_counter(secret,code,owner['last_counter'])
    self.db.execute('UPDATE owner SET last_counter=? WHERE email=?',(counter,self.owner))
   self.db.execute('DELETE FROM challenges WHERE digest=?',(digest(challenge),));token=self.create_session(agent)
   self.db.execute('DELETE FROM limits WHERE bucket IN (?,?)',(digest('login-owner'),digest('login-ip:'+ip)));self.audit('login_success')
  return token
 def create_session(self,agent):
  token=secrets.token_urlsafe(32);now=self.clock()
  self.db.execute('DELETE FROM sessions WHERE expires<=? OR last_seen<=?',(now,now-1800))
  self.db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(digest(token),now+28800,now,digest(agent)));return token
 def account(self,token,agent,touch=True):
  if not isinstance(token,str) or len(token)>128:raise Denied('Sesión vencida.')
  now=self.clock();row=self.db.execute('SELECT * FROM sessions WHERE digest=? AND expires>? AND last_seen>? AND agent=?',(digest(token),now,now-1800,digest(agent))).fetchone()
  if not row:raise Denied('Sesión vencida.')
  if touch:
   with self.db:self.db.execute('UPDATE sessions SET last_seen=? WHERE digest=?',(now,digest(token)))
  return {'email':self.owner,'role':'owner','csrf_token':csrf(token),'factor':self.factor}
 def logout(self,token):
  with self.db:self.db.execute('DELETE FROM sessions WHERE digest=?',(digest(token),));self.audit('logout')

 def mail_digest(self,challenge,code):
  return hmac.new((self.state/'mfa.key').read_bytes(),(challenge+':'+code).encode(),hashlib.sha256).hexdigest()
 def issue_email(self,token,purpose,ip):
  key=digest(purpose+':'+token);now=self.clock()
  row=self.db.execute('SELECT * FROM email_codes WHERE challenge=?',(key,)).fetchone()
  if row and now-row['created']<60 and row['expires']>now and row['used']==0:return
  self.allow('email-owner',5);self.allow('email-ip:'+ip,5)
  if self.delivery is None:raise RuntimeError('Mail transport unavailable')
  code=str(secrets.randbelow(1000000)).zfill(6);hashed=self.mail_digest(key,code)
  with self.db:
   self.db.execute('DELETE FROM email_codes WHERE expires<?',(now-86400,))
   self.db.execute('INSERT OR REPLACE INTO email_codes VALUES (?,?,?,?,0,0)',(key,hashed,now,now+600))
  try:self.delivery(code)
  except Exception:
   with self.db:self.db.execute('DELETE FROM email_codes WHERE challenge=? AND code=?',(key,hashed));self.audit('email_delivery_failed')
   raise RuntimeError('No pudimos enviar el código. Vuelve a intentarlo en unos minutos.') from None
  with self.db:self.audit('email_code_sent')
 def check_email(self,token,purpose,code):
  key=digest(purpose+':'+token);accepted=False
  with self.db:
   self.db.execute('BEGIN IMMEDIATE');row=self.db.execute('SELECT * FROM email_codes WHERE challenge=?',(key,)).fetchone()
   if row and row['expires']>self.clock() and row['attempts']<5 and not row['used']:
    accepted=isinstance(code,str) and len(code)==6 and code.isdigit() and hmac.compare_digest(row['code'],self.mail_digest(key,code))
    self.db.execute('UPDATE email_codes SET attempts=attempts+1,used=? WHERE challenge=?',(int(accepted),key))
  if not accepted:raise Denied('Código incorrecto, vencido o ya utilizado. Solicita uno nuevo.')
 def email_session(self,challenge,code,agent,ip):
  row=self.db.execute('SELECT * FROM challenges WHERE digest=? AND expires>? AND agent=?',(digest(challenge),self.clock(),digest(agent))).fetchone()
  if not row:raise Denied('Vuelve a iniciar sesión.')
  self.check_email(challenge,'login',code)
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   row=self.db.execute('SELECT * FROM challenges WHERE digest=? AND expires>? AND agent=?',(digest(challenge),self.clock(),digest(agent))).fetchone()
   if not row:raise Denied('Vuelve a iniciar sesión.')
   self.db.execute('DELETE FROM challenges WHERE digest=?',(digest(challenge),));token=self.create_session(agent)
   self.db.execute('DELETE FROM limits WHERE bucket IN (?,?)',(digest('login-owner'),digest('login-ip:'+ip)));self.audit('login_success')
  return token
 def resend_email(self,challenge,agent,ip):
  if self.factor!='email':raise Denied('Solicitud no disponible.')
  row=self.db.execute('SELECT * FROM challenges WHERE digest=? AND expires>? AND agent=?',(digest(challenge),self.clock(),digest(agent))).fetchone()
  if not row:raise Denied('Vuelve a iniciar sesión.')
  self.issue_email(challenge,'login',ip)
