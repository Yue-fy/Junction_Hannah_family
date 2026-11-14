import unittest

from scoach.db import connect, initialize_schema
from scoach.statistics import compare_transaction_statistics, transaction_statistics


def add_row(conn, ref, day, category, amount, balance, kind, *, merchant=None):
    conn.execute(
        "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ref,
            "C",
            "A",
            day,
            "15SEP26:12:00:00",
            category,
            amount,
            balance,
            kind,
            merchant,
            None,
            1,
            ref,
            "{}",
        ),
    )


class TransactionStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_schema(self.conn)
        self.conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        add_row(self.conn, "salary", "2026-09-01", "Salary", 200_000, 200_000, "salary")
        add_row(self.conn, "restaurant", "2026-09-02", "Restaurants", -1_200, 198_800, "purchase", merchant="R1")
        add_row(self.conn, "transport", "2026-09-03", "Transportation", -2_500, 196_300, "purchase", merchant="T1")
        add_row(self.conn, "invest", "2026-09-04", "Invest Deposit", -10_000, 186_300, "investment_deposit")
        add_row(self.conn, "withdraw", "2026-09-05", "Invest Withdraw", 3_000, 189_300, "investment_withdrawal")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_reconciles_observed_flows_and_keeps_transfers_out_of_consumption(self):
        result = transaction_statistics(self.conn, "C", "2026-09-01", "2026-09-30")

        self.assertTrue(result["available"])
        self.assertTrue(result["observed"])
        self.assertTrue(result["has_transactions"])
        self.assertEqual(result["account_id"], "A")
        self.assertEqual(result["transaction_count"], 5)
        self.assertEqual(result["inflow_total_cents"], 203_000)
        self.assertEqual(result["outflow_total_cents"], 13_700)
        self.assertEqual(result["net_cents"], 189_300)
        self.assertEqual(result["consumption_cents"], 3_700)
        self.assertEqual(result["transfer_outflow_cents"], 10_000)
        self.assertEqual(result["transfer_inflow_cents"], 3_000)
        self.assertEqual(result["average_outflow_cents"], 4_567)
        self.assertEqual(result["average_consumption_cents"], 1_850)
        self.assertEqual(result["largest_outflow"]["transaction_ref"], "invest")
        self.assertEqual(result["largest_outflow"]["amount_cents"], 10_000)
        self.assertEqual(result["transaction_refs"], ["salary", "restaurant", "transport", "invest", "withdraw"])
        self.assertTrue(result["fact_id"].startswith("transaction-statistics:"))

    def test_exact_filters_and_honest_empty_result(self):
        result = transaction_statistics(
            self.conn,
            "C",
            "2026-09-01",
            "2026-09-30",
            filters={"category": "Transportation", "role": "fixed_obligation"},
        )
        self.assertEqual(result["filters"], {"category": "Transportation", "role": "fixed_obligation"})
        self.assertEqual(result["transaction_count"], 1)
        self.assertEqual(result["consumption_cents"], 2_500)
        self.assertEqual(result["average_outflow_cents"], 2_500)
        self.assertEqual(result["largest_outflow"]["merchant_id"], "T1")

        empty = transaction_statistics(
            self.conn,
            "C",
            "2026-09-01",
            "2026-09-30",
            filters={"category": "Explicit Tax"},
        )
        self.assertTrue(empty["available"])
        self.assertFalse(empty["has_transactions"])
        self.assertEqual(empty["transaction_count"], 0)
        self.assertEqual(empty["outflow_total_cents"], 0)
        self.assertIsNone(empty["average_outflow_cents"])
        self.assertIsNone(empty["largest_outflow"])
        self.assertEqual(empty["transaction_refs"], [])

    def test_comparison_uses_exact_facts_and_null_safe_averages(self):
        add_row(self.conn, "aug-a", "2026-08-02", "Restaurants", -1_000, 1_000, "purchase")
        add_row(self.conn, "aug-b", "2026-08-03", "Restaurants", -1_500, -500, "purchase")
        # A second September restaurant row makes September total €42 and average €21.
        add_row(self.conn, "sep-b", "2026-09-06", "Restaurants", -3_000, 159_300, "purchase")
        self.conn.commit()

        result = compare_transaction_statistics(
            self.conn,
            "C",
            "2026-09-01",
            "2026-09-30",
            "2026-08-01",
            "2026-08-31",
            filters={"category": "Restaurants"},
        )
        self.assertEqual(result["current"]["outflow_total_cents"], 4_200)
        self.assertEqual(result["comparison"]["outflow_total_cents"], 2_500)
        self.assertEqual(result["outflow_delta_cents"], 1_700)
        self.assertEqual(result["transaction_count_delta"], 0)
        self.assertEqual(result["average_outflow_delta_cents"], 850)
        self.assertEqual(result["current_fact_id"], result["current"]["fact_id"])
        self.assertEqual(result["comparison_fact_id"], result["comparison"]["fact_id"])
        self.assertTrue(result["fact_id"].startswith("transaction-statistics-comparison:"))

        empty = compare_transaction_statistics(
            self.conn,
            "C",
            "2026-09-01",
            "2026-09-30",
            "2026-08-01",
            "2026-08-31",
            filters={"category": "No such category"},
        )
        self.assertIsNone(empty["average_outflow_delta_cents"])

    def test_rejects_invalid_scope_period_and_filters(self):
        cases = [
            ("MISSING", "2026-09-01", "2026-09-30", None),
            ("C", "2026-09-30", "2026-09-01", None),
            ("C", "2026-08-31", "2026-09-30", None),
            ("C", "2026-09-01", "2026-10-01", None),
            ("C", "not-a-date", "2026-09-30", None),
            ("C", "2026-09-01", "2026-09-30", {"unsupported": "x"}),
            ("C", "2026-09-01", "2026-09-30", {"category": ""}),
            ("C", "2026-09-01", "2026-09-30", {"role": "not-a-role"}),
        ]
        for customer, start, end, filters in cases:
            with self.subTest(customer=customer, start=start, end=end, filters=filters):
                with self.assertRaises(ValueError):
                    transaction_statistics(self.conn, customer, start, end, filters=filters)


if __name__ == "__main__":
    unittest.main()
