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
 def __init__(self,state,owner,clock=time.time):
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
   secret=self.cipher.decrypt(row['secret']).decode() if row['secret'] else base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
   self.db.execute('UPDATE enrollment SET secret=? WHERE digest=?',(self.cipher.encrypt(secret.encode()),digest(token)))
  return {'email':self.owner,'secret':secret}
 def finish_enrollment(self,token,password,code,agent,ip):
  self.allow('activate-finish:'+ip)
  encoded=password_hash(password)
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   row=self.db.execute('SELECT * FROM enrollment WHERE digest=? AND used=0 AND expires>?',(digest(token),self.clock())).fetchone()
   if not row or not row['secret'] or self.db.execute('SELECT 1 FROM owner').fetchone():raise Denied('Enlace inválido o vencido.')
   secret=self.cipher.decrypt(row['secret']).decode();counter=self.valid_counter(secret,code,-1)
   self.db.execute('INSERT INTO owner VALUES (?,?,?,?)',(self.owner,encoded,row['secret'],counter));self.db.execute('UPDATE enrollment SET used=1,secret=NULL')
   codes=[secrets.token_hex(6) for _ in range(8)]
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
   self.db.execute('DELETE FROM challenges WHERE expires<=?',(self.clock(),));self.db.execute('INSERT INTO challenges VALUES (?,?,?)',(digest(token),self.clock()+300,digest(agent)));self.audit('password_verified')
  return token
 def mfa(self,challenge,code,agent,ip):
  self.allow('mfa:'+ip)
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
  return {'email':self.owner,'role':'owner','csrf_token':csrf(token)}
 def logout(self,token):
  with self.db:self.db.execute('DELETE FROM sessions WHERE digest=?',(digest(token),));self.audit('logout')
