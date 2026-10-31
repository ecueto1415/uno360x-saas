import io
import secrets
import tarfile
import unittest
from control.recovery import seal,unseal,safe_volume

class RecoveryTests(unittest.TestCase):
    def test_encryption_authentication_and_tenant_binding(self):
        key=secrets.token_bytes(32);data=seal(b'fictional backup',{'tenant_id':'alfa','version':1},key)
        self.assertNotIn(b'fictional backup',data)
        self.assertEqual(unseal(data,key,'alfa')[1],b'fictional backup')
        for blob,k,t in [(data[:-1]+bytes([data[-1]^1]),key,'alfa'),(data,secrets.token_bytes(32),'alfa'),(data,key,'beta')]:
            with self.assertRaises(ValueError):unseal(blob,k,t)
    def tar(self,name,content=b'x',kind=tarfile.REGTYPE):
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w') as archive:
            member=tarfile.TarInfo(name);member.type=kind;member.size=len(content) if kind==tarfile.REGTYPE else 0
            archive.addfile(member,io.BytesIO(content) if kind==tarfile.REGTYPE else None)
        return buffer.getvalue()
    def test_sessions_are_not_restored(self):
        clean,hashes=safe_volume(self.tar('sessions/live-cookie',b'fictional cookie'))
        self.assertFalse(hashes)
        self.assertEqual(tarfile.open(fileobj=io.BytesIO(clean)).getnames(),[])
    def test_traversal_and_links_rejected_regular_files_preserved(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('/escape',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('device',tarfile.CHRTYPE)]:
            with self.assertRaises(ValueError):safe_volume(self.tar(name,kind=kind))
        clean,hashes=safe_volume(self.tar('./filestore/data',b'abc'))
        self.assertIn('filestore/data',hashes)
        self.assertEqual(tarfile.open(fileobj=io.BytesIO(clean)).extractfile('./filestore/data').read(),b'abc')
    def test_privileged_mode_bits_are_removed_without_changing_content(self):
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w') as archive:
            member=tarfile.TarInfo('filestore/file');member.mode=0o6755;member.size=1
            archive.addfile(member,io.BytesIO(b'x'))
        clean,_=safe_volume(buffer.getvalue())
        restored=tarfile.open(fileobj=io.BytesIO(clean))
        self.assertEqual(restored.getmember('filestore/file').mode,0o755)
