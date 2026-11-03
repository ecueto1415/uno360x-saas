import unittest,tempfile,pathlib,datetime,json,gzip
from deployment.antivirus_history import collect,maintain
class HistoryTests(unittest.TestCase):
 def test_thirty_days_pending_compression_and_review(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);logs=root/'logs';logs.mkdir();state=root/'state';state.mkdir();now=2000000000
   def add(age,n):
    t=datetime.datetime.fromtimestamp(now-age*86400,datetime.timezone(datetime.timedelta(hours=-4)));ident=t.strftime('%Y%m%d-%H%M%S');p=logs/('scan-'+ident+'.log');p.write_text(f'Scanned files: 10\nInfected files: {n}\nTime: 1.5 sec\n');return p,ident
   recent,_=add(2,0);old,_=add(31,0);pending,ident=add(40,1);unknown=logs/'scan-20010101-000000.log';unknown.write_text('incomplete analysis')
   external=root/'outside';external.write_text('keep');(logs/'scan-20000101-000000.log').symlink_to(external)
   rows,_=collect(logs,now);self.assertEqual(len(rows),2);self.assertEqual(sum(r['pending_review'] for r in rows),1)
   maintain(logs,state,now,apply=False);self.assertTrue(old.exists())
   maintain(logs,state,now,apply=True);self.assertFalse(old.exists());self.assertTrue(pending.with_name(pending.name+'.gz').exists());self.assertTrue(recent.with_name(recent.name+'.gz').exists());self.assertTrue(unknown.exists());self.assertEqual(external.read_text(),'keep')
   rows,_=collect(logs,now);self.assertEqual(len(rows),2)
   (state/'reviews.json').write_text(json.dumps({ident:{'reviewed_at':now,'note':'Reviewed by administrator'}}))
   maintain(logs,state,now,apply=True);self.assertFalse(pending.with_name(pending.name+'.gz').exists())
 def test_more_than_twelve_scans_are_visible_and_duplicates_deduplicated(self):
  with tempfile.TemporaryDirectory() as tmp:
   logs=pathlib.Path(tmp);now=2000000000
   for i in range(40):
    t=datetime.datetime.fromtimestamp(now-i*3600,datetime.timezone(datetime.timedelta(hours=-4)));p=logs/('scan-'+t.strftime('%Y%m%d-%H%M%S')+'.log');p.write_text('Scanned files: 7\nInfected files: 0\n')
   with gzip.open(str(p)+'.1.gz','wt') as f:f.write(p.read_text())
   rows,_=collect(logs,now);self.assertEqual(len(rows),40)
if __name__=='__main__':unittest.main()
