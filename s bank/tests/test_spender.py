import shutil
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from scoach.db import connect, initialize_schema
from scoach import spender
from scoach.spender import ARCHETYPE_LABELS, irregular_buffer, offline_summary, spender_profile

MONTHS = ('2026-04', '2026-05', '2026-06')


def _days(month, predicate):
    first = date.fromisoformat(month + '-01')
    day = first
    out = []
    while day.month == first.month:
        if predicate(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def weekdays(month, last=20):
    return _days(month, lambda d: d.weekday() < 5 and d.day <= last)


def saturdays(month, last=20):
    return _days(month, lambda d: d.weekday() == 5 and d.day <= last)


class Ledger:
    def __init__(self, months=MONTHS, saving_cents=0):
        self.c = connect(':memory:')
        initialize_schema(self.c)
        self.c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        self.n = 0
        for month in months:
            self.add(month + '-01', 'Housing', -80000, 'housing_payment')
            for day in (3, 10, 17):
                self.add(month + '-%02d' % day, 'Groceries', -5000)
            self.add(month + '-25', 'Salary', 300000, 'salary')
            if saving_cents:
                self.add(month + '-26', 'Invest Deposit', -saving_cents, 'investment_deposit')

    def add(self, day, category, amount, kind='purchase'):
        if isinstance(day, date):
            day = day.isoformat()
        self.n += 1
        d = date.fromisoformat(day)
        stamp = d.strftime('%d%b%y').upper() + ':12:00:%02d' % (self.n % 60)
        self.c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       ('t%d' % self.n, 'C', 'A', day, stamp, category, amount, 100000, kind, None, None, self.n, 'h', '{}'))

    def profile(self, **kwargs):
        self.c.commit()
        return spender_profile(self.c, 'C', **kwargs)


class ArchetypeTests(unittest.TestCase):
    def test_payday_sprinter(self):
        ledger = Ledger()
        for month in MONTHS:
            for day in range(25, 31):
                ledger.add(month + '-%02d' % day, 'Restaurants', -3000)
        p = ledger.profile()
        self.assertEqual(p['archetype'], 'payday_sprinter')
        self.assertEqual(p['archetype_label'], 'Payday Sprinter')
        self.assertEqual(p['figures']['little_leaks']['payday_share_percent'], '100.0')
        self.assertEqual(p['why'][0]['fact'], 'payday_share')

    def test_weekend_spender(self):
        ledger = Ledger()
        for month in MONTHS:
            for day in saturdays(month):
                ledger.add(day, 'Entertainment', -3000)
            ledger.add(weekdays(month)[0], 'Restaurants', -1000)
        p = ledger.profile()
        self.assertEqual(p['archetype'], 'weekend_spender')
        self.assertGreaterEqual(Decimal(p['figures']['little_leaks']['weekend_share_percent']), spender.WEEKEND_SHARE_MIN)
        self.assertEqual(p['figures']['top_little_leaks_categories'][0]['category'], 'Entertainment')

    def test_small_and_often(self):
        ledger = Ledger()
        for month in MONTHS:
            for day in range(1, 25):
                ledger.add(month + '-%02d' % day, 'Restaurants', -500)
        p = ledger.profile()
        self.assertEqual(p['archetype'], 'small_and_often')
        little = p['figures']['little_leaks']
        self.assertEqual(little['median_purchase_cents'], 500)
        # 72 purchases over 91 days -> 5.5 a week
        self.assertEqual(little['purchases_per_week'], '5.5')

    def test_big_ticket_occasional(self):
        ledger = Ledger()
        for month in MONTHS:
            days = weekdays(month)
            ledger.add(days[0], 'Travel', -20000)
            ledger.add(days[1], 'Restaurants', -1000)
            ledger.add(days[2], 'Restaurants', -1000)
        p = ledger.profile()
        self.assertEqual(p['archetype'], 'big_ticket_occasional')
        self.assertEqual(p['figures']['little_leaks']['big_ticket_share_percent'], '90.9')
        top = p['figures']['top_little_leaks_categories'][0]
        self.assertEqual((top['category'], top['annualised_cents']), ('Travel', 240000))

    def _steady_leaks(self, ledger):
        for month in MONTHS:
            for day in weekdays(month)[:4]:
                ledger.add(day, 'Restaurants', -2000)

    def test_steady_planner(self):
        ledger = Ledger(saving_cents=40000)
        self._steady_leaks(ledger)
        p = ledger.profile()
        self.assertEqual(p['archetype'], 'steady_planner')
        self.assertEqual(p['figures']['saving']['share_of_salary_percent'], '13.3')
        self.assertEqual(p['figures']['baskets']['discretionary']['variability_percent'], '0.0')
        self.assertEqual(p['why'][0]['fact'], 'saving_share')

    def test_balanced(self):
        ledger = Ledger()
        self._steady_leaks(ledger)
        p = ledger.profile()
        self.assertEqual(p['archetype'], 'balanced')
        self.assertEqual(p['archetype_label'], 'Balanced')

    def test_result_shape_and_shares_sum(self):
        ledger = Ledger()
        self._steady_leaks(ledger)
        for month in MONTHS:
            ledger.add(month + '-12', 'Health', -3333)
        p = ledger.profile()
        self.assertEqual(p['months_used'], 3)
        self.assertEqual(p['period'], {'start': '2026-04-01', 'end': '2026-06-30'})
        self.assertEqual(p['label_note'], 'A description of your last 3 months. It changes as your habits do.')
        shares = [Decimal(b['share_percent']) for b in p['figures']['baskets'].values()]
        self.assertLessEqual(abs(sum(shares) - 100), Decimal('0.2'))
        self.assertTrue(2 <= len(p['why']) <= 3)
        for item in p['why'] + [p['strength'], p['watch']]:
            self.assertIn('fact', item)
            self.assertIsInstance(item['text'], str)
            if 'percent' in item:
                self.assertRegex(item['percent'], r'^\d+\.\d$')
        self.assertTrue(p['transaction_refs'])
        self.assertEqual(p['figures']['consumption_cents'], 3 * (80000 + 15000 + 8000 + 3333))

    def test_unavailable_with_one_month(self):
        ledger = Ledger(months=('2026-06',))
        for day in weekdays('2026-06')[:4]:
            ledger.add(day, 'Restaurants', -2000)
        p = ledger.profile()
        self.assertFalse(p['available'])
        self.assertIn('reason', p)
        self.assertEqual(p['months_used'], 1)
        for locale in ('en', 'fi', 'sv'):
            self.assertTrue(offline_summary(p, locale))

    def test_bad_arguments(self):
        ledger = Ledger()
        with self.assertRaises(ValueError):
            ledger.profile(months=0)
        with self.assertRaises(ValueError):
            ledger.profile(end_month='2027-01')

    def test_offline_summary_locales(self):
        ledger = Ledger()
        for month in MONTHS:
            for day in range(25, 31):
                ledger.add(month + '-%02d' % day, 'Restaurants', -3000)
        p = ledger.profile()
        for locale in ('en', 'fi', 'sv'):
            text = offline_summary(p, locale)
            self.assertIn(ARCHETYPE_LABELS['payday_sprinter'][locale], text)
            self.assertIn('100', text)
        self.assertIn('Payday Sprinter', offline_summary(p, 'xx'))


class BufferTests(unittest.TestCase):
    def test_hand_computed_average(self):
        ledger = Ledger()  # groceries -5000 three times a month = 9 purchases, median 5000
        ledger.add('2026-04-14', 'Health', -10000)
        ledger.add('2026-05-14', 'Health', -5000)
        ledger.add('2026-05-20', 'Groceries', -20000)   # > 3 x 5000 -> counted
        ledger.add('2026-06-20', 'Groceries', -15000)   # == 3 x 5000 -> not counted
        ledger.add('2026-06-21', 'Restaurants', -90000)  # Little leaks -> not counted
        ledger.c.commit()
        b = irregular_buffer(ledger.c, 'C', end_month='2026-06', months=3)
        self.assertEqual(b['months_used'], 3)
        self.assertEqual(b['count'], 3)
        self.assertEqual(b['total_cents'], 35000)
        self.assertEqual(b['monthly_average_cents'], 11667)  # 35000 / 3, half-up
        self.assertEqual(b['suggested_monthly_set_aside_cents'], 11667)
        self.assertEqual(b['largest'], {'category': 'Groceries', 'date': '2026-05-20', 'amount_cents': 20000})
        self.assertEqual([i['amount_cents'] for i in b['items']], [20000, 10000, 5000])
        self.assertEqual(b['period'], {'start': '2026-04-01', 'end': '2026-06-30'})
        self.assertEqual(len(b['transaction_refs']), 3)

    def test_items_capped(self):
        ledger = Ledger()
        for i in range(25):
            ledger.add('2026-05-%02d' % (i + 1), 'Health', -(1000 + i))
        ledger.c.commit()
        b = irregular_buffer(ledger.c, 'C', months=3)
        self.assertEqual(b['count'], 25)
        self.assertEqual(len(b['items']), 20)
        self.assertTrue(b['items_truncated'])


class DemoSmokeTest(unittest.TestCase):
    def test_real_demo_customer(self):
        source = Path(__file__).resolve().parents[1] / 'var/scoach.sqlite3'
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / 'demo.sqlite3'
            shutil.copy(source, copy)
            conn = connect(copy)
            try:
                p = spender_profile(conn, 'CUST00001')
                self.assertTrue(p['available'])
                self.assertIn(p['archetype'], spender.ARCHETYPE_PRIORITY)
                self.assertEqual(p['months_used'], 6)
                shares = [Decimal(b['share_percent']) for b in p['figures']['baskets'].values()]
                self.assertLessEqual(abs(sum(shares) - 100), Decimal('0.2'))
                for locale in ('en', 'fi', 'sv'):
                    self.assertIn(ARCHETYPE_LABELS[p['archetype']][locale], offline_summary(p, locale))
                b = irregular_buffer(conn, 'CUST00001')
                self.assertEqual(b['months_used'], 12)
                self.assertGreater(b['count'], 0)
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
