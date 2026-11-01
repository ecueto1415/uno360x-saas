"""WSL-only adapter; never usable on the operational VM."""
import json,os
from pathlib import Path
from tenants import ROOT
from control.container_adapter import ContainerAdapter
STATE=Path('/var/lib/uno360x-saas-dev/automatic')
class LocalAdapter(ContainerAdapter):
    def __init__(self):
        if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():
            raise RuntimeError('Solo WSL root de laboratorio.')
        images=json.loads(Path('/var/lib/uno360x-saas-dev/images.json').read_text())
        super().__init__(STATE,images,ROOT,'local-development','uno360x-auto-')
