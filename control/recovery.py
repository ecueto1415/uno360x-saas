"""Authenticated backup envelope and safe volume archive inspection."""
import hashlib
import copy
import io
import json
from pathlib import PurePosixPath
import secrets
import struct
import tarfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC=b'UNO360X-BACKUP-1\0'
LIMIT=128*1024*1024

def seal(payload,metadata,key):
    if len(key)!=32 or len(payload)>LIMIT:raise ValueError('Tamaño de respaldo inválido.')
    header=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    if len(header)>4096:raise ValueError('Metadatos inválidos.')
    nonce=secrets.token_bytes(12)
    return MAGIC+struct.pack('>I',len(header))+header+nonce+AESGCM(key).encrypt(nonce,payload,header)

def unseal(envelope,key,expected_tenant):
    if len(envelope)>LIMIT+8192 or not envelope.startswith(MAGIC):raise ValueError('Respaldo inválido.')
    try:
        size=struct.unpack('>I',envelope[len(MAGIC):len(MAGIC)+4])[0]
        if not 1<=size<=4096:raise ValueError()
        start=len(MAGIC)+4;header=envelope[start:start+size]
        metadata=json.loads(header)
        if metadata.get('tenant_id')!=expected_tenant or metadata.get('version')!=1:raise ValueError()
        nonce=envelope[start+size:start+size+12]
        payload=AESGCM(key).decrypt(nonce,envelope[start+size+12:],header)
        return metadata,payload
    except Exception:raise ValueError('No se pudo autenticar el respaldo para esta empresa.') from None

def safe_volume(tar_bytes):
    """Return a session-free tar and hashes, refusing links/devices/traversal."""
    if len(tar_bytes)>LIMIT:raise ValueError('Archivo demasiado grande.')
    output=io.BytesIO();hashes={};seen=set();expanded=0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes),mode='r:*') as source,tarfile.open(fileobj=output,mode='w') as target:
        for member in source:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError('Entrada de respaldo no permitida.')
            name=str(path)
            if name in seen:raise ValueError('Entrada duplicada.')
            seen.add(name)
            if path.parts and path.parts[0]=='sessions':continue
            safe=copy.copy(member)
            safe.mode &= 0o777
            safe.pax_headers={k:v for k,v in member.pax_headers.items() if k in ('mtime','atime','ctime')}
            if member.isfile():
                expanded+=member.size
                if expanded>LIMIT:raise ValueError('Contenido expandido demasiado grande.')
                data=source.extractfile(member).read()
                hashes[name]=hashlib.sha256(data).hexdigest()
                target.addfile(safe,io.BytesIO(data))
            else:target.addfile(safe)
    return output.getvalue(),hashes
