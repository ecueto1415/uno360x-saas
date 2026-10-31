"""Separate privileged local worker; no job is executed by HTTP handlers."""
import argparse
import os
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter
from control_state import control_database
from control.identity import IdentityService
from control.onboarding import Onboarding

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',help='UUID de una preparación local; revalida si ya está lista')
    args=parser.parse_args()
    adapter=LocalAdapter();os.umask(0o077)
    path=control_database()
    if not path.exists():raise SystemExit('Primero registrar una cuenta y reservar su empresa en el laboratorio.')
    identity=IdentityService(path,lambda notice:None)
    try:
        jobs=Onboarding(identity)
        if args.job:
            if not re.fullmatch('[a-f0-9]{32}',args.job):raise SystemExit('ID de preparación inválido.')
            queue=[args.job]
        else:
            queue=[r[0] for r in identity.db.execute("SELECT id FROM preparation_jobs WHERE status IN ('queued','failed','running') ORDER BY updated")]
        for job in queue:
            result=jobs.run(job,adapter)
            print(result['job_id'],result['status'],flush=True)
        print('Trabajos locales procesados:',len(queue))
    finally:identity.close()
