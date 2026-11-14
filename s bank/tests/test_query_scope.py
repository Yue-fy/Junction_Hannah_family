"""Independent question-definition cases, before SQL or model execution."""
import unittest

from scoach.query_scope import resolve_statistics, validate_previous_query


CONTEXT = {
    'customer_id': 'C', 'account_id': 'A', 'period': '2026-09',
    'reference_date': '2026-09-30', 'observed_start': '2024-10-03',
    'observed_end': '2026-09-30', 'interface_locale': 'en',
    'filter_catalog': {'categories': ['Restaurants', 'Groceries', 'Transportation', 'Health', 'Housing'],
                       'roles': [], 'transaction_types': ['purchase'], 'merchant_ids': ['M001']},
}


class QueryScopeTests(unittest.TestCase):
    def test_named_categories_and_narrow_mcc_concepts_do_not_widen(self):
        cases = [
            ('How much did I spend on restaurants?', {'category': 'Restaurants'}),
            ('How much did I spend on groceries?', {'category': 'Groceries'}),
            ('How much did I spend on taxis?', {'mcc_code': '4121'}),
            ('Paljonko käytin takseihin?', {'mcc_code': '4121'}),
            ('Hur mycket spenderade jag på taxi?', {'mcc_code': '4121'}),
            ('How much did I spend at pharmacies?', {'mcc_code': '5912'}),
            ('How much did I spend on doctors?', {'mcc_code': '8011'}),
            ('How much did I spend on health?', {'category': 'Health'}),
        ]
        for message, filters in cases:
            with self.subTest(message=message):
                result = resolve_statistics(message, CONTEXT)
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['query_scope']['filters'], filters)

    def test_dates_override_interface_month_and_relative_dates_use_data_clock(self):
        cases = [
            ('How much did I spend on restaurants in August 2026?', '2026-08-01', '2026-08-31'),
            ('How much did I spend on restaurants last month?', '2026-08-01', '2026-08-31'),
            ('How much did I spend on restaurants this month?', '2026-09-01', '2026-09-30'),
            ('How much did I spend on restaurants in 2026-07?', '2026-07-01', '2026-07-31'),
            ('How much did I spend on restaurants from 2026-08-15 to 2026-09-15?', '2026-08-15', '2026-09-15'),
            ('Paljonko käytin ravintoloihin elokuussa?', '2026-08-01', '2026-08-31'),
            ('Hur mycket spenderade jag på restauranger i augusti?', '2026-08-01', '2026-08-31'),
        ]
        for message, start, end in cases:
            with self.subTest(message=message):
                scope = resolve_statistics(message, CONTEXT)['query_scope']
                self.assertEqual((scope['start'], scope['end']), (start, end))
                self.assertEqual(scope['reference_date'], '2026-09-30')

    def test_undefined_average_asks_for_definition(self):
        result = resolve_statistics('What is my average restaurant spending?', CONTEXT)
        self.assertTrue(result['needs_clarification'])
        self.assertEqual(result['clarification_code'], 'average_definition')
        self.assertTrue(result['clarification_options'])

    def test_explicit_metrics_have_a_defined_denominator(self):
        cases = [('What was my average restaurant purchase?', 'average_outflow'),
                 ('How many restaurant purchases did I make?', 'transaction_count'),
                 ('What was my largest restaurant purchase?', 'largest_outflow')]
        for message, metric in cases:
            with self.subTest(message=message):
                self.assertEqual(resolve_statistics(message, CONTEXT)['query_scope']['metric'], metric)

    def test_invalid_or_uncovered_dates_require_clarification(self):
        for message in ['Restaurants in August 2030', 'Restaurants from 2026-09-20 to 2026-09-01',
                        'Restaurants on 2026-02-31', 'Restaurants in 2027-01',
                        'Restaurant spending in August and September', 'Restaurant spending yesterday']:
            with self.subTest(message=message):
                result = resolve_statistics(message, CONTEXT)
                self.assertTrue(result['needs_clarification'])
                self.assertIsNone(result['query_scope'])

    def test_unsupported_item_detail_is_not_a_category_total(self):
        for message in ['How much did I spend on coffee?', 'How much beer did I buy?',
                        'How much did I spend at Starbucks?']:
            with self.subTest(message=message):
                result = resolve_statistics(message, CONTEXT)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], 'unsupported_detail')

    def test_followups_preserve_only_validated_scope(self):
        first = resolve_statistics('How much did I spend on restaurants in August?', CONTEXT)['query_scope']
        context = {**CONTEXT, 'previous_query': first}
        second = resolve_statistics('And groceries?', context)['query_scope']
        self.assertEqual(second['filters'], {'category': 'Groceries'})
        self.assertEqual(second['start'], '2026-08-01')
        third = resolve_statistics('What about September?', {**CONTEXT, 'previous_query': second})['query_scope']
        self.assertEqual(third['filters'], {'category': 'Groceries'})
        self.assertEqual(third['start'], '2026-09-01')

    def test_followup_without_prior_query_asks_for_context(self):
        result = resolve_statistics('And groceries?', CONTEXT)
        self.assertTrue(result['needs_clarification'])
        self.assertEqual(result['clarification_code'], 'missing_context')

    def test_previous_scope_cannot_cross_account_or_carry_arbitrary_text(self):
        valid = resolve_statistics('How much did I spend on restaurants?', CONTEXT)['query_scope']
        self.assertEqual(validate_previous_query(valid, CONTEXT), valid)
        for changes in [{'customer_id': 'OTHER'}, {'account_id': 'OTHER'}, {'raw_messages': ['secret']},
                        {'filters': {'sql': 'SELECT *'}}, {'metric': 'credit_approval'}, {'start': 'bad'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_previous_query({**valid, **changes}, CONTEXT)

    def test_affordability_needs_amount_and_time_instead_of_a_confident_answer(self):
        result = resolve_statistics('Can I afford it?', CONTEXT)
        self.assertTrue(result['needs_clarification'])
        self.assertEqual(result['clarification_code'], 'affordability_context')

    def test_multiple_categories_and_missing_investment_values_are_explicit(self):
        for message, code in [('How much did I spend on restaurants and groceries?', 'category_selection'),
                              ('How much did I spend on doctors and pharmacies?', 'category_selection'),
                              ('What were my investment returns?', 'investment_data_limit')]:
            with self.subTest(message=message):
                result = resolve_statistics(message, CONTEXT)
                self.assertTrue(result['needs_clarification'])
                self.assertEqual(result['clarification_code'], code)

    def test_followup_named_month_inherits_year_from_explicit_prior_period(self):
        scope = resolve_statistics('How much did I spend on restaurants in August 2025?', CONTEXT)['query_scope']
        later = resolve_statistics('What about September?', {**CONTEXT, 'previous_query': scope})
        self.assertEqual(later['query_scope']['start'], '2025-09-01')
