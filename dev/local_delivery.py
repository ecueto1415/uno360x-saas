"""Private lab mailbox on the local filesystem, never an HTTP inbox or SMTP."""
import hashlib
import json
import os
from pathlib import Path


class LocalMailbox:
    def __init__(self, directory, port=18072):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.port = port

    def __call__(self, notification):
        notice = dict(notification)
        route = {'verify': '/prueba/confirmar', 'reset': '/prueba/restablecer'}.get(notice['purpose'])
        if route:
            notice['local_url'] = f'http://127.0.0.1:{self.port}{route}#token={notice["token"]}'
        name = hashlib.sha256((notice['purpose'] + ':' + notice['email']).encode()).hexdigest() + '.json'
        # Open no-follow with 0600; never follow an unexpected file reference.
        fd = os.open(self.directory / name, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(notice, handle)
