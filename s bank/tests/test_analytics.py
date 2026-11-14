import pathlib, unittest
from scoach.db import connect, initialize_schema
from scoach.ledger import transactions, account_scope
from scoach.analytics import month_summary, money_map, compare_periods, trend_series, unusual_candidates

class AnalyticsTests(unittest.TestCase):
    def setUp(self): self.conn=connect(pathlib.Path(__file__).resolve().parents[1]/'var/scoach.sqlite3')
    def tearDown(self): self.conn.close()
    def test_gold_comparison_and_evidence(self):
        r=compare_periods(self.conn,'CUST00001','2026-09-01','2026-09-30','2026-08-01','2026-08-31',{'category':'Restaurants'})
        self.assertEqual([r['previous']['total_cents'],r['current']['total_cents'],r['delta_cents']],[11543,22570,11027])
        self.assertEqual([r['previous']['count'],r['current']['count']],[10,10])
        self.assertEqual([r['previous']['average_cents'],r['current']['average_cents']],[1154,2257])
        self.assertEqual(len(r['current']['transaction_refs']),10); self.assertTrue(r['fact_id'])
        with self.assertRaises(ValueError): compare_periods(self.conn,'CUST00001','2026-09-02','2026-09-30','2026-08-01','2026-08-31')
    def test_scope_filters_empty_and_transfer_separation(self):
        scope=account_scope(self.conn,'CUST00001'); self.assertEqual(scope['account_id'],'ACC000001')
        with self.assertRaises(ValueError): transactions(self.conn,'CUST00001',filters={'account_id':'OTHER'})
        with self.assertRaises(ValueError): transactions(self.conn,'CUST00001','2026-10-01','2026-09-01')
        self.assertEqual(month_summary(self.conn,'CUST00001','2026-09',{'category':'No such category'})['average_cents'],None)
        m=money_map(self.conn,'CUST00001','2026-09')
        self.assertGreater(m['committed_saving_transfers_cents'],0); self.assertGreater(m['salary_cents'],0)
        rows=transactions(self.conn,'CUST00001','2026-09-01','2026-09-30')
        self.assertEqual(m['consumption_cents'],-sum(r['amount_cents'] for r in rows if r['role'] in ('fixed_obligation','flexible_essential','discretionary') and r['amount_cents']<0))
        self.assertEqual(len(trend_series(self.conn,'CUST00001','2026-09')['months']),12)
    def test_unusual_is_customer_relative_and_strict_cutoff(self):
        candidates=unusual_candidates(self.conn,'CUST05097','2026-07')
        self.assertTrue(any(r['amount_cents']==787003 for r in candidates))
        for r in candidates:
            self.assertGreater(r['amount_cents'],r['cutoff_cents']); self.assertGreaterEqual(r['prior_count'],10)

    def test_annual_view_uses_two_complete_twelve_month_windows(self):
        r=trend_series(self.conn,'CUST00001','2026-09',12,{'category':'Restaurants'})
        annual=r['annual_comparison']
        self.assertTrue(annual['available'])
        self.assertEqual((annual['current']['start'],annual['current']['end']),('2025-10-01','2026-09-30'))
        self.assertEqual((annual['previous']['start'],annual['previous']['end']),('2024-10-01','2025-09-30'))
        self.assertEqual(annual['delta_cents'],annual['current']['total_cents']-annual['previous']['total_cents'])
        early=trend_series(self.conn,'CUST00001','2025-02',12)
        self.assertFalse(early['annual_comparison']['available'])
        self.assertIsNone(early['year_over_year_delta_cents'])
        with self.assertRaises(ValueError): month_summary(self.conn,'CUST00001','2027-01')
        with self.assertRaises(ValueError): trend_series(self.conn,'CUST00001','2027-01')

    def test_unusual_cutoff_is_strict_and_requires_ten_prior_rows(self):
        c=connect(':memory:'); initialize_schema(c); c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        for i in range(12):
            month='2026-08' if i<10 else '2026-09'; amount=-10000 if i<11 else -10001
            c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(str(i),'C','A',month+'-15','15X26:12:00:00','Travel',amount,100000,'purchase',None,None,i,'hash','{}'))
        c.commit(); result=unusual_candidates(c,'C','2026-09')
        self.assertEqual([r['amount_cents'] for r in result],[10001]); self.assertEqual(result[0]['cutoff_cents'],10000)
        self.assertEqual(len(result[0]['comparison_transaction_refs']),10)
        c.close()

    def test_money_map_rejects_unobserved_period(self):
        with self.assertRaises(ValueError): money_map(self.conn,'CUST00001','2027-01')
