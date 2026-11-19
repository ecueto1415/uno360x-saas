import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from control.subscription_store import Subscription,BillingInvalid,MAX_PROOF
from control.subscription_views import screen,embed
from control.subscription import dispatch,token,form,PATH

class SubscriptionTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.execute('CREATE TABLE tenants(id TEXT PRIMARY KEY,modules TEXT)')
  self.db.executemany('INSERT INTO tenants VALUES (?,?)',[('a','[]'),('b','["payroll_hr"]')])
  self.role='owner'
  self.identity=SimpleNamespace(db=self.db,clock=lambda:1795080000,
   _account=lambda s:{'id':s},_membership=lambda user,tenant:{'role':self.role} if tenant=='a' else (_ for _ in ()).throw(PermissionError()))
  self.ledger=Subscription(self.identity);self.ledger.initialize()
  self.invoice='1'*32
  self.db.execute("INSERT INTO subscription_invoices VALUES (?,?,'SUS-001',1795080000,1795166400,4500,'USD','pending',?)",(self.invoice,'a',b'%PDF-fixture'))
  self.db.execute("INSERT INTO subscription_invoices VALUES (?,?,'OTHER SECRET',1795080000,NULL,9000,'USD','pending',?)",('2'*32,'b',b'%PDF-other-private'))
  self.db.commit()
 def tearDown(self):self.db.close()
 def test_read_only_status_does_not_invent_price_payment_or_expiry(self):
  status=self.ledger.overview('alice','a')
  self.assertIsNone(status['terms']);self.assertFalse(status['automatic_charge']);self.assertFalse(status['card_available'])
  self.assertEqual('',status['preferences']['method'])
  self.assertEqual(['SUS-001'],[r['number'] for r in self.ledger.invoices('alice','a')])
 def test_only_administrators_and_current_membership_allowed(self):
  for role in ['owner','admin']:
   self.role=role;self.assertEqual('SUS-001',self.ledger.invoice('alice','a',self.invoice)['number'])
  self.role='member'
  for action in [lambda:self.ledger.overview('alice','a'),lambda:self.ledger.invoices('alice','a'),lambda:self.ledger.preferences('alice','a','transfer','a@example.test'),lambda:self.ledger.report_transfer('alice','a',self.invoice,'ref',b'%PDF-test','a'*32)]:
   with self.assertRaises(PermissionError):action()
 def test_foreign_invoice_id_and_proof_are_not_readable(self):
  with self.assertRaises(BillingInvalid):self.ledger.invoice('alice','a','2'*32)
  with self.assertRaises(BillingInvalid):self.ledger.report_transfer('alice','a','2'*32,'ref',b'%PDF-test','a'*32)
  with self.assertRaises(BillingInvalid):self.ledger.proof('alice','a','2'*32)
 def test_preferences_save_and_validate_without_payment_or_access_changes(self):
  self.ledger.preferences('alice','a','transfer','Billing@Example.Test')
  self.assertEqual('billing@example.test',self.ledger.overview('alice','a')['preferences']['email'])
  self.assertEqual('pending',self.ledger.invoice('alice','a',self.invoice)['state'])
  for method,email in [('card','a@example.test'),('transfer','bad-email')]:
   with self.assertRaises(BillingInvalid):self.ledger.preferences('alice','a',method,email)
 def test_transfer_retries_and_reselected_same_file_do_not_duplicate_or_pay(self):
  a=self.ledger.report_transfer('alice','a',self.invoice,'REF-01',b'%PDF-proof','a'*32)
  self.assertEqual(a,self.ledger.report_transfer('alice','a',self.invoice,'REF-01',b'%PDF-proof','a'*32))
  self.assertEqual(a,self.ledger.report_transfer('alice','a',self.invoice,'REF-01',b'%PDF-proof','b'*32))
  self.assertEqual(1,self.db.execute('SELECT COUNT(*) FROM subscription_transfer_reports').fetchone()[0])
  self.assertEqual('pending',self.ledger.invoice('alice','a',self.invoice)['state'])
  self.assertEqual(1,self.ledger.invoices('alice','a')[0]['awaiting_review'])
  with self.assertRaises(BillingInvalid):self.ledger.report_transfer('alice','a',self.invoice,'DIFFERENT',b'%PDF-proof','a'*32)
 def test_paid_invoice_invalid_file_and_excessive_attachment_rejected(self):
  for proof in [b'<svg onload=alert(1)>',b'x'*(MAX_PROOF+1),b'']:
   with self.assertRaises(BillingInvalid):self.ledger.report_transfer('alice','a',self.invoice,'REF',proof,'a'*32)
  self.db.execute("UPDATE subscription_invoices SET state='paid' WHERE id=?",(self.invoice,));self.db.commit()
  with self.assertRaises(BillingInvalid):self.ledger.report_transfer('alice','a',self.invoice,'REF',b'%PDF-test','a'*32)
 def test_filters_and_html_escape_with_approved_shell(self):
  self.assertEqual([],self.ledger.invoices('alice','a',state='paid'))
  self.assertEqual([],self.ledger.invoices('alice','a',year='2025'))
  self.assertEqual([],self.ledger.invoices('alice','a',query='unknown'))
  data=self.ledger.overview('alice','a');data['preferences']['email']='"><script>alert(1)</script>'
  body=screen(data,self.ledger.invoices('alice','a'),'csrf',tab='payment')
  self.assertNotIn(b'<script>',body);self.assertIn(b'&lt;script&gt;',body)
  shell=b'<html><head><title>Old</title></head><body><aside>MENU</aside><div class="ux-page"><header>NAME GEAR</header>OLD<footer class="ux-footer">FOOTER</footer></div></body></html>'
  result=embed(shell,body)
  self.assertIn(b'MENU',result);self.assertIn(b'NAME GEAR',result);self.assertIn(b'FOOTER',result);self.assertNotIn(b'>OLD<',result)
 def handler(self,method='GET',body=b'',headers=None):
  identity=SimpleNamespace(**vars(self.identity),close=lambda:None)
  handle=SimpleNamespace(tenant='a',token='private',backend=SimpleNamespace(central_session='alice',claims={'role':self.role,'work_permissions':()}))
  shell=b'<html><head><title>Old</title></head><body><div class="ux-page"><header>NAME</header>OLD<footer class="ux-footer">FOOTER</footer></div></body></html>'
  manager=SimpleNamespace(identity=lambda:identity,validate=lambda h,i:None,forward=lambda *args:(200,[('Content-Type','text/html')],shell))
  replies=[]
  handler=SimpleNamespace(server=SimpleNamespace(manager=manager),command=method,rfile=io.BytesIO(body),headers=headers or {},reply=lambda *a,**kw:replies.append((a,kw)))
  return handler,handle,replies
 def test_http_admin_page_member_denied_and_csrf_blocks_write(self):
  from urllib.parse import urlsplit,urlencode
  h,handle,replies=self.handler()
  dispatch(h,handle,urlsplit(PATH));self.assertEqual(200,replies[0][0][0])
  self.role='member';h,handle,replies=self.handler()
  dispatch(h,handle,urlsplit(PATH));self.assertEqual(403,replies[0][0][0]);self.assertNotIn(b'SUS-001',replies[0][0][1])
  self.role='owner'
  for good in [False,True]:
   h,handle,replies=self.handler('POST')
   values={'csrf':token(handle) if good else 'bad','operation':'preferences','method':'transfer','email':'a@example.test'}
   body=urlencode(values).encode();h.rfile=io.BytesIO(body);h.headers={'Content-Type':'application/x-www-form-urlencoded','Content-Length':str(len(body))}
   dispatch(h,handle,urlsplit(PATH+'?tab=payment'));self.assertEqual(303 if good else 403,replies[0][0][0])
 def test_multipart_parser_deduplicates_fields_and_validates_limits(self):
  body=b'--ABC\r\nContent-Disposition: form-data; name="reference"\r\n\r\nREF\r\n--ABC\r\nContent-Disposition: form-data; name="proof"; filename="receipt.pdf"\r\nContent-Type: application/pdf\r\n\r\n%PDF-file\r\n--ABC--\r\n'
  h,_,_=self.handler('POST',body,{'Content-Type':'multipart/form-data; boundary=ABC','Content-Length':str(len(body))})
  parsed=form(h);self.assertEqual('REF',parsed['reference']);self.assertEqual(b'%PDF-file',parsed['proof'])
  h.headers['Content-Length']=str(MAX_PROOF+16385)
  with self.assertRaises(BillingInvalid):form(h)

 def test_pdf_download_uses_invoice_number_and_cannot_cross_companies(self):
  from urllib.parse import urlsplit
  h,handle,replies=self.handler()
  dispatch(h,handle,urlsplit(PATH+'?pdf='+self.invoice))
  self.assertEqual(200,replies[0][0][0]);self.assertEqual(b'%PDF-fixture',replies[0][0][1])
  self.assertIn(('Content-Disposition','attachment; filename="SUS-001.pdf"'),replies[0][0][2])
  h,handle,replies=self.handler()
  dispatch(h,handle,urlsplit(PATH+'?pdf='+'2'*32))
  self.assertEqual(400,replies[0][0][0]);self.assertNotIn(b'other-private',replies[0][0][1])

 def test_operator_import_is_idempotent_and_never_marks_paid(self):
  from deployment.subscription_ledger import import_invoice
  invoice=import_invoice(self.db,'a','SUS-002',4500,'USD',1795080000,None,b'%PDF-operator')
  self.assertEqual(invoice,import_invoice(self.db,'a','SUS-002',4500,'USD',1795080000,None,b'%PDF-operator'))
  self.assertEqual('pending',self.ledger.invoice('alice','a',invoice)['state'])
  with self.assertRaises(ValueError):import_invoice(self.db,'a','SUS-002',9999,'USD',1795080000,None,b'%PDF-operator')

if __name__=='__main__':unittest.main()
