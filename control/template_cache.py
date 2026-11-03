"""Versioned pristine installation cache. Contains no tenant identity or credentials."""
import hashlib,json,pathlib,os,tarfile,re
RECIPE=1
CACHE=pathlib.Path('/var/lib/uno360x-saas/templates')

def cache_key(profile,images):
 return hashlib.sha256(json.dumps({'recipe':RECIPE,'fingerprint':profile['fingerprint'],'images':images},sort_keys=True).encode()).hexdigest()
def checksum(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def verified_cache(profile,images,base=CACHE):
 base=pathlib.Path(base);key=cache_key(profile,images);directory=base/'ready'/key
 if not directory.exists():return None
 if base.is_symlink() or directory.is_symlink() or directory.stat().st_uid!=os.geteuid():raise RuntimeError('Unowned template cache')
 p=directory/'manifest.json'
 if p.is_symlink():raise RuntimeError('Unexpected template manifest')
 meta=json.loads(p.read_text())
 if meta.get('key')!=key or meta.get('recipe')!=RECIPE or meta.get('fingerprint')!=profile['fingerprint'] or meta.get('images')!=images or meta.get('pristine') is not True:raise RuntimeError('Invalid template manifest')
 for name in ('database.dump','files.tar'):
  p=directory/name
  if p.is_symlink() or not p.is_file() or checksum(p)!=meta['sha256'].get(name):raise RuntimeError('Corrupt template cache')
 with tarfile.open(directory/'files.tar') as archive:
  for m in archive.getmembers():
   path=pathlib.PurePosixPath(m.name)
   if path.is_absolute() or '..' in path.parts or not (m.isfile() or m.isdir()):raise RuntimeError('Unsafe template archive')
 return directory

def custom_addons(profile,root):
 import ast
 wanted=set(profile['addons']);pending=list(wanted)
 while pending:
  name=pending.pop();meta=ast.literal_eval((pathlib.Path(root)/'addons'/name/'__manifest__.py').read_text())
  for dependency in meta.get('depends',[]):
   if dependency.startswith('uno360x_') and dependency not in wanted:wanted.add(dependency);pending.append(dependency)
 return sorted(wanted)
