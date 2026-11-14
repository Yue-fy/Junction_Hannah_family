import json
import unittest

from scoach.db import connect, initialize_schema
from scoach.tax import observed_tax_evidence, tax_planning_scenario


def add_row(conn, ref, day, category, amount, balance, kind="purchase"):
    conn.execute(
        "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ref, "C", "A", day, "15SEP26:12:00:00", category, amount, balance, kind, None, None, 1, ref, "{}"),
    )


class TaxEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_schema(self.conn)
        self.conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        add_row(self.conn, "ordinary", "2026-09-01", "Government fee", -5_000, 95_000)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_absence_is_unavailable_not_zero_tax_paid(self):
        result = observed_tax_evidence(self.conn, "C", "2026-09-01", "2026-09-30")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "no_explicit_tax_records")
        self.assertIsNone(result["observed_tax_paid_cents"])
        self.assertIsNone(result["observed_tax_refund_cents"])
        self.assertIsNone(result["observed_net_tax_cents"])
        self.assertEqual(result["transaction_refs"], [])
        self.assertEqual(result["mortgage_event_refs"], [])
        self.assertIn("not inferred", " ".join(result["limitations"]).lower())

    def test_uses_only_explicit_transaction_and_mortgage_transfer_tax_fields(self):
        add_row(self.conn, "tax-paid", "2026-09-02", "Tax", -10_000, 85_000)
        add_row(self.conn, "tax-refund", "2026-09-03", "Taxes", 2_000, 87_000, "other_income")
        final = {"customer_id": "C", "mortgage_customer_id": "M"}
        self.conn.execute("INSERT INTO mortgage_final VALUES(?,?,?)", ("M", "C", json.dumps(final)))
        event = {
            "mortgage_customer_id": "M",
            "timestamp": "04SEP26:12:00:00",
            "event_type": "expense_recorded",
            "expense_type": "transfer_tax",
            "expense_amount": "5800",
        }
        self.conn.execute(
            "INSERT INTO mortgage_events VALUES(?,?,?,?,?)",
            ("tax-event", "M", event["timestamp"], event["event_type"], json.dumps(event)),
        )
        self.conn.commit()

        result = observed_tax_evidence(self.conn, "C", "2026-09-01", "2026-09-30")
        self.assertTrue(result["available"])
        self.assertTrue(result["observed"])
        self.assertEqual(result["observed_tax_paid_cents"], 590_000)
        self.assertEqual(result["observed_tax_refund_cents"], 2_000)
        self.assertEqual(result["observed_net_tax_cents"], 588_000)
        self.assertEqual(result["transaction_refs"], ["tax-paid", "tax-refund"])
        self.assertEqual(result["mortgage_event_refs"], ["tax-event"])
        self.assertEqual([row["source"] for row in result["records"]], ["transaction", "transaction", "mortgage_event"])
        self.assertNotIn("ordinary", result["transaction_refs"])
        for forbidden in ("estimated_tax_cents", "tax_rate", "filing_status", "tax_liability_cents"):
            self.assertNotIn(forbidden, result)

    def test_period_filters_mortgage_events_and_validates_scope(self):
        with self.assertRaises(ValueError):
            observed_tax_evidence(self.conn, "C", "2026-10-01", "2026-10-31")
        with self.assertRaises(ValueError):
            observed_tax_evidence(self.conn, "MISSING", "2026-09-01", "2026-09-30")
        with self.assertRaises(ValueError):
            observed_tax_evidence(self.conn, "C", "bad-date", "2026-09-30")


class TaxPlanningScenarioTests(unittest.TestCase):
    def test_exact_user_declared_monthly_plan_and_balance_impact(self):
        result = tax_planning_scenario(
            amount_cents=120_000,
            due_date="2027-03-31",
            reference_date="2026-09-15",
            already_set_aside_cents=20_000,
            current_balance_cents=300_000,
            reserve_floor_cents=50_000,
            label="Estimated property tax",
        )
        self.assertEqual(result["amount_cents"], 120_000)
        self.assertEqual(result["remaining_cents"], 100_000)
        self.assertEqual(result["remaining_monthly_periods"], 6)
        self.assertEqual(result["required_monthly_set_aside_cents"], 16_667)
        self.assertEqual(result["set_aside_location"], "inside_current_balance")
        self.assertEqual(result["protected_from_current_balance_cents"], 120_000)
        self.assertEqual(result["available_above_reserve_cents"], 250_000)
        self.assertEqual(result["available_after_full_set_aside_cents"], 130_000)
        self.assertEqual(result["upfront_funding_gap_cents"], 0)
        self.assertEqual(result["source"], "user_declared")
        self.assertTrue(result["scenario"])
        self.assertFalse(result["observed"])
        self.assertTrue(result["not_tax_advice"])
        self.assertEqual(result["persistence"], "not_saved")
        self.assertTrue(result["scenario_id"].startswith("tax-planning-scenario:"))
        self.assertIn("not tax advice", " ".join(result["limitations"]).lower())
        for forbidden in ("tax_rate", "filing_status", "deduction_cents", "estimated_liability_cents"):
            self.assertNotIn(forbidden, result)

    def test_same_month_and_fully_funded_scenarios_are_well_defined(self):
        same_month = tax_planning_scenario(10_001, "2026-09-30", "2026-09-01")
        self.assertEqual(same_month["remaining_monthly_periods"], 1)
        self.assertEqual(same_month["required_monthly_set_aside_cents"], 10_001)

        funded = tax_planning_scenario(10_000, "2026-10-15", "2026-09-15", already_set_aside_cents=12_000)
        self.assertEqual(funded["remaining_cents"], 0)
        self.assertEqual(funded["required_monthly_set_aside_cents"], 0)
        self.assertIsNone(funded["available_above_reserve_cents"])
        self.assertIsNone(funded["upfront_funding_gap_cents"])
        self.assertEqual(funded["protected_from_current_balance_cents"], 10_000)

        overdrawn = tax_planning_scenario(
            10_000,
            "2026-10-15",
            "2026-09-15",
            current_balance_cents=-5_000,
            reserve_floor_cents=1_000,
        )
        self.assertEqual(overdrawn["available_above_reserve_cents"], 0)
        self.assertEqual(overdrawn["available_after_full_set_aside_cents"], 0)
        self.assertEqual(overdrawn["upfront_funding_gap_cents"], 10_000)

    def test_set_aside_location_prevents_double_counting_current_balance(self):
        # The user has a €1,000 tax target, has mentally earmarked €900, and the
        # account still holds €1,000. By default the earmarked €900 is inside
        # that balance, so the full €1,000 remains protected from spending.
        inside = tax_planning_scenario(
            100_000,
            "2026-10-15",
            "2026-09-15",
            already_set_aside_cents=90_000,
            current_balance_cents=100_000,
        )
        self.assertEqual(inside["remaining_cents"], 10_000)
        self.assertEqual(inside["required_monthly_set_aside_cents"], 10_000)
        self.assertEqual(inside["set_aside_location"], "inside_current_balance")
        self.assertEqual(inside["protected_from_current_balance_cents"], 100_000)
        self.assertEqual(inside["available_after_full_set_aside_cents"], 0)
        self.assertEqual(inside["upfront_funding_gap_cents"], 0)

        outside = tax_planning_scenario(
            100_000,
            "2026-10-15",
            "2026-09-15",
            already_set_aside_cents=90_000,
            current_balance_cents=100_000,
            set_aside_location="outside_current_balance",
        )
        self.assertEqual(outside["set_aside_location"], "outside_current_balance")
        self.assertEqual(outside["protected_from_current_balance_cents"], 10_000)
        self.assertEqual(outside["available_after_full_set_aside_cents"], 90_000)
        self.assertEqual(outside["upfront_funding_gap_cents"], 0)

        no_balance = tax_planning_scenario(
            100_000,
            "2026-10-15",
            "2026-09-15",
            already_set_aside_cents=90_000,
            set_aside_location="outside_current_balance",
        )
        self.assertEqual(no_balance["protected_from_current_balance_cents"], 10_000)
        self.assertIsNone(no_balance["available_above_reserve_cents"])
        self.assertIsNone(no_balance["available_after_full_set_aside_cents"])
        self.assertIsNone(no_balance["upfront_funding_gap_cents"])

    def test_rejects_past_dates_invalid_money_and_non_text_label(self):
        invalid = [
            {"amount_cents": 0, "due_date": "2026-10-01", "reference_date": "2026-09-01"},
            {"amount_cents": True, "due_date": "2026-10-01", "reference_date": "2026-09-01"},
            {"amount_cents": 10_000, "due_date": "2026-09-01", "reference_date": "2026-09-01"},
            {"amount_cents": 10_000, "due_date": "bad", "reference_date": "2026-09-01"},
            {"amount_cents": 10_000, "due_date": "2026-10-01", "reference_date": "2026-09-01", "already_set_aside_cents": -1},
            {"amount_cents": 10_000, "due_date": "2026-10-01", "reference_date": "2026-09-01", "current_balance_cents": 1.5},
            {"amount_cents": 10_000, "due_date": "2026-10-01", "reference_date": "2026-09-01", "reserve_floor_cents": -1},
            {"amount_cents": 10_000, "due_date": "2026-10-01", "reference_date": "2026-09-01", "label": 123},
            {"amount_cents": 10_000, "due_date": "2026-10-01", "reference_date": "2026-09-01", "set_aside_location": "unknown"},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                tax_planning_scenario(**values)


if __name__ == "__main__":
    unittest.main()
