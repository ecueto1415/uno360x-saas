"""Canonical private control database for the lab API and preparation worker."""
import os
from pathlib import Path

DIRECTORY=Path('/var/lib/uno360x-saas-dev/control')

def control_database():
    DIRECTORY.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(DIRECTORY,0o700)
    return DIRECTORY/'control.sqlite3'
