"""Versioned installation catalog; planning only, never changes a running tenant."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def installation_profile(modules, root=ROOT):
    catalog=json.loads((root/'product/catalog.json').read_text(encoding='utf-8'))
    selected=set(modules)
    optional=set(catalog['options'])
    if not selected <= optional | {'business_base','electronic_invoicing'}:
        raise ValueError('Capacidad de producto desconocida.')
    addons=set(catalog['base'])
    for name in selected & optional:
        addons.update(catalog['options'][name])
    versions={}
    for addon in sorted(addons):
        manifest=ast.literal_eval((root/'addons'/addon/'__manifest__.py').read_text(encoding='utf-8'))
        if not manifest.get('installable'):
            raise ValueError('Paquete no instalable.')
        tree=hashlib.sha256()
        for file in sorted((root/'addons'/addon).rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix in {'.py','.xml','.js','.csv','.xsd','.css','.scss','.svg'}:
                tree.update(file.relative_to(root/'addons'/addon).as_posix().encode())
                tree.update(b'\0')
                # Git may normalize LF/CRLF across Windows and Linux.
                tree.update(file.read_bytes().replace(b'\r\n',b'\n'))
                tree.update(b'\0')
        versions[addon]={'version':manifest['version'],'source_sha256':tree.hexdigest()}
    encoded=json.dumps({'catalog':catalog,'versions':versions},sort_keys=True).encode()
    return {'release':catalog['release'],'odoo_series':catalog['odoo_series'],
            'addons':versions,'fingerprint':hashlib.sha256(encoded).hexdigest(),
            'gates':catalog['gates'],'production_deployment':False}


def addon_update_args(previous, target):
    old, new = previous['addons'], target['addons']
    if old.keys() - new.keys():
        raise ValueError('An addon removal requires a reviewed migration.')
    install = sorted(new.keys() - old.keys())
    update = sorted(name for name in old if old[name] != new[name])
    return [*(['-i', ','.join(install)] if install else []),
            *(['-u', ','.join(update)] if update else [])]
