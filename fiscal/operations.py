"""Root-only local backup and restore verification; no signing credentials copied."""
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone

STATE = pathlib.Path('/var/lib/uno360x-dgii-production')
BACKUPS = pathlib.Path('/var/backups/uno360x-dgii-production')


def backup(state=STATE, backups=BACKUPS):
    state, backups = pathlib.Path(state), pathlib.Path(backups)
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    archive = backups/(stamp+'.tar.gz')
    with tempfile.TemporaryDirectory(prefix='fiscal-backup-') as directory:
        snapshot = pathlib.Path(directory)/'inbox.sqlite3'
        with sqlite3.connect('file:'+str(state/'inbox.sqlite3')+'?mode=ro', uri=True) as source:
            with sqlite3.connect(snapshot) as target:
                source.backup(target)
        with sqlite3.connect(snapshot) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            digests = [r[0] for r in db.execute('SELECT sha256 FROM messages')]
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(snapshot, arcname='inbox.sqlite3')
            for digest in digests:
                path = state/(digest+'.xml')
                assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
                tar.add(path, arcname=path.name)
    archive.chmod(0o600)
    result = restore_check(archive)
    for old in sorted(backups.glob('*.tar.gz'), reverse=True)[30:]:
        old.unlink()  # Only our rolling backup copies; never fiscal originals.
    return {'archive': archive.name, **result}


def restore_check(archive):
    with tempfile.TemporaryDirectory(prefix='fiscal-restore-check-') as directory:
        target = pathlib.Path(directory)
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar:
                assert member.isfile() and pathlib.PurePosixPath(member.name).name == member.name
                (target/member.name).write_bytes(tar.extractfile(member).read())
        with sqlite3.connect(target/'inbox.sqlite3') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            digests = [r[0] for r in db.execute('SELECT sha256 FROM messages')]
        for digest in digests:
            assert hashlib.sha256((target/(digest+'.xml')).read_bytes()).hexdigest() == digest
    return {'restore_verified': True, 'documents': len(digests)}


def health():
    with urllib.request.urlopen('http://127.0.0.1:18187/health', timeout=10) as response:
        assert response.status == 200
        result = json.load(response)
    assert result['environment'] == 'production'
    return {'production_health': 'ok'}


if __name__ == '__main__':
    os.umask(0o077)
    print(json.dumps(backup() if sys.argv[1:] == ['backup'] else health()))
