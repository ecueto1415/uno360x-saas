"""Start loopback-only account API; notifications stay in volatile lab memory."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from control.identity import IdentityService
from control.identity_http import IdentityHTTPServer


if __name__=='__main__':
    if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo root dentro del WSL de laboratorio.')
    state=Path('/var/lib/uno360x-saas-dev/identity')
    state.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(state,0o700)
    os.umask(0o077)
    mailbox=[]
    path=state/'identity.sqlite3'
    service=IdentityService(path,mailbox.append);service.close()
    server=IdentityHTTPServer(18072,path,mailbox.append)
    print('API local: http://127.0.0.1:18072/health',flush=True)
    print('Sin UI ni correo real. Las notificaciones viven solo en memoria; no se imprimen tokens.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();mailbox.clear()
