"""Decisions about future spending must not turn into historical category totals."""
import unittest
from contextlib import closing
from pathlib import Path
import tempfile
from unittest.mock import patch

from scoach.api import Application
from scoach.coach import interpret
from scoach.db import connect, initialize_schema
from scoach.query_scope import resolve_statistics


CONTEXT = {
    'customer_id': 'C', 'account_id': 'A', 'period': '2026-09',
    'comparison_period': '2026-08', 'reference_date': '2026-09-30', 'days': 7,
    'observed_start': '2026-07-01', 'observed_end': '2026-09-30',
    'interface_locale': 'en',
    'filter_catalog': {'categories': ['Restaurants', 'Entertainment', 'Groceries', 'Lifestyle', 'Housing'],
                       'roles': [], 'transaction_types': ['purchase'], 'merchant_ids': []},
    'facts': [{'id': 'restaurant_delta', 'value_cents': 9000},
              {'id': 'safe_fact', 'value_cents': 10000, 'available': True, 'status': 'scenario'}],
    'candidates': [
        {'id': 'restaurant_change', 'kind': 'explain_change',
         'text': 'Restaurant visits stayed level; average purchase size changed.',
         'fact_ids': ['restaurant_delta'], 'materiality': 1, 'explainability': 1},
        {'id': 'safe_to_spend', 'kind': 'safe_to_spend', 'available': True,
         'text': 'The estimate protects the reserve.', 'fact_ids': ['safe_fact'],
         'materiality': 1, 'explainability': 1},
    ],
}


class PlannedSpendingTests(unittest.TestCase):
    def ask(self, message, **changes):
        return interpret(message, {**CONTEXT, **changes}, api_key='')

    def test_exact_movie_wish_asks_for_budget_without_a_historical_result(self):
        result = self.ask('I want to go see a movie this week')
        self.assertEqual(result['intent'], 'safe_to_spend')
        self.assertTrue(result['needs_clarification'])
        self.assertEqual(result['clarification_code'], 'planned_purchase_cost')
        self.assertIn('movie', result['clarification_question'].lower())
        self.assertIn('budget', result['clarification_question'].lower())
        self.assertIsNone(result['query_scope'])
        self.assertIsNone(result['selected_candidate_id'])
        self.assertEqual(result['explanation_blocks'], [])
        self.assertIsNone(result['proposed_action'])

    def test_everyday_wishes_and_supported_languages_keep_the_planning_intent(self):
        for locale, message in [
            ('en', 'I would like to buy new clothes'),
            ('en', 'I want to have dinner at a restaurant this weekend'),
            ('en', 'Can I spend money on a movie this week?'),
            ('en', "I'm thinking about getting a coffee tomorrow"),
            ('fi', 'Haluan mennä elokuviin tällä viikolla'),
            ('fi', 'Voinko ostaa uudet vaatteet?'),
            ('sv', 'Jag vill gå på bio den här veckan'),
            ('sv', 'Jag skulle vilja köpa nya kläder'),
        ]:
            with self.subTest(message=message):
                result = self.ask(message, interface_locale=locale)
                self.assertEqual(result['clarification_code'], 'planned_purchase_cost')
                self.assertTrue(result['needs_clarification'])
                self.assertIsNone(result['query_scope'])
                self.assertIsNone(result['selected_candidate_id'])

    def test_known_euro_cost_compares_with_snapshot_allowance_in_plain_language(self):
        for amount, cost, remaining in [('€20', '20.00', '80.00'), ('20 euros', '20.00', '80.00'),
                                        ('EUR 20', '20.00', '80.00'), ('20,50 €', '20.50', '79.50')]:
            with self.subTest(amount=amount):
                result = self.ask(f'I want to see a movie this week. My total budget is {amount}.')
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['intent'], 'safe_to_spend')
                self.assertEqual(result['clarification_code'], 'planned_purchase_preview')
                self.assertEqual(result['parameters'], {'reference_date': '2026-09-30', 'days': 7})
                text = ' '.join(block['text'] for block in result['explanation_blocks'])
                for value in (cost, remaining, '2026-09-30'):
                    self.assertIn(value, text)
                self.assertIn('snapshot', text)
                self.assertEqual(result['explanation_blocks'][0]['fact_ids'], ['safe_fact'])
                self.assertIsNone(result['query_scope'])
                self.assertIsNone(result['proposed_action'])

    def test_cost_above_allowance_describes_the_gap_without_approval(self):
        result = self.ask('Can I spend €120 on dinner this week?')
        self.assertFalse(result['needs_clarification'])
        text = ' '.join(block['text'] for block in result['explanation_blocks'])
        self.assertIn('exceed', text.lower())
        self.assertIn('20.00', text)
        self.assertIn('2026-09-30', text)
        self.assertNotIn('approved', text.lower())

    def test_zero_allowance_does_not_claim_reserves_or_expected_costs_are_funded(self):
        result = self.ask('I want to see a movie for €20',
                          facts=[{'id': 'safe_fact', 'value_cents': 0, 'available': True}])
        self.assertFalse(result['needs_clarification'])
        prose = ' '.join(block['text'] for block in result['explanation_blocks'])
        self.assertIn('no room', prose.lower())
        self.assertIn('0.00', prose)
        self.assertIn('20.00', prose)
        self.assertNotIn('protects', prose.lower())
        self.assertNotIn('fits', prose.lower())

    def test_unknown_or_ambiguous_price_does_not_become_a_numeric_plan(self):
        for amount in ('-€20', '€20 or €30', '€20-30', '€20.555', '$20', '20', 'under €20',
                       '€20 excluding travel', '€20 each'):
            with self.subTest(amount=amount):
                result = self.ask(f'I want to see a movie this week for {amount}')
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'planned_purchase_price')
                self.assertIsNone(result['query_scope'])
                self.assertIsNone(result['selected_candidate_id'])
                self.assertEqual(result['explanation_blocks'], [])

    def test_major_or_recurring_commitments_are_not_assessed_from_weekly_allowance(self):
        for message in ('I want to buy a car for €20000', 'I want to buy a home for €200000',
                        'I want to travel next month for €300', 'I need to pay rent this month',
                        'I want to buy clothes for €5000', 'I want a €20 cinema subscription every month',
                        'I want to buy clothes using a €200 loan'):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertTrue(result['needs_clarification'])
                self.assertNotEqual(result['clarification_code'], 'planned_purchase_preview')
                self.assertIsNone(result['query_scope'])
                self.assertIsNone(result['selected_candidate_id'])

    def test_future_window_does_not_silently_use_the_snapshot_week(self):
        for message in ('I want to see a movie next month for €20',
                        'I want to see a movie in December for €20',
                        'I want to see a movie on 2026-12-01 for €20',
                        'I want to see a movie this week and next month for €20'):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'planned_purchase_timing')
                self.assertIsNone(result['query_scope'])
                self.assertEqual(result['explanation_blocks'], [])

    def test_specific_planned_days_and_payday_windows_do_not_become_seven_days(self):
        for locale, message in [
            ('en', 'Can I spend EUR20 on a movie before payday?'),
            ('en', 'Can I spend EUR20 on a movie until my next payday?'),
            ('en', 'Can I spend EUR20 on a movie on Friday?'),
            ('en', 'I want to see a movie this weekend for EUR20'),
            ('en', 'I want a coffee tomorrow for EUR5'),
            ('en', 'I want to see a movie over the next two weeks for EUR20'),
            ('fi', 'Haluan mennä elokuviin ennen palkkapäivää. Budjetti on EUR20.'),
            ('fi', 'Haluan mennä elokuviin perjantaina. Budjetti on EUR20.'),
            ('fi', 'Haluan mennä elokuviin viikonloppuna. Budjetti on EUR20.'),
            ('sv', 'Jag vill gå på bio före nästa lön. Min budget är EUR20.'),
            ('sv', 'Jag vill gå på bio på fredag. Min budget är EUR20.'),
            ('sv', 'Jag vill gå på bio i helgen. Min budget är EUR20.'),
        ]:
            with self.subTest(message=message):
                result = self.ask(message, interface_locale=locale)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'planned_purchase_timing')
                self.assertIsNone(result['query_scope'])
                self.assertIsNone(result['selected_candidate_id'])
                self.assertEqual(result['explanation_blocks'], [])

    def test_snapshot_week_remains_available_in_each_product_language(self):
        for locale, message in [('en', 'I want to see a movie this week for EUR20'),
                                 ('fi', 'Haluan mennä elokuviin tällä viikolla. Budjetti on EUR20.'),
                                 ('sv', 'Jag vill gå på bio den här veckan. Min budget är EUR20.')]:
            with self.subTest(message=message):
                result = self.ask(message, interface_locale=locale)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'planned_purchase_preview')
                self.assertEqual(result['parameters']['reference_date'], '2026-09-30')
                self.assertEqual(result['parameters']['days'], 7)

    def test_missing_forecast_history_never_claims_the_purchase_fits(self):
        result = self.ask('I want to see a movie for €20',
                          facts=[{'id': 'safe_fact', 'value_cents': None, 'available': False}],
                          candidates=[{**CONTEXT['candidates'][1], 'available': False}])
        text = ' '.join(block['text'] for block in result['explanation_blocks'])
        self.assertEqual(result['intent'], 'safe_to_spend')
        self.assertIn('enough', text.lower())
        self.assertNotIn('fits', text.lower())
        self.assertNotIn('100.00', text)

    def test_historical_requests_remain_explicit_statistics(self):
        for message, category, start in (
            ('How much did I spend on entertainment?', 'Entertainment', '2026-09-01'),
            ('Paljonko käytin elokuviin?', 'Entertainment', '2026-09-01'),
            ('I want to know how much I spent on entertainment', 'Entertainment', '2026-09-01'),
            ('Show restaurant spending in August', 'Restaurants', '2026-08-01'),
            ('Restaurants in August', 'Restaurants', '2026-08-01'),
        ):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['intent'], 'transaction_statistics')
                self.assertEqual(result['query_scope']['filters'], {'category': category})
                self.assertEqual(result['query_scope']['start'], start)

    def test_a_new_plan_does_not_inherit_a_prior_restaurant_query(self):
        previous = self.ask('How much did I spend on restaurants in August?')['query_scope']
        result = self.ask('I want to go see a movie this week', previous_query=previous)
        self.assertEqual(result['clarification_code'], 'planned_purchase_cost')
        self.assertIsNone(result['query_scope'])
        ordinary = self.ask('And groceries?', previous_query=previous)
        self.assertEqual(ordinary['query_scope']['filters'], {'category': 'Groceries'})
        self.assertEqual(ordinary['query_scope']['start'], '2026-08-01')

    def test_greetings_support_and_unrelated_questions_never_select_restaurants(self):
        for message in ('Hello', 'Thanks', 'I feel stressed about money this month',
                        'What should I do this month?', 'Tell me about my balance',
                        'Explain how football changed this month', 'My movie was great',
                        'Do you like restaurants?', 'What month is the next election?'):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertTrue(result['needs_clarification'])
                self.assertIsNone(result['selected_candidate_id'])
                self.assertIsNone(result['query_scope'])
                self.assertEqual(result['explanation_blocks'], [])
                self.assertTrue(result['clarification_question'])

    def test_explicit_financial_change_still_uses_its_grounded_candidate(self):
        result = self.ask('What changed in restaurants?')
        self.assertFalse(result['needs_clarification'])
        self.assertEqual(result['selected_candidate_id'], 'restaurant_change')

    def test_stated_worry_is_not_turned_into_a_salary_or_category_total(self):
        for message in ("I'm worried about my restaurant spending", 'I feel stressed about my income',
                        'I am anxious about my salary'):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'coaching_support')
                self.assertIsNone(result['query_scope'])
                self.assertIsNone(result['selected_candidate_id'])

    def test_language_model_cannot_turn_a_local_plan_back_into_history(self):
        calls = []
        def transport(payload, timeout):
            calls.append(payload)
            return {'intent': 'transaction_statistics', 'parameters': {'period': '2026-09', 'category': 'Entertainment'},
                    'needs_clarification': False, 'explanation_blocks': []}
        result = interpret('I want to go see a movie this week', CONTEXT, transport=transport, api_key='test')
        self.assertEqual(result['clarification_code'], 'planned_purchase_cost')
        self.assertEqual(calls, [])
        result = interpret('I want to see a movie for €20', CONTEXT, transport=transport, api_key='test')
        self.assertEqual(result['clarification_code'], 'planned_purchase_preview')
        self.assertEqual(calls, [])

    def test_mixed_planning_and_history_request_keeps_both_meanings_explicit(self):
        result = self.ask('I want to go see a movie this week, and how much did I spend on entertainment last month?')
        self.assertTrue(result['needs_clarification'])
        self.assertIsNone(result['query_scope'])
        self.assertEqual(result['clarification_code'], 'mixed_request')

    def test_unresolved_historical_week_and_date_predicates_are_not_dropped(self):
        for question in ('Restaurant spending this week', 'Restaurant spending next week',
                         'Restaurant spending over the past three months',
                         'Restaurant spending before 2026-09-15',
                         'Restaurant spending since 2026-08-15',
                         'Restaurant spending in August and last month'):
            with self.subTest(question=question):
                result = resolve_statistics(question, CONTEXT)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'period_scope')
                self.assertIsNone(result['query_scope'])


class PlannedSpendingAPITests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {'GEMINI_API_KEY': ''})
        environment.start()
        self.addCleanup(environment.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'plans.sqlite3'
        with closing(connect(self.database)) as conn, conn:
            initialize_schema(conn)
            conn.execute("INSERT INTO customers VALUES('C','00100',25,'{}')")
            rows = [('2026-07-01', 'Salary', 200000, 'salary'),
                    ('2026-07-15', 'Entertainment', -1000, 'purchase'),
                    ('2026-08-01', 'Salary', 200000, 'salary'),
                    ('2026-08-15', 'Entertainment', -2000, 'purchase'),
                    ('2026-09-01', 'Salary', 200000, 'salary'),
                    ('2026-09-15', 'Entertainment', -3000, 'purchase'),
                    ('2026-09-30', 'Restaurants', -4000, 'purchase')]
            balance = 0
            for line, (day, category, amount, kind) in enumerate(rows, 1):
                balance += amount
                conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             (f'row-{line}', 'C', 'A', day, day + 'T12:00:00', category, amount,
                              balance, kind, 'M', '7832' if category == 'Entertainment' else None,
                              line, f'hash-{line}', '{}'))
        self.app = Application(self.database)

    def ask(self, message, locale='en'):
        status, envelope = self.app.handle('POST', '/api/coach', {
            'customer_id': 'C', 'month': '2026-09', 'locale': locale, 'message': message})
        self.assertEqual(status, 200, envelope)
        return envelope['data']

    def test_exact_request_and_price_reply_use_the_plan_without_saving_state(self):
        initial = self.ask('I want to go see a movie this week')
        self.assertEqual(initial['clarification_code'], 'planned_purchase_cost')
        self.assertNotIn('tool_result', initial)
        result = self.ask('I want to go see a movie this week\nMy total budget is EUR20.')
        self.assertEqual(result['tool_kind'], 'safe_to_spend')
        self.assertTrue(result['tool_result']['available'])
        prose = ' '.join(block['text'] for block in result['explanation_blocks'])
        self.assertIn('20.00', prose)
        self.assertIn('snapshot dated 2026-09-30', prose)
        self.assertEqual(result['explanation_blocks'][0]['fact_ids'], [result['tool_fact_id']])
        self.assertTrue(result['source_refs']['transaction_refs'])
        historical = self.ask('How much did I spend on entertainment this month?')
        self.assertEqual(historical['tool_result']['metric_value_cents'], 3000)
        self.assertEqual(historical['source_refs']['transaction_refs'], ['row-6'])
        with closing(connect(self.database)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM audit_events').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM goals').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM scenarios').fetchone()[0], 0)

    def test_english_price_suffix_completes_finnish_and_swedish_plan_context(self):
        for locale, original in [('fi', 'Haluan mennä elokuviin tällä viikolla'),
                                 ('sv', 'Jag vill gå på bio den här veckan')]:
            with self.subTest(locale=locale):
                result = self.ask(original + '\nMy total budget is EUR20.', locale)
                self.assertEqual(result['tool_kind'], 'safe_to_spend')
                self.assertEqual(result['clarification_code'], 'planned_purchase_preview')
                prose = ' '.join(block['text'] for block in result['explanation_blocks'])
                self.assertIn('20.00', prose)
                self.assertIn('2026-09-30', prose)
                self.assertNotIn('Here are the exact observed results', prose)

    def test_future_tax_planning_does_not_run_historical_tax_evidence(self):
        for locale, message in [
            ('en', 'Help me plan for tax'),
            ('en', 'I want to plan a tax amount'),
            ('en', 'How much tax should I set aside?'),
            ('en', 'Help me budget for my tax payment'),
            ('fi', 'Haluan suunnitella verojen maksun'),
            ('sv', 'Hjälp mig planera för skatt'),
            ('sv', 'Hur mycket ska jag lägga undan för skatt?'),
        ]:
            with self.subTest(message=message):
                result = self.ask(message, locale)
                self.assertEqual(result['intent'], 'plan_tax')
                self.assertTrue(result['needs_clarification'])
                self.assertNotIn('tool_result', result)
                self.assertEqual(result['parameters'], {})
                self.assertIsNone(result['query_scope'])

    def test_tax_already_paid_remains_a_recorded_evidence_question(self):
        for locale, message in [('en', 'How much tax did I pay last month?'),
                                 ('fi', 'Paljonko maksoin veroja?'),
                                 ('sv', 'Hur mycket skatt betalade jag?')]:
            with self.subTest(message=message):
                result = self.ask(message, locale)
                self.assertEqual(result['intent'], 'observed_tax_evidence')
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['tool_kind'], 'observed_tax_evidence')

    def test_personal_tax_liability_cannot_be_answered_with_paid_tax_records(self):
        for locale, message in [
            ('en', 'How much tax do I owe?'),
            ('en', 'Do I owe taxes?'),
            ('en', 'What is my personal tax liability?'),
            ('en', 'How much tax should I pay?'),
            ('fi', 'Paljonko olen veroa velkaa?'),
            ('fi', 'Kuinka paljon minun pitää maksaa veroja?'),
            ('sv', 'Hur mycket skatt är jag skyldig?'),
            ('sv', 'Hur mycket skatt ska jag betala?'),
            ('sv', 'Måste jag betala skatt?'),
        ]:
            with self.subTest(message=message):
                result = self.ask(message, locale)
                self.assertEqual(result['intent'], 'plan_tax')
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'liability_unavailable')
                self.assertIsNone(result['query_scope'])
                self.assertIsNone(result['selected_candidate_id'])
                self.assertEqual(result['parameters'], {})
                self.assertEqual(result['explanation_blocks'], [])
                self.assertNotIn('tool_result', result)
                self.assertTrue(result['clarification_options'])
                planner = self.ask(result['clarification_options'][0], locale)
                self.assertEqual(planner['intent'], 'plan_tax')
                self.assertTrue(planner['needs_clarification'])
                self.assertIsNone(planner['clarification_code'])
                self.assertNotIn('tool_result', planner)

    def test_a_declared_tax_amount_with_explicit_planning_still_opens_the_planner(self):
        result = self.ask('I owe €500 in tax; help me plan for that payment')
        self.assertEqual(result['intent'], 'plan_tax')
        self.assertTrue(result['needs_clarification'])
        self.assertIsNone(result['clarification_code'])
        self.assertNotIn('tool_result', result)


if __name__ == '__main__':
    unittest.main()
