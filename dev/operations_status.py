"""Root-only read-only lab operations overview, no web admin permissions added."""
import json
import os
from pathlib import Path
import sqlite3
from control_state import DIRECTORY
from auto_adapter import STATE

def main():
    if os.name!='posix' or os.geteuid()!=0 or 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise SystemExit('Solo WSL root.')
    db=sqlite3.connect((DIRECTORY/'control.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:
        accounts=db.execute('SELECT count(*) FROM accounts WHERE verified=1 AND active=1').fetchone()[0]
        memberships=db.execute('SELECT count(*) FROM memberships WHERE active=1').fetchone()[0]
        jobs=dict(db.execute('SELECT status,count(*) FROM preparation_jobs GROUP BY status').fetchall())
        audit=db.execute('SELECT count(*) FROM identity_audit').fetchone()[0]
    finally:db.close()
    backup=STATE/'backups/verification.json'
    last=json.loads(backup.read_text()) if backup.exists() else {'database_restored':False}
    print(json.dumps({'mode':'local_only','verified_accounts':accounts,'active_memberships':memberships,
      'preparation_states':jobs,'audit_events':audit,'last_restore_verified':last.get('database_restored',False),
      'external_backup_configured':False,'production_deployment':False},indent=2))

if __name__=='__main__':main()
