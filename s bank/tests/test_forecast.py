import unittest
from datetime import date, timedelta
from tests.core_helper import demo_connection
from scoach.db import connect, initialize_schema
from scoach.forecast import detect_recurring, preview_30_days, backtest_preview

class ForecastTests(unittest.TestCase):
    def setUp(self): self.c=demo_connection()
    def tearDown(self): self.c.close()
    def test_salary_housing_utilities_and_observed_projected_split(self):
        groups=detect_recurring(self.c,'CUST00676')
        types={r['transaction_type'] for r in groups}
        self.assertTrue({'salary','housing_payment','utilities_payment'}<=types)
        utility=next(r for r in groups if r['transaction_type']=='utilities_payment')
        self.assertEqual(utility['recurrence_kind'],'monthly envelope')
        self.assertTrue(utility['transaction_refs'])
        preview=preview_30_days(self.c,'CUST00676')
        self.assertEqual(preview['label'],'Pattern-based cash-flow preview')
        self.assertTrue(all(p['observed'] for p in preview['observed']))
        self.assertTrue(all(not p['observed'] for p in preview['projected']))
        self.assertEqual(len(preview['projected']),30)
        self.assertEqual(preview['scenario_band']['label'],'Historical variation — not a probability interval')
        self.assertEqual(set(preview['scenario_band']['spending_cents']),{'p25','p50','p75'})
        self.assertTrue(all(e['date']>preview['as_of'] for e in preview['scheduled_items']))
    def test_fixed_variable_cadence_and_transfer_semantics(self):
        c=connect(':memory:'); initialize_schema(c)
        c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        for i,month in enumerate(range(4,10)):
            for cat,kind,amount in [('Rent','housing_payment',-50000),('Salary','salary',200000),('Tax','purchase',[-10000,-30000,-10000,-30000,-10000,-30000][i]),('Invest Deposit','investment_deposit',-10000)]:
                c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'{cat}{month}','C','A',f'2026-{month:02d}-15',f'15X26:12:00:00',cat,amount,100000,kind,None,None,month,cat,'{}'))
        c.commit()
        groups=detect_recurring(c,'C',as_of='2026-09-30')
        tax=next(r for r in groups if r['category']=='Tax'); self.assertEqual(tax['recurrence_kind'],'variable recurring')
        rent=next(r for r in groups if r['transaction_type']=='housing_payment'); self.assertEqual(rent['recurrence_kind'],'fixed')
        transfer=next(r for r in groups if r['transaction_type']=='investment_deposit'); self.assertFalse(transfer['is_consumption'])
        p=preview_30_days(c,'C',as_of='2026-09-30'); self.assertTrue(any(e['transaction_type']=='investment_deposit' for e in p['scheduled_items']))
        c.close()
    def test_backtest_reports_error_without_confidence(self):
        result=backtest_preview(self.c,'CUST00676','2026-08-31')
        self.assertIsInstance(result['ending_balance_error_cents'],int)
        self.assertEqual(result['horizon_days'],30)
        self.assertNotIn('confidence',result)
        self.assertEqual(result['actual_end_date'],'2026-09-30')

    def test_utilities_require_five_months_and_projection_arithmetic(self):
        c=connect(':memory:'); initialize_schema(c); c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        for month in range(4,10):
            for cat,kind,amount,day in [('Rent','housing_payment',-50000,1),('Salary','salary',200000,15),('Invest Deposit','investment_deposit',-10000,15)]:
                c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'{cat}{month}','C','A',f'2026-{month:02d}-{day:02d}','15X26:12:00:00',cat,amount,100000,kind,None,None,month,cat,'{}'))
        c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('utility','C','A','2026-09-15','15X26:12:00:00','Utilities',-1000,100000,'utilities_payment',None,None,100,'u','{}')); c.commit()
        groups=detect_recurring(c,'C','2026-09-30')
        self.assertFalse(any(g['transaction_type']=='utilities_payment' for g in groups))
        preview=preview_30_days(c,'C','2026-09-30')
        self.assertEqual(preview['projected'][0]['confirmed_balance_cents'],50000)
        self.assertEqual(preview['projected'][-1]['confirmed_balance_cents'],240000)
        self.assertEqual(preview['projected'][-1]['balance_cents'],240000)
        for edits in ({'unknown':{}},{groups[0]['id']:{'median_day':0}}):
            with self.assertRaises(ValueError): preview_30_days(c,'C','2026-09-30',edits)
        c.close()

    def test_historical_p50_uses_half_up_median(self):
        c=connect(':memory:'); initialize_schema(c); c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        for i,(day,amount) in enumerate([('2026-08-30',-100),('2026-09-28',-201),('2026-09-29',-200)]):
            c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(str(i),'C','A',day,'30X26:12:00:00','Groceries',amount,1000,'purchase',None,None,i,'h','{}'))
        c.commit(); p=preview_30_days(c,'C','2026-09-30')
        self.assertEqual(p['scenario_band']['window_count'],2)
        self.assertEqual(p['scenario_band']['spending_cents'],{'p25':301,'p50':351,'p75':401})
        c.close()
