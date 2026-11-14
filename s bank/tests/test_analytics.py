import pathlib, unittest
from scoach.db import connect, initialize_schema
from scoach.ledger import transactions, account_scope
from scoach.analytics import month_summary, money_map, compare_periods, trend_series, unusual_candidates, salary_change_signal, payday_timing_signal

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

    def test_salary_change_uses_recent_three_complete_months_and_excludes_other_income(self):
        c=connect(':memory:'); initialize_schema(c); c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        line=0
        for month in range(1,10):
            salary=100000 if month<=6 else 130000
            line+=1; c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f's{month}','C','A',f'2026-{month:02d}-15','15X26:12:00:00','Salary',salary,200000,'salary',None,None,line,f's{month}','{}'))
            if month>=7:
                line+=1; c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'o{month}','C','A',f'2026-{month:02d}-20','20X26:12:00:00','Other Income',900000,1100000,'other_income',None,None,line,f'o{month}','{}'))
        c.commit()

        signal=salary_change_signal(c,'C','2026-09')

        self.assertTrue(signal['available']); self.assertTrue(signal['qualified'])
        self.assertEqual(signal['direction'],'increase')
        self.assertEqual(signal['recent_period'],{'start':'2026-07-01','end':'2026-09-30','months':3})
        self.assertEqual(signal['baseline_period'],{'start':'2026-01-01','end':'2026-06-30','months':6})
        self.assertEqual(signal['recent_salary_median_cents'],130000)
        self.assertEqual(signal['baseline_salary_median_cents'],100000)
        self.assertEqual(signal['delta_cents'],30000)
        self.assertEqual(signal['change_basis_points'],3000)
        self.assertEqual(signal['threshold_basis_points'],1500)
        self.assertEqual(signal['absolute_threshold_cents'],10000)
        self.assertTrue(signal['other_income_excluded'])
        self.assertEqual(set(signal['transaction_refs']),{f's{i}' for i in range(1,10)})
        self.assertTrue(signal['fact_id'])

        selected=salary_change_signal(c,'C','2026-08')
        self.assertEqual(selected['recent_period']['end'],'2026-08-31')
        c.execute("INSERT INTO customers VALUES('D','00100',30,'{}')")
        for month in range(2,10):
            c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'ds{month}','D','D1',f'2026-{month:02d}-15','15X26:12:00:00','Salary',100000,200000,'salary',None,None,100+month,f'ds{month}','{}'))
        c.commit()
        insufficient=salary_change_signal(c,'D','2026-09')
        self.assertFalse(insufficient['available']); self.assertFalse(insufficient['qualified'])
        c.close()

    def test_payday_timing_uses_observed_pre_salary_troughs_and_minimum_evidence(self):
        c=connect(':memory:'); initialize_schema(c); c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        line=0
        for month in range(4,10):
            line+=1; c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'low{month}','C','A',f'2026-{month:02d}-14','14X26:12:00:00','Groceries',-1000,10000,'purchase',None,None,line,f'low{month}','{}'))
            line+=1; c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'salary{month}','C','A',f'2026-{month:02d}-15','15X26:12:00:00','Salary',100000,110000,'salary',None,None,line,f'salary{month}','{}'))
        c.commit()

        signal=payday_timing_signal(c,'C','2026-09')

        self.assertTrue(signal['available']); self.assertTrue(signal['qualified'])
        self.assertEqual(signal['period'],{'start':'2026-04-01','end':'2026-09-30','months':6})
        self.assertEqual(signal['lookback_days'],7)
        self.assertEqual(signal['salary_median_cents'],100000)
        self.assertEqual(signal['low_balance_threshold_cents'],25000)
        self.assertEqual(signal['threshold_rule'],'lower of EUR 500 or 25% of the observed median salary')
        self.assertEqual(signal['observed_window_count'],6)
        self.assertEqual(signal['low_balance_event_count'],6)
        self.assertEqual(signal['lowest_pre_salary_balance_cents'],10000)
        self.assertEqual(len(signal['events']),6)
        self.assertEqual(len(signal['transaction_refs']),12)
        self.assertTrue(signal['fact_id'])

        c.execute("INSERT INTO customers VALUES('D','00100',30,'{}')")
        for month in (8,9):
            c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'dlow{month}','D','D1',f'2026-{month:02d}-14','14X26:12:00:00','Groceries',-1000,10000,'purchase',None,None,100+month,f'dlow{month}','{}'))
            c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'dsalary{month}','D','D1',f'2026-{month:02d}-15','15X26:12:00:00','Salary',100000,110000,'salary',None,None,200+month,f'dsalary{month}','{}'))
        c.commit()
        insufficient=payday_timing_signal(c,'D','2026-09')
        self.assertFalse(insufficient['available']); self.assertFalse(insufficient['qualified'])
        c.close()
