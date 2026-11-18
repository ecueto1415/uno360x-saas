"""Versioned, shared billing assets. Contains no tenant or session data."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = {
    'css': ('static/src/css/workspace.css', 'static/src/css/extra.css',
            'static/src/css/reference.css', 'static/src/css/areas.css'),
    'js': ('static/src/js/navigation.js', 'static/src/js/areas.js'),
}


@lru_cache(maxsize=16)
def _bundle(kind, versions):
    separator = b'\n' if kind == 'css' else b';\n'
    content = separator.join((ROOT / name).read_bytes() for name in FILES[kind])
    return sha256(content).hexdigest(), content


def billing_asset(kind):
    paths = [ROOT / name for name in FILES[kind]]
    versions = tuple((path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
    return _bundle(kind, versions)


def billing_asset_urls():
    return {kind: '/uno360x_workspace/billing-assets/%s/%s.%s' %
            (kind, billing_asset(kind)[0], kind) for kind in FILES}
