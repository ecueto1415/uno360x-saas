import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from support_center.store import Store, Invalid, Limited, area_for
from support_center.worker import run
from control.support import decorate, token_for

class SupportTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'support.sqlite3'
        self.now=2000000000
        self.s=Store(self.path,clock=lambda:self.now)
        self.s.initialize()
    def tearDown(self):
        self.s.close();self.tmp.cleanup()
    def message(self,**extra):
        return dict(body='¿Cómo reviso el stock mínimo?',request_id='a'*32,**extra)
    def test_tenant_and_account_isolation(self):
        c=self.s.send('tenant-a','alice',self.message())
        self.assertEqual([],self.s.listing('tenant-b','alice')['cases'])
        self.assertEqual([],self.s.listing('tenant-a','bob')['cases'])
        for tenant,user in [('tenant-b','alice'),('tenant-a','bob')]:
            with self.assertRaises(Invalid):self.s.listing(tenant,user,c)
            with self.assertRaises(Invalid):self.s.send(tenant,user,self.message(case_id=c))
            with self.assertRaises(Invalid):self.s.handoff(tenant,user,c)
    def test_first_message_and_retry_are_idempotent(self):
        c=self.s.send('t','a',self.message())
        self.assertEqual(c,self.s.send('t','a',self.message()))
        self.assertEqual(1,len(self.s.messages(c)))
        with self.assertRaises(Invalid):self.s.send('t','a',dict(self.message(),body='Different'))
        job=self.s.claim();self.assertIsNone(self.s.claim())
        self.s.finish(job,'Abre Inventario.','inventory')
        self.s.finish(job,'Duplicated','inventory')
        self.assertEqual(2,len(self.s.messages(c)))
    def test_two_workers_claim_once(self):
        self.s.send('t','a',self.message())
        def claim(_):
            db=Store(self.path,clock=lambda:self.now)
            try:return db.claim()
            finally:db.close()
        with ThreadPoolExecutor(2) as p:jobs=list(p.map(claim,range(2)))
        self.assertEqual(1,sum(bool(x) for x in jobs))
    def test_parallel_first_retry_creates_one_message(self):
        def send(_):
            db=Store(self.path,clock=lambda:self.now)
            try:return db.send('t','a',self.message())
            finally:db.close()
        with ThreadPoolExecutor(5) as p:ids=list(p.map(send,range(5)))
        self.assertEqual(1,len(set(ids)))
        self.assertEqual(1,len(self.s.messages(ids[0])))
    def test_human_handoff_stops_ai_and_admin_reply_deduplicates(self):
        c=self.s.send('t','a',self.message());job=self.s.claim()
        self.s.handoff('t','a',c)
        self.s.finish(job,'Must not be sent')
        self.assertEqual(1,len(self.s.messages(c)))
        action={'case_id':c,'action':'reply','body':'El equipo te ayuda.','request_id':'b'*32}
        self.s.admin_action('owner',action);self.s.admin_action('owner',action)
        self.assertEqual(2,len(self.s.messages(c)))
        self.assertEqual('team',self.s.messages(c)[-1]['role'])
        self.assertEqual(1,self.s.db.execute('SELECT COUNT(*) FROM audit').fetchone()[0])
    def test_expired_claim_is_review_not_automatic_retry(self):
        self.s.send('t','a',self.message());self.s.claim();self.now+=181
        self.assertIsNone(self.s.claim())
        self.assertEqual('review',self.s.db.execute('SELECT state FROM messages').fetchone()[0])
        self.assertEqual(1,self.s.db.execute('SELECT human FROM cases').fetchone()[0])
    def test_limits_do_not_block_business_gateway(self):
        for i in range(12):self.s.send('t','a',dict(self.message(),request_id=('%032x'%i)))
        with self.assertRaises(Limited):self.s.send('t','a',dict(self.message(),request_id='f'*32))
        self.assertIsNotNone(self.s.send('other','a',self.message()))
    def test_bad_input_rejected(self):
        for data in [dict(self.message(),tenant='forged'),dict(self.message(),body=''),dict(self.message(),body='x'*3001),dict(self.message(),human='yes')]:
            with self.assertRaises(Invalid):self.s.send('t','a',data)
        with self.assertRaises(Invalid):self.s.handoff('t','a',[])
    def test_report_metrics_are_aggregated_without_urls(self):
        self.s.record_metric('t','/odoo/customer-invoices/42?secret=do-not-save',200,2800)
        self.s.record_metric('t','/odoo/customer-invoices/99',500,450)
        self.s.send('t','a',self.message())
        report=self.s.daily_report('2033-05-18')
        self.assertEqual(2,report['metrics'][0]['requests'])
        self.assertEqual(1,report['metrics'][0]['slow'])
        self.assertEqual(1,report['metrics'][0]['errors'])
        self.assertNotIn('do-not-save',json.dumps(report))
        self.assertEqual(report,self.s.daily_report('2033-05-18'))
        self.assertIsNone(area_for('/web/dataset/call_kw'))
    def test_worker_no_api_when_idle_and_isolated_history(self):
        calls=[]
        run({},self.path,lambda *args:calls.append(args),budget=.1)
        self.assertEqual([],calls)
        c=self.s.send('t','a',self.message());self.s.send('other','z',dict(self.message(),body='OTHER TENANT SECRET'))
        def responder(settings,history):
            calls.append(history)
            self.assertNotIn('OTHER TENANT SECRET',json.dumps(history))
            return {'reply':'Consulta la ficha.','topic':'inventory','human':False}
        # One bounded worker turn; second tenant intentionally handed to humans.
        other=self.s.listing('other','z')['selected']['id'];self.s.handoff('other','z',other)
        run({},self.path,responder,budget=.2)
        self.assertEqual(1,len(calls));self.assertEqual('assistant',self.s.messages(c)[-1]['role'])
    def test_gateway_decoration_no_native_outsolutech(self):
        headers=[('Content-Type','text/html')]
        status,h,body=decorate('/uno360x-resumen',200,headers,b'<html><body></body></html>')
        self.assertIn(b'chat.js',body)
        self.assertEqual(body,decorate('/uno360x-resumen',200,h,body)[2])
        self.assertEqual(b'{}',decorate('/web/dataset',200,headers,b'{}')[2])

if __name__=='__main__':unittest.main()
