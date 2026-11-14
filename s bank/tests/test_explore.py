import unittest

from tests.core_helper import demo_connection
from scoach.db import connect, initialize_schema
from scoach.explore import explore, hour_band, parse_timestamp, payday_phase
from scoach.ledger import account_scope, month_bounds
from scoach.statistics import transaction_statistics


def add_row(conn, ref, day, stamp, category, amount, kind, *, merchant=None, mcc=None):
    conn.execute(
        "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ref, "C", "A", day, stamp, category, amount, 0, kind, merchant, mcc, 1, ref, "{}"),
    )


def fixture(salaries=True):
    conn = connect(":memory:")
    initialize_schema(conn)
    conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
    # 2026-09-07 is a Monday.
    if salaries:
        add_row(conn, "sal1", "2026-08-15", "15AUG26:06:00:00", "Salary", 300_000, "salary")
    add_row(conn, "mon_night", "2026-09-07", "07SEP26:02:15:00", "Restaurants", -1_000, "purchase", merchant="R1", mcc="5812")
    add_row(conn, "mon_morning", "2026-09-07", "07SEP2026:08:30:00", "Groceries", -2_000, "purchase", merchant="G1", mcc="5411")
    add_row(conn, "wed_afternoon", "2026-09-09", "09SEP26:12:00:00", "Groceries", -3_000, "purchase", merchant="G1", mcc="5411")
    add_row(conn, "sat_evening", "2026-09-12", "12SEP26:23:59:59", "Restaurants", -4_000, "purchase", merchant="R1", mcc="5812")
    add_row(conn, "sat_iso", "2026-09-12", "2026-09-12T18:00:00", "Travel", -5_000, "purchase")
    if salaries:
        add_row(conn, "sal2", "2026-09-15", "15SEP26:06:00:00", "Salary", 300_000, "salary")
    add_row(conn, "after", "2026-09-21", "21SEP26:10:00:00", "Lifestyle", -6_000, "purchase")
    add_row(conn, "invest", "2026-09-22", "22SEP26:10:00:00", "Invest Deposit", -50_000, "investment_deposit")
    add_row(conn, "refund", "2026-09-23", "23SEP26:10:00:00", "Lifestyle", 1_500, "purchase")
    add_row(conn, "rent", "2026-09-30", "garbage", "Housing", -70_000, "housing_payment")
    conn.commit()
    return conn


class ParsingTests(unittest.TestCase):
    def test_timestamps(self):
        self.assertEqual(parse_timestamp("05OCT24:17:51:20").isoformat(), "2024-10-05T17:51:20")
        self.assertEqual(parse_timestamp("05OCT2024:17:51:20").hour, 17)
        self.assertEqual(parse_timestamp("2024-10-05 06:01").hour, 6)
        self.assertEqual(parse_timestamp("2024-10-05T23:00:00Z").hour, 23)
        for bad in ("", None, "2024-10-05", "32OCT24:10:00:00", "05XYZ24:10:00:00", "garbage"):
            self.assertIsNone(parse_timestamp(bad))
        self.assertEqual([hour_band(v) for v in ("01JAN25:00:00:00", "01JAN25:05:59:59", "01JAN25:06:00:00",
                                                 "01JAN25:11:59:00", "01JAN25:12:00:00", "01JAN25:17:59:00",
                                                 "01JAN25:18:00:00", "01JAN25:23:59:00", "x")],
                         ["night", "night", "morning", "morning", "afternoon", "afternoon", "evening", "evening",
                          "unknown"])

    def test_payday_phase_rules(self):
        salaries = ["2026-08-15", "2026-09-15"]
        self.assertEqual(payday_phase("2026-08-15", salaries), "after_payday")
        self.assertEqual(payday_phase("2026-08-21", salaries), "after_payday")
        self.assertEqual(payday_phase("2026-08-22", salaries), "mid_cycle")
        self.assertEqual(payday_phase("2026-09-07", salaries), "mid_cycle")
        self.assertEqual(payday_phase("2026-09-08", salaries), "before_payday")
        self.assertEqual(payday_phase("2026-09-14", salaries), "before_payday")
        self.assertEqual(payday_phase("2026-09-22", salaries), "unknown")
        self.assertEqual(payday_phase("2026-08-01", salaries), "unknown")
        self.assertEqual(payday_phase("2026-08-10", salaries), "before_payday")


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixture()

    def tearDown(self):
        self.conn.close()

    def rows(self, result):
        return {row["key"]: row for row in result["rows"]}

    def test_weekday_fixture_in_week_order_with_empty_days(self):
        result = explore(self.conn, "C", "2026-09-07", "2026-09-13", group_by="weekday")
        self.assertEqual([r["label"] for r in result["rows"]],
                         ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        self.assertEqual([r["value_cents"] for r in result["rows"]], [3_000, 0, 3_000, 0, 0, 9_000, 0])
        self.assertEqual(result["total"]["value_cents"], 15_000)
        self.assertEqual(self.rows(result)[6]["share_percent"], "60.0")
        self.assertEqual(self.rows(result)[6]["count"], 2)
        self.assertEqual(result["chart"]["kind"], "bar")
        self.assertEqual(len(result["chart"]["series"]), 7)
        self.assertEqual(result["period"], {"start": "2026-09-07", "end": "2026-09-13"})

    def test_hour_band_fixture(self):
        result = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="hour_band")
        values = {r["key"]: r["value_cents"] for r in result["rows"]}
        self.assertEqual(values, {"night": 1_000, "morning": 8_000, "afternoon": 3_000,
                                  "evening": 9_000, "unknown": 70_000})
        self.assertEqual([r["key"] for r in result["rows"]], ["night", "morning", "afternoon", "evening", "unknown"])

    def test_payday_phase_fixture(self):
        result = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="payday_phase")
        values = {r["key"]: r["value_cents"] for r in result["rows"]}
        # 07 Sep is 8 days before the 15 Sep salary; 09/12 Sep within 7 days; 21 Sep 6 days after.
        self.assertEqual(values, {"after_payday": 6_000, "mid_cycle": 3_000, "before_payday": 12_000,
                                  "unknown": 70_000})
        self.assertIn("Payday phases", result["basis"])

    def test_payday_without_salary_is_unknown(self):
        self.conn.close()
        self.conn = fixture(salaries=False)
        result = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="payday_phase")
        self.assertEqual(self.rows(result)["unknown"]["value_cents"], 91_000)
        self.assertIn("limitations", result)

    def test_default_consumption_excludes_transfers_and_refunds(self):
        result = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="transaction_type")
        self.assertEqual({r["key"] for r in result["rows"]}, {"purchase", "housing_payment"})
        self.assertEqual(result["filters"], {"consumption_only": "true"})
        explicit = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="transaction_type",
                           filters={"transaction_type": "investment_deposit"})
        self.assertEqual(explicit["total"]["value_cents"], 50_000)
        inflow = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="category", metric="inflow_total")
        self.assertEqual(self.rows(inflow)["Salary"]["value_cents"], 300_000)
        self.assertEqual(self.rows(inflow)["Lifestyle"]["value_cents"], 1_500)

    def test_metrics(self):
        args = (self.conn, "C", "2026-09-01", "2026-09-30")
        count = explore(*args, group_by="category", metric="count")
        self.assertEqual(count["unit"], "count")
        self.assertEqual(self.rows(count)["Groceries"]["count"], 2)
        self.assertNotIn("value_cents", count["rows"][0])
        self.assertEqual(count["chart"]["series"][0]["value"], 2)
        average = explore(*args, group_by="category", metric="average_outflow")
        self.assertEqual(self.rows(average)["Groceries"]["value_cents"], 2_500)
        largest = explore(*args, group_by="merchant_id", metric="largest_outflow")
        self.assertEqual(self.rows(largest)["R1"]["value_cents"], 4_000)
        self.assertEqual(self.rows(largest)["R1"]["largest"]["date"], "2026-09-12")
        share = explore(*args, group_by="category", metric="share_of_outflow")
        self.assertEqual(share["rows"][0]["key"], "Housing")
        self.assertEqual(share["rows"][0]["share_percent"], "76.9")
        self.assertEqual(share["total"]["share_percent"], "100.0")
        mcc = explore(*args, group_by="mcc_code")
        self.assertEqual(self.rows(mcc)["5411"]["label"], "Grocery stores and supermarkets")
        self.assertEqual(self.rows(mcc)[None]["label"], "Not available")

    def test_top_cap_and_ordering(self):
        result = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="category", top=2)
        self.assertEqual([r["key"] for r in result["rows"]], ["Housing", "Lifestyle"])
        self.assertEqual(result["total_count"], 5)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total"]["value_cents"], 91_000)
        weeks = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="week", top=2)
        self.assertEqual([r["key"] for r in weeks["rows"]], ["2026-09-21", "2026-09-28"])
        self.assertEqual(weeks["chart"]["kind"], "line")
        self.assertEqual(weeks["total_count"], 5)

    def test_user_rules_change_baskets(self):
        self.conn.execute("INSERT INTO user_rules VALUES('r1','C','row','sat_iso',NULL,NULL,'flexible_essential',"
                          "NULL,'user','2026-10-01T00:00:00')")
        result = explore(self.conn, "C", "2026-09-01", "2026-09-30", group_by="basket")
        rows = self.rows(result)
        self.assertEqual(rows["flexible_essential"]["value_cents"], 5_000)
        self.assertEqual(rows["flexible_essential"]["label"], "Surprise must-pays")
        self.assertEqual(rows["discretionary"]["label"], "Little leaks")

    def test_invalid_arguments_rejected(self):
        args = (self.conn, "C", "2026-09-01", "2026-09-30")
        for kwargs in ({"group_by": "colour"}, {"group_by": "category", "metric": "median"},
                       {"group_by": "category", "top": 0}, {"group_by": "category", "top": 32},
                       {"group_by": "category", "top": True},
                       {"group_by": "category", "filters": {"amount": "1"}},
                       {"group_by": "category", "filters": {"role": "bogus"}},
                       {"group_by": "category", "filters": {"mcc_code": "12"}},
                       {"group_by": "category", "filters": {"category": ""}}):
            with self.assertRaises(ValueError):
                explore(*args, **kwargs)
        with self.assertRaises(ValueError):
            explore(self.conn, "C", "2026-09-30", "2026-09-01", group_by="category")
        with self.assertRaises(ValueError):
            explore(self.conn, "C", "2026-09", "2026-09-30", group_by="category")
        with self.assertRaises(ValueError):
            explore(self.conn, "C", "2027-01-01", "2027-01-31", group_by="category")


class DemoReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = demo_connection()
        cls.customer = cls.conn.execute("SELECT customer_id FROM customers ORDER BY customer_id").fetchone()[0]
        cls.end_month = account_scope(cls.conn, cls.customer)["observed_end"][:7]

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_category_totals_equal_transaction_statistics(self):
        start, end = month_bounds(self.end_month)
        result = explore(self.conn, self.customer, start, end, group_by="category", top=31)
        stats = transaction_statistics(self.conn, self.customer, start, end, {"consumption_only": "true"})
        self.assertFalse(result["truncated"])
        self.assertEqual(sum(r["value_cents"] for r in result["rows"]), stats["outflow_total_cents"])
        self.assertEqual(result["total"]["value_cents"], stats["consumption_cents"])
        self.assertEqual(sorted(result["transaction_refs"]), sorted(stats["transaction_refs"]))
        for row in result["rows"]:
            one = transaction_statistics(self.conn, self.customer, start, end,
                                         {"consumption_only": "true", "category": row["key"]})
            self.assertEqual(row["value_cents"], one["outflow_total_cents"])
            self.assertEqual(row["count"], one["outflow_count"])
        values = [r["value_cents"] for r in result["rows"]]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_month_totals_equal_transaction_statistics(self):
        start = month_bounds(self.end_month[:4] + "-01")[0]
        end = month_bounds(self.end_month)[1]
        result = explore(self.conn, self.customer, start, end, group_by="month", top=31)
        self.assertEqual([r["key"] for r in result["rows"]], sorted(r["key"] for r in result["rows"]))
        self.assertEqual(result["chart"]["kind"], "line")
        for row in result["rows"]:
            first, last = month_bounds(row["key"])
            stats = transaction_statistics(self.conn, self.customer, first, last, {"consumption_only": "true"})
            self.assertEqual(row["value_cents"], stats["consumption_cents"])
        inflow = explore(self.conn, self.customer, start, end, group_by="month", metric="inflow_total", top=31)
        stats = transaction_statistics(self.conn, self.customer, start, end)
        self.assertEqual(inflow["total"]["value_cents"], stats["inflow_total_cents"])

    def test_real_timestamps_parse(self):
        result = explore(self.conn, self.customer, *month_bounds(self.end_month), group_by="hour_band")
        self.assertNotIn("unknown", {r["key"] for r in result["rows"]})


if __name__ == "__main__":
    unittest.main()
