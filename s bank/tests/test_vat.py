import tempfile
import unittest
from pathlib import Path

from scoach.api import Application
from scoach.db import connect, initialize_schema
from scoach.vat import estimate_transaction_vat, vat_lens


def row(day, category, gross_cents, mcc=None, ref="row"):
    return {
        "transaction_ref": ref,
        "date": day,
        "category": category,
        "amount_cents": -gross_cents,
        "transaction_type": "purchase",
        "merchant_id": None,
        "mcc_code": mcc,
    }


class TransactionVatTests(unittest.TestCase):
    def test_date_aware_rate_regimes_and_half_up_cents(self):
        cases = [
            (row("2024-12-01", "Lifestyle", 12_550, "5651"), 2_550, 2550),
            (row("2024-12-01", "Restaurants", 11_400, "5812"), 1_400, 1400),
            (row("2024-12-01", "Transportation", 11_000, "4111"), 1_000, 1000),
            (row("2025-06-01", "Restaurants", 11_400, "5814"), 1_400, 1400),
            (row("2025-06-01", "Transportation", 11_400, "4111"), 1_400, 1400),
            (row("2026-01-01", "Restaurants", 11_350, "5812"), 1_350, 1350),
            (row("2026-09-26", "Lifestyle", 23_644, "5651"), 4_804, 2550),
        ]
        for transaction, expected_vat, expected_rate in cases:
            with self.subTest(transaction=transaction):
                result = estimate_transaction_vat(transaction)
                self.assertEqual(result["estimated_vat_cents"], expected_vat)
                self.assertEqual(result["rate_basis_points"], expected_rate)
                self.assertTrue(result["estimated"])

    def test_exact_rate_boundaries_and_newspaper_exception(self):
        cases = [
            (row("2024-12-31", "Transportation", 11_000, "4111"), 1_000, 1000),
            (row("2025-01-01", "Transportation", 11_400, "4111"), 1_400, 1400),
            (row("2025-12-31", "Restaurants", 11_400, "5812"), 1_400, 1400),
            (row("2026-01-01", "Restaurants", 11_350, "5812"), 1_350, 1350),
            (row("2024-12-31", "Newspapers", 1_100), 100, 1000),
            (row("2026-01-01", "Newspapers", 1_100), 100, 1000),
        ]
        for transaction, expected_vat, expected_rate in cases:
            with self.subTest(transaction=transaction):
                result = estimate_transaction_vat(transaction)
                self.assertEqual(result["estimated_vat_cents"], expected_vat)
                self.assertEqual(result["rate_basis_points"], expected_rate)

    def test_mcc_wins_over_category_and_exempt_health_is_explicit(self):
        dentist = estimate_transaction_vat(row("2026-02-01", "Health", 10_000, "8021"))
        pharmacy = estimate_transaction_vat(row("2026-02-01", "Health", 11_350, "5912"))
        bar = estimate_transaction_vat(row("2026-02-01", "Restaurants", 12_550, "5813"))

        self.assertEqual((dentist["rate_band"], dentist["estimated_vat_cents"]), ("exempt", 0))
        self.assertEqual((pharmacy["rate_band"], pharmacy["estimated_vat_cents"]), ("reduced", 1_350))
        self.assertEqual((bar["rate_band"], bar["estimated_vat_cents"]), ("general", 2_550))
        self.assertEqual(bar["rate_source"], {"kind": "mcc", "value": "5813"})
        self.assertEqual(bar["mapping_quality"], "direct_mcc")

    def test_mcc_less_purchase_uses_documented_category_fallback(self):
        result = estimate_transaction_vat(row("2026-03-01", "Home & Tech", 12_550))
        self.assertEqual(result["estimated_vat_cents"], 2_550)
        self.assertEqual(result["rate_band"], "general")
        self.assertEqual(result["rate_source"], {"kind": "category", "value": "Home & Tech"})
        self.assertEqual(result["mapping_quality"], "category_fallback")

        unknown = estimate_transaction_vat(row("2026-03-01", "Other", 10_000))
        self.assertIsNone(unknown["estimated_vat_cents"])
        self.assertEqual(unknown["rate_band"], "unknown")

    def test_ambiguous_fallbacks_are_uncovered_or_explicitly_qualified(self):
        missing_health = estimate_transaction_vat(row("2026-03-01", "Health", 10_000))
        travel_agent = estimate_transaction_vat(row("2026-03-01", "Travel", 10_000, "4722"))
        unknown_transport = estimate_transaction_vat(row("2026-03-01", "Transportation", 10_000, "9999"))
        recreation = estimate_transaction_vat(row("2026-03-01", "Entertainment", 12_550, "7999"))

        for result in (missing_health, travel_agent, unknown_transport):
            self.assertIsNone(result["estimated_vat_cents"])
            self.assertEqual(result["mapping_quality"], "unmapped")
            self.assertIn("ambiguous", result["mapping_note"].lower())

        self.assertEqual(recreation["estimated_vat_cents"], 2_550)
        self.assertEqual(recreation["mapping_quality"], "broad_mcc_estimate")
        self.assertIn("ambiguous", recreation["mapping_note"].lower())

    def test_known_book_and_car_rental_mccs_do_not_use_broad_category_rate(self):
        book = estimate_transaction_vat(row("2026-03-01", "Lifestyle", 11_350, "5942"))
        car_rental = estimate_transaction_vat(row("2026-03-01", "Travel", 12_550, "7512"))

        self.assertEqual((book["rate_band"], book["estimated_vat_cents"]), ("reduced", 1_350))
        self.assertEqual((car_rental["rate_band"], car_rental["estimated_vat_cents"]), ("general", 2_550))
        self.assertEqual(book["mapping_quality"], "direct_mcc")
        self.assertEqual(car_rental["mapping_quality"], "direct_mcc")

    def test_non_spending_rows_are_not_vat_estimates(self):
        salary = row("2026-03-01", "Salary", 100_000)
        salary["amount_cents"] = 100_000
        salary["transaction_type"] = "salary"
        transfer = row("2026-03-01", "Invest Deposit", 10_000)
        transfer["transaction_type"] = "investment_deposit"
        self.assertIsNone(estimate_transaction_vat(salary))
        self.assertIsNone(estimate_transaction_vat(transfer))


class VatLensTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        initialize_schema(self.conn)
        self.conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")

    def tearDown(self):
        self.conn.close()

    def add(self, ref, day, category, amount, mcc=None, kind="purchase"):
        self.conn.execute(
            "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ref, "C", "A", day, "15SEP26:12:00:00", category, amount, 100_000, kind, None, mcc, 1, ref, "{}"),
        )

    def test_monthly_lens_sums_per_row_rounding_and_reports_coverage(self):
        self.add("food", "2026-09-01", "Groceries", -11_350, "5411")
        self.add("bar", "2026-09-02", "Restaurants", -12_550, "5813")
        self.add("dentist", "2026-09-03", "Health", -10_000, "8021")
        self.add("fallback", "2026-09-04", "Home & Tech", -12_550)
        self.add("unknown", "2026-09-05", "Other", -10_000)
        self.add("transfer", "2026-09-06", "Invest Deposit", -50_000, None, "investment_deposit")
        self.conn.commit()

        result = vat_lens(self.conn, "C", "2026-09-01", "2026-09-30")

        self.assertEqual(result["gross_spending_cents"], 56_450)
        self.assertEqual(result["covered_spending_cents"], 46_450)
        self.assertEqual(result["uncovered_spending_cents"], 10_000)
        self.assertEqual(result["estimated_vat_cents"], 6_450)
        self.assertEqual(result["coverage_basis_points"], 8229)
        self.assertEqual(len(result["transactions"]), 5)
        self.assertNotIn("transfer", result["transaction_refs"])
        self.assertTrue(result["estimated"])
        self.assertTrue(result["fact_id"].startswith("vat-lens:"))
        limitations = " ".join(result["limitations"]).lower()
        self.assertIn("estimated", limitations)
        self.assertIn("excise", limitations)

    def test_monthly_lens_rounds_each_row_before_summing(self):
        self.add("tiny-1", "2026-09-01", "Groceries", -4, "5411")
        self.add("tiny-2", "2026-09-02", "Groceries", -4, "5411")
        self.conn.commit()

        result = vat_lens(self.conn, "C", "2026-09-01", "2026-09-02")

        self.assertEqual(result["gross_spending_cents"], 8)
        self.assertEqual(result["estimated_vat_cents"], 0)
        self.assertEqual([item["estimated_vat_cents"] for item in result["transactions"]], [0, 0])

    def test_fact_provenance_changes_when_the_rate_evidence_changes(self):
        self.add("same-ref", "2026-09-01", "Groceries", -11_350, "5411")
        self.conn.commit()
        food = vat_lens(self.conn, "C", "2026-09-01", "2026-09-01")

        other = connect(":memory:")
        initialize_schema(other)
        other.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        other.execute(
            "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("same-ref", "C", "A", "2026-09-01", "15SEP26:12:00:00", "Restaurants", -11_350, 100_000, "purchase", None, "5813", 1, "same-ref", "{}"),
        )
        other.commit()
        try:
            bar = vat_lens(other, "C", "2026-09-01", "2026-09-01")
        finally:
            other.close()

        self.assertNotEqual(food["estimated_vat_cents"], bar["estimated_vat_cents"])
        self.assertNotEqual(food["fact_id"], bar["fact_id"])
        self.assertEqual(food["value_status"], "estimated")
        self.assertEqual(food["source_status"], "observed")
        self.assertFalse(food["scenario"])
        self.assertTrue(food["method_version"])
        self.assertTrue(food["rate_map_version"])

    def test_rejects_reversed_or_out_of_scope_period(self):
        self.add("only", "2026-09-01", "Groceries", -1_000, "5411")
        self.conn.commit()
        with self.assertRaises(ValueError):
            vat_lens(self.conn, "C", "2026-09-30", "2026-09-01")
        with self.assertRaises(ValueError):
            vat_lens(self.conn, "C", "2026-10-01", "2026-10-31")

    def test_rejects_exact_days_outside_observed_history(self):
        self.add("middle", "2026-09-15", "Groceries", -1_000, "5411")
        self.conn.commit()
        with self.assertRaises(ValueError):
            vat_lens(self.conn, "C", "2026-09-01", "2026-09-14")
        with self.assertRaises(ValueError):
            vat_lens(self.conn, "C", "2026-09-16", "2026-09-30")


class VatApiTests(unittest.TestCase):
    def test_month_endpoint_returns_decorated_estimate_and_rejects_unknown_query(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "demo.sqlite3"
            conn = connect(database)
            initialize_schema(conn)
            conn.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
            conn.execute(
                "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("food", "C", "A", "2026-09-01", "15SEP26:12:00:00", "Groceries", -11_350, 100_000, "purchase", None, "5411", 1, "food", "{}"),
            )
            conn.commit()
            conn.close()

            app = Application(database)
            status, response = app.handle("GET", "/api/vat?customer_id=C&month=2026-09")
            self.assertEqual(status, 200, response)
            data = response["data"]
            self.assertEqual(data["estimated_vat_cents"], 1_350)
            self.assertEqual(data["estimated_vat_display"], "13.50")
            self.assertEqual(data["transactions"][0]["rate_source"], {"kind": "mcc", "value": "5411"})
            self.assertEqual(data["status"], "observed")
            self.assertEqual(data["source_status"], "observed")
            self.assertEqual(data["value_status"], "estimated")
            self.assertFalse(data["scenario"])
            self.assertEqual(app.handle("GET", "/api/vat?customer_id=C&month=2026-09&guess=true")[0], 400)


if __name__ == "__main__":
    unittest.main()
