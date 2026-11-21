"""Collection timing tests against the deployed native worker, without email."""
import datetime as dt
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

worker = None
if os.environ.get('WORKER_SOURCE'):
    spec = importlib.util.spec_from_file_location('collection_worker', os.environ['WORKER_SOURCE'])
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)


@unittest.skipUnless(worker, 'Requires Linux worker via WORKER_SOURCE')
class CollectionTimingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = worker.Store(Path(self.directory.name) / 'state.sqlite')

    def tearDown(self):
        self.store.db.close()
        self.directory.cleanup()

    def sent(self, when, status='accepted'):
        self.store.db.execute('INSERT INTO dispatch VALUES (?,?,?,?,?,?,?,?)',
                              ('cron:46:test:partner', status, '<test@example.com>',
                               'Test', 'test@example.com', 'res.partner', 42, when))
        self.store.db.commit()

    def test_business_window_includes_eight_excludes_seventeen(self):
        zone = dt.timezone(dt.timedelta(hours=-4))
        for hour, minute, expected in [(7, 59, False), (8, 0, True),
                                       (16, 59, True), (17, 0, False), (23, 59, False)]:
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(worker.collection_send_window(
                    dt.datetime(2026, 11, 21, hour, minute, tzinfo=zone)), expected)

    def test_seven_day_cadence_blocks_early_repetition(self):
        self.sent('2026-11-14 15:00:00')
        self.assertFalse(worker.collection_cadence_due(self.store, 42, dt.date(2026, 11, 20), 7))
        self.assertTrue(worker.collection_cadence_due(self.store, 42, dt.date(2026, 11, 21), 7))

    def test_three_day_cadence_blocks_day_two(self):
        self.sent('2026-11-18 15:00:00')
        self.assertFalse(worker.collection_cadence_due(self.store, 42, dt.date(2026, 11, 20), 3))
        self.assertTrue(worker.collection_cadence_due(self.store, 42, dt.date(2026, 11, 21), 3))

    def test_utc_timestamp_uses_dominican_calendar_date(self):
        self.sent('2026-11-15 02:00:00')  # Nov 14, 22:00 RD.
        self.assertTrue(worker.collection_cadence_due(self.store, 42, dt.date(2026, 11, 21), 7))

    def test_smtp_accepted_without_sent_copy_still_prevents_duplicate(self):
        self.sent('2026-11-21 15:00:00', 'accepted_no_copy')
        self.assertFalse(worker.collection_cadence_due(self.store, 42, dt.date(2026, 11, 21), 7))

    def test_another_customer_does_not_block_current_customer(self):
        self.sent('2026-11-21 15:00:00')
        self.assertTrue(worker.collection_cadence_due(self.store, 99, dt.date(2026, 11, 21), 7))

    def test_uncertain_delivery_requires_review(self):
        self.sent('2026-11-21 15:00:00', 'uncertain')
        self.assertEqual(self.store.needs_review(), 1)


if __name__ == '__main__':
    unittest.main()
