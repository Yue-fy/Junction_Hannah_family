"""Customer wording regressions using independent, inspectable ledger amounts."""
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from scoach.api import Application
from scoach.db import connect, initialize_schema


class CustomerQueryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'queries.sqlite3'
        with closing(connect(self.database)) as conn, conn:
            initialize_schema(conn)
            conn.execute("INSERT INTO customers VALUES('C','00100',25,'{}')")
            rows = [
                ('salary-jul', '2026-07-01', 'Salary', 200000, 'salary'),
                ('restaurant-jul', '2026-07-14', 'Restaurants', -1000, 'purchase'),
                ('salary-aug', '2026-08-01', 'Salary', 200000, 'salary'),
                ('restaurant-aug', '2026-08-15', 'Restaurants', -2000, 'purchase'),
                ('investment-aug', '2026-08-20', 'Invest Deposit', -5000, 'investment_deposit'),
                ('salary-sep', '2026-09-01', 'Salary', 200000, 'salary'),
                ('restaurant-sep', '2026-09-02', 'Restaurants', -4000, 'purchase'),
                ('grocery-sep', '2026-09-07', 'Groceries', -3000, 'purchase'),
                ('investment-sep', '2026-09-15', 'Invest Deposit', -12000, 'investment_deposit'),
                ('restaurant-end', '2026-09-30', 'Restaurants', -6000, 'purchase'),
            ]
            balance = 0
            for line, (ref, day, category, amount, kind) in enumerate(rows, 1):
                balance += amount
                conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             (ref, 'C', 'A', day, day + 'T12:00:00', category,
                              amount, balance, kind, 'M' + str(line), None, line, ref, '{}'))
        self.app = Application(self.database)

    def ask(self, message, locale='en'):
        status, envelope = self.app.handle('POST', '/api/coach', {
            'customer_id': 'C', 'month': '2026-09', 'locale': locale,
            'message': message,
        })
        self.assertEqual(status, 200, envelope)
        return envelope['data']

    def test_exact_dining_chip_previews_twenty_percent_instead_of_full_spending(self):
        result = self.ask('How much could I save by reducing dining out by 20%?')
        self.assertFalse(result['needs_clarification'])
        self.assertEqual(result['tool_kind'], 'spending_adjustment_preview')
        self.assertEqual(result['parameters'], {
            'period': '2026-09', 'category': 'Restaurants', 'percent': 20,
        })
        self.assertEqual(result['tool_result']['actual_total_cents'], 10000)
        self.assertEqual(result['tool_result']['modeled_monthly_contribution_cents'], 2000)
        self.assertEqual(result['tool_result']['persistence'], 'not_saved')

    def test_reduction_inflections_keep_complete_decimal_and_word_percentages(self):
        cases = [
            ('reducing', '12.5%', 1250), ('reducing', 'twelve point five percent', 1250),
            ('cutting', '0.5 percent', 50), ('lowering', 'twenty-five percent', 2500),
            ('reduced', '20%', 2000), ('reduce', '20%', 2000),
        ]
        for action, percentage, expected in cases:
            with self.subTest(action=action, percentage=percentage):
                result = self.ask(f'How much could I save by {action} dining out by {percentage}?')
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['tool_kind'], 'spending_adjustment_preview')
                self.assertEqual(result['tool_result']['modeled_monthly_contribution_cents'], expected)

    def test_reducing_does_not_turn_invalid_percentages_into_spending_totals(self):
        for percentage in ('120%', '-5%', '12.5.0%', '20% or 30%',
                           'one thousand twenty percent', 'a little'):
            with self.subTest(percentage=percentage):
                result = self.ask(f'How much could I save by reducing dining out by {percentage}?')
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'adjustment_percentage')
                self.assertNotIn('tool_result', result)

    def test_reduction_keeps_explicit_month_and_unsupported_conditions(self):
        august = self.ask('How much could I save by reducing dining out by 20% in August 2026?')
        self.assertEqual(august['parameters']['period'], '2026-08')
        self.assertEqual(august['tool_kind'], 'spending_adjustment_preview')
        self.assertEqual(august['tool_result']['modeled_monthly_contribution_cents'], 400)
        for message in (
            'How much could I save by reducing dining out by 20% on weekdays?',
            'How much could I save by reducing dining out by 20% excluding the biggest purchase?',
            'How much could I save by reducing dining out and travel by 20%?',
        ):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertTrue(result['needs_clarification'])
                self.assertNotIn('tool_result', result)

    def test_dated_explanations_cannot_cite_selected_month_facts(self):
        cases = [
            ('en', 'What changed in restaurants in August 2026?'),
            ('fi', 'Mikä muuttui ravintolamenoissa elokuussa 2026?'),
            ('sv', 'Vad förändrades i restaurangutgifterna i augusti 2026?'),
            ('en', 'What changed in restaurants from 2026-09-01 to 2026-09-15?'),
            ('en', 'What changed in restaurants in August 2030?'),
        ]
        for locale, message in cases:
            with self.subTest(locale=locale, message=message):
                result = self.ask(message, locale)
                self.assertTrue(result['needs_clarification'])
                self.assertIsNone(result['selected_candidate_id'])
                self.assertEqual(result['explanation_blocks'], [])
                self.assertEqual(result['parameters'], {})
                self.assertNotIn('tool_result', result)

    def test_selected_month_explanation_remains_available(self):
        result = self.ask('What changed in restaurants in September 2026?')
        self.assertFalse(result['needs_clarification'])
        self.assertEqual(result['intent'], 'explain_change')
        self.assertTrue(result['explanation_blocks'])

    def test_vague_savings_wishes_start_with_exploration_in_all_product_languages(self):
        cases = [
            ('en', 'Plan an emergency buffer'),
            ('en', 'I want to save but I do not know how much'),
            ('en', 'I want a buffer but I do not know the amount yet'),
            ('fi', 'Suunnittele vararahasto'),
            ('fi', 'Haluan säästää, mutta en tiedä vielä summaa'),
            ('fi', 'Haluan puskurin, mutta en tiedä vielä summaa'),
            ('sv', 'Planera en buffert'),
            ('sv', 'Jag vill spara men jag vet inte hur mycket'),
            ('sv', 'Jag vill ha en buffert men jag vet inte beloppet ännu'),
        ]
        for locale, message in cases:
            with self.subTest(locale=locale, message=message):
                result = self.ask(message, locale)
                self.assertEqual(result['intent'], 'plan_goal')
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'exploratory_goal')
                self.assertTrue(result['clarification_question'])
                self.assertEqual(result['locale'], locale)
                self.assertEqual(result['parameters'], {})
                self.assertIsNone(result['proposed_action'])
                self.assertNotIn('tool_result', result)

    def test_buffer_word_does_not_override_income_statistics_or_unknown_qualifiers(self):
        income = self.ask('How much income did I receive to build my buffer?')
        self.assertEqual(income['query_scope']['metric'], 'inflow_total')
        self.assertEqual(income['tool_result']['metric_value_cents'], 200000)
        spending = self.ask('How much did I spend on restaurants while saving for a buffer?')
        self.assertEqual(spending['query_scope']['metric'], 'outflow_total')
        self.assertEqual(spending['tool_result']['metric_value_cents'], 10000)
        for message in ('How much did I spend on buffer supplies?',
                        'Plan an emergency buffer excluding groceries'):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertTrue(result['needs_clarification'])
                self.assertNotEqual(result['clarification_code'], 'exploratory_goal')
                self.assertNotIn('tool_result', result)

    def test_cashflow_month_or_unknown_window_does_not_use_selected_month_forecast(self):
        for locale, question in (
            ('en', 'Show cash flow in August 2026'),
            ('fi', 'Näytä kassavirta elokuussa 2026'),
            ('sv', 'Visa kassaflöde i augusti 2026'),
            ('en', 'Show cash flow last summer'),
            ('en', 'Show cash flow over the next six weeks'),
        ):
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertEqual(result['intent'], 'preview_cashflow')
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'period_scope')
                self.assertEqual(result['parameters'], {})
                self.assertEqual(result['explanation_blocks'], [])
                self.assertNotIn('tool_result', result)

    def test_cashflow_explicit_reference_date_reaches_existing_forecast_endpoint(self):
        for locale, question in (
            ('en', 'Show cash flow as of 2026-08-31'),
            ('fi', 'Näytä kassavirta alkaen 2026-08-31'),
            ('sv', 'Visa kassaflöde från 2026-08-31'),
        ):
            with self.subTest(locale=locale):
                result = self.ask(question, locale)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['parameters'], {'reference_date': '2026-08-31', 'days': 30})
                status, envelope = self.app.handle('GET', '/api/forecast?customer_id=C&month=2026-09&as_of=' + result['parameters']['reference_date'])
                self.assertEqual(status, 200, envelope)
                self.assertEqual(envelope['data']['as_of'], '2026-08-31')
        for question in ('Show cash flow as of 2026-10-01',
                         'Show cash flow as of 2026-08-32',
                         'Show cash flow as of 2026-08-31 for 90 days'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['parameters'], {})

    def test_investment_single_month_reaches_existing_endpoint_without_a_year_window(self):
        for locale, question in (
            ('en', 'Show investment transfers in August 2026'),
            ('en', 'Show my investment transfers last month'),
            ('en', 'Show investment transfers in 2026-08'),
            ('fi', 'Näytä sijoitussiirtoni elokuussa 2026'),
            ('fi', 'Näytä sijoitussiirrot elokuussa 2026'),
            ('sv', 'Visa mina investeringsöverföringar i augusti 2026'),
        ):
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['parameters'], {'period': '2026-08', 'months': 1})
                self.assertIsNone(result['selected_candidate_id'])
                self.assertEqual(result['explanation_blocks'], [])
                status, envelope = self.app.handle('GET', '/api/investments?customer_id=C&month=' + result['parameters']['period'] + '&months=' + str(result['parameters']['months']))
                self.assertEqual(status, 200, envelope)
                self.assertEqual(envelope['data']['requested_period_months'], 1)
                self.assertEqual(envelope['data']['start_month'], '2026-08')
                self.assertEqual(envelope['data']['end_month'], '2026-08')
                self.assertEqual(envelope['data']['total_contributions_cents'], 5000)
                self.assertEqual(envelope['data']['transaction_refs'], ['investment-aug'])

    def test_unresolved_investment_windows_do_not_fall_back_to_twelve_months(self):
        for question in ('Show investment transfers over the last 3 months',
                         'Show investment transfers last summer',
                         'Show investment transfers in August and September 2026',
                         'Show investment transfers in August 2026 and last summer',
                         'Show investment transfers before August 2026'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'period_scope')
                self.assertEqual(result['parameters'], {})
                self.assertEqual(result['explanation_blocks'], [])

    def test_undated_supporting_tools_keep_the_selected_data_clock(self):
        for locale, question in (('en', 'Show cash flow'), ('fi', 'Näytä kassavirta'),
                                 ('sv', 'Visa kassaflöde')):
            with self.subTest(question=question):
                result = self.ask(question, locale)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['parameters'], {'reference_date': '2026-09-30', 'days': 30})
        result = self.ask('Show my investment transfers')
        self.assertFalse(result['needs_clarification'])
        self.assertEqual(result['parameters'], {'period': '2026-09', 'months': 12})

    def test_supported_tool_dates_cannot_be_overridden_by_optional_language_model(self):
        self.app.coach_transport = lambda payload, timeout: {
            'intent': 'investment_cashflow', 'parameters': {'period': '2026-09', 'months': 12},
            'needs_clarification': False, 'explanation_blocks': [],
        }
        investment = self.ask('Show investment transfers in August 2026')
        self.assertEqual(investment['parameters'], {'period': '2026-08', 'months': 1})
        forecast = self.ask('Show cash flow as of 2026-08-31')
        self.assertEqual(forecast['intent'], 'preview_cashflow')
        self.assertEqual(forecast['parameters'], {'reference_date': '2026-08-31', 'days': 30})

    def test_safe_to_spend_does_not_silently_use_a_different_reference_period(self):
        for locale, question in (
            ('en', 'What is safe to spend in August 2026?'),
            ('en', 'What is safe to spend as of 2026-08-31?'),
            ('en', 'What is safe to spend next month?'),
            ('en', 'What is safe to spend last summer?'),
            ('fi', 'Paljonko voin käyttää elokuussa 2026?'),
            ('fi', 'Paljonko voin käyttää turvallisesti elokuussa 2026?'),
            ('sv', 'Hur mycket kan jag spendera i augusti 2026?'),
            ('sv', 'Hur mycket är tryggt för mig att spendera i augusti 2026?'),
        ):
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertEqual(result['intent'], 'safe_to_spend')
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'period_scope')
                self.assertEqual(result['parameters'], {})
                self.assertIsNone(result['selected_candidate_id'])
                self.assertEqual(result['explanation_blocks'], [])
                self.assertNotIn('tool_result', result)

    def test_exact_safe_to_spend_starter_chips_use_the_selected_data_clock(self):
        for locale, question in (
            ('en', 'What is safe for me to spend this week?'),
            ('fi', 'Paljonko voin käyttää turvallisesti tällä viikolla?'),
            ('sv', 'Hur mycket är tryggt för mig att spendera den här veckan?'),
        ):
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertFalse(result['needs_clarification'], result)
                self.assertEqual(result['intent'], 'safe_to_spend')
                self.assertEqual(result['tool_kind'], 'safe_to_spend')
                self.assertEqual(result['locale'], locale)
                self.assertEqual(result['parameters'], {'reference_date': '2026-09-30', 'days': 7})
                self.assertEqual(result['tool_result']['reference_date'], '2026-09-30')

    def test_current_safe_to_spend_questions_still_reach_the_existing_tool(self):
        for locale, question in (
            ('en', 'What is safe for me to spend this week?'),
            ('en', 'How much can I spend this week?'),
            ('en', 'How much is safe to spend this week?'),
            ('en', 'How much can I safely spend this week?'),
            ('fi', 'Paljonko voin käyttää tällä viikolla?'),
            ('sv', 'Hur mycket kan jag spendera den här veckan?'),
        ):
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['tool_kind'], 'safe_to_spend')
                self.assertEqual(result['parameters']['reference_date'], '2026-09-30')

    def test_non_restaurant_explanation_does_not_cite_restaurant_comparison(self):
        for locale, question in (
            ('en', 'What changed in groceries?'),
            ('en', 'Explain my grocery spending'),
            ('en', 'What changed in transportation in August 2026?'),
            ('fi', 'Mikä muuttui ruokaostoksissa?'),
            ('sv', 'Vad förändrades i matvaror?'),
        ):
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'comparison_definition')
                self.assertEqual(result['parameters'], {})
                self.assertIsNone(result['selected_candidate_id'])
                self.assertEqual(result['explanation_blocks'], [])
                self.assertNotIn('tool_result', result)
