import unittest
from pathlib import Path

from scoach.api import Application
from scoach.db import connect


DATABASE = Path(__file__).resolve().parents[1] / "var" / "scoach.sqlite3"


class OfficialBriefQuestionTests(unittest.TestCase):
    def setUp(self):
        self.app = Application(DATABASE)

    def ask(self, message, locale="en"):
        status, response = self.app.handle(
            "POST",
            "/api/coach",
            {
                "customer_id": "CUST00001",
                "month": "2026-09",
                "locale": locale,
                "message": message,
            },
        )
        self.assertEqual(status, 200, response)
        return response["data"]

    def test_taxi_question_returns_exact_transportation_rows(self):
        result = self.ask("How much did I spend on taxis last month?")
        self.assertEqual(result["intent"], "transaction_statistics")
        self.assertEqual(result["tool_kind"], "transaction_statistics")
        self.assertEqual(result["tool_result"]["filters"], {"category": "Transportation"})
        self.assertEqual(result["tool_result"]["outflow_total_cents"], 26_680)
        self.assertEqual(result["tool_result"]["transaction_count"], 6)
        self.assertEqual(len(result["source_refs"]["transaction_refs"]), 6)

    def test_dining_reduction_question_returns_read_only_twenty_percent_scenario(self):
        conn = connect(DATABASE)
        try:
            before = conn.execute(
                "SELECT count(*) FROM scenarios WHERE customer_id='CUST00001'"
            ).fetchone()[0]
        finally:
            conn.close()

        result = self.ask("How much could I save if I reduced dining out by 20%?")

        self.assertEqual(result["intent"], "spending_adjustment")
        self.assertEqual(result["tool_kind"], "spending_adjustment_preview")
        self.assertEqual(result["tool_result"]["category"], "Restaurants")
        self.assertEqual(result["tool_result"]["percent"], "20")
        self.assertEqual(result["tool_result"]["actual_total_cents"], 22_570)
        self.assertEqual(result["tool_result"]["adjustable_base_cents"], 22_570)
        self.assertEqual(result["tool_result"]["modeled_monthly_contribution_cents"], 4_514)
        self.assertEqual(len(result["tool_result"]["transaction_refs"]), 10)
        self.assertFalse(result["tool_result"]["observed"])
        self.assertEqual(result["tool_result"]["persistence"], "not_saved")

        conn = connect(DATABASE)
        try:
            after = conn.execute(
                "SELECT count(*) FROM scenarios WHERE customer_id='CUST00001'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(after, before)

    def test_spender_question_returns_three_basket_profile_without_score_or_judgment(self):
        result = self.ask("What kind of spender am I?")
        self.assertEqual(result["intent"], "spending_profile")
        self.assertEqual(result["tool_kind"], "three_basket_profile")
        profile = result["tool_result"]
        self.assertEqual(profile["period"], "2026-09")
        self.assertEqual(
            [(row["role"], row["amount_cents"]) for row in profile["baskets"]],
            [
                ("fixed_obligation", 126_690),
                ("flexible_essential", 0),
                ("discretionary", 61_176),
            ],
        )
        self.assertEqual(profile["total_consumption_cents"], 187_866)
        self.assertNotIn("score", profile)
        self.assertNotIn("type", profile)
        prose = " ".join(block["text"] for block in result["explanation_blocks"]).lower()
        for judgment in ("good", "bad", "healthy", "unhealthy", "overspender"):
            self.assertNotIn(judgment, prose)

    def test_safe_to_spend_question_keeps_the_existing_bounded_scenario(self):
        result = self.ask("What is safe for me to spend this week?")
        self.assertEqual(result["intent"], "safe_to_spend")
        self.assertEqual(result["selected_candidate_id"], "safe_to_spend")
        self.assertEqual(result["tool_kind"], "safe_to_spend")
        self.assertEqual(result["tool_source"], "deterministic_safe_to_spend")
        self.assertEqual(result["tool_result"]["safe_to_spend_cents"], 328_831)
        self.assertEqual(result["tool_result"]["horizon_days"], 7)
        self.assertEqual(result["tool_result"]["reserve_floor_cents"], 50_000)
        self.assertTrue(result["tool_result"]["available"])
        self.assertTrue(result["tool_result"]["assumptions"])
        self.assertEqual(result["tool_fact_id"], result["tool_result"]["fact_id"])
        self.assertTrue(result["source_refs"]["transaction_refs"])
        self.assertTrue(result["explanation_blocks"])

    def test_finnish_restaurant_question_returns_exact_september_rows(self):
        result = self.ask("Paljonko käytin ravintoloihin syyskuussa?", locale="fi")
        self.assertEqual(result["intent"], "transaction_statistics")
        self.assertEqual(result["parameters"]["category"], "Restaurants")
        self.assertEqual(result["tool_result"]["outflow_total_cents"], 22_570)
        self.assertEqual(result["tool_result"]["transaction_count"], 10)
        self.assertEqual(len(result["source_refs"]["transaction_refs"]), 10)

    def test_model_cannot_invent_an_adjustment_percentage_hidden_by_redaction(self):
        def transport(payload, timeout):
            return {
                "intent": "spending_adjustment",
                "parameters": {
                    "period": "2026-09",
                    "category": "Restaurants",
                    "percent": 37,
                },
                "selected_candidate_id": None,
                "needs_clarification": False,
                "clarification_question": None,
                "proposed_action": None,
                "explanation_blocks": [
                    {
                        "text": "Die Planung basiert auf beobachteten Buchungen.",
                        "fact_ids": [payload["context"]["facts"][0]["id"]],
                    }
                ],
            }

        app = Application(DATABASE, coach_transport=transport)
        status, response = app.handle(
            "POST",
            "/api/coach",
            {
                "customer_id": "CUST00001",
                "month": "2026-09",
                "locale": "en",
                "message": "Wie viel spare ich, wenn ich Restaurantbesuche um 20% reduziere?",
            },
        )
        self.assertEqual(status, 200, response)
        result = response["data"]
        self.assertEqual(result["intent"], "explain_change")
        self.assertEqual(result["fallback_reason"], "invalid_response")
        self.assertNotIn("tool_result", result)


if __name__ == "__main__":
    unittest.main()
