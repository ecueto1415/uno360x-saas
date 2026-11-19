"""Serve reviewed direct assets keyed by the installed addon revision."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ASSET_STATE = Path('/etc/uno360x-saas/visual-assets')
ASSET_TYPES = {
    '.css': 'text/css; charset=utf-8', '.png': 'image/png',
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
    '.webp': 'image/webp', '.avif': 'image/avif', '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
}
MAX_ASSET = 8 * 1024 * 1024
ASSET_ROUTE = re.compile(r'/(uno360x_[a-z0-9_]+)/static/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)')
DIGEST = re.compile('[a-f0-9]{64}')


def visual_asset(path, snapshot, state=None):
    route = urlsplit(path).path
    match = ASSET_ROUTE.fullmatch(route)
    mime = ASSET_TYPES.get(Path(route).suffix)
    if not match or not mime or any(part in ('.', '..') for part in match[2].split('/')):
        return None
    addon = match[1]
    revision = snapshot.get('installation', {}).get('addons', {}).get(addon, {}).get('source_sha256', '')
    if not DIGEST.fullmatch(revision):
        return None
    if addon == 'uno360x_ecf_core':
        # Do not mask customer-specific fiscal graphics.
        return None
    state = state or ASSET_STATE
    try:
        manifest = json.loads((state / 'current.json').read_text(encoding='utf-8'))
        digest = manifest[addon][revision][route]
        if not DIGEST.fullmatch(digest):
            return None
        with (state / 'files' / digest).open('rb') as asset:
            content = asset.read(MAX_ASSET + 1)
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if len(content) > MAX_ASSET:
        return None
    headers = [('Content-Type', mime)]
    if mime == 'image/svg+xml':
        headers.append(('Content-Security-Policy', "sandbox; default-src 'none'; style-src 'unsafe-inline'"))
    return 200, headers, content
