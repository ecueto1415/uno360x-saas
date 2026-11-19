"""Publish direct CSS and images without changing module or database versions."""
import argparse
import ast
from collections import Counter
import fcntl
from fnmatch import fnmatchcase
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from tempfile import NamedTemporaryFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from control.catalog import installation_profile
from control.visual_assets import ASSET_ROUTE, ASSET_STATE, ASSET_TYPES, MAX_ASSET

BASE = Path('/srv/uno360x-saas')
CONTROL = Path('/var/lib/uno360x-saas/control/control.sqlite3')
LOCK = Path('/run/lock/uno360x-saas-release.lock')


def tree(root):
    result = {}
    for directory in ('addons', 'product', 'control', 'deployment', 'tenant-addon-overrides'):
        for path in (root / directory).rglob('*'):
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            if path.is_symlink():
                raise ValueError('Symlink in release: ' + str(path.relative_to(root)))
            if path.is_file():
                with path.open('rb') as handle:
                    result[path.relative_to(root).as_posix()] = hashlib.file_digest(handle, 'sha256').hexdigest()
    return result


def bundle_patterns(root):
    patterns = []
    for path in (root / 'addons').glob('*/__manifest__.py'):
        meta = ast.literal_eval(path.read_text(encoding='utf-8'))
        for assets in meta.get('assets', {}).values():
            for entry in assets:
                parts = (entry,) if isinstance(entry, str) else entry
                patterns.extend(p for p in parts if isinstance(p, str) and '/static/' in p)
    return patterns


def direct_changes(previous, candidate):
    old, new = tree(previous), tree(candidate)
    changes = {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}
    patterns = bundle_patterns(candidate)
    result = {}
    for name in sorted(changes):
        route = '/' + name.removeprefix('addons/')
        match = ASSET_ROUTE.fullmatch(route)
        if (not name.startswith('addons/') or not match or match[1] == 'uno360x_ecf_core'
                or Path(name).suffix not in ASSET_TYPES or name not in new
                or any(fnmatchcase(route[1:], pattern.lstrip('/')) for pattern in patterns)):
            raise ValueError('Este cambio requiere el despliegue normal: ' + name)
        path = candidate / name
        if path.stat().st_size > MAX_ASSET:
            raise ValueError('Archivo demasiado grande: ' + name)
        result[route] = (match[1], path, new[name])
    return result


def atomic_bytes(path, data):
    with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o644)
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def run(candidate, apply, clear):
    previous = (BASE / 'master-current').resolve()
    changes = {} if clear else direct_changes(previous, candidate)
    if not changes and not clear:
        raise ValueError('La versión candidata no contiene cambios visuales.')
    catalog = json.loads((previous / 'product/catalog.json').read_text(encoding='utf-8'))
    options = sorted(catalog['options'])
    profiles = [installation_profile(combo, previous) for n in range(len(options) + 1)
                for combo in itertools.combinations(options, n)]
    revisions = {addon: {p['addons'][addon]['source_sha256'] for p in profiles if addon in p['addons']}
                 for addon, _, _ in changes.values()}
    existing_file = ASSET_STATE / 'current.json'
    current = json.loads(existing_file.read_text(encoding='utf-8')) if existing_file.exists() else {}
    target = {} if clear else json.loads(json.dumps(current))
    for route, (addon, _, digest) in changes.items():
        if not revisions[addon]:
            raise ValueError('Módulo fuera del catálogo SaaS: ' + addon)
        for revision in revisions[addon]:
            target.setdefault(addon, {}).setdefault(revision, {})[route] = digest
    affected = {addon for addon in current.keys() | target.keys() if current.get(addon) != target.get(addon)}
    with sqlite3.connect(CONTROL.as_uri() + '?mode=ro', uri=True) as db:
        snapshots = db.execute("SELECT snapshot FROM preparation_jobs WHERE status='ready_local'")
        tenant_count = 0
        for (snapshot,) in snapshots:
            installed = json.loads(snapshot)['installation']['addons']
            if any(installed.get(addon, {}).get('source_sha256') in
                   (current.get(addon, {}).keys() | target.get(addon, {}).keys())
                   for addon in affected):
                tenant_count += 1
    if apply:
        ASSET_STATE.mkdir(mode=0o755, exist_ok=True)
        (ASSET_STATE / 'files').mkdir(mode=0o755, exist_ok=True)
        for _, path, digest in changes.values():
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise RuntimeError('La versión candidata cambió durante la publicación.')
            atomic_bytes(ASSET_STATE / 'files' / digest, content)
        atomic_bytes(existing_file, json.dumps(target, sort_keys=True).encode())
    return {'published': apply, 'assets': len(changes), 'addons': sorted(affected),
            'profiles_affected': sum(bool(affected.intersection(p['addons'])) for p in profiles),
            'tenants_affected': tenant_count, 'templates_rebuilt': 0}


def carry_forward(previous, candidate):
    """Keep published direct assets across a change to another file in their addon."""
    manifest_file = ASSET_STATE / 'current.json'
    if not manifest_file.is_file():
        return
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    options = sorted(json.loads((candidate / 'product/catalog.json').read_text())['options'])
    for size in range(len(options) + 1):
        for combo in itertools.combinations(options, size):
            try:
                old = installation_profile(combo, previous)['addons']
                new = installation_profile(combo, candidate)['addons']
            except ValueError:
                continue
            for addon in old.keys() & new.keys() & manifest.keys():
                prior_revision = old[addon]['source_sha256']
                next_revision = new[addon]['source_sha256']
                if prior_revision == next_revision:
                    continue
                for route, digest in manifest[addon].get(prior_revision, {}).items():
                    relative = 'addons' + route
                    before, after = previous / relative, candidate / relative
                    if (before.is_file() and after.is_file() and before.read_bytes() == after.read_bytes()) or (
                            not before.exists() and not after.exists()):
                        manifest[addon].setdefault(next_revision, {})[route] = digest
    atomic_bytes(manifest_file, json.dumps(manifest, sort_keys=True).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--candidate', type=Path)
    target.add_argument('--clear', action='store_true', help='Restore the assets from the installed releases.')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    candidate = args.candidate.resolve() if args.candidate else None
    if candidate and (not candidate.is_relative_to(BASE / 'releases') or candidate.name != 'source'):
        parser.error('Usa el directorio source de una versión candidata.')
    if args.apply:
        if os.geteuid() != 0:
            parser.error('La publicación requiere el coordinador SaaS.')
        with LOCK.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = run(candidate, True, args.clear)
    else:
        result = run(candidate, False, args.clear)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
