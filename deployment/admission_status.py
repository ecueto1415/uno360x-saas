"""Worker-owned readiness signal; no tenant credentials or public provisioning."""
import json,time
from pathlib import Path
PATH=Path('/var/lib/uno360x-saas/control/admission-status.json')

def publish(adapter,path=PATH):
    cap=adapter.max_active
    if not getattr(adapter,'enforce_admission',True):available=True
    else:available=adapter.has_headroom('0'*32) if cap is None else adapter._allocated('0'*32)<cap
    payload={'checked':time.time(),'can_prepare':bool(available),'reason':'available' if available else 'capacity'}
    tmp=path.with_suffix('.next');tmp.write_text(json.dumps(payload));tmp.chmod(0o600);tmp.replace(path)
    return payload
