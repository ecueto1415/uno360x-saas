"""Separate privileged local worker; no job is executed by HTTP handlers."""
import argparse
import os
from pathlib import Path
import re
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter
from control_state import control_database
from control.identity import IdentityService
from control.onboarding import Onboarding

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',help='UUID de una preparación local; revalida si ya está lista')
    parser.add_argument('--watch',action='store_true',help='Procesa nuevas altas locales hasta detenerlo')
    args=parser.parse_args()
    adapter=LocalAdapter();os.umask(0o077)
    path=control_database()
    if not path.exists():raise SystemExit('Primero registrar una cuenta y reservar su empresa en el laboratorio.')
    identity=IdentityService(path,lambda notice:None)
    try:
        jobs=Onboarding(identity)
        if args.job and (args.watch or not re.fullmatch('[a-f0-9]{32}',args.job)):
            raise SystemExit('ID inválido o combinación de opciones no permitida.')
        initial=True
        while True:
            if args.job:
                queue=[args.job]
            else:
                states="('queued','failed','running')" if initial else "('queued')"
                queue=[r[0] for r in identity.db.execute('SELECT id FROM preparation_jobs WHERE status IN '+states+' ORDER BY updated')]
            for job in queue:
                try:
                    result=jobs.run(job,adapter)
                    print(result['job_id'],result['status'],flush=True)
                except Exception:
                    print(job,'preparación no completada; revisar estado privado',flush=True)
                    if not args.watch:raise
            if not args.watch:
                print('Trabajos locales procesados:',len(queue));break
            initial=False
            time.sleep(3)
    finally:identity.close()
