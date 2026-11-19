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
        for i in range(12):self.s.send('t','a',dict(self.message(human=True),request_id=('%032x'%i)))
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
        def responder(settings,history,context):
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
        self.assertIn(b'chat.js',decorate('/uno360x/finanzas/cheques',200,headers,b'<html><body></body></html>')[2])
        self.assertIn(b'chat.js',decorate('/uno360x/area/inventory',200,headers,b'<html><body></body></html>')[2])
        self.assertEqual(body,decorate('/uno360x-resumen',200,h,body)[2])
        self.assertEqual(b'{}',decorate('/web/dataset',200,headers,b'{}')[2])

    def test_context_only_for_new_ai_messages_and_scoped_to_owner(self):
        self.assertTrue(self.s.needs_context('t','a',self.message()))
        c=self.s.send('t','a',self.message(),context={'verified':True,'diagnostics':{'user_id':77}})
        self.assertFalse(self.s.needs_context('t','a',self.message()))
        job=self.s.claim();self.assertTrue(self.s.job_context(job)['verified'])
        self.s.db.execute("UPDATE message_context SET account='another-user'");self.s.db.commit()
        self.assertFalse(self.s.job_context(job)['verified'])
        self.s.handoff('t','a',c)
        self.assertFalse(self.s.needs_context('t','a',dict(self.message(case_id=c),request_id='b'*32)))

    def test_expired_diagnostic_is_not_presented_as_current(self):
        self.s.send('t','a',self.message(),context={'verified':True})
        job=self.s.claim();self.now+=601
        self.assertFalse(self.s.job_context(job)['verified'])

    def test_preflight_rejects_invalid_and_foreign_messages_before_read(self):
        c=self.s.send('t','a',self.message())
        with self.assertRaises(Invalid):self.s.needs_context('other','a',self.message(case_id=c))
        with self.assertRaises(Invalid):self.s.needs_context('t','a',dict(self.message(),model='res.users'))

    def test_message_after_resolution_returns_to_ai(self):
        c=self.s.send('t','a',self.message(human=True))
        self.s.admin_action('owner',{'case_id':c,'action':'resolve','body':'','request_id':'b'*32})
        data=dict(self.message(case_id=c),body='¿Dónde está el CRM?',request_id='c'*32)
        self.assertTrue(self.s.needs_context('t','a',data))
        self.s.send('t','a',data,context={'verified':True})
        self.assertEqual(0,self.s.case('t','a',c)['human'])
        self.assertIsNotNone(self.s.claim())

    def test_resume_queues_existing_unanswered_message_once(self):
        c=self.s.send('t','a',self.message(human=True))
        with self.assertRaises(Invalid):self.s.resume_ai('other','a',c,{'verified':True})
        self.s.resume_ai('t','a',c,{'verified':True})
        self.s.resume_ai('t','a',c,{'verified':True})
        self.assertEqual(1,len(self.s.messages(c)))
        job=self.s.claim();self.assertTrue(self.s.job_context(job)['verified'])
        self.s.finish(job,'Aquí está el CRM.','sales')
        self.assertEqual(2,len(self.s.messages(c)))

    def test_continuous_chat_reuses_anchor_without_case_id(self):
        c=self.s.send('t','a',self.message())
        self.s.finish(self.s.claim(),'Abre Inventario.','inventory')
        second=dict(self.message(),body='¿Y los mínimos?',request_id='b'*32)
        self.assertEqual(c,self.s.send('t','a',second))
        self.assertEqual(c,self.s.listing('t','a')['selected']['id'])
        self.assertEqual(1,self.s.db.execute('SELECT COUNT(*) FROM cases').fetchone()[0])
        self.assertEqual(3,len(self.s.messages(c)))

    def test_legacy_history_preserved_and_scoped_and_admin_uses_same_thread(self):
        for cid,tenant,account,title,updated in [('1'*32,'t','a','Anterior',1),('2'*32,'t','a','Reciente',2),('3'*32,'other','a','Privada',3),('4'*32,'t','other','Otra persona',4)]:
            self.s.db.execute('INSERT INTO cases(id,tenant,account,title,created,updated) VALUES (?,?,?,?,?,?)',(cid,tenant,account,title,updated,updated))
            self.s.db.execute("INSERT INTO messages(case_id,role,body,created) VALUES (?,'user',?,?)",(cid,title,updated))
        self.s.db.commit()
        listing=self.s.listing('t','a')
        self.assertEqual('2'*32,listing['selected']['id'])
        self.assertEqual(['Anterior','Reciente'],[m['body'] for m in listing['messages']])
        self.assertEqual(1,len(listing['cases']))
        self.assertEqual('2'*32,self.s.listing('t','a','1'*32)['selected']['id'])
        self.s.send('t','a',dict(self.message(case_id='1'*32),body='Continúo',request_id='b'*32),context={'verified':True})
        history=[]
        run({},self.path,lambda settings,h,c:(history.extend(h) or {'reply':'Seguimos.','topic':'other','human':False}),budget=.1)
        self.assertEqual(['Anterior','Reciente','Continúo'],[m['body'] for m in history])
        self.assertEqual(4,self.s.db.execute('SELECT COUNT(*) FROM cases').fetchone()[0])
        self.assertEqual(3,len(self.s.overview()['cases']))
        self.assertEqual('2'*32,self.s.admin_case('1'*32)['selected']['id'])
        self.assertEqual(4,len(self.s.admin_case('2'*32)['messages']))
        self.assertEqual(1,self.s.db.execute('SELECT COUNT(*) FROM messages WHERE case_id=?',('1'*32,)).fetchone()[0])

    def test_retry_of_legacy_message_does_not_duplicate_after_unification(self):
        for cid,stamp in [('1'*32,1),('2'*32,2)]:
            self.s.db.execute('INSERT INTO cases(id,tenant,account,title,created,updated) VALUES (?,\'t\',\'a\',\'Legacy\',?,?)',(cid,stamp,stamp))
        self.s.db.execute("INSERT INTO messages(case_id,role,body,created,request_id) VALUES (?,'user',?,1,?)",('1'*32,self.message()['body'],'a'*32))
        self.s.db.commit()
        self.s.listing('t','a')
        retry=self.message(case_id='1'*32)
        self.assertFalse(self.s.needs_context('t','a',retry))
        self.assertEqual('2'*32,self.s.send('t','a',retry))
        self.assertEqual(1,len(self.s.messages('2'*32)))

    def test_all_history_can_be_loaded_without_overlap_or_cross_scope(self):
        c=self.s.send('t','a',self.message(human=True))
        for i in range(170):self.s.db.execute("INSERT INTO messages(case_id,role,body,created) VALUES (?,'team',?,?)",(c,str(i),self.now+i))
        self.s.db.commit()
        page=self.s.listing('t','a');ids=[m['id'] for m in page['messages']]
        self.assertTrue(page['has_older'])
        while page['has_older']:
            page=self.s.listing('t','a',before=page['messages'][0]['id'])
            ids=[m['id'] for m in page['messages']]+ids
        self.assertEqual(list(range(1,172)),ids)
        with self.assertRaises(Invalid):self.s.listing('other','a',c,before=100)
        for before in [0,-1,True,'2']:
            with self.assertRaises(Invalid):self.s.listing('t','a',before=before)

    def test_two_distinct_first_messages_cannot_create_two_threads(self):
        def send(i):
            db=Store(self.path,clock=lambda:self.now)
            try:
                try:return db.send('t','a',dict(self.message(),request_id=('%032x'%i)))
                except Invalid:return None
            finally:db.close()
        with ThreadPoolExecutor(2) as p:ids=list(p.map(send,range(2)))
        self.assertEqual(1,sum(x is not None for x in ids))
        self.assertEqual(1,self.s.db.execute('SELECT COUNT(*) FROM cases').fetchone()[0])

if __name__=='__main__':unittest.main()
