"""Root task: read only active native login identifiers, never password hashes."""
import hashlib,json,os,pathlib,pwd,subprocess,time
directory=pathlib.Path('/var/lib/uno360x-saas/operational-directory.json')
rows=subprocess.check_output(['runuser','-u','postgres','--','psql','-d','Outsolutech_prueba','-Atc',
    'BEGIN READ ONLY; SELECT lower(trim(login)) FROM res_users WHERE active AND login IS NOT NULL; COMMIT;'],text=True)
logins=[hashlib.sha256(s.encode()).hexdigest() for s in rows.splitlines() if '@' in s]
temporary=directory.with_suffix('.tmp')
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o640)
with os.fdopen(fd,'w') as target:
    json.dump({'updated':time.time(),'logins':logins},target)
os.chown(temporary,0,pwd.getpwnam('uno360x-saas').pw_gid)
os.chmod(temporary,0o640)
os.replace(temporary,directory)
