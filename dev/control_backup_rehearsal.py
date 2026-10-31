"""Encrypted local control/fixture-secret backup; restore only to temp storage."""
import hashlib,io,json,os,sqlite3,sys,tempfile,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_adapter import LocalAdapter,STATE
from control_state import DIRECTORY
from control.recovery import seal,unseal

def main():
    adapter=LocalAdapter();os.umask(0o077)
    directory=STATE/'backups';directory.mkdir(mode=0o700,exist_ok=True)
    keyfile=directory/'recovery.key'
    if not keyfile.exists():raise RuntimeError('Primero completar respaldo/restauración de una empresa ficticia.')
    source=sqlite3.connect((DIRECTORY/'control.sqlite3').as_uri()+'?mode=ro',uri=True)
    memory=sqlite3.connect(':memory:')
    try:
        source.backup(memory)
        snapshots=[json.loads(row[0]) for row in memory.execute('SELECT snapshot FROM preparation_jobs')]
        accounts=memory.execute('SELECT count(*) FROM accounts WHERE verified=1').fetchone()[0]
        payloads={'control.sqlite3':memory.serialize()}
    finally:source.close();memory.close()
    allowed=['database-password','operator-password','bridge.key','odoo.conf','postgres.env','bootstrap.sql','installed.json']
    for snapshot in snapshots:
        n=adapter.names(snapshot)
        for name in allowed:
            path=n['directory']/name
            if path.is_symlink():raise RuntimeError('Referencia de archivo inesperada.')
            if path.exists():payloads['tenants/'+snapshot['tenant_id']+'/'+name]=path.read_bytes()
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in payloads.items():archive.writestr(name,data)
        archive.writestr('manifest.json',json.dumps(manifest))
    bid=uuid.uuid4().hex
    path=directory/('control_'+bid+'.aesgcm')
    path.write_bytes(seal(buffer.getvalue(),{'version':1,'tenant_id':'control','backup_id':bid},keyfile.read_bytes()))
    _,decrypted=unseal(path.read_bytes(),keyfile.read_bytes(),'control')
    with tempfile.TemporaryDirectory(prefix='uno360x-control-restore-') as temporary:
        destination=Path(temporary)
        with zipfile.ZipFile(io.BytesIO(decrypted)) as archive:
            if set(archive.namelist())!=set(manifest)|{'manifest.json'}:raise RuntimeError('Archivo inesperado.')
            for name,digest in manifest.items():
                data=archive.read(name)
                assert hashlib.sha256(data).hexdigest()==digest
                target=destination/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.write_bytes(data)
        restored=sqlite3.connect(destination/'control.sqlite3')
        try:
            assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert restored.execute('SELECT count(*) FROM accounts WHERE verified=1').fetchone()[0]==accounts
            with restored:
                restored.execute('DELETE FROM identity_sessions')
                restored.execute('UPDATE identity_tokens SET used=1')
                restored.execute('DELETE FROM handoff_tickets')
                restored.execute("UPDATE preparation_jobs SET status='failed' WHERE status='running'")
            assert restored.execute('SELECT count(*) FROM identity_sessions').fetchone()[0]==0
        finally:restored.close()
    report={'control_backup_encrypted':True,'consistent_sqlite_snapshot':True,'restored_integrity_ok':True,
            'verified_accounts_preserved':accounts,'protected_files_verified':len(manifest)-1,
            'restored_sessions_invalidated':True,'original_control_unchanged':True,
            'external_copy_configured':False,'portable_recovery_key_configured':False}
    (directory/'control_verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
