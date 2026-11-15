"""WP-D: safe to spend until payday and safe to save."""
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from scoach.db import connect, initialize_schema
from scoach.forecast import safe_until_payday, safe_to_spend

MONTHS = range(4, 10)  # April..September 2026


def build(rows_spec, start_balance=100000):
    """rows_spec: list of (iso_date, category, amount_cents, transaction_type, merchant_id)."""
    c = connect(':memory:'); initialize_schema(c)
    c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
    balance = start_balance
    for i, (day, category, amount, kind, merchant) in enumerate(sorted(rows_spec)):
        balance += amount
        c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  ('t%d' % i, 'C', 'A', day, '01X26:12:00:00', category, amount, balance, kind, merchant, None, i, 'h%d' % i, '{}'))
    c.commit()
    return c, balance


def groceries():
    rows = []
    d = date(2026, 4, 1)
    while d <= date(2026, 9, 30):
        rows.append((d.isoformat(), 'Groceries', -5000, 'purchase', 'M%d' % d.toordinal()))
        d += timedelta(days=7)
    return rows


def base(salary=True, extra=()):
    rows = groceries() + list(extra)
    for m in MONTHS:
        rows.append(('2026-%02d-10' % m, 'Housing', -80000, 'housing_payment', None))
        if salary:
            rows.append(('2026-%02d-25' % m, 'Salary', 300000, 'salary', None))
    return rows


class SafeUntilPaydayTests(unittest.TestCase):
    def test_rent_before_payday_is_held_back(self):
        c, balance = build(base())
        r = safe_until_payday(c, 'C', as_of='2026-09-30')
        self.assertEqual(r['next_payday'], '2026-10-25'); self.assertEqual(r['days_until_payday'], 25)
        self.assertEqual(r['payday_source'], 'detected')
        self.assertEqual(r['starting_balance_cents'], balance)
        self.assertEqual(r['committed_cents'], 80000)
        self.assertEqual([i['date'] for i in r['committed_items']], ['2026-10-10'])
        # V4: everyday costs (groceries) are held back too, so free = balance - rent - cushion - everyday.
        free = balance - 50000 - 80000 - r['everyday_cents']
        self.assertGreater(r['everyday_cents'], 0)
        self.assertEqual(r['free_cents'], free)
        self.assertEqual(r['spendable_until_payday_cents'] + r['extra_cents'], free)
        self.assertEqual(r['per_day_cents'], r['daily_life_cents'] // 25)
        self.assertEqual(r['this_week_cents'], r['per_day_cents'] * 7)
        # The legacy name returns the same plan (the seven-day path is gone).
        self.assertEqual(safe_to_spend(c, 'C', as_of='2026-09-30')['scheduled_outflows_cents'], 80000)
        self.assertEqual(r['chart']['kind'], 'runway')
        self.assertEqual(r['chart']['series'][-1]['label'], '2026-10-25')
        self.assertEqual(len(r['chart']['series']), 25)
        self.assertTrue(r['fact_id'].startswith('spending-plan:'))
        self.assertIn(r['starting_transaction_ref'], r['transaction_refs'])
        self.assertEqual({x['key'] for x in r['components']} >= {'balance', 'reserve', 'committed', 'planned_saving', 'free', 'per_day', 'this_week', 'safe_to_save'}, True)
        c.close()

    def test_payday_already_passed_this_month_and_short_month(self):
        c, _ = build(base())
        self.assertEqual(safe_until_payday(c, 'C', as_of='2026-09-25')['next_payday'], '2026-10-25')
        self.assertEqual(safe_until_payday(c, 'C', as_of='2026-09-24')['next_payday'], '2026-09-25')
        c.close()
        rows = groceries()
        for m in MONTHS:
            rows.append(('2026-%02d-%02d' % (m, 30 if m in (4, 6, 9) else 31), 'Salary', 300000, 'salary', None))
        c, _ = build(rows)
        # Salary on the 31st is moved to the last day of shorter months.
        self.assertEqual(safe_until_payday(c, 'C', as_of='2026-09-15')['next_payday'], '2026-09-30')
        c.close()

    def test_no_salary_falls_back_to_30_days(self):
        c, _ = build(base(salary=False), start_balance=900000)
        r = safe_until_payday(c, 'C', as_of='2026-09-30')
        self.assertEqual(r['payday_source'], 'fallback_30_days'); self.assertEqual(r['days_until_payday'], 30)
        self.assertEqual(r['next_payday'], '2026-10-30')
        self.assertTrue(any('30 days ahead' in a for a in r['assumptions']))
        self.assertEqual(r['committed_cents'], 80000)
        c.close()

    def test_saving_target_reduces_spendable(self):
        c, _ = build(base())
        plain = safe_until_payday(c, 'C', as_of='2026-09-30')
        saving = safe_until_payday(c, 'C', as_of='2026-09-30', profile={'saving_rate_target_pct': 10})
        self.assertIn(('goal', 30000), [(h['kind'], h['amount_cents']) for h in saving['held_back']])
        self.assertEqual(saving['planned_saving_cents'], 30000)
        self.assertEqual(saving['free_cents'], plain['free_cents'] - 30000)
        self.assertLessEqual(saving['per_day_cents'], plain['per_day_cents'])
        self.assertEqual(saving['extra_cents'], plain['extra_cents'] - 30000)
        self.assertEqual(plain['planned_saving_cents'], 0)
        with self.assertRaises(ValueError):
            safe_until_payday(c, 'C', as_of='2026-09-30', profile={'saving_rate_target_pct': 120})
        with self.assertRaises(ValueError):
            safe_until_payday(c, 'C', as_of='2026-09-30', profile={'coaching_mode': 'panic'})
        c.close()

    def test_declared_debt_not_double_counted_when_recurring(self):
        loan = [('2026-%02d-15' % m, 'Loan', -20000, 'purchase', 'BANK') for m in MONTHS]
        c, _ = build(base(extra=loan), start_balance=500000)
        plain = safe_until_payday(c, 'C', as_of='2026-09-30')
        self.assertEqual(plain['committed_cents'], 100000)  # rent + detected loan
        r = safe_until_payday(c, 'C', as_of='2026-09-30', profile={
            'debts': [{'type': 'car loan', 'monthly_payment_cents': 20500}, {'type': 'card', 'monthly_payment_cents': 10000}],
            'regular_investing': {'active': False, 'monthly_cents': 99999}})
        self.assertEqual(r['committed_cents'], 110000)  # only the undetected card counted
        self.assertEqual([s['label'] for s in r['skipped_declared_items']], ['Debt payment (car loan)'])
        self.assertEqual([i['source'] for i in r['committed_items'] if i['source'] == 'declared'], ['declared'])
        invest = safe_until_payday(c, 'C', as_of='2026-09-30', profile={'regular_investing': {'active': True, 'monthly_cents': 5000}})
        self.assertEqual(invest['committed_cents'], 105000)
        c.close()

    def test_steady_mode_raises_reserve_and_zeroes_saving(self):
        c, _ = build(base(), start_balance=500000)
        r = safe_until_payday(c, 'C', as_of='2026-09-30', profile={'coaching_mode': 'steady', 'saving_rate_target_pct': 10})
        self.assertTrue(r['steady_mode']); self.assertEqual(r['planned_saving_cents'], 0)
        # Must-pays = rent + groceries (fixed_obligation) over July-September, averaged.
        groceries_total = -sum(a for d, cat, a, k, mm in groceries() if '2026-07-01' <= d <= '2026-09-30')
        expected = round((3 * 80000 + groceries_total) / 3)
        self.assertEqual(r['must_pays_monthly_cents'], expected)
        self.assertEqual(r['reserve_floor_cents'], expected); self.assertGreater(expected, 50000)
        self.assertEqual(r['reserve_floor_source'], 'steady_mode_must_pays')
        override = safe_until_payday(c, 'C', as_of='2026-09-30', profile={'coaching_mode': 'steady', 'must_pays_monthly_cents': 123456})
        self.assertEqual(override['reserve_floor_cents'], 123456)
        # An explicit larger reserve is kept.
        bigger = safe_until_payday(c, 'C', as_of='2026-09-30', reserve_floor_cents=999999, profile={'coaching_mode': 'steady'})
        self.assertEqual(bigger['reserve_floor_cents'], 999999)
        c.close()

    def test_safe_to_save_never_negative_and_shortfall_reported(self):
        c, balance = build(base(), start_balance=-1200000)
        r = safe_until_payday(c, 'C', as_of='2026-09-30')
        # free is floored at zero; the gap is reported separately.
        self.assertEqual(r['free_cents'], 0)
        self.assertEqual(r['shortfall_cents'], r['held_back_cents'] + r['everyday_cents'] - r['starting_balance_cents'])
        self.assertGreater(r['shortfall_cents'], 0)
        self.assertEqual(r['per_day_cents'], 0); self.assertEqual(r['this_week_cents'], 0)
        self.assertEqual(r['safe_to_save_cents'], 0); self.assertEqual(r['spendable_cents'], 0)
        c.close()
        c, balance = build(base(), start_balance=2000000)
        r = safe_until_payday(c, 'C', as_of='2026-09-30')
        # Plenty of money: spending is capped at a comfortable pace, the rest could be saved, never both.
        self.assertEqual(r['safe_to_save_cents'], r['free_cents'] - r['spendable_until_payday_cents'])
        self.assertEqual(r['spendable_until_payday_cents'], r['cap_cents'])
        self.assertGreater(r['safe_to_save_cents'], 0)
        c.close()

    def test_invalid_reserve_rejected(self):
        c, _ = build(base())
        for bad in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                safe_until_payday(c, 'C', as_of='2026-09-30', reserve_floor_cents=bad)
        c.close()

    def test_demo_database_smoke(self):
        source = Path(__file__).resolve().parents[1] / 'var/scoach.sqlite3'
        if not source.exists():
            self.skipTest('demo database missing')
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, 'copy.sqlite3'); shutil.copy(source, path)
            c = connect(path)
            try:
                old = safe_to_spend(c, 'CUST00001', as_of='2026-09-30')
                new = safe_until_payday(c, 'CUST00001', as_of='2026-09-30')
                self.assertEqual(new['payday_source'], 'detected')
                self.assertEqual(new['next_payday'], '2026-10-15')
                self.assertEqual(new['this_week_cents'], old['safe_to_spend_cents'])
                self.assertGreaterEqual(new['safe_to_save_cents'], 0)
            finally:
                c.close()
        finally:
            shutil.rmtree(folder)


if __name__ == '__main__':
    unittest.main()
