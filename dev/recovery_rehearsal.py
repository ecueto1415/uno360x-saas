"""Stop exactly one owned fictional app and reconcile without duplicating it."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter
from control_state import control_database
from tenants import run,inspect
from control.identity import IdentityService
from control.onboarding import Onboarding

def main():
    adapter=LocalAdapter()
    identity=IdentityService(control_database(),lambda notice:None)
    try:
        jobs=Onboarding(identity)
        row=identity.db.execute("SELECT * FROM preparation_jobs WHERE status='ready_local' ORDER BY tenant_id LIMIT 1").fetchone()
        if not row:raise RuntimeError('No hay espacio de laboratorio listo.')
        snapshot=json.loads(row['snapshot']);n=adapter.names(snapshot)
        app=adapter.check_container(n['app'],snapshot);database=adapter.check_container(n['database'],snapshot)
        before=(app['Id'],database['Id'],n['files'])
        with adapter.lock(snapshot['tenant_id']):run('stop',n['app'])
        assert not inspect(n['app'])['State']['Running']
        try:jobs.run(row['id'],adapter)
        finally:
            adapter.check_container(n['app'],snapshot)
            run('start',n['app'])
        after=(inspect(n['app'])['Id'],inspect(n['database'])['Id'],adapter.names(snapshot)['files'])
        assert before==after
        assert inspect(n['app'])['State']['Running']
        print(json.dumps({'owned_fictional_app_stopped':True,'recovered':True,
                          'same_app_and_database_containers':True,'same_files_volume':True,
                          'production_touched':False},indent=2))
    finally:identity.close()

if __name__=='__main__':main()
