"""Thirty-day scan history; unresolved detections are retained without expiry."""
import pathlib,re,gzip,datetime,time,json,os,tempfile,sys
DAYS=30
PATTERN=re.compile(r'^scan-(\d{8}-\d{6})\.log(?:\.\d+)?(?:\.gz)?$')

def collect(logs,now=None,reviews=None):
 now=time.time() if now is None else now;reviews=reviews or {};rows={};files=[]
 for p in pathlib.Path(logs).iterdir():
  match=PATTERN.fullmatch(p.name)
  if not match or p.is_symlink() or not p.is_file():continue
  try:
   started=datetime.datetime.strptime(match[1],'%Y%m%d-%H%M%S').replace(tzinfo=datetime.timezone(datetime.timedelta(hours=-4))).timestamp()
   with (gzip.open(p,'rb') if p.suffix=='.gz' else p.open('rb')) as stream:data=stream.read(10_000_001)
   if len(data)>10_000_000:continue
   text=data.decode(errors='replace');infected=re.search(r'Infected files:\s*(\d+)',text);scanned=re.search(r'Scanned files:\s*(\d+)',text);duration=re.search(r'Time:\s*([\d.]+)',text)
   detections=int(infected[1]) if infected else (1 if re.search(r' FOUND(?:\r?\n|$)',text) else None)
   if detections is None:continue
   ident=match[1];review=reviews.get(ident,{})
   reviewed=isinstance(review,dict) and isinstance(review.get('reviewed_at'),(int,float)) and started<=review['reviewed_at']<=now and isinstance(review.get('note'),str) and bool(review['note'].strip())
   pending=detections>0 and not reviewed;keep=started>=now-DAYS*86400 or pending
   row={'id':ident,'started':started,'files':int(scanned[1]) if scanned else 0,'detections':detections,'seconds':float(duration[1]) if duration else None,'pending_review':pending,'reviewed':reviewed}
   files.append((p,keep,started))
   if keep and (ident not in rows or (row['detections'],row['files'])>(rows[ident]['detections'],rows[ident]['files'])):rows[ident]=row
  except (ValueError,OSError,EOFError):continue
 return sorted(rows.values(),key=lambda x:x['started'],reverse=True),files

def maintain(logs,state,now=None,apply=False):
 now=time.time() if now is None else now;logs=pathlib.Path(logs).resolve();state=pathlib.Path(state)
 p=state/'reviews.json';reviews=json.loads(p.read_text()) if p.exists() else {}
 if not isinstance(reviews,dict):raise ValueError('Invalid reviews')
 rows,files=collect(logs,now,reviews);result={'retention_days':DAYS,'records':len(rows),'pending_detections':sum(r['pending_review'] for r in rows),'removed_logs':0,'compressed_logs':0}
 for p,keep,started in files:
  if p.parent.resolve()!=logs or p.is_symlink():raise ValueError('Log outside allowed directory')
  if not keep:
   if apply:p.unlink()
   result['removed_logs']+=1
  elif p.suffix!='.gz' and started<now-86400:
   target=p.with_name(p.name+'.gz')
   if target.exists():continue
   if apply:
    fd,tmp=tempfile.mkstemp(prefix='.scan-compress-',dir=logs)
    try:
     with os.fdopen(fd,'wb') as out,gzip.GzipFile(fileobj=out,mode='wb') as gz:gz.write(p.read_bytes())
     os.chmod(tmp,0o640);os.replace(tmp,target);p.unlink()
    finally:
     if os.path.exists(tmp):os.unlink(tmp)
   result['compressed_logs']+=1
 if apply:
  fd,tmp=tempfile.mkstemp(prefix='.history-',dir=state)
  with os.fdopen(fd,'w') as out:json.dump({'generated':now,**result,'history':rows},out)
  os.chmod(tmp,0o640);os.replace(tmp,state/'history.json')
 return result

if __name__=='__main__':print(json.dumps(maintain('/var/log/uno360x-antivirus','/var/lib/uno360x-antivirus',apply='--apply' in sys.argv)))
