"""Length-limited JSON over a private Unix socket; never pickle or TCP."""
import json
from multiprocessing.connection import Client
from pathlib import Path

from .identity import IdentityError

SOCKET = Path('/var/lib/uno360x-saas-dev/control/gateway.sock')


def launch_local(session, ticket):
    try:
        with Client(str(SOCKET), family='AF_UNIX') as connection:
            connection.send_bytes(json.dumps({'session': session, 'ticket': ticket}).encode())
            if not connection.poll(120):
                raise IdentityError('El acceso local no respondió.')
            result = json.loads(connection.recv_bytes(4096))
        if 'error' in result:
            raise IdentityError('El acceso local no está disponible.')
        return result
    except (OSError,EOFError,ValueError):
        raise IdentityError('Inicia el broker de acceso local.') from None
