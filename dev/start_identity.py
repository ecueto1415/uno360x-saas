"""Start approved local UI/API; private filesystem mailbox, never real SMTP."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from control.identity import IdentityService
from control.identity_http import IdentityHTTPServer
from control_state import control_database
from local_delivery import LocalMailbox
from control.gateway_ipc import launch_local


if __name__=='__main__':
    if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
        raise SystemExit('Solo root dentro del WSL de laboratorio.')
    os.umask(0o077)
    path=control_database()
    mailbox=LocalMailbox(path.parent/'mailbox')
    service=IdentityService(path,mailbox);service.close()
    server=IdentityHTTPServer(18072,path,mailbox,launch=launch_local)
    print('Diseño local: http://127.0.0.1:18072/',flush=True)
    print('Sin correo real. Enlaces en buzón Linux privado; nunca se imprimen tokens.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
