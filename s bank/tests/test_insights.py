import unittest

from scoach.analytics import investment_cashflows
from scoach.db import connect, initialize_schema
from scoach.forecast import safe_to_spend


def add_row(conn, ref, date, category, amount, balance, kind, *, merchant=None):
    conn.execute(
        'INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            ref,
            'C',
            'A',
            date,
            '15X26:12:00:00',
            category,
            amount,
            balance,
            kind,
            merchant,
            None,
            1,
            ref,
            '{}',
        ),
    )


class InsightTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(':memory:')
        initialize_schema(self.conn)
        self.conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")

    def tearDown(self):
        self.conn.close()

    def test_safe_to_spend_is_conservative_explainable_and_horizon_bound(self):
        for month in range(4, 10):
            add_row(self.conn, f'rent-{month}', f'2026-{month:02d}-02', 'Rent', -50_000, 80_000, 'housing_payment')
            add_row(self.conn, f'salary-{month}', f'2026-{month:02d}-15', 'Salary', 200_000, 280_000, 'salary')
            add_row(self.conn, f'food-{month}', f'2026-{month:02d}-20', 'Groceries', -10_000, 270_000, 'purchase', merchant=f'shop-{month}')
        add_row(self.conn, 'closing', '2026-09-30', 'Restaurants', -1_000, 100_000, 'purchase')
        self.conn.commit()

        result = safe_to_spend(self.conn, 'C', '2026-09-30', days=7, reserve_floor_cents=20_000)

        self.assertEqual(result['reference_date'], '2026-09-30')
        self.assertEqual(result['horizon_end'], '2026-10-07')
        self.assertEqual(result['starting_balance_cents'], 100_000)
        self.assertEqual(result['scheduled_outflows_cents'], 50_000)
        self.assertEqual(result['scheduled_income_excluded_cents'], 0)
        self.assertEqual(
            result['safe_to_spend_cents'],
            max(
                0,
                result['starting_balance_cents']
                - result['reserve_floor_cents']
                - result['scheduled_outflows_cents']
                - result['historical_flexible_buffer_cents'],
            ),
        )
        self.assertEqual(result['label'], 'Estimated safe-to-spend — not a guarantee')
        self.assertTrue(result['available'])
        self.assertEqual(result['reserve_floor_source'], 'explicit_request')
        self.assertTrue(result['scenario'])
        self.assertFalse(result['observed'])
        self.assertTrue(result['starting_transaction_ref'])
        self.assertTrue(result['comparison_transaction_refs'])
        self.assertTrue(all(item['amount_cents'] < 0 for item in result['scheduled_outflows']))
        self.assertNotIn('confidence', result)

        stricter = safe_to_spend(self.conn, 'C', '2026-09-30', days=7, reserve_floor_cents=200_000)
        self.assertEqual(stricter['safe_to_spend_cents'], 0)
        for invalid in (0, 31, True):
            with self.subTest(days=invalid), self.assertRaises(ValueError):
                safe_to_spend(self.conn, 'C', '2026-09-30', days=invalid)

    def test_safe_to_spend_needs_a_complete_historical_window_and_has_a_sourced_default_reserve(self):
        add_row(self.conn, 'opening', '2026-09-29', 'Salary', 100_000, 100_000, 'salary')
        add_row(self.conn, 'closing', '2026-09-30', 'Groceries', -1_000, 99_000, 'purchase')
        self.conn.commit()

        result = safe_to_spend(self.conn, 'C', '2026-09-30')

        self.assertFalse(result['available'])
        self.assertTrue(result['needs_history'])
        self.assertIsNone(result['safe_to_spend_cents'])
        self.assertIsNone(result['historical_flexible_buffer_cents'])
        self.assertEqual(result['reserve_floor_cents'], 50_000)
        self.assertEqual(result['reserve_floor_source'], 'demo_default')
        self.assertEqual(result['history_required_days'], 30)
        self.assertEqual(result['observed_history_days'], 1)
        self.assertEqual(result['complete_historical_window_count'], 0)
        self.assertIn('history', result['unavailable_reason'].lower())
        self.assertNotEqual(result.get('safe_to_spend_cents'), result['starting_balance_cents'])

    def test_investment_cashflows_are_transfers_not_performance(self):
        add_row(self.conn, 'salary', '2026-07-01', 'Salary', 100_000, 100_000, 'salary')
        add_row(self.conn, 'deposit-jul', '2026-07-05', 'Invest Deposit', -10_000, 90_000, 'investment_deposit')
        add_row(self.conn, 'sweep-jul', '2026-07-06', 'Salary Sweep', -5_000, 85_000, 'salary_sweep')
        add_row(self.conn, 'withdraw-aug', '2026-08-06', 'Invest Withdraw', 2_500, 87_500, 'investment_withdrawal')
        add_row(self.conn, 'deposit-sep', '2026-09-05', 'Invest Deposit', -20_000, 67_500, 'investment_deposit')
        self.conn.commit()

        result = investment_cashflows(self.conn, 'C', '2026-09', months=3)

        self.assertEqual(result['start_month'], '2026-07')
        self.assertEqual(result['end_month'], '2026-09')
        self.assertEqual(result['investment_deposits_cents'], 30_000)
        self.assertEqual(result['salary_sweeps_cents'], 5_000)
        self.assertEqual(result['total_contributions_cents'], 35_000)
        self.assertEqual(result['withdrawals_cents'], 2_500)
        self.assertEqual(result['net_contributions_cents'], 32_500)
        self.assertEqual(result['account_cashflow_cents'], -32_500)
        self.assertEqual(result['contribution_share_of_salary_basis_points'], 3_500)
        self.assertEqual(result['contribution_months'], 2)
        self.assertEqual([row['month'] for row in result['months']], ['2026-07', '2026-08', '2026-09'])
        self.assertEqual(result['label'], 'Observed investment cash flows — not portfolio performance')
        self.assertTrue(result['observed'])
        self.assertEqual(len(result['transaction_refs']), 4)
        for forbidden in ('holdings', 'return_cents', 'risk_score', 'recommendation'):
            self.assertNotIn(forbidden, result)
        with self.assertRaises(ValueError):
            investment_cashflows(self.conn, 'C', '2026-09', months=25)


if __name__ == '__main__':
    unittest.main()
