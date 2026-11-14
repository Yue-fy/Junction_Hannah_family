import copy
import json
import io
import time
import unittest
from scoach.coach import interpret
from scoach.gemini import validate_response, rest_transport
from unittest.mock import patch
from test_coach import CONTEXT


def valid():
    return {'intent': 'explain_change', 'parameters': {'period': '2026-09', 'category': 'Restaurants'}, 'selected_candidate_id': 'restaurants', 'needs_clarification': False, 'explanation_blocks': [{'text': 'Average purchase size rose.', 'fact_ids': ['restaurant_delta']}]}


class GeminiTests(unittest.TestCase):
    def test_validated_model_intent_and_fact_refs(self):
        result = interpret('Explain', CONTEXT, transport=lambda payload, timeout: json.dumps(valid()), api_key='test')
        self.assertEqual(result['source'], 'gemini')
        self.assertEqual(result['explanation_blocks'][0]['fact_ids'], ['restaurant_delta'])

    def test_rejects_unknown_intents_candidates_facts_actions_and_parameter_types(self):
        changes = [ {'intent': 'transfer_money'}, {'selected_candidate_id': 'invented'}, {'explanation_blocks': [{'text': 'Claim', 'fact_ids': ['invented']}]}, {'proposed_action': {'type': 'transfer_money', 'parameters': {}}}, {'parameters': {'period': 202609}}, {'explanation_blocks': [{'text': 'You can save 900 euros.', 'fact_ids': ['restaurant_delta']}]} ]
        for change in changes:
            with self.subTest(change=change):
                value = valid(); value.update(change)
                with self.assertRaises(ValueError):
                    validate_response(value, CONTEXT)

    def test_rejects_non_string_references_and_unsourced_numeric_fields(self):
        for change in [{'intent': []}, {'selected_candidate_id': []}, {'computed_total_cents': 99999}, {'explanation_blocks': [{'text': 'A change', 'fact_ids': ['restaurant_delta'], 'value_cents': 99999}]}]:
            with self.subTest(change=change):
                response = valid(); response.update(change)
                with self.assertRaises(ValueError):
                    validate_response(response, CONTEXT)

    def test_model_action_is_only_a_confirmation_proposal(self):
        value = valid(); value['proposed_action'] = {'type': 'exclude_from_scenario', 'parameters': {'transaction_ref': 'r1', 'scenario_id': 's1'}}
        context = copy.deepcopy(CONTEXT); context.update(transaction_refs=['r1'], scenario_ids=['s1'])
        result = validate_response(value, context)
        self.assertTrue(result['proposed_action']['requires_confirmation'])
        self.assertFalse(result['proposed_action'].get('applied', False))

    def test_rejects_unsourced_numbers_in_model_clarification_questions(self):
        for question in ['You can safely save €900 monthly. Shall I use that?', 'Can I assume 900 euros monthly?', 'Shall I reduce this by 20%?']:
            with self.subTest(question=question):
                response = valid()
                response.update(needs_clarification=True, clarification_question=question)
                with self.assertRaises(ValueError):
                    validate_response(response, CONTEXT)

    def test_unsafe_clarification_falls_back_without_rendering_model_claim(self):
        response = valid()
        response.update(needs_clarification=True, clarification_question='You can safely save €900 monthly. Shall I use that?')
        result = interpret('Can I save more?', CONTEXT, transport=lambda payload, timeout: response, api_key='test')
        self.assertEqual(result['source'], 'deterministic')
        self.assertEqual(result['fallback_reason'], 'invalid_response')
        self.assertNotIn('900', json.dumps(result))

    def test_valid_non_numeric_model_clarification_is_preserved(self):
        response = valid()
        response.update(needs_clarification=True, clarification_question='Was this purchase a one-off?')
        result = interpret('Explain this purchase', CONTEXT, transport=lambda payload, timeout: response, api_key='test')
        self.assertEqual(result['source'], 'gemini')
        self.assertEqual(result['clarification_question'], 'Was this purchase a one-off?')
        self.assertEqual(result['explanation_blocks'][0]['fact_ids'], ['restaurant_delta'])

    def test_missing_required_parameter_becomes_clarification(self):
        value = valid(); value.update(intent='compare_periods', parameters={})
        result = validate_response(value, CONTEXT)
        self.assertTrue(result['needs_clarification'])
        self.assertIn('period', result['clarification_question'])

    def test_safe_to_spend_and_investment_intent_parameter_bounds(self):
        safe = {'intent': 'safe_to_spend', 'parameters': {'reference_date': '2026-09-30', 'days': 7, 'reserve_floor_cents': 10000}, 'needs_clarification': False, 'explanation_blocks': []}
        self.assertEqual(validate_response(safe, CONTEXT)['intent'], 'safe_to_spend')
        investing = {'intent': 'investment_cashflow', 'parameters': {'period': '2026-09', 'months': 12}, 'needs_clarification': False, 'explanation_blocks': []}
        self.assertEqual(validate_response(investing, CONTEXT)['intent'], 'investment_cashflow')
        for broken in [
            {**safe, 'parameters': {**safe['parameters'], 'days': 31}},
            {**safe, 'parameters': {**safe['parameters'], 'reserve_floor_cents': -1}},
            {**investing, 'parameters': {**investing['parameters'], 'months': 0}},
        ]:
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                validate_response(broken, CONTEXT)

    def test_transport_payload_excludes_identity_and_ledger(self):
        captured = []
        def fake(payload, timeout):
            captured.append(payload)
            return valid()
        result = interpret('What changed?', {**CONTEXT, 'transactions': [{'secret': 'RAW_LEDGER'}]}, transport=fake, api_key='test')
        self.assertEqual(result['source'], 'gemini')
        encoded = json.dumps(captured)
        for private in ['PRIVATE_CUSTOMER', 'PRIVATE_ACCOUNT', 'RAW_LEDGER']:
            self.assertNotIn(private, encoded)

    def test_minimized_transport_context_carries_validated_response_locale(self):
        captured = []
        response = valid()
        context = {**CONTEXT, 'interface_locale': 'fi'}
        result = interpret('Selitä muutos', context, transport=lambda payload, timeout: captured.append(payload) or response, api_key='test')
        self.assertEqual(result['locale'], 'fi')
        self.assertEqual(captured[0]['context']['interface_locale'], 'fi')
        self.assertEqual(captured[0]['context']['response_language_policy'], 'match_query_language_when_clear')
        self.assertEqual(result['response_language_source'], 'query_language_gemini')

    def test_only_scoped_action_refs_are_available_to_model(self):
        captured = []
        context = {**CONTEXT, 'transaction_refs': ['r1'], 'scenario_ids': ['s1'], 'goal_ids': ['g1']}
        def fake(payload, timeout):
            captured.append(payload)
            return valid()
        interpret('Review this purchase', context, transport=fake, api_key='test')
        self.assertEqual(captured[0]['context'].get('transaction_refs'), ['r1'])
        self.assertEqual(captured[0]['context'].get('scenario_ids'), ['s1'])
        self.assertEqual(captured[0]['context'].get('goal_ids'), ['g1'])

    def test_malformed_timeout_unavailable_and_no_key_fall_back(self):
        def unavailable(payload, timeout):
            raise OSError('service unavailable')
        def timeout(payload, timeout):
            raise TimeoutError('timeout')
        for transport in [lambda payload, timeout: '{broken', unavailable, timeout]:
            self.assertEqual(interpret('Explain', CONTEXT, transport=transport, api_key='test')['source'], 'deterministic')
        self.assertEqual(interpret('Explain', CONTEXT, api_key='')['fallback_reason'], 'not_configured')

    def test_rest_transport_uses_json_mode_and_keeps_key_out_of_url(self):
        captured = []
        def open_request(request, timeout):
            captured.append((request, timeout))
            return io.BytesIO(json.dumps({'candidates': [{'content': {'parts': [{'text': json.dumps(valid())}]}}]}).encode())
        with patch('scoach.gemini.urllib.request.urlopen', open_request):
            result = rest_transport({'message': 'Explain', 'context': {}}, api_key='secret-test-key', model='gemini-2.5-flash')
        self.assertEqual(result['intent'], 'explain_change')
        request, timeout = captured[0]
        self.assertEqual(timeout, 4.0)
        self.assertNotIn('secret-test-key', request.full_url)
        self.assertEqual(request.get_header('X-goog-api-key'), 'secret-test-key')
        self.assertEqual(json.loads(request.data)['generationConfig']['responseMimeType'], 'application/json')
        instruction = json.loads(request.data)['system_instruction']['parts'][0]['text']
        self.assertIn("same language as the user's message", instruction)
        self.assertIn('interface locale', instruction)

    def test_slow_transport_has_bounded_fallback(self):
        def slow(payload, timeout):
            time.sleep(4.3)
            return valid()
        start = time.monotonic()
        result = interpret('Explain', CONTEXT, transport=slow, api_key='test')
        self.assertLess(time.monotonic() - start, 4.2)
        self.assertEqual(result['fallback_reason'], 'timeout')
