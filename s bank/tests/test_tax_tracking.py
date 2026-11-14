"""WP-M: income tax tracking from customer-entered data, and the VAT learn card."""
import inspect
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scoach import tax as tax_module
from scoach.db import connect, initialize_schema
from scoach.tax import (
    MISSING_WITHHOLDING_REASON,
    TAX_STAGES,
    back_tax_plan,
    load_tax_calendar,
    tax_cycle_status,
    tax_overview,
    tax_planning_scenario,
    tax_refund_seen,
    vat_learn_card,
    withholding_estimate,
)
from scoach.vat import vat_lens

DEMO_DB = Path(__file__).resolve().parents[1] / "var" / "scoach.sqlite3"


def add_row(conn, ref, day, category, amount, balance, kind="purchase"):
    conn.execute(
        "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ref, "C", "A", day, day + ":12:00:00", category, amount, balance, kind, None, None, 1, ref, "{}"),
    )


def fixture_connection():
    conn = connect(":memory:")
    initialize_schema(conn)
    conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
    balance = 100_000
    for month in range(1, 12):
        day = "2026-%02d-15" % month
        balance += 250_000
        add_row(conn, "salary-%d" % month, day, "Salary", 250_000, balance, "salary")
        balance -= 40_000
        add_row(conn, "shop-%d" % month, "2026-%02d-20" % month, "Groceries", -40_000, balance)
    add_row(conn, "salary-2025-12", "2025-12-15", "Salary", 250_000, 100_000, "salary")
    conn.commit()
    return conn


def rate(amount, bp):
    return (amount * bp + 5_000) // 10_000


class WithholdingTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixture_connection()

    def tearDown(self):
        self.conn.close()

    def test_base_rate_only(self):
        tax = {"base_rate_bp": 2_000, "gross_monthly_cents": 320_000}
        result = withholding_estimate(self.conn, "C", "2026-03-31", tax)
        self.assertTrue(result["available"])
        self.assertEqual(result["tax_year"], 2026)
        self.assertEqual(result["salary_months"], 3)
        self.assertEqual(result["gross_ytd_cents"], 960_000)
        self.assertEqual(result["withheld_ytd_cents"], rate(960_000, 2_000))
        self.assertFalse(result["additional_rate_applied"])
        self.assertEqual(result["observed_net_salary_ytd_cents"], 750_000)
        self.assertEqual(result["flow"]["received_cents"], 750_000)
        self.assertEqual(result["projected_gross_full_year_cents"], 320_000 * 12)
        self.assertEqual(result["projected_withheld_full_year_cents"], rate(320_000 * 12, 2_000))
        self.assertEqual(len(result["transaction_refs"]), 3)
        # expected net 768,000 vs received 750,000: gap 18,000 > 3 x 5,000 -> note
        self.assertTrue(result["gap_is_large"])
        self.assertIn("not included", " ".join(result["notes"]))

    def test_additional_rate_above_income_limit(self):
        tax = {
            "base_rate_bp": 2_000,
            "additional_rate_bp": 4_000,
            "income_limit_cents": 2_000_000,
            "gross_ytd_cents": 2_500_000,
        }
        result = withholding_estimate(self.conn, "C", "2026-09-30", tax)
        self.assertTrue(result["additional_rate_applied"])
        self.assertEqual(result["gross_ytd_source"], "entered_ytd")
        self.assertEqual(result["withheld_ytd_cents"], rate(2_000_000, 2_000) + rate(500_000, 4_000))
        self.assertIsNone(result["projected_gross_full_year_cents"])
        below = withholding_estimate(self.conn, "C", "2026-09-30", dict(tax, gross_ytd_cents=1_500_000))
        self.assertFalse(below["additional_rate_applied"])
        self.assertEqual(below["withheld_ytd_cents"], rate(1_500_000, 2_000))

    def test_projection_crosses_limit(self):
        tax = {
            "base_rate_bp": 2_000,
            "additional_rate_bp": 4_000,
            "income_limit_cents": 3_000_000,
            "gross_monthly_cents": 300_000,
        }
        result = withholding_estimate(self.conn, "C", "2026-06-30", tax)
        self.assertFalse(result["additional_rate_applied"])
        self.assertEqual(result["projected_gross_full_year_cents"], 3_600_000)
        self.assertTrue(result["projected_additional_rate_applied"])
        self.assertEqual(
            result["projected_withheld_full_year_cents"],
            rate(3_000_000, 2_000) + rate(600_000, 4_000),
        )

    def test_missing_gross_or_rate(self):
        for tax in (None, {}, {"base_rate_bp": 2_000}, {"gross_monthly_cents": 300_000}):
            result = withholding_estimate(self.conn, "C", "2026-03-31", tax)
            self.assertFalse(result["available"])
            self.assertEqual(result["reason"], MISSING_WITHHOLDING_REASON)
            self.assertTrue(result["missing"])

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            withholding_estimate(self.conn, "C", "2026-03-31", {"base_rate_bp": "20"})
        with self.assertRaises(ValueError):
            withholding_estimate(self.conn, "C", "2026-03-31", {"decision_result": "maybe"})


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixture_connection()
        self.calendar = load_tax_calendar(2026)

    def tearDown(self):
        self.conn.close()

    def status(self, as_of, tax=None):
        result = tax_cycle_status(self.conn, "C", as_of, tax or {}, self.calendar)
        self.assertIn(result["stage"], TAX_STAGES)
        self.assertTrue(result["tasks"])
        return result

    def test_return_coming(self):
        result = self.status("2026-02-10")
        self.assertEqual(result["stage"], "return_coming")
        self.assertEqual(result["next_date"], "2026-04-01")
        self.assertEqual(result["days_until"], 50)

    def test_check_return(self):
        result = self.status("2026-04-10")
        self.assertEqual(result["stage"], "check_return")
        self.assertEqual(result["next_date"], "2026-04-14")
        self.assertEqual(result["days_until"], 4)
        self.assertEqual(self.status("2026-04-29")["stage"], "decision_pending")

    def test_decision_pending(self):
        result = self.status("2026-06-15")
        self.assertEqual(result["stage"], "decision_pending")
        self.assertEqual(result["next_date"], "2026-10-31")
        own = self.status("2026-06-15", {"assessment_end_month": "2026-07"})
        self.assertEqual(own["next_date"], "2026-07-31")

    def test_refund_expected(self):
        tax = {"decision_result": "refund", "decision_amount_cents": 45_000, "assessment_end_month": "2026-08"}
        result = self.status("2026-09-20", tax)
        self.assertEqual(result["stage"], "refund_expected")
        self.assertEqual(result["next_date"], "2026-10-05")
        self.assertEqual(result["date_source"], "calendar")
        self.assertFalse(result["refund_seen"]["seen"])
        own = self.status("2026-09-20", dict(tax, decision_due_dates=["2026-10-09"]))
        self.assertEqual(own["next_date"], "2026-10-09")
        self.assertEqual(own["date_source"], "tax_decision")

    def test_back_tax_due(self):
        tax = {"decision_result": "back_tax", "decision_amount_cents": 80_000, "assessment_end_month": "2026-08"}
        result = self.status("2026-10-15", tax)
        self.assertEqual(result["stage"], "back_tax_due")
        self.assertEqual(result["next_date"], "2026-12-01")
        self.assertEqual(result["days_until"], 47)

    def test_year_end(self):
        self.assertEqual(self.status("2026-11-20")["stage"], "year_end")
        settled = self.status("2026-08-01", {"decision_result": "none"})
        self.assertEqual(settled["stage"], "year_end")
        old = {"decision_result": "back_tax", "decision_amount_cents": 80_000, "assessment_end_month": "2026-05"}
        self.assertEqual(self.status("2026-11-20", old)["stage"], "year_end")


class BackTaxPlanTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixture_connection()

    def tearDown(self):
        self.conn.close()

    def test_equals_direct_tax_planning_scenario(self):
        tax = {
            "decision_result": "back_tax",
            "decision_amount_cents": 90_001,
            "decision_due_dates": ["2026-12-01", "2026-10-01"],
            "already_set_aside_cents": 50_000,
        }
        plan = back_tax_plan(self.conn, "C", "2026-08-25", tax)
        self.assertTrue(plan["available"])
        self.assertEqual(plan["due_dates"], ["2026-10-01", "2026-12-01"])
        self.assertIn("50/50", " ".join(plan["assumptions"]))
        balance = [row for row in self.conn.execute(
            "SELECT balance_after_cents FROM transactions WHERE date<='2026-08-25' ORDER BY date DESC LIMIT 1")][0][0]
        self.assertEqual(plan["current_balance_cents"], balance)
        first = tax_planning_scenario(45_001, "2026-10-01", "2026-08-25", already_set_aside_cents=45_001,
                                      current_balance_cents=balance, label="Back tax instalment 1 of 2")
        second = tax_planning_scenario(45_000, "2026-12-01", "2026-08-25", already_set_aside_cents=4_999,
                                       current_balance_cents=balance, label="Back tax instalment 2 of 2")
        self.assertEqual(plan["instalments"][0]["scenario"], first)
        self.assertEqual(plan["instalments"][1]["scenario"], second)
        self.assertEqual(
            plan["monthly_set_aside_now_cents"],
            first["required_monthly_set_aside_cents"] + second["required_monthly_set_aside_cents"],
        )

    def test_calendar_dates_and_passed_instalment(self):
        tax = {"decision_result": "back_tax", "decision_amount_cents": 60_000, "assessment_end_month": "2026-08"}
        plan = back_tax_plan(self.conn, "C", "2026-10-15", tax)
        self.assertEqual(plan["date_source"], "calendar")
        self.assertEqual(plan["instalments"][0]["status"], "due_date_passed")
        self.assertIsNone(plan["instalments"][0]["scenario"])
        self.assertEqual(plan["instalments"][1]["scenario"]["amount_cents"], 30_000)

    def test_unavailable_without_back_tax(self):
        self.assertFalse(back_tax_plan(self.conn, "C", "2026-08-25", None)["available"])
        no_dates = {"decision_result": "back_tax", "decision_amount_cents": 60_000}
        self.assertFalse(back_tax_plan(self.conn, "C", "2026-08-25", no_dates)["available"])


class RefundSeenTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixture_connection()
        self.tax = {"decision_result": "refund", "decision_amount_cents": 45_000, "assessment_end_month": "2026-08"}

    def tearDown(self):
        self.conn.close()

    def test_declared_amount_near_expected_date(self):
        add_row(self.conn, "refund", "2026-10-06", "Other Income", 45_050, 500_000, "other_income")
        result = tax_refund_seen(self.conn, "C", self.tax)
        self.assertTrue(result["seen"])
        self.assertEqual(result["matched_by"], "declared_amount")
        self.assertEqual(result["match"]["date"], "2026-10-06")
        self.assertEqual(result["transaction_refs"], ["refund"])
        cycle = tax_cycle_status(self.conn, "C", "2026-10-10", self.tax)
        self.assertEqual(cycle["stage"], "refund_expected")
        self.assertIn("arrived on 2026-10-06", cycle["tasks"][0])

    def test_wrong_amount_or_outside_window(self):
        add_row(self.conn, "near-amount", "2026-10-06", "Other Income", 45_500, 500_000, "other_income")
        add_row(self.conn, "too-late", "2026-12-20", "Other Income", 45_000, 500_000, "other_income")
        result = tax_refund_seen(self.conn, "C", self.tax)
        self.assertFalse(result["seen"])
        self.assertIn("reason", result)
        self.assertFalse(tax_refund_seen(self.conn, "C", None)["seen"])

    def test_explicit_tax_category(self):
        add_row(self.conn, "tax-credit", "2026-10-02", "Tax", 12_345, 500_000, "other_income")
        result = tax_refund_seen(self.conn, "C", self.tax)
        self.assertTrue(result["seen"])
        self.assertEqual(result["matched_by"], "tax_category")


class VatCardTests(unittest.TestCase):
    def test_largest_vat_category_on_demo_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "demo.sqlite3"
            shutil.copyfile(DEMO_DB, path)
            conn = connect(path)
            try:
                customer = conn.execute("SELECT customer_id FROM customers ORDER BY customer_id LIMIT 1").fetchone()[0]
                card = vat_learn_card(conn, customer, "2026-08")
                lens = vat_lens(conn, customer, "2026-08-01", "2026-08-31")
            finally:
                conn.close()
        totals = {}
        for item in lens["transactions"]:
            if item["estimated_vat_cents"] is not None:
                vat, gross, labels = totals.get(item["category"], (0, 0, set()))
                totals[item["category"]] = (vat + item["estimated_vat_cents"], gross + item["gross_cents"],
                                            labels | {item["rate_display"]})
        best = max(totals, key=lambda key: totals[key][0])
        self.assertTrue(card["available"])
        self.assertEqual(card["category"], best)
        self.assertEqual(card["estimated_vat_cents"], totals[best][0])
        self.assertEqual(card["spending_cents"], totals[best][1])
        self.assertEqual(set(card["rate_labels"]), totals[best][2])
        self.assertEqual(card["month_estimated_vat_cents"], lens["estimated_vat_cents"])
        self.assertIn(card["category"], card["sentence"])
        self.assertTrue(card["sentence"].endswith("."))
        self.assertNotIn("\n", card["sentence"])


class OverviewTests(unittest.TestCase):
    def test_ai_view_omits_rates(self):
        conn = fixture_connection()
        try:
            tax = {"base_rate_bp": 2_000, "additional_rate_bp": 4_000, "income_limit_cents": 2_000_000,
                   "gross_monthly_cents": 300_000, "decision_result": "back_tax",
                   "decision_amount_cents": 60_000, "assessment_end_month": "2026-08"}
            result = tax_overview(conn, "C", "2026-09-10", tax)
        finally:
            conn.close()
        ui = json.dumps(result["overview"])
        ai = json.dumps(result["ai_view"])
        self.assertIn("base_rate_bp", ui)
        self.assertNotIn("base_rate_bp", ai)
        self.assertNotIn("additional_rate_bp", ai)
        self.assertEqual(result["ai_view"]["withholding"]["withheld_ytd_cents"],
                         result["overview"]["withholding"]["withheld_ytd_cents"])
        self.assertEqual(result["overview"]["cycle"]["stage"], "back_tax_due")
        self.assertTrue(result["overview"]["back_tax_plan"]["available"])
        self.assertTrue(result["overview"]["vat_card"]["available"])

    def test_empty_profile_explains_what_is_missing(self):
        conn = fixture_connection()
        try:
            result = tax_overview(conn, "C", "2026-09-10", None)
        finally:
            conn.close()
        self.assertFalse(result["overview"]["has_tax_data"])
        self.assertEqual(result["ai_view"]["withholding"]["reason"], MISSING_WITHHOLDING_REASON)


class NoHardcodedRatesTests(unittest.TestCase):
    def test_new_functions_contain_no_percentage_literals(self):
        names = ["load_tax_calendar", "withholding_estimate", "tax_cycle_status", "back_tax_plan",
                 "tax_refund_seen", "vat_learn_card", "tax_overview", "_withheld", "_apply_rate",
                 "_clean_tax", "_back_tax_dates", "_refund_date"]
        source = "\n".join(inspect.getsource(getattr(tax_module, name)) for name in names)
        code = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
        patterns = [
            r"(?<![\w.])\d*\.\d+(?![\w.])",  # float literals such as 0.2 or .255
            r"\d+(\.\d+)?\s*%",              # 20 %, 25.5%
            r"/\s*100(?!\d)",               # x / 100
            r"\*\s*\d{1,2}(?!\d)\s*/",      # x * 20 / ...
            r"_bp\s*[=,:]\s*\d",            # hardcoded basis-point rates
        ]
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, code), pattern)
        self.assertNotIn("_rate_bp\"] or", code)


class CalendarTests(unittest.TestCase):
    def test_calendar_loads_with_sources(self):
        calendar = load_tax_calendar(2026)
        self.assertEqual(calendar["calendar_year"], 2026)
        self.assertIn("retrieved_at", calendar)
        self.assertIsInstance(calendar["verified"], bool)
        urls = [item["url"] for item in calendar["sources"]]
        self.assertIn("https://vero.fi/en/individuals/payments/refunds/tax-refund-amount-and-dates-of-payment/", urls)
        self.assertIn("https://vero.fi/en/individuals/payments/back-taxes/payment-instructions/", urls)
        self.assertEqual(calendar["refund_dates_by_assessment_end_month"]["2026-05"], "2026-07-03")
        self.assertEqual(calendar["back_tax_instalments_by_assessment_end_month"]["2026-09"],
                         ["2026-11-02", "2027-01-04"])
        self.assertEqual(len(calendar["return_check_due_dates"]), 4)
        self.assertIsNone(load_tax_calendar(1999))


if __name__ == "__main__":
    unittest.main()
