import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scoach.db import connect, initialize_schema
from scoach.year_review import year_review, year_options, mcc_label

WEDNESDAYS = ['2025-01-08', '2025-02-12', '2025-03-12', '2025-04-09', '2025-05-14', '2025-06-11',
              '2025-07-09', '2025-08-13', '2025-09-10', '2025-10-08', '2025-11-12', '2025-12-10']


class Fixture:
    def __init__(self):
        self.conn = connect(':memory:'); initialize_schema(self.conn); self.n = 0

    def customer(self, cid):
        self.conn.execute('INSERT INTO customers VALUES(?,?,?,?)', (cid, '00100', 30, '{}'))

    def row(self, cid, day, category, amount, kind='purchase', mcc=None):
        self.n += 1; ref = 'r{}'.format(self.n)
        self.conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (ref, cid, 'A-' + cid, day, '01JAN25:12:00:00', category, amount, 0, kind,
                           None, mcc, self.n, ref, '{}'))
        return ref


def build():
    f = Fixture(); f.customer('C')
    # 2024: Oct-Dec only (partial year).
    for m in ('10', '11', '12'):
        f.row('C', '2024-{}-01'.format(m), 'Income', 200000, 'salary')
        f.row('C', '2024-{}-15'.format(m), 'Groceries', -10000, mcc='5411')
        f.row('C', '2024-{}-16'.format(m), 'Savings', -10000, 'investment_deposit')
    # 2025: complete year.
    for i in range(12):
        m = '{:02d}'.format(i + 1)
        f.row('C', '2025-{}-01'.format(m), 'Income', 300000, 'salary')
        f.row('C', '2025-{}-02'.format(m), 'Housing', -80000, 'housing_payment')
        f.row('C', '2025-{}-03'.format(m), 'Savings', -20000, 'investment_deposit')
        f.row('C', WEDNESDAYS[i], 'Groceries', -10000, mcc='5411')
    f.row('C', '2025-03-15', 'Restaurants', -5000, mcc='5812')
    f.row('C', '2025-03-15', 'Restaurants', -7000, mcc='5812')
    travel = f.row('C', '2025-06-20', 'Travel', -150000, mcc='4511')
    f.row('C', '2025-06-20', 'Lifestyle', -3000, mcc='5311')
    f.row('C', '2025-05-05', 'Income', 5000, 'other_income')
    f.row('C', '2025-07-01', 'Savings', 10000, 'investment_withdrawal')
    f.row('C', '2026-01-05', 'Groceries', -1000, mcc='5411')
    # Tiny customer: two months of data.
    f.customer('D')
    f.row('D', '2025-01-03', 'Income', 100000, 'salary')
    f.row('D', '2025-02-03', 'Groceries', -1000, mcc='5411')
    f.conn.commit()
    return f.conn, travel


class YearReviewFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn, cls.travel_ref = build()
        cls.r = year_review(cls.conn, 'C', 2025)

    def test_completeness_and_totals(self):
        r = self.r
        self.assertTrue(r['available']); self.assertTrue(r['complete']); self.assertEqual(r['observed_months'], 12)
        self.assertEqual(r['money_in_cents'], 12 * 300000 + 5000)
        self.assertEqual(r['money_out_cents'], 960000 + 120000 + 12000 + 153000)
        self.assertEqual(r['saved_cents'], 12 * 20000 - 10000)
        self.assertEqual(r['saving_rate_percent'], '6.4')
        self.assertEqual(r['money_in'], '€36,050.00')

    def test_categories_baskets_leaks(self):
        r = self.r
        self.assertEqual(r['top_category'], {'category': 'Housing', 'cents': 960000, 'share_percent': '77.1'})
        baskets = {b['role']: b for b in r['baskets']}
        self.assertEqual(baskets['fixed_obligation']['cents'], 1080000)
        self.assertEqual(baskets['flexible_essential']['cents'], 0)
        self.assertEqual(baskets['discretionary']['cents'], 165000)
        self.assertEqual(r['little_leaks']['average_monthly_housing_cents'], 80000)
        self.assertEqual(r['little_leaks']['months_of_rent_equivalent'], '2.1')
        self.assertEqual(r['little_leaks']['share_percent'], '13.3')

    def test_days_months_purchases(self):
        r = self.r
        self.assertEqual(r['biggest_month'], {'month': '2025-06', 'cents': 243000})
        self.assertEqual(r['calmest_month'], {'month': '2025-01', 'cents': 90000})
        self.assertEqual((r['busiest_day']['date'], r['busiest_day']['cents'], r['busiest_day']['count']), ('2025-06-20', 153000, 2))
        self.assertEqual(r['largest_purchase'], {'category': 'Travel', 'date': '2025-06-20', 'cents': 150000,
                                                 'mcc_code': '4511', 'transaction_ref': self.travel_ref})
        self.assertEqual(r['purchase_count'], 16)
        self.assertEqual(r['favourite_weekday'], {'weekday': 'Wednesday', 'weekday_index': 2, 'count': 12})
        self.assertEqual(r['most_frequent_mcc'], {'mcc_code': '5411', 'count': 12, 'label': 'Groceries'})
        self.assertIn(self.travel_ref, r['transaction_refs'])

    def test_previous_year(self):
        p = self.r['previous_year']
        self.assertEqual((p['year'], p['complete'], p['observed_months'], p['comparable']), (2024, False, 3, False))
        self.assertEqual((p['money_in_cents'], p['money_out_cents'], p['saved_cents'], p['saving_rate_percent']), (600000, 30000, 30000, '5.0'))
        self.assertEqual(p['changes']['money_in'], {'delta_cents': 3005000, 'change_percent': '500.8'})
        self.assertEqual(p['saving_rate_delta_points'], '1.4')
        self.assertEqual(p['monthly_average_changes']['money_in']['delta_cents'], round(3605000 / 12) - 200000)
        self.assertIsNone(year_review(self.conn, 'C', 2024)['previous_year'])

    def test_cards(self):
        cards = self.r['cards']
        self.assertTrue(8 <= len(cards) <= 10)
        kinds = [c['kind'] for c in cards]
        self.assertEqual(kinds[0], 'intro'); self.assertEqual(kinds[-1], 'closing')
        self.assertNotIn('archetype', kinds)
        for card in cards:
            self.assertEqual(set(card), {'id', 'kind', 'facts', 'caption_template'})
            card['caption_template'].format(**card['facts'])
            for name in re.findall(r'{(\w+)}', card['caption_template']):
                self.assertIn(name, card['facts'])
        leaks = next(c for c in cards if c['kind'] == 'little_leaks')
        self.assertIn('2.1 months', leaks['caption_template'].format(**leaks['facts']))

    def test_archetype_and_goals_plumbing(self):
        calls = []

        def archetype(conn, cid, end_month, months):
            calls.append((cid, end_month, months))
            return {'archetype': 'Steady Planner' if end_month == '2025-12' else 'Weekend Spender'}

        r = year_review(self.conn, 'C', 2025, archetype_fn=archetype, goals_fn=lambda conn, cid, year: [{'year': year}])
        self.assertEqual(calls, [('C', '2025-12', 12), ('C', '2024-12', 3)])
        self.assertEqual(r['archetype'], {'archetype': 'Steady Planner'})
        self.assertEqual(r['goals'], [{'year': 2025}])
        cards = r['cards']
        self.assertTrue(8 <= len(cards) <= 10)
        card = next(c for c in cards if c['kind'] == 'archetype')
        self.assertEqual(card['facts'], {'archetype_label': 'Steady Planner', 'previous_archetype_label': 'Weekend Spender', 'changed': True})
        for c in cards:
            c['caption_template'].format(**c['facts'])
        self.assertIsNone(self.r['archetype']); self.assertIsNone(self.r['goals'])
        self.assertIsNone(year_review(self.conn, 'C', 2025, archetype_fn=lambda *a: None)['archetype'])

    def test_tiny_data_unavailable(self):
        r = year_review(self.conn, 'D', 2025)
        self.assertFalse(r['available']); self.assertEqual(r['observed_months'], 2); self.assertEqual(r['cards'], [])
        self.assertFalse(year_review(self.conn, 'C', 2026)['available'])
        self.assertEqual(year_options(self.conn, 'D'), [{'year': 2025, 'observed_months': 2, 'complete': False, 'available': False}])
        with self.assertRaises(ValueError):
            year_review(self.conn, 'NOPE', 2025)

    def test_year_options(self):
        self.assertEqual(year_options(self.conn, 'C'), [
            {'year': 2026, 'observed_months': 1, 'complete': False, 'available': False},
            {'year': 2025, 'observed_months': 12, 'complete': True, 'available': True},
            {'year': 2024, 'observed_months': 3, 'complete': False, 'available': True}])

    def test_mcc_label(self):
        self.assertEqual(mcc_label('4121'), 'Taxis'); self.assertEqual(mcc_label('9999'), 'Code 9999')


class DemoSmoke(unittest.TestCase):
    def test_demo_customer_2025(self):
        source = Path(__file__).resolve().parents[1] / 'var/scoach.sqlite3'
        if not source.exists():
            self.skipTest('demo database not present')
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'demo.sqlite3'; shutil.copy(source, copy)
            conn = connect(copy)
            try:
                r = year_review(conn, 'CUST00001', 2025)
                self.assertTrue(r['available']); self.assertTrue(r['complete'])
                self.assertTrue(8 <= len(r['cards']) <= 10)
                self.assertGreater(r['money_in_cents'], 0); self.assertGreater(r['purchase_count'], 0)
                for card in r['cards']:
                    card['caption_template'].format(**card['facts'])
                self.assertIn(2025, [o['year'] for o in year_options(conn, 'CUST00001') if o['complete']])
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
