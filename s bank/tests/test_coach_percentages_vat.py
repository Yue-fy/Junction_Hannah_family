"""Customer-facing regressions for complete percentages and the VAT chat tool."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core_helper import demo_connection
from scoach.api import Application


class CoachPercentageVatTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'coach.sqlite3'
        with closing(demo_connection()) as source, closing(sqlite3.connect(self.database)) as target:
            source.backup(target)
        self.app = Application(self.database)

    def ask(self, message, locale='en', month='2026-09', app=None):
        status, envelope = (app or self.app).handle('POST', '/api/coach', {
            'customer_id': 'CUST00001', 'month': month, 'locale': locale,
            'message': message,
        })
        self.assertEqual(status, 200, envelope)
        return envelope['data']

    def test_complete_numeric_percentage_not_a_matching_suffix(self):
        for expression, saving in [('12.5%', 2821), ('12,5 %', 2821),
                                   ('0.5 percent', 113), ('0%', 0), ('100%', 22570)]:
            with self.subTest(expression=expression):
                result = self.ask('How much could I save if I reduced dining out by ' + expression + '?')
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['tool_kind'], 'spending_adjustment_preview')
                self.assertEqual(result['tool_result']['modeled_monthly_contribution_cents'], saving)
                self.assertEqual(result['tool_result']['persistence'], 'not_saved')

    def test_word_percentages_in_supported_product_languages(self):
        cases = [
            ('en', 'How much could I save if I reduced dining out by twenty percent?', 4514),
            ('en', 'How much could I save if I reduced dining out by twenty-five percent?', 5643),
            ('en', 'How much could I save if I reduced dining out by twelve point five percent?', 2821),
            ('fi', 'Paljonko säästäisin, jos vähennän ravintolamenoja kaksikymmentä prosenttia?', 4514),
            ('sv', 'Hur mycket kan jag spara om jag minskar restaurangutgifter med tjugo procent?', 4514),
        ]
        for locale, question, expected in cases:
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['tool_kind'], 'spending_adjustment_preview')
                self.assertEqual(result['tool_result']['modeled_monthly_contribution_cents'], expected)

    def test_missing_invalid_and_ambiguous_percentages_ask_instead_of_changing_the_task(self):
        for expression in ['120%', '1000%', '-5%', '12.5.0%', '1e2%',
                           '20% or 30%', '10 to 20%', 'twenty or thirty percent',
                           'one thousand twenty percent', 'one thousand 20%',
                           '-twenty percent', '−5%', 'a little', 'twenty percentage points']:
            with self.subTest(expression=expression):
                result = self.ask('How much could I save if I reduced dining out by ' + expression + '?')
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'adjustment_percentage')
                self.assertNotIn('tool_result', result)
                self.assertTrue(result['clarification_question'])

    def test_unsupported_percentage_is_not_sent_to_the_language_model(self):
        calls = []
        app = Application(self.database, coach_transport=lambda *args, **kwargs: calls.append(args))
        result = self.ask('How much could I save if I reduced dining out by a little?', app=app)
        self.assertTrue(result['needs_clarification'])
        self.assertEqual(calls, [])

    def test_vat_chat_uses_the_existing_estimate_in_each_product_language(self):
        cases = [('en', 'How much VAT did I pay in September?'),
                 ('en', 'How much VAT is inside my purchases?'),
                 ('en', 'Show the tax inside my purchases in September.'),
                 ('fi', 'Paljonko ALV:tä sisältyi ostoksiini syyskuussa?'),
                 ('fi', 'Paljonko arvonlisäveroa ostoksiini sisältyi?'),
                 ('sv', 'Hur mycket moms ingick i mina köp i september?'),
                 ('sv', 'Visa mervärdesskatten i mina inköp.')]
        for locale, question in cases:
            with self.subTest(locale=locale, question=question):
                result = self.ask(question, locale)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['tool_kind'], 'vat_estimate')
                vat = result['tool_result']
                self.assertEqual(vat['estimated_vat_cents'], 21238)
                self.assertEqual(vat['gross_spending_cents'], 187866)
                self.assertEqual(vat['value_status'], 'estimated')
                self.assertFalse(vat['scenario'])
                self.assertEqual(result['source_refs']['transaction_refs'], vat['transaction_refs'])

    def test_vat_dates_override_the_home_month_and_support_exact_ranges(self):
        for phrase, start, end in [('in August 2026', '2026-08-01', '2026-08-31'),
                                   ('from 2026-08-15 to 2026-09-15', '2026-08-15', '2026-09-15')]:
            with self.subTest(phrase=phrase):
                result = self.ask('How much VAT is inside my purchases ' + phrase + '?')
                self.assertEqual(result['tool_kind'], 'vat_estimate')
                self.assertEqual((result['tool_result']['start'], result['tool_result']['end']), (start, end))
                status, direct = self.app.handle('GET', '/api/vat?customer_id=CUST00001&start=' + start + '&end=' + end)
                self.assertEqual(status, 200, direct)
                self.assertEqual(result['tool_result']['transaction_refs'], direct['data']['transaction_refs'])
                self.assertEqual(result['tool_result']['estimated_vat_cents'], direct['data']['estimated_vat_cents'])

    def test_vat_liability_and_unknown_periods_do_not_become_estimated_tax_answers(self):
        for question in ['How much VAT do I owe?', 'How much VAT can I reclaim?',
                         'How much VAT is inside my purchases in October 2026?']:
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertTrue(result['needs_clarification'])
                self.assertNotIn('tool_result', result)

    def test_general_tax_records_remain_distinct_from_vat_estimates(self):
        result = self.ask('How much tax did I pay?')
        self.assertEqual(result['tool_kind'], 'observed_tax_evidence')
        self.assertFalse(result['tool_result']['available'])
        self.assertNotIn('estimated_vat_cents', result['tool_result'])

    def test_optional_language_adapter_can_select_the_vat_tool_without_calculating(self):
        def transport(payload, timeout):
            return {'intent': 'vat_estimate', 'parameters': {'period': '2026-09'},
                    'selected_candidate_id': None, 'needs_clarification': False,
                    'clarification_question': None, 'proposed_action': None,
                    'explanation_blocks': []}
        result = self.ask('我的购物包含多少增值税？', app=Application(self.database, coach_transport=transport))
        self.assertEqual(result['source'], 'gemini')
        self.assertEqual(result['tool_kind'], 'vat_estimate')
        self.assertEqual(result['tool_result']['estimated_vat_cents'], 21238)
