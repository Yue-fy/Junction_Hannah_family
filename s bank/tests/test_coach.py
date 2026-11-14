import unittest
from scoach.coach import interpret, rank_candidates


CONTEXT = {
    'customer_id': 'PRIVATE_CUSTOMER', 'account_id': 'PRIVATE_ACCOUNT',
    'period': '2026-09', 'comparison_period': '2026-08',
    'facts': [{'id': 'restaurant_delta', 'value_cents': 11027}, {'id': 'restaurant_count', 'value': 10}],
    'candidates': [{'id': 'restaurants', 'kind': 'explain_change', 'text': 'Restaurant visits stayed level; average purchase size increased.', 'fact_ids': ['restaurant_delta', 'restaurant_count'], 'materiality': 1, 'explainability': 1}],
}


class CoachTests(unittest.TestCase):
    def test_ranking_prioritizes_goal_then_materiality_without_mutating_input(self):
        candidates = [{'id': 'b', 'materiality': 0.8}, {'id': 'a', 'materiality': 0.8}, {'id': 'goal', 'goal_id': 'g', 'materiality': 0.1}]
        self.assertEqual([x['id'] for x in rank_candidates(candidates, {'id': 'g'})], ['goal', 'a', 'b'])
        self.assertEqual(candidates[0]['id'], 'b')

    def test_offline_headline_cites_deterministic_facts(self):
        response = interpret('What changed in restaurants?', CONTEXT, api_key='')
        self.assertEqual(response['source'], 'deterministic')
        self.assertEqual(response['intent'], 'explain_change')
        self.assertEqual(response['selected_candidate_id'], 'restaurants')
        self.assertEqual(response['explanation_blocks'][0]['fact_ids'], ['restaurant_delta', 'restaurant_count'])
        self.assertNotIn('110.27', response['explanation_blocks'][0]['text'])

    def test_goal_without_target_asks_one_question(self):
        response = interpret('Help me plan a goal', CONTEXT, api_key='')
        self.assertTrue(response['needs_clarification'])
        self.assertIn('target', response['clarification_question'].lower())
        self.assertIsNone(response['proposed_action'])

    def test_supported_locales_localize_offline_intents_and_questions(self):
        context = {
            **CONTEXT,
            'facts': [*CONTEXT['facts'], {'id': 'safe_fact', 'value_cents': 5000}],
            'candidates': [
                *CONTEXT['candidates'],
                {'id': 'safe', 'kind': 'safe_to_spend', 'text': 'English source text.', 'fact_ids': ['safe_fact'], 'materiality': 2},
            ],
        }
        fi = interpret('Paljonko voin käyttää tällä viikolla?', {**context, 'interface_locale': 'fi'}, api_key='')
        self.assertEqual(fi['intent'], 'safe_to_spend')
        self.assertEqual(fi['locale'], 'fi')
        self.assertIn('vararahasi', fi['explanation_blocks'][0]['text'])
        self.assertNotIn('English source text', fi['explanation_blocks'][0]['text'])

        sv = interpret('Hjälp mig planera ett sparmål', {**context, 'interface_locale': 'sv'}, api_key='')
        self.assertEqual(sv['intent'], 'plan_goal')
        self.assertEqual(sv['locale'], 'sv')
        self.assertIn('målbelopp', sv['clarification_question'])

        en = interpret('Help me plan a goal', context, api_key='')
        self.assertEqual(en['locale'], 'en')
        self.assertIn('target amount', en['clarification_question'])

    def test_unavailable_safe_to_spend_is_explained_without_an_amount(self):
        context = {
            **CONTEXT,
            'interface_locale': 'fi',
            'facts': [{'id': 'safe-unavailable', 'value': None}],
            'candidates': [{
                'id': 'safe', 'kind': 'safe_to_spend', 'copy_key': 'safe_unavailable',
                'text': 'There is not enough observed history yet.',
                'fact_ids': ['safe-unavailable'], 'materiality': 0,
            }],
        }
        result = interpret('Paljonko voin käyttää tällä viikolla?', context, api_key='')
        self.assertEqual(result['intent'], 'safe_to_spend')
        self.assertIn('tilihistoriaa', result['explanation_blocks'][0]['text'])
        self.assertNotRegex(result['explanation_blocks'][0]['text'], r'\d|[€%]')

    def test_financing_history_has_explicit_en_fi_sv_historical_boundaries(self):
        base = {
            **CONTEXT,
            'facts': [{'id': 'home-history', 'value_cents': 26600000, 'historical_context_only': True}],
            'candidates': [{
                'id': 'home_financing_history', 'kind': 'home_financing_history',
                'copy_key': 'home_financing_history',
                'text': 'Linked past mortgage data is historical context only. It is not a current affordability or approval assessment.',
                'fact_ids': ['home-history'], 'materiality': 1,
                'historical_context_only': True,
            }],
        }
        cases = [
            ('en', 'What does my mortgage history show?', ['historical context only', 'not a current', 'approval', 'affordability assessment'], ['account transaction']),
            ('fi', 'Mitä asuntolainahistoriani kertoo?', ['historiallista taustatietoa', 'eivät ole nykyinen', 'maksukyky', 'hyväksyntä'], ['tilitapahtuma']),
            ('sv', 'Vad visar min bolånehistorik?', ['historisk bakgrund', 'inte en aktuell', 'betalningsförmåga', 'godkännande'], ['kontohändelse']),
        ]
        for locale, message, expected, forbidden in cases:
            with self.subTest(locale=locale):
                result = interpret(message, {**base, 'interface_locale': locale}, api_key='')
                self.assertEqual(result['intent'], 'home_financing_history')
                text = result['explanation_blocks'][0]['text'].lower()
                for phrase in expected:
                    self.assertIn(phrase, text)
                for phrase in forbidden:
                    self.assertNotIn(phrase, text)

    def test_statistics_tax_and_tax_plan_canned_intents_are_localized_and_precise(self):
        catalog = {
            'categories': ['Groceries', 'Restaurants', 'Transportation'],
            'roles': ['discretionary', 'flexible_essential'],
            'transaction_types': ['purchase'],
            'merchant_ids': [],
        }
        cases = [
            ('en', 'How much did I spend on taxis?', 'Transportation'),
            ('fi', 'Paljonko käytin ravintoloihin?', 'Restaurants'),
            ('sv', 'Hur mycket spenderade jag på matvaror?', 'Groceries'),
        ]
        for locale, message, category in cases:
            with self.subTest(locale=locale):
                result = interpret(message, {**CONTEXT, 'interface_locale': locale, 'filter_catalog': catalog}, api_key='')
                self.assertEqual(result['intent'], 'transaction_statistics')
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['parameters'], {'period': '2026-09', 'category': category})

        for locale, question_fragment in [('en', 'category'), ('fi', 'luok'), ('sv', 'kategori')]:
            with self.subTest(missing_locale=locale):
                result = interpret('How much did I spend?', {**CONTEXT, 'interface_locale': locale, 'filter_catalog': catalog}, api_key='')
                self.assertTrue(result['needs_clarification'])
                self.assertIn(question_fragment, result['clarification_question'].lower())

        taxes = interpret('Did I pay taxes this month?', {**CONTEXT, 'filter_catalog': catalog}, api_key='')
        self.assertEqual(taxes['intent'], 'observed_tax_evidence')
        self.assertEqual(taxes['parameters'], {'period': '2026-09'})
        planning = interpret('Help me plan for a tax payment', {**CONTEXT, 'interface_locale': 'fi', 'filter_catalog': catalog}, api_key='')
        self.assertEqual(planning['intent'], 'plan_tax')
        self.assertTrue(planning['needs_clarification'])
        self.assertIn('summa', planning['clarification_question'].lower())

    def test_free_exploration_recognizes_all_everyday_categories_offline(self):
        categories = [
            'Entertainment', 'Groceries', 'Health', 'Home & Tech', 'Housing',
            'Lifestyle', 'Restaurants', 'Transportation', 'Travel', 'Utilities',
        ]
        context = {
            **CONTEXT,
            'filter_catalog': {
                'categories': categories,
                'roles': [],
                'transaction_types': ['purchase'],
                'merchant_ids': [],
            },
        }
        cases = [
            ('en', 'How much did I spend on entertainment?', 'Entertainment'),
            ('en', 'How much did I spend on health?', 'Health'),
            ('en', 'How much did I spend on home appliances?', 'Home & Tech'),
            ('en', 'How much did I spend on rent?', 'Housing'),
            ('en', 'How much did I spend on clothes?', 'Lifestyle'),
            ('en', 'How much did I spend on travel?', 'Travel'),
            ('en', 'How much did I spend on utilities?', 'Utilities'),
            ('fi', 'Paljonko käytin viihteeseen?', 'Entertainment'),
            ('fi', 'Paljonko käytin matkailuun?', 'Travel'),
            ('sv', 'Hur mycket spenderade jag på hälsa?', 'Health'),
            ('sv', 'Hur mycket spenderade jag på boende?', 'Housing'),
        ]
        for locale, message, category in cases:
            with self.subTest(locale=locale, category=category):
                result = interpret(message, {**context, 'interface_locale': locale}, api_key='')
                self.assertEqual(result['intent'], 'transaction_statistics')
                self.assertFalse(result['needs_clarification'])
                self.assertEqual(result['parameters']['category'], category)

        current = interpret(
            'How much did I spend in the current month?',
            {**context, 'interface_locale': 'en'},
            api_key='',
        )
        self.assertEqual(current['intent'], 'transaction_statistics')
        self.assertTrue(current['needs_clarification'])
        self.assertNotIn('category', current['parameters'])
