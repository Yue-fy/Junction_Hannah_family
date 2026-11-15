"""V4 lane N: one spending plan until payday, payday detection, profile inputs, goals consistency."""
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scoach.db import connect
from scoach.forecast import cluster_paydays, next_payday, spending_plan, safe_to_spend, safe_until_payday
from test_safe_until_payday import build, base, MONTHS

DEMO = Path(__file__).resolve().parents[1] / 'var/scoach.sqlite3'
PERSONAS = ('CUST00001', 'CUST00296', 'CUST00676', 'CUST00756', 'CUST01331', 'CUST05097')


def with_fun(extra=()):
    """base() plus regular eating out (free-choice spending) and a health cost."""
    rows = base(extra=extra)
    d = date(2026, 4, 3)
    while d <= date(2026, 9, 30):
        rows.append((d.isoformat(), 'Restaurants', -3000, 'purchase', 'R%d' % d.toordinal()))
        d += timedelta(days=5)
    rows.append(('2026-08-12', 'Health', -9000, 'purchase', 'DOC'))
    return rows


class PaydayTests(unittest.TestCase):
    def test_alex_pattern_mid_month_and_month_end_never_the_median(self):
        dates = [date(2026, 4, 15), date(2026, 5, 29), date(2026, 6, 30), date(2026, 7, 31), date(2026, 8, 15), date(2026, 9, 15),
                 date(2026, 3, 15), date(2026, 2, 15), date(2026, 1, 15)]
        pattern = cluster_paydays(dates)
        self.assertEqual(pattern['dominant']['day'], 15)
        self.assertEqual([c['kind'] for c in pattern['clusters']], ['day', 'month_end'])
        self.assertTrue(pattern['regular'])
        pattern['salary_dates'] = [d.isoformat() for d in sorted(dates)]
        self.assertEqual(next_payday(pattern, date(2026, 9, 10)), (date(2026, 9, 15), 'detected'))
        self.assertEqual(next_payday(pattern, date(2026, 9, 30)), (date(2026, 10, 15), 'detected'))
        # Salary did not arrive on the 15th of July: the month-end pay day seen in history is next.
        pattern2 = cluster_paydays([d for d in dates if d < date(2026, 7, 1)])
        pattern2['salary_dates'] = sorted(d.isoformat() for d in dates if d < date(2026, 7, 1))
        self.assertEqual(next_payday(pattern2, date(2026, 7, 20)), (date(2026, 7, 31), 'detected_late'))
        for reference in (date(2026, 9, 10), date(2026, 9, 30), date(2026, 7, 20)):
            self.assertNotEqual(next_payday(pattern, reference)[0].day, 22)

    def test_weekend_rule_follows_history(self):
        # Salaries always on banking days -> a weekend pay day moves to the Friday before.
        weekdays = [date(2026, m, 15) for m in (4, 5, 6, 7, 9) if date(2026, m, 15).weekday() < 5]
        pattern = cluster_paydays(weekdays)
        pattern['salary_dates'] = [d.isoformat() for d in weekdays]
        self.assertEqual(pattern['weekend_rule'], 'previous_banking_day')
        self.assertEqual(next_payday(pattern, date(2026, 10, 20))[0], date(2026, 11, 13))  # 15 Nov 2026 is a Sunday
        # Salary has arrived on a Saturday before -> keep the calendar day.
        saturday = weekdays + [date(2026, 8, 15)]
        pattern = cluster_paydays(saturday)
        pattern['salary_dates'] = sorted(d.isoformat() for d in saturday)
        self.assertEqual(pattern['weekend_rule'], 'same_day')
        self.assertEqual(next_payday(pattern, date(2026, 10, 20))[0], date(2026, 11, 15))

    def test_irregular_pay_is_flagged_and_after_reference(self):
        dates = [date(2025, 10, 24), date(2025, 11, 12), date(2025, 12, 11), date(2026, 1, 12), date(2026, 2, 20), date(2026, 3, 15),
                 date(2026, 4, 25), date(2026, 5, 30), date(2026, 6, 22), date(2026, 7, 9), date(2026, 8, 21), date(2026, 9, 10)]
        pattern = cluster_paydays(dates)
        pattern['salary_dates'] = [d.isoformat() for d in dates]
        self.assertFalse(pattern['regular'])
        day, source = next_payday(pattern, date(2026, 9, 29))
        self.assertEqual(source, 'irregular')
        self.assertGreater(day, date(2026, 9, 29))

    def test_demo_alex_payday_is_the_15th(self):
        if not DEMO.exists() or DEMO.stat().st_size == 0:
            self.skipTest('demo database missing')
        c = connect(str(DEMO))
        try:
            self.assertEqual(spending_plan(c, 'CUST00001', '2026-09-10')['next_payday'], '2026-09-15')
            plan = spending_plan(c, 'CUST00001', '2026-09-30')
            self.assertEqual(plan['next_payday'], '2026-10-15')
            self.assertEqual(plan['days_to_payday'], 15)
            from scoach.forecast import detect_recurring
            salary = [r for r in detect_recurring(c, 'CUST00001', '2026-09-30') if r['transaction_type'] == 'salary'][0]
            self.assertEqual(salary['median_day'], 15)
        finally:
            c.close()


class PlanInvariantTests(unittest.TestCase):
    def test_spendable_plus_extra_is_free_and_cap_applies(self):
        c, balance = build(with_fun(), start_balance=3_000_000)
        p = spending_plan(c, 'C', '2026-09-30')
        self.assertEqual(p['spendable_until_payday_cents'] + p['extra_cents'], p['free_cents'])
        self.assertEqual(p['free_cents'], balance - p['held_back_cents'] - p['everyday_cents'])
        self.assertEqual(p['spendable_until_payday_cents'], p['cap_cents'])
        self.assertGreater(p['extra_cents'], 0)
        self.assertEqual(p['safe_to_save_cents'], p['extra_cents'])
        self.assertEqual(p['per_day_cents'], p['daily_life_cents'] // p['days_to_payday'])
        self.assertEqual(p['daily_life_cents'], max(p['everyday_cents'] - p['shortfall_cents'], 0) + p['spendable_until_payday_cents'])
        self.assertEqual({h['kind'] for h in p['held_back']} >= {'bill', 'buffer', 'reserve'}, True)
        self.assertGreater(p['buffer_cents'], 0)
        for locale in ('en', 'fi', 'sv'):
            self.assertTrue(p['summary'][locale]); self.assertEqual(len(p['assumption_texts'][locale]), len(p['assumptions']))
        self.assertIn('€', p['summary']['fi'][0]); self.assertIn(',', p['summary']['fi'][0])
        c.close()

    def test_legacy_names_return_the_same_numbers(self):
        c, _ = build(with_fun(), start_balance=500_000)
        plan = spending_plan(c, 'C', '2026-09-30')
        for other in (safe_until_payday(c, 'C', '2026-09-30'), safe_to_spend(c, 'C', '2026-09-30', days=7), safe_to_spend(c, 'C', '2026-09-30')):
            for key in ('free_cents', 'per_day_cents', 'this_week_cents', 'extra_cents', 'next_payday', 'fact_id'):
                self.assertEqual(other[key], plan[key])
        c.close()

    def test_date_after_last_observed_day_uses_last_day(self):
        c, _ = build(with_fun())
        self.assertEqual(spending_plan(c, 'C', '2026-10-05')['as_of'], '2026-09-30')
        c.close()


class ProfileInputTests(unittest.TestCase):
    """Each money-profile input still changes the spending plan."""

    def setUp(self):
        self.c, _ = build(with_fun(), start_balance=600_000)
        self.plain = spending_plan(self.c, 'C', '2026-09-30')

    def tearDown(self):
        self.c.close()

    def plan(self, **profile):
        return spending_plan(self.c, 'C', '2026-09-30', profile=profile)

    def test_steady_mode_bigger_reserve_and_no_more_than_usual(self):
        p = self.plan(coaching_mode='steady', saving_rate_target_pct=10)
        self.assertGreater(p['reserve_floor_cents'], self.plain['reserve_floor_cents'])
        self.assertEqual(p['planned_saving_cents'], 0)
        self.assertLess(p['cap_cents'], self.plain['cap_cents'])
        self.assertIn('steady_reserve', [h['key'] for h in p['held_back']])

    def test_saving_target_is_held_back(self):
        p = self.plan(saving_rate_target_pct=10)
        self.assertIn(('goal', 30000), [(h['kind'], h['amount_cents']) for h in p['held_back']])
        self.assertEqual(p['free_cents'], self.plain['free_cents'] - 30000)

    def test_debt_is_held_back_as_loan(self):
        p = self.plan(debts=[{'type': 'student_loan', 'monthly_payment_cents': 12000}])
        self.assertIn(('loan', 12000), [(h['kind'], h['amount_cents']) for h in p['held_back']])
        self.assertEqual(p['free_cents'], self.plain['free_cents'] - 12000)

    def test_regular_investing_is_held_back(self):
        p = self.plan(regular_investing={'active': True, 'monthly_cents': 7000})
        self.assertEqual(p['free_cents'], self.plain['free_cents'] - 7000)

    def test_protected_category_moves_to_everyday(self):
        p = self.plan(protected_categories=['Restaurants'])
        self.assertGreater(p['everyday_cents'], self.plain['everyday_cents'])
        self.assertLess(p['cap_cents'], self.plain['cap_cents'])
        self.assertEqual(p['protected_categories'], ['Restaurants'])
        self.assertTrue(any('Ravintolat' in line for line in p['assumption_texts']['fi']))

    def test_emergency_fund_months_raise_the_buffer(self):
        p = self.plan(emergency_fund_target_months=3)
        self.assertIsNone(self.plain['emergency_fund'])
        fund = p['emergency_fund']
        self.assertEqual(fund['target_cents'], 3 * fund['must_pays_monthly_cents'])
        self.assertEqual(fund['this_payday_cents'], round(fund['target_cents'] / 12 * p['days_to_payday'] / 30))
        self.assertEqual(p['buffer_cents'], max(fund['this_payday_cents'], self.plain['buffer_cents']))
        self.assertGreater(p['buffer_cents'], self.plain['buffer_cents'])
        self.assertIn('emergency_fund', [h['key'] for h in p['held_back'] if h['kind'] == 'buffer'])
        self.assertEqual(p['free_cents'], self.plain['free_cents'] - (p['buffer_cents'] - self.plain['buffer_cents']))
        bigger = self.plan(emergency_fund_target_months=6)
        self.assertGreater(bigger['buffer_cents'], p['buffer_cents'])

    def test_tax_set_aside_is_held_back(self):
        p = self.plan(tax_set_aside_monthly_cents=4000)
        self.assertIn(('tax', 4000), [(h['kind'], h['amount_cents']) for h in p['held_back']])

    def test_plan_set_asides_from_switched_on_plans(self):
        mortgage = {'kind': 'loan', 'plan': 'mortgage', 'label': 'Mortgage payment', 'amount_cents': 65000, 'day_of_month': 5,
                    'until': '2040-06', 'dedupe_hint': {'transaction_type': 'housing_payment', 'amount_cents': 65000}}
        tax = {'kind': 'tax', 'plan': 'tax', 'label': 'Money for back taxes', 'amount_cents': 8000, 'day_of_month': None,
               'until': '2027-03', 'dedupe_hint': None}
        p = self.plan(plan_set_asides=[mortgage, tax], plan_set_asides_monthly_total_cents=73000)
        loans = [h for h in p['held_back'] if h['kind'] == 'loan']
        self.assertEqual([(h['label'], h['amount_cents']) for h in loans], [('Mortgage payment', 65000)])
        self.assertEqual(loans[0]['labels']['fi'], 'Asuntolainan erä')
        self.assertIn(('tax', 8000, 'Money for back taxes'), [(h['kind'], h['amount_cents'], h['label']) for h in p['held_back']])
        self.assertEqual(p['free_cents'], self.plain['free_cents'] - 73000)
        self.assertEqual(p['committed_cents'], self.plain['committed_cents'] + 73000)

    def test_mortgage_plan_already_paid_as_rent_is_not_held_twice(self):
        # The fixture pays €800 housing every month; a mortgage plan of the same payment is that money.
        mortgage = {'kind': 'loan', 'plan': 'mortgage', 'label': 'Mortgage payment', 'amount_cents': 80500, 'day_of_month': 10,
                    'until': None, 'dedupe_hint': {'transaction_type': 'housing_payment', 'amount_cents': 80500}}
        p = self.plan(plan_set_asides=[mortgage])
        self.assertEqual(p['free_cents'], self.plain['free_cents'])
        self.assertEqual([s['plan'] for s in p['skipped_declared_items']], ['mortgage'])
        self.assertFalse([h for h in p['held_back'] if h['kind'] == 'loan'])

    def test_finished_plan_is_not_held_back(self):
        tax = {'kind': 'tax', 'plan': 'tax', 'label': 'Money for back taxes', 'amount_cents': 8000, 'until': '2026-05', 'dedupe_hint': None}
        self.assertEqual(self.plan(plan_set_asides=[tax])['free_cents'], self.plain['free_cents'])

    def test_invalid_profile_rejected(self):
        for bad in ({'protected_categories': 'Restaurants'}, {'emergency_fund_target_months': 30}, {'tax_set_aside_monthly_cents': -1}):
            with self.assertRaises(ValueError):
                spending_plan(self.c, 'C', '2026-09-30', profile=bad)


class DemoPersonaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DEMO.exists() or DEMO.stat().st_size == 0:
            raise unittest.SkipTest('demo database missing')
        cls.folder = tempfile.mkdtemp()
        path = os.path.join(cls.folder, 'copy.sqlite3'); shutil.copy(DEMO, path)
        cls.c = connect(path)

    @classmethod
    def tearDownClass(cls):
        cls.c.close(); shutil.rmtree(cls.folder)

    def test_every_persona_plan_adds_up(self):
        for cid in PERSONAS:
            with self.subTest(cid=cid):
                p = spending_plan(self.c, cid, '2026-09-30')
                self.assertEqual(p['spendable_until_payday_cents'] + p['extra_cents'], p['free_cents'])
                self.assertLessEqual(p['this_week_cents'], p['daily_life_cents'])
                self.assertGreaterEqual(p['free_cents'], 0)
                self.assertNotEqual(date.fromisoformat(p['next_payday']).day, 22)

    def test_savers_get_sensible_spending_and_the_rest_as_could_be_saved(self):
        for cid in ('CUST00296', 'CUST05097'):
            with self.subTest(cid=cid):
                p = spending_plan(self.c, cid, '2026-09-30')
                self.assertLess(p['this_week_cents'], 100_000)  # was €11k-15k a week
                self.assertGreater(p['extra_cents'], 1_000_000)

    def test_goal_capacity_agrees_with_plan(self):
        from scoach.goals import create_goal
        g = create_goal(self.c, 'CUST00001', 'A summer in Italy', 300000, '2027-03-31', as_of='2026-09-30')
        plan = spending_plan(self.c, 'CUST00001', '2026-09-30')
        self.assertEqual(g['upfront_available_cents'], plan['extra_cents'])
        self.assertEqual(g['could_save_now_cents'], plan['extra_cents'])
        self.assertGreater(g['conservative_monthly_contribution_cents'], 0)
        # €3,000 is reachable: what could be saved now covers most of it, so no big monthly gap remains.
        self.assertEqual(g['monthly_gap_cents'], 0)

    def test_api_has_one_answer_for_every_horizon(self):
        from scoach.api import Application
        app = Application(os.path.join(self.folder, 'copy.sqlite3'))
        answers = []
        for query in ('', '&days=7', '&horizon=until_payday', '&horizon=week&days=7', '&as_of=2026-09-30'):
            status, body = app.handle('GET', '/api/safe-to-spend?customer_id=CUST00001&month=2026-09' + query)
            self.assertEqual(status, 200, body)
            answers.append((body['data']['this_week_cents'], body['data']['next_payday'], body['data']['extra_cents']))
        self.assertEqual(len(set(answers)), 1)
        status, body = app.handle('GET', '/api/safe-to-spend?customer_id=CUST00296&as_of=2026-09-30')
        self.assertEqual(status, 200, body)
        self.assertEqual(body['data']['as_of'], '2026-09-27')


if __name__ == '__main__':
    unittest.main()
