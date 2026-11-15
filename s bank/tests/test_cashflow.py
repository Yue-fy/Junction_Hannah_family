from decimal import Decimal, ROUND_HALF_UP
import unittest

from tests.core_helper import demo_connection
from scoach.analytics import money_map
from scoach.cashflow import cashflow_series, cashflow_summary
from scoach.db import connect, initialize_schema
from scoach.ledger import account_scope, month_bounds, shift_month
from scoach.statistics import transaction_statistics


def add_row(conn, ref, day, category, amount, kind):
    conn.execute(
        "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ref, "C", "A", day, "01JAN25:12:00:00", category, amount, 0, kind, None, None, 1, ref, "{}"),
    )


def fixture():
    """Observed 2024-11-10 .. 2026-02-20: Nov 2024 and Feb 2026 are partial months."""
    conn = connect(":memory:")
    initialize_schema(conn)
    conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
    add_row(conn, "first", "2024-11-10", "Groceries", -1_000, "purchase")
    month, n = "2024-12", 0
    while month <= "2026-01":
        n += 1
        add_row(conn, "sal" + month, month + "-15", "Salary", 200_000 + n * 1_000, "salary")
        add_row(conn, "buy" + month, month + "-16", "Groceries", -100_000, "purchase")
        add_row(conn, "inv" + month, month + "-17", "Invest Deposit", -20_000, "investment_deposit")
        month = shift_month(month, 1)
    add_row(conn, "other", "2025-03-05", "Other Income", 10_000, "other_income")
    add_row(conn, "refund", "2025-03-06", "Groceries", 500, "purchase")
    add_row(conn, "withdraw", "2025-03-07", "Invest Withdraw", 5_000, "investment_withdrawal")
    add_row(conn, "last", "2026-02-20", "Groceries", -2_000, "purchase")
    conn.commit()
    return conn


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixture()

    def tearDown(self):
        self.conn.close()

    def test_month_definitions(self):
        result = cashflow_series(self.conn, "C", "2025-03", "2025-04")
        march = result["periods"][0]
        self.assertEqual(march["period"], "2025-03")
        self.assertEqual(march["income_cents"], 204_000 + 10_000)
        self.assertEqual(march["salary_cents"], 204_000)
        self.assertEqual(march["consumption_cents"], 100_000)
        self.assertEqual(march["savings_contributions_cents"], 20_000)
        self.assertEqual(march["savings_withdrawals_cents"], 5_000)
        self.assertEqual(march["savings_transfers_cents"], 15_000)
        self.assertEqual(march["net_cents"], 214_000 - 100_000 - 15_000)
        # V4: saving rate = left over after spending / income (was transfers / income, the constant-9.6 % bug).
        self.assertEqual(march["left_over_cents"], 214_000 - 100_000)
        self.assertEqual(march["saving_rate_percent"], "53.3")       # 114000 / 214000
        self.assertEqual(march["moved_to_savings_cents"], 15_000)
        self.assertEqual(march["moved_to_savings_percent"], "7.0")  # 15000 / 214000
        self.assertTrue(march["complete"])
        self.assertEqual(result["chart"]["kind"], "cashflow")
        self.assertEqual([s["key"] for s in result["chart"]["series"]], ["income", "consumption", "net"])
        self.assertEqual(result["chart"]["series"][2]["values"], [p["net_cents"] for p in result["periods"]])
        self.assertEqual(result["totals"]["net_cents"], sum(p["net_cents"] for p in result["periods"]))

    def test_partial_months_flagged(self):
        result = cashflow_series(self.conn, "C", "2024-11", "2026-02")
        flags = {p["period"]: p["complete"] for p in result["periods"]}
        self.assertFalse(flags["2024-11"])
        self.assertFalse(flags["2026-02"])
        self.assertTrue(flags["2024-12"])
        self.assertEqual(result["totals"]["partial_periods"], 2)
        self.assertIsNone(flags.get("2024-10"))
        self.assertIsNone(result["periods"][0]["saving_rate_percent"])

    def test_yearly_equals_sum_of_months_and_partial_years(self):
        months = cashflow_series(self.conn, "C", "2024-11", "2026-02")
        years = cashflow_series(self.conn, "C", "2024", "2026", granularity="year")
        self.assertEqual([p["period"] for p in years["periods"]], ["2024", "2025", "2026"])
        self.assertEqual([p["complete"] for p in years["periods"]], [False, True, False])
        self.assertEqual([p["months"] for p in years["periods"]], [2, 12, 2])
        fields = ("income_cents", "consumption_cents", "savings_transfers_cents", "net_cents")
        for year in years["periods"]:
            members = [p for p in months["periods"] if p["period"].startswith(year["period"])]
            for field in fields:
                self.assertEqual(year[field], sum(p[field] for p in members))
        for field in fields:
            self.assertEqual(years["totals"][field], months["totals"][field])
        # A year cut by the requested range is partial even when fully observed.
        cut = cashflow_series(self.conn, "C", "2025-02", "2025-12", granularity="year")
        self.assertFalse(cut["periods"][0]["complete"])

    def test_summary_comparisons(self):
        result = cashflow_summary(self.conn, "C", "2024-11", "2026-02")
        comparisons = result["comparisons"]
        self.assertEqual(comparisons["basis_periods"], "complete")
        self.assertEqual(comparisons["first_complete"]["period"], "2024-12")
        self.assertEqual(comparisons["last_complete"]["period"], "2026-01")
        self.assertEqual(comparisons["best_net_period"]["period"], "2025-03")
        self.assertEqual(comparisons["worst_net_period"]["period"], "2024-12")
        change = comparisons["saving_rate_change"]
        first, last = comparisons["first_complete"], comparisons["last_complete"]
        self.assertEqual(change["from_percent"], first["saving_rate_percent"])
        self.assertEqual(change["to_percent"], last["saving_rate_percent"])
        self.assertEqual(Decimal(change["from_percent"]), (Decimal(first["left_over_cents"]) * 100 / Decimal(first["income_cents"])).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        self.assertEqual(first["moved_to_savings_percent"], "10.0")  # 20000 / 201000 = 9.95, half up
        self.assertEqual(last["moved_to_savings_percent"], "9.3")    # 20000 / 214000
        self.assertEqual(comparisons["income_change_cents"], 13_000)
        self.assertEqual(comparisons["net_change_cents"], 13_000)

    def test_invalid_ranges(self):
        for args in (("2024-10", "2025-01"), ("2025-01", "2026-03"), ("2025-05", "2025-01"),
                     ("2025-1", "2025-02"), ("2025-13", "2025-12")):
            with self.assertRaises(ValueError):
                cashflow_series(self.conn, "C", *args)
        with self.assertRaises(ValueError):
            cashflow_series(self.conn, "C", "2025-01", "2025-02", granularity="week")
        with self.assertRaises(ValueError):
            cashflow_series(self.conn, "C", "2025", "2025-02")


class LimitTests(unittest.TestCase):
    def test_month_and_year_limits(self):
        conn = connect(":memory:")
        initialize_schema(conn)
        conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        add_row(conn, "a", "2019-01-01", "Groceries", -100, "purchase")
        add_row(conn, "b", "2025-12-31", "Groceries", -100, "purchase")
        self.assertEqual(len(cashflow_series(conn, "C", "2023-01", "2025-12")["periods"]), 36)
        with self.assertRaises(ValueError):
            cashflow_series(conn, "C", "2022-12", "2025-12")
        self.assertEqual(len(cashflow_series(conn, "C", "2021", "2025", "year")["periods"]), 5)
        with self.assertRaises(ValueError):
            cashflow_series(conn, "C", "2020", "2025", "year")
        conn.close()


class DemoReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = demo_connection()
        cls.customers = [r[0] for r in cls.conn.execute("SELECT customer_id FROM customers ORDER BY customer_id")]

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_month_matches_money_map_and_statistics(self):
        for customer in self.customers:
            month = shift_month(account_scope(self.conn, customer)["observed_end"][:7], -1)
            period = cashflow_series(self.conn, customer, month, month)["periods"][0]
            overview = money_map(self.conn, customer, month)
            stats = transaction_statistics(self.conn, customer, *month_bounds(month), {"consumption_only": "true"})
            self.assertEqual(period["income_cents"], overview["salary_cents"] + overview["other_income_cents"])
            self.assertEqual(period["consumption_cents"], overview["consumption_cents"])
            self.assertEqual(period["consumption_cents"], stats["outflow_total_cents"])
            self.assertEqual(period["savings_contributions_cents"], overview["committed_saving_transfers_cents"])
            self.assertEqual(period["savings_transfers_cents"], -overview["transfer_net_cents"])
            self.assertEqual(period["net_cents"],
                             overview["free_cashflow_cents"] + period["savings_withdrawals_cents"])
            self.assertTrue(period["complete"])

    def test_demo_years(self):
        customer = self.customers[0]
        scope = account_scope(self.conn, customer)
        years = cashflow_summary(self.conn, customer, scope["observed_start"][:4], scope["observed_end"][:4], "year")
        complete = [p for p in years["periods"] if p["complete"]]
        self.assertTrue(complete)
        self.assertFalse(years["periods"][0]["complete"])
        months = cashflow_series(self.conn, customer, complete[0]["period"] + "-01", complete[0]["period"] + "-12")
        self.assertEqual(complete[0]["net_cents"], months["totals"]["net_cents"])
        self.assertEqual(years["comparisons"]["basis_periods"], "complete")


if __name__ == "__main__":
    unittest.main()
