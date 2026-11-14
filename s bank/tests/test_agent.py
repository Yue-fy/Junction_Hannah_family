import json
import os
import threading
import time
from unittest.mock import patch

from agent_helper import AgentFixture, ScriptedTransport, answer, call
from scoach.api import Application


class AgentLoopTests(AgentFixture):
    def test_goal_proposal_round_trips_through_confirmation_api(self):
        fake = ScriptedTransport(call('goal_plan', name='Buffer', target_cents=60000, target_date='2027-03-28'),
            call('propose_action', kind='create_goal', params={'name': 'Buffer', 'target_cents': 60000, 'target_date': '2027-03-28'}),
            answer('Review the goal when you are ready.'))
        app = Application(self.database, agent_transport=fake)
        status, response = app.handle('POST', '/api/agent', {'customer_id': self.customer, 'month': '2026-09', 'message': 'Plan a €600 buffer by March 2027.'})
        self.assertEqual(status, 200)
        params = response['data']['actions'][0]['params']
        self.assertEqual(set(params), {'name', 'target_cents', 'target_date'})
        self.assertEqual(self.conn.execute('SELECT count(*) FROM goals').fetchone()[0], 0)
        self.assertEqual(app.handle('POST', '/api/goals', {'customer_id': self.customer, **params})[0], 400)
        status, saved = app.handle('POST', '/api/goals', {'customer_id': self.customer, **params, 'confirmed': True})
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM goals').fetchone()[0], 1)

    def run_agent(self, transport, message='How much did I spend on restaurants?', **kwargs):
        from scoach.agent import run_agent
        return run_agent(self.conn, self.customer, '2026-09', 'en', message, [], transport=transport, **kwargs)

    def test_single_tool_answer_binds_highlight_and_exact_evidence(self):
        fake = ScriptedTransport(call('spending_total', start='2026-09-01', end='2026-09-30', category='Restaurants'),
            answer('You spent €225.70 on restaurants.\n\nThat covers 2 payments.\n```ui\n{"highlight":"ev1","suggestions":["And groceries?"]}\n```'))
        result = self.run_agent(fake)
        self.assertEqual(result['source'], 'agent')
        self.assertEqual(result['answer'], ['You spent €225.70 on restaurants.', 'That covers 2 payments.'])
        self.assertEqual(result['highlight']['value'], '€225.70')
        self.assertEqual(result['evidence'][0]['query'], {'start': '2026-09-01', 'end': '2026-09-30', 'category': 'Restaurants', 'consumption_only': 'true'})
        self.assertEqual(result['evidence'][0]['count'], 2)
        self.assertEqual(result['steps'][0]['tool'], 'spending_total')
        self.assertEqual(result['suggestions'], ['And groceries?'])

    def test_sequential_and_parallel_calls_preserve_signatures_and_call_ids(self):
        first = {'role': 'model', 'parts': [
            {'thoughtSignature': 'opaque-first', 'functionCall': {'id': 'call-a', 'name': 'get_overview', 'args': {}}},
            {'functionCall': {'id': 'call-b', 'name': 'spending_total', 'args': {'start': '2026-09-01', 'end': '2026-09-30', 'category': 'Restaurants'}}}]}
        second = call('calculate', expression='225.70 * 12')
        second['parts'][0]['thoughtSignature'] = 'opaque-second'
        fake = ScriptedTransport(first, second, answer('That annualised amount is €2,708.40.'))
        result = self.run_agent(fake)
        self.assertEqual(result['source'], 'agent')
        self.assertEqual(fake.requests[1]['contents'][1], first)
        self.assertEqual(fake.requests[2]['contents'][3], second)
        responses = fake.requests[1]['contents'][2]['parts']
        self.assertEqual([p['functionResponse']['id'] for p in responses], ['call-a', 'call-b'])
        self.assertEqual([p['functionResponse']['name'] for p in responses], ['get_overview', 'spending_total'])
        for request in fake.requests:
            sent = json.dumps(request)
            for forbidden in ('CUST', 'ACC', 'tx:', 'raw_json', 'row_hash'):
                self.assertNotIn(forbidden, sent)

    def test_argument_error_is_returned_to_model_and_can_be_repaired(self):
        fake = ScriptedTransport(call('spending_total', start='2026-09-01', end='2026-09-30', category='Fake'),
            call('spending_total', start='2026-09-01', end='2026-09-30', category='Restaurants'), answer('€225.70.'))
        result = self.run_agent(fake)
        self.assertEqual(result['source'], 'agent')
        self.assertIn('error', fake.requests[1]['contents'][-1]['parts'][0]['functionResponse']['response'])

    def test_unverified_answer_gets_one_correction_then_deterministic_fallback(self):
        fake = ScriptedTransport(answer('You spent €999.99.'), answer('You spent €888.88.'))
        result = self.run_agent(fake)
        self.assertEqual(result['source'], 'deterministic')
        self.assertEqual(result['fallback_reason'], 'unverified_numbers')
        self.assertIn('999.99', fake.requests[1]['contents'][-1]['parts'][0]['text'])
        self.assertEqual(len(fake.requests), 2)
        self.assertIn('legacy', result)

    def test_correction_may_call_a_tool_before_answering(self):
        fake = ScriptedTransport(answer('€999.99.'), call('spending_total', start='2026-09-01', end='2026-09-30', category='Restaurants'), answer('€225.70.'))
        self.assertEqual(self.run_agent(fake)['source'], 'agent')

    def test_no_key_legacy_equals_the_existing_coach_payload(self):
        body = {'customer_id': self.customer, 'month': '2026-09', 'locale': 'en', 'message': 'How much did I spend on restaurants?'}
        app = Application(self.database)
        with patch.dict(os.environ, {}, clear=True):
            status, response = app.handle('POST', '/api/agent', {**body, 'history': []})
            old_status, old = app.handle('POST', '/api/coach', body)
        self.assertEqual(status, 200)
        self.assertEqual(old_status, 200)
        self.assertEqual(response['data']['source'], 'deterministic')
        self.assertEqual(response['data']['fallback_reason'], 'not_configured')
        self.assertEqual(response['data']['legacy'], old['data'])

    def test_errors_deadline_and_exhausted_steps_fall_back_without_waiting(self):
        for error, reason in ((RuntimeError('Do not expose secrets'), 'unavailable'), (TimeoutError(), 'timeout')):
            with self.subTest(reason=reason):
                result = self.run_agent(ScriptedTransport(error))
                self.assertEqual(result['fallback_reason'], reason)
                self.assertNotIn('secrets', json.dumps(result))
        finished = threading.Event()
        def slow(*args, **kwargs):
            finished.wait(2)
            return answer('Too late')
        started = time.monotonic()
        try:
            result = self.run_agent(slow, deadline_s=.05)
            self.assertEqual(result['fallback_reason'], 'timeout')
            self.assertLess(time.monotonic() - started, .5)
        finally:
            finished.set()
        result = self.run_agent(ScriptedTransport(call('get_overview')), max_steps=1)
        self.assertEqual(result['fallback_reason'], 'max_steps')

    def test_ui_cannot_inject_a_chart_or_unverified_suggestions(self):
        fake = ScriptedTransport(answer('Hello.\n```ui\n{"chart":{"series":[{"value_cents":99999}]},"highlight":"unknown","suggestions":["Spend €9999?"]}\n```'))
        result = self.run_agent(fake, message='Hello')
        self.assertEqual(result['answer'], ['Hello.'])
        self.assertIsNone(result['chart'])
        self.assertIsNone(result['highlight'])
        self.assertEqual(result['suggestions'], [])
        malformed = self.run_agent(ScriptedTransport(answer('Hello.\n```ui\nnot json\n```')), message='Hello')
        self.assertEqual(malformed['answer'], ['Hello.'])

    def test_chart_is_copied_from_verified_tool_result(self):
        fake = ScriptedTransport(call('monthly_trend', months=3, category='Restaurants'), answer('Your monthly restaurant spending stayed level.\n```ui\n{"chart":"ev1"}\n```'))
        result = self.run_agent(fake)
        self.assertEqual(result['chart']['kind'], 'line')
        self.assertEqual([p['value_cents'] for p in result['chart']['series']], [22570, 22570, 22570])

    def test_private_user_identifiers_are_redacted_before_transport(self):
        fake = ScriptedTransport(answer('I can help with your spending.'))
        result = self.run_agent(fake, message='My CUST_TEST account ACC_TEST has tx:99:secret. Help me.')
        self.assertEqual(result['source'], 'agent')
        for forbidden in ('CUST', 'ACC', 'tx:'):
            self.assertNotIn(forbidden, json.dumps(fake.requests))

    def test_thought_parts_are_not_user_answers(self):
        fake = ScriptedTransport({'role': 'model', 'parts': [{'thought': True, 'text': 'Private reasoning 999.'}, {'text': 'Hello.'}]})
        self.assertEqual(self.run_agent(fake, message='Hello')['answer'], ['Hello.'])

    def test_api_validation_health_and_no_confirmation_requirement(self):
        fake = ScriptedTransport(answer('Hello.'))
        app = Application(self.database, agent_transport=fake)
        self.assertTrue(app.handle('GET', '/api/health')[1]['data']['agent_configured'])
        body = {'customer_id': self.customer, 'month': '2026-09', 'message': 'Hello'}
        self.assertEqual(app.handle('POST', '/api/agent', body)[0], 200)
        for extra in ({'message': ''}, {'message': 'a' * 2001}, {'message': []}, {'locale': 'xx'}, {'history': 'bad'}, {'unknown': True}, {'account_id': 'OTHER'}):
            with self.subTest(extra=extra):
                self.assertEqual(app.handle('POST', '/api/agent', {**body, **extra})[0], 400)
        self.assertEqual(app.handle('GET', '/api/agent')[0], 405)
        self.assertEqual(app.handle('POST', '/api/goals', {**body, 'message': 'Hi'})[0], 400)
