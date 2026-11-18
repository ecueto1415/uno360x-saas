"""Exercise concurrent dispatch without credentials, database, or networking."""
import ast
import base64
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from hashlib import sha256
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest


def worker_functions():
    path = Path(__file__).resolve().parents[1] / 'deployment/send_saas_fiscal.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {'sql_text', 'dispatch', 'consult', 'process_document', 'process_pending'}
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = dict(base64=base64, sha256=sha256, time=time, ThreadPoolExecutor=ThreadPoolExecutor,
                     wait=wait, FIRST_COMPLETED=FIRST_COMPLETED,
                     etree=SimpleNamespace(LxmlError=RuntimeError))
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace


class SubmissionUnknown(Exception):
    pass


class Queue:
    def __init__(self, count):
        self.lock = threading.Lock()
        self.docs = {number: dict(id=number, encf='LAB-%s' % number, issuer='LAB',
            fingerprint='', payload={}, state='queued', is_summary=False, track_id=None)
            for number in range(count)}

    def pending(self):
        with self.lock:
            return [dict(doc) for doc in self.docs.values() if doc['state'] == 'queued']

    def change(self, doc, assignments):
        with self.lock:
            stored = self.docs[doc['id']]
            if stored['state'] != doc['state']:
                return False
            for text in assignments:
                if text == "state='uncertain'":
                    stored['state'] = 'uncertain'
                elif text == "state='sent'":
                    stored['state'] = 'sent'
                elif text.startswith('state=') and '6163636570746564' in text:
                    stored['state'] = 'accepted'
            return True


class ParallelWorkerTest(unittest.TestCase):
    def exercise(self, ambiguous=False):
        module = worker_functions()
        queue = Queue(5)
        barrier = threading.Barrier(5)
        calls = []
        clients = []
        lock = threading.Lock()

        class Client:
            def submit(self, xml, issuer, encf):
                with lock:
                    calls.append(encf)
                # This would time out if dispatch serialized five submissions.
                barrier.wait(timeout=5)
                if ambiguous and encf == 'LAB-0':
                    raise SubmissionUnknown()
                return {'trackId': encf}

            def result(self, track):
                return 'accepted'

        def connect(*args):
            client = Client()
            clients.append(client)
            return client

        issuance = SimpleNamespace(connect=connect, prepare_signed=lambda *args: b'LAB XML')
        api = SimpleNamespace(SubmissionUnknown=SubmissionUnknown,
                              validate_result=lambda value, *args: value)
        rfce = SimpleNamespace(requires_summary=lambda payload: False)
        original = queue.pending()
        module['process_pending'](queue, [dict(doc) for doc in original] + [dict(original[0])],
                                  issuance, api, rfce, b'', b'')
        self.assertEqual(len(calls), 5)
        self.assertEqual(len(set(calls)), 5)
        self.assertEqual(len({id(client) for client in clients}), 5)
        # Replay a stale queued snapshot: the durable state guard blocks POST.
        module['process_pending'](queue, original, issuance, api, rfce, b'', b'')
        self.assertEqual(len(calls), 5)
        self.assertEqual(queue.docs[0]['state'], 'uncertain' if ambiguous else 'accepted')
        self.assertTrue(all(queue.docs[number]['state'] == 'accepted' for number in range(1, 5)))

    def test_five_independent_sends_and_no_duplicate_on_retry(self):
        self.exercise()

    def test_uncertain_send_is_not_repeated_and_other_boxes_complete(self):
        self.exercise(ambiguous=True)


if __name__ == '__main__':
    unittest.main()
