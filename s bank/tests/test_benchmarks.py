import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scoach import benchmarks
from scoach.db import connect

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / 'var' / 'scoach.sqlite3'


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        if not DEMO.exists():
            self.skipTest('demo database not present')
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'demo.sqlite3'
        shutil.copy(DEMO, path)
        self.conn = connect(path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_snapshot_is_sourced_and_complete(self):
        snapshot = json.loads(benchmarks.SNAPSHOT.read_text(encoding='utf-8'))
        self.assertEqual(snapshot['statistical_year'], 2022)
        self.assertIn('pxdata.stat.fi', snapshot['api_url'])
        for codes, _ in benchmarks.CATEGORY_MAP.values():
            for code in codes:
                self.assertEqual(len(snapshot['groups'][code]['by_age']), 9)

    def test_age_bands(self):
        self.assertEqual(benchmarks.age_band(30), '25-34')
        self.assertEqual(benchmarks.age_band(63), '55-64')
        self.assertEqual(benchmarks.age_band(90), '85-')
        self.assertIsNone(benchmarks.age_band(12))

    def test_comparison_matches_ledger_and_snapshot(self):
        result = benchmarks.compare_to_peers(self.conn, 'CUST00001', 'Restaurants', months=12)
        self.assertTrue(result['available'])
        age = self.conn.execute("SELECT age FROM customers WHERE customer_id='CUST00001'").fetchone()[0]
        snapshot = json.loads(benchmarks.SNAPSHOT.read_text(encoding='utf-8'))
        expected_peer = snapshot['groups']['1111']['by_age'][benchmarks.age_band(age)]['per_consumption_unit_month_eur'] * 100
        self.assertEqual(result['peers']['per_consumption_unit_cents'], expected_peer)
        start, end = result['customer']['period']['start'], result['customer']['period']['end']
        total = -sum(r['amount_cents'] for r in benchmarks.transactions(self.conn, 'CUST00001', start, end, {'category': 'Restaurants'})
                     if r['amount_cents'] < 0 and r['transaction_type'] in benchmarks.CONSUMPTION_TYPES)
        self.assertEqual(result['customer']['total_cents'], total)
        self.assertEqual(result['difference_cents'], result['customer']['monthly_average_cents'] - expected_peer)
        self.assertEqual(len(result['caveats']), 3)

    def test_unmapped_category_and_missing_snapshot(self):
        self.assertFalse(benchmarks.compare_to_peers(self.conn, 'CUST00001', 'Housing')['available'])
        original = benchmarks.SNAPSHOT
        try:
            benchmarks.SNAPSHOT = Path(self.tmp.name) / 'missing.json'
            result = benchmarks.compare_to_peers(self.conn, 'CUST00001', 'Restaurants')
            self.assertFalse(result['available'])
            self.assertTrue(result['caveats'])
        finally:
            benchmarks.SNAPSHOT = original
        with self.assertRaises(ValueError):
            benchmarks.compare_to_peers(self.conn, 'CUST00001', 'Restaurants', months=0)


class BenchmarkWiringTests(unittest.TestCase):
    def setUp(self):
        if not DEMO.exists():
            self.skipTest('demo database not present')
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'demo.sqlite3'
        shutil.copy(DEMO, self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_endpoint_and_tool(self):
        from scoach.api import Application
        from scoach.agent_tools import ToolContext, dispatch
        app = Application(str(self.path))
        status, body = app.handle('GET', '/api/benchmarks?customer_id=CUST00001&category=Restaurants')
        self.assertEqual(status, 200)
        self.assertTrue(body['data']['available'])
        status, body = app.handle('GET', '/api/benchmarks?customer_id=CUST00001')
        self.assertEqual(status, 200)
        self.assertTrue(body['data']['categories'])
        self.assertEqual(app.handle('GET', '/api/benchmarks?customer_id=CUST00001&nope=1')[0], 400)
        conn = connect(self.path)
        try:
            ctx = ToolContext(conn, 'CUST00001', '2026-09')
            result = dispatch(conn, 'CUST00001', ctx, 'compare_to_peers', {'category': 'Groceries'})
            self.assertTrue(result['available'])
            self.assertIn('evidence_id', result)
            self.assertNotIn('transaction_refs', result)
        finally:
            conn.close()
