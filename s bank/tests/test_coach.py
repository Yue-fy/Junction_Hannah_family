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
