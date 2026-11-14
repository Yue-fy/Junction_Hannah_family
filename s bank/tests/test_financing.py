import json
import unittest

from scoach.db import connect, initialize_schema
from scoach.financing import financing_context


def insert_customer(conn, customer_id):
    conn.execute(
        "INSERT INTO customers VALUES(?,?,?,?)",
        (customer_id, "00100", 35, "{}"),
    )


def insert_event(conn, ref, mortgage_id, timestamp, event_type, **values):
    raw = {
        "mortgage_customer_id": mortgage_id,
        "timestamp": timestamp or "",
        "event_type": event_type,
        "property_id": values.pop("property_id", "P1"),
        "property_type": values.pop("property_type", ""),
        "property_price_estimate": values.pop("property_price_estimate", ""),
        "loan_amount": values.pop("loan_amount", ""),
        "equity_amount": values.pop("equity_amount", ""),
        "collateral_type": values.pop("collateral_type", ""),
        "collateral_value": values.pop("collateral_value", ""),
        "collateral_status": values.pop("collateral_status", ""),
        "expense_type": values.pop("expense_type", ""),
        "expense_amount": values.pop("expense_amount", ""),
        "decision": values.pop("decision", ""),
        "rejection_reason": values.pop("rejection_reason", ""),
        "note": values.pop("note", ""),
        **values,
    }
    conn.execute(
        "INSERT INTO mortgage_events VALUES(?,?,?,?,?)",
        (ref, mortgage_id, timestamp, event_type, json.dumps(raw)),
    )


class FinancingContextTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_schema(self.conn)
        insert_customer(self.conn, "LINKED")
        insert_customer(self.conn, "UNLINKED")
        final = {
            "mortgage_customer_id": "M1",
            "customer_id": "LINKED",
            "final_property_price_eur": "290000",
            "final_requested_loan_eur": "266000",
            "final_equity_amount_eur": "24000",
            "final_collateral_value_eur": "192000",
            "lfinal_loan_to_value": "0.91724137931034",
            "final_decision": "rejected",
            "rejection_reason": "insufficient_income",
            "required_monthly_income_eur": "4896.69065128991",
        }
        self.conn.execute(
            "INSERT INTO mortgage_final VALUES(?,?,?)",
            ("M1", "LINKED", json.dumps(final)),
        )

        # Insert deliberately out of chronological and reference order. SAS-like
        # timestamps cannot be sorted lexicographically across month names.
        insert_event(
            self.conn,
            "event-aug",
            "M1",
            "01AUG26:19:39:07",
            "expense_recorded",
            expense_type="maintenance_fee",
            expense_amount="230",
        )
        insert_event(
            self.conn,
            "event-jul-b",
            "M1",
            "30JUL26:04:39:15",
            "expense_recorded",
            expense_type="valuation_fee",
            expense_amount="250.005",
        )
        insert_event(
            self.conn,
            "event-jul-a",
            "M1",
            "30JUL26:04:39:15",
            "expense_recorded",
            expense_type="bank_fee",
            expense_amount="150",
        )
        insert_event(
            self.conn,
            "event-tax",
            "M1",
            "31JUL26:10:00:00",
            "expense_recorded",
            expense_type="transfer_tax",
            expense_amount="5800",
        )
        insert_event(
            self.conn,
            "event-decision",
            "M1",
            "12AUG26:15:39:00",
            "loan_decision",
            property_price_estimate="290000",
            loan_amount="266000",
            equity_amount="24000",
            collateral_value="192000",
            decision="rejected",
            rejection_reason="insufficient_income",
        )
        insert_event(
            self.conn,
            "event-undated",
            "M1",
            None,
            "document_received",
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_linked_history_returns_exact_recorded_values_and_chronology(self):
        result = financing_context(self.conn, "LINKED")

        self.assertTrue(result["available"])
        self.assertTrue(result["observed"])
        self.assertTrue(result["historical_context_only"])
        self.assertEqual(result["mortgage_customer_id"], "M1")
        self.assertEqual(result["property_price_cents"], 29_000_000)
        self.assertEqual(result["requested_loan_cents"], 26_600_000)
        self.assertEqual(result["equity_cents"], 2_400_000)
        self.assertEqual(result["collateral_value_cents"], 19_200_000)
        self.assertEqual(result["loan_to_value_basis_points"], 9_172)
        self.assertEqual(result["recorded_outcome"], {
            "decision": "rejected",
            "rejection_reason": "insufficient_income",
        })

        refs = [event["event_ref"] for event in result["events"]]
        self.assertEqual(
            refs,
            [
                "event-jul-a",
                "event-jul-b",
                "event-tax",
                "event-aug",
                "event-decision",
                "event-undated",
            ],
        )
        self.assertEqual(result["events"][0]["timestamp"], "2026-07-30T04:39:15")
        self.assertIsNone(result["events"][-1]["timestamp"])
        self.assertEqual(result["event_refs"], refs)
        self.assertTrue(result["fact_id"].startswith("financing-history:"))

    def test_recorded_fees_are_itemized_and_transfer_tax_is_not_inferred(self):
        result = financing_context(self.conn, "LINKED")

        self.assertEqual(result["recorded_fees_total_cents"], 643_001)
        self.assertEqual(result["recorded_transfer_tax_cents"], 580_000)
        self.assertEqual(
            [fee["expense_type"] for fee in result["recorded_fees"]],
            ["bank_fee", "valuation_fee", "transfer_tax", "maintenance_fee"],
        )
        self.assertEqual(
            [fee["amount_cents"] for fee in result["recorded_fees"]],
            [15_000, 25_001, 580_000, 23_000],
        )

        self.conn.execute("DELETE FROM mortgage_events WHERE event_ref='event-tax'")
        without_tax = financing_context(self.conn, "LINKED")
        self.assertEqual(without_tax["recorded_transfer_tax_cents"], 0)
        self.assertNotIn("transfer_tax", [fee["expense_type"] for fee in without_tax["recorded_fees"]])

    def test_income_threshold_is_not_exposed_as_comparable_or_used_for_advice(self):
        result = financing_context(self.conn, "LINKED")

        self.assertFalse(result["required_income_comparability"]["available"])
        self.assertIn("undocumented", result["required_income_comparability"]["reason"].lower())
        self.assertNotIn("required_monthly_income_cents", result)
        self.assertNotIn("affordability_score", result)
        self.assertNotIn("approval_probability", result)
        self.assertNotIn("recommended_loan_cents", result)
        joined = " ".join(result["limitations"]).lower()
        self.assertIn("historical", joined)
        self.assertIn("not", joined)
        self.assertIn("approval", joined)

    def test_unlinked_and_non_home_goals_do_not_receive_mortgage_assumptions(self):
        unlinked = financing_context(self.conn, "UNLINKED")
        self.assertFalse(unlinked["available"])
        self.assertEqual(unlinked["reason"], "no_linked_mortgage_history")
        self.assertEqual(unlinked["events"], [])

        for kind in ("vehicle", "custom"):
            with self.subTest(kind=kind):
                result = financing_context(self.conn, "LINKED", goal_type=kind)
                self.assertFalse(result["available"])
                self.assertEqual(result["goal_type"], kind)
                self.assertEqual(result["reason"], "no_financing_history_for_goal_type")
                self.assertNotIn("mortgage_customer_id", result)
                self.assertEqual(result["events"], [])

    def test_unknown_customer_goal_type_and_malformed_source_are_rejected(self):
        with self.assertRaises(ValueError):
            financing_context(self.conn, "MISSING")
        with self.assertRaises(ValueError):
            financing_context(self.conn, "LINKED", goal_type="boat")

        self.conn.execute(
            "UPDATE mortgage_final SET raw_json='not-json' WHERE customer_id='LINKED'"
        )
        with self.assertRaises(ValueError):
            financing_context(self.conn, "LINKED")


class RealMortgageFixtureTests(unittest.TestCase):
    def test_c0115_matches_imported_official_history_without_invented_tax(self):
        from tests.core_helper import demo_connection

        conn = demo_connection()
        try:
            result = financing_context(conn, "CUST00296")
        finally:
            conn.close()

        self.assertTrue(result["available"])
        self.assertEqual(result["mortgage_customer_id"], "C0115")
        self.assertEqual(result["property_price_cents"], 29_000_000)
        self.assertEqual(result["requested_loan_cents"], 26_600_000)
        self.assertEqual(result["equity_cents"], 2_400_000)
        self.assertEqual(result["recorded_outcome"]["rejection_reason"], "insufficient_income")
        self.assertEqual(result["recorded_fees_total_cents"], 63_000)
        self.assertEqual(result["recorded_transfer_tax_cents"], 0)
        dated = [event["timestamp"] for event in result["events"] if event["timestamp"]]
        self.assertEqual(dated, sorted(dated))


if __name__ == "__main__":
    unittest.main()
