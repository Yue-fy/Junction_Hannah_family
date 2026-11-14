import copy
import json
import io
import time
import unittest
from scoach.coach import interpret
from scoach.gemini import validate_response, rest_transport, minimized_context
from unittest.mock import patch
from test_coach import CONTEXT


def valid():
    return {'intent': 'explain_change', 'parameters': {'period': '2026-09', 'category': 'Restaurants'}, 'selected_candidate_id': 'restaurants', 'needs_clarification': False, 'explanation_blocks': [{'text': 'Average purchase size rose.', 'fact_ids': ['restaurant_delta']}]}


class GeminiTests(unittest.TestCase):
    def test_validated_model_intent_and_fact_refs(self):
        result = interpret('Explain', CONTEXT, transport=lambda payload, timeout: json.dumps(valid()), api_key='test')
        self.assertEqual(result['source'], 'gemini')
        self.assertEqual(result['explanation_blocks'][0]['fact_ids'], ['restaurant_delta'])

    def test_nonnumeric_spending_profile_can_use_gemini_while_python_keeps_the_calculation(self):
        response = {
            'intent': 'spending_profile',
            'parameters': {'period': '2026-09'},
            'needs_clarification': False,
            'explanation_blocks': [{
                'text': 'Your observed basket pattern is ready to explore.',
                'fact_ids': ['restaurant_delta'],
            }],
        }
        result = interpret(
            'What kind of spender am I?',
            CONTEXT,
            transport=lambda payload, timeout: response,
            api_key='test',
        )
        self.assertEqual(result['source'], 'gemini')
        self.assertEqual(result['intent'], 'spending_profile')
        self.assertEqual(result['parameters'], {'period': '2026-09'})

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
        for question in ['You can safely save €900 monthly. Shall I use that?', 'Can I assume 900 euros monthly?', 'Shall I reduce this by 20%?', 'Can I assume one thousand euros monthly?', 'Voinko olettaa tuhat euroa kuukaudessa?', 'Kan jag anta tusen euro per månad?']:
            with self.subTest(question=question):
                response = valid()
                response.update(needs_clarification=True, clarification_question=question)
                with self.assertRaises(ValueError):
                    validate_response(response, CONTEXT)

    def test_rejects_spelled_out_numeric_claims_in_every_model_explanation(self):
        for text in [
            'You spent nine hundred euros.',
            'Your spending rose by twenty percent.',
            'Kulutit yhdeksänsataa euroa.',
            'Säästän kaksikymmentä kuussa.',
            'Dina utgifter steg med tjugo procent.',
            'Jag sparar etthundra varje månad.',
            'Ich spare neunhundert monatlich.',
            'You spent ¥.',
        ]:
            with self.subTest(text=text):
                response=valid(); response['explanation_blocks']=[{'text':text,'fact_ids':['restaurant_delta']}]
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

    def test_financing_event_notes_are_never_in_minimized_model_context(self):
        context = {
            **CONTEXT,
            'facts': [{
                'id': 'financing-history', 'value_cents': 100000,
                'label': 'Historical home-financing context',
                'historical_context_only': True,
                'description': 'RAW PRIVATE EVENT NOTE', 'note': 'SECOND RAW NOTE',
                'events': [{'description': 'NESTED RAW NOTE'}], 'event_refs': ['PRIVATE-EVENT-ID'],
            }],
            'candidates': [{'id': 'home', 'kind': 'home_financing_history', 'text': 'Historical context is available.', 'fact_ids': ['financing-history'], 'historical_context_only': True, 'event_refs': ['SECOND-PRIVATE-EVENT-ID']}],
        }
        minimized = minimized_context(context)
        encoded = json.dumps(minimized)
        self.assertTrue(minimized['facts'][0]['historical_context_only'])
        self.assertTrue(minimized['candidates'][0]['historical_context_only'])
        for private in ['RAW PRIVATE EVENT NOTE', 'SECOND RAW NOTE', 'NESTED RAW NOTE', 'PRIVATE-EVENT-ID', 'SECOND-PRIVATE-EVENT-ID']:
            self.assertNotIn(private, encoded)

    def test_minimized_transport_context_carries_validated_response_locale(self):
        captured = []
        response = valid()
        context = {**CONTEXT, 'interface_locale': 'fi', 'facts': [*CONTEXT['facts'], {'id': 'safe', 'value_cents': None, 'available': False, 'reserve_floor_cents': 50000, 'reserve_floor_source': 'demo_default'}]}
        result = interpret('Selitä muutos', context, transport=lambda payload, timeout: captured.append(payload) or response, api_key='test')
        self.assertEqual(result['locale'], 'fi')
        self.assertEqual(captured[0]['context']['interface_locale'], 'fi')
        self.assertEqual(captured[0]['context']['response_language_policy'], 'match_query_language_when_clear')
        safe = next(fact for fact in captured[0]['context']['facts'] if fact['id'] == 'safe')
        self.assertEqual((safe['reserve_floor_cents'], safe['reserve_floor_source']), (50000, 'demo_default'))
        self.assertEqual(result['response_language_source'], 'query_language_gemini')

    def test_only_bounded_catalogs_and_fact_metadata_are_available_to_model(self):
        captured = []
        context = {**CONTEXT, 'transaction_refs': ['PRIVATE-ROW'], 'scenario_ids': ['PRIVATE-SCENARIO'], 'goal_ids': ['PRIVATE-GOAL'], 'filter_catalog': {'categories': ['Restaurants', 'Transportation'], 'roles': ['discretionary'], 'transaction_types': ['purchase'], 'merchant_ids': []}}
        def fake(payload, timeout):
            captured.append(payload)
            return valid()
        interpret('Review this purchase', context, transport=fake, api_key='test')
        minimized = captured[0]['context']
        self.assertEqual(minimized['filter_catalog']['categories'], ['Restaurants', 'Transportation'])
        for forbidden in ['transaction_refs', 'scenario_ids', 'goal_ids']:
            self.assertNotIn(forbidden, minimized)
        self.assertNotIn('PRIVATE-', json.dumps(minimized))

    def test_statistics_model_filters_must_match_the_bounded_customer_catalog(self):
        context = {**CONTEXT, 'filter_catalog': {'categories': ['Restaurants', 'Transportation'], 'roles': ['discretionary'], 'transaction_types': ['purchase'], 'merchant_ids': ['M1']}}
        response = {'intent': 'transaction_statistics', 'parameters': {'period': '2026-09', 'category': 'Transportation'}, 'needs_clarification': False, 'explanation_blocks': []}
        self.assertEqual(validate_response(response, context)['parameters']['category'], 'Transportation')
        for field, value in [('category', 'Taxis'), ('role', 'invented'), ('transaction_type', 'wire'), ('merchant_id', 'PRIVATE')]:
            invalid = {**response, 'parameters': {'period': '2026-09', field: value}}
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_response(invalid, context)

    def test_tax_queries_never_send_user_declared_tax_values_to_model(self):
        calls=[]
        def transport(payload, timeout):
            calls.append(payload)
            return valid()
        for message, intent in [
            ('Help me plan for a tax payment of 900 euros', 'plan_tax'),
            ('Did I pay taxes of 900 euros this month?', 'observed_tax_evidence'),
        ]:
            with self.subTest(intent=intent):
                result=interpret(message, {**CONTEXT, 'filter_catalog': {'categories': [], 'roles': [], 'transaction_types': [], 'merchant_ids': []}}, transport=transport, api_key='test')
                self.assertEqual(result['intent'],intent)
                self.assertEqual(result['source'],'deterministic')
                self.assertEqual(result['fallback_reason'],'sensitive_tax_query_local_only')
        self.assertEqual(calls,[])

    def test_numeric_currency_and_percent_user_messages_are_redacted_before_transport(self):
        captured=[]
        catalog={'categories':['Transportation'],'roles':[],'transaction_types':['purchase'],'merchant_ids':[]}
        stats={'intent':'transaction_statistics','parameters':{'period':'2026-09','category':'Transportation'},'needs_clarification':False,'explanation_blocks':[]}
        result=interpret('How much did I spend on taxis in 2026?', {**CONTEXT,'filter_catalog':catalog}, transport=lambda payload,timeout: captured.append(payload) or stats, api_key='test')
        self.assertEqual(result['intent'],'transaction_statistics')
        goal={'intent':'plan_goal','parameters':{},'needs_clarification':True,'clarification_question':'What target amount and date should I use?','explanation_blocks':[]}
        result=interpret('Help me save 1,000.50 euros, then twenty percent more', {**CONTEXT,'filter_catalog':catalog}, transport=lambda payload,timeout: captured.append(payload) or goal, api_key='test')
        self.assertEqual(result['intent'],'plan_goal')
        encoded=' '.join(item['message'].lower() for item in captured)
        for private in ['2026','1,000.50','euros','twenty']:
            self.assertNotIn(private,encoded)
        self.assertIn('[number]',encoded); self.assertIn('[currency]',encoded); self.assertIn('[percent]',encoded)

    def test_compound_number_words_and_currency_units_are_redacted_before_transport(self):
        captured=[]
        response=valid()
        messages=[
            'Säästän kaksikymmentä kuussa',
            'Jag sparar etthundra varje månad',
            'Ich spare neunhundert monatlich',
            'I saved 900 CHF and ¥',
        ]
        for message in messages:
            result=interpret(message, CONTEXT, transport=lambda payload,timeout: captured.append(payload) or response, api_key='test')
            self.assertEqual(result['source'],'gemini')
        encoded=' '.join(item['message'].casefold() for item in captured)
        for private in ['kaksikymmentä','etthundra','neunhundert','900','chf','¥']:
            self.assertNotIn(private,encoded)
        self.assertIn('[number]',encoded)
        self.assertIn('[currency]',encoded)

    def test_malformed_timeout_unavailable_and_no_key_fall_back(self):
        def unavailable(payload, timeout):
            raise OSError('service unavailable')
        def timeout(payload, timeout):
            raise TimeoutError('timeout')
        for transport in [lambda payload, timeout: '{broken', unavailable, timeout]:
            self.assertEqual(interpret('Explain', CONTEXT, transport=transport, api_key='test')['source'], 'deterministic')
        self.assertEqual(interpret('Explain', CONTEXT, api_key='')['fallback_reason'], 'not_configured')

    def test_rest_transport_uses_working_default_model_json_mode_and_keeps_key_out_of_url(self):
        captured = []
        def open_request(request, timeout):
            captured.append((request, timeout))
            return io.BytesIO(json.dumps({'candidates': [{'content': {'parts': [{'text': json.dumps(valid())}]}}]}).encode())
        with patch.dict('os.environ', {}, clear=True), patch('scoach.gemini.urllib.request.urlopen', open_request):
            result = rest_transport({'message': 'Explain', 'context': {}}, api_key='secret-test-key')
        self.assertEqual(result['intent'], 'explain_change')
        request, timeout = captured[0]
        self.assertEqual(timeout, 9.0)
        self.assertIn('/models/gemini-3-flash-preview:generateContent', request.full_url)
        self.assertNotIn('secret-test-key', request.full_url)
        self.assertEqual(request.get_header('X-goog-api-key'), 'secret-test-key')
        self.assertEqual(json.loads(request.data)['generationConfig']['responseMimeType'], 'application/json')
        instruction = json.loads(request.data)['system_instruction']['parts'][0]['text']
        self.assertIn("same language as the user's message", instruction)
        self.assertIn('interface locale', instruction)
        for prohibited in ['current eligibility', 'affordability', 'approval probability', 'recommended loan amount', 'product', 'offer']:
            self.assertIn(prohibited, instruction)

    def test_slow_transport_has_bounded_fallback(self):
        received=[]
        def slow(payload, timeout):
            received.append(timeout)
            time.sleep(0.08)
            return valid()
        start = time.monotonic()
        with patch('scoach.coach.MODEL_TIMEOUT_SECONDS', 0.05):
            result = interpret('Explain', CONTEXT, transport=slow, api_key='test')
        self.assertLess(time.monotonic() - start, 0.075)
        self.assertEqual(received, [0.05])
        self.assertEqual(result['fallback_reason'], 'timeout')
