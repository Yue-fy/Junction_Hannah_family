import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode
from scoach.api import Application, create_server
from scoach.db import connect, initialize_schema


class APITests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {'GEMINI_API_KEY': ''})
        environment.start(); self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'demo.sqlite3'
        conn = connect(self.db); initialize_schema(conn)
        conn.execute("INSERT INTO customers VALUES ('CUST00001', '00100', 30, '{}')")
        for i, (day, amount, category) in enumerate([('2026-08-02', -11543, 'Restaurants'), ('2026-09-02', -3647, 'Restaurants'), ('2026-09-03', -18923, 'Restaurants')]):
            conn.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (f'r{i}', 'CUST00001', 'A1', day, day+'T12:00:00', category, amount, 100000, 'purchase', None, None, i+2, str(i), '{}'))
        conn.commit(); conn.close()
        self.web = Path(self.temp.name) / 'web'; self.web.mkdir()
        (self.web/'index.html').write_text('<main>Coach</main>')
        self.app = Application(self.db, self.web)

    def request(self, method, target, body=None):
        return self.app.handle(method, target, body)

    def test_health_personas_and_missing_database_are_explicit(self):
        status, result = self.request('GET', '/api/health')
        self.assertEqual((status, result['ok']), (200, True))
        self.assertEqual(self.request('GET', '/api/personas')[1]['data']['personas'][0]['customer_id'], 'CUST00001')
        missing = Application(Path(self.temp.name)/'missing.db', self.web)
        status, result = missing.handle('GET', '/api/overview')
        self.assertEqual(status, 503)
        self.assertEqual(result['error']['code'], 'database_unavailable')
        self.assertFalse((Path(self.temp.name)/'missing.db').exists())

    def test_comparison_and_scope_validation(self):
        status, result = self.request('GET', '/api/comparison?month=2026-09&comparison_month=2026-08')
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['current']['total_cents'], 22570)
        for target, code in [('/api/overview?customer_id=UNKNOWN', 404), ('/api/transactions?account_id=OTHER', 400), ('/api/comparison?month=invalid', 400), ('/api/overview?month=2099-01', 400), ('/api/forecast?as_of=2099-01-01', 400), ('/api/nope', 404)]:
            self.assertEqual(self.request('GET', target)[0], code)

    def test_confirmed_scenario_exclusion_audit_undo_and_immutable_actuals(self):
        status, result = self.request('POST', '/api/scenarios', {'percent': 20})
        self.assertEqual(status, 400)
        payload = {'confirmed': True, 'percent': 20, 'category': 'Restaurants', 'month': '2026-09'}
        status, result = self.request('POST', '/api/scenarios', payload)
        self.assertEqual(status, 200, result)
        data = result['data']; scenario = data['scenario']
        self.assertEqual(scenario['monthly_contribution_cents'], 4514)
        self.assertIn('audit_event', data)
        status, result = self.request('POST', '/api/scenarios/exclude', {'confirmed': True, 'scenario_id': scenario['id'], 'transaction_ref': 'r1'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['data']['scenario']['monthly_contribution_cents'], 3785)
        self.assertEqual(self.request('GET', '/api/comparison')[1]['data']['current']['total_cents'], 22570)
        self.assertEqual(self.request('POST', '/api/undo', {'confirmed': True})[0], 200)
        self.assertEqual(self.request('POST', '/api/scenarios/exclude', {'confirmed': True, 'scenario_id': scenario['id'], 'transaction_ref': 'UNKNOWN'})[0], 404)

    def test_goal_rule_and_reset_routes_preserve_audit_and_goal_handoff(self):
        status, result = self.request('POST', '/api/goals', {'confirmed': True, 'name': 'My bicycle', 'target_cents': 300000, 'target_date': '2027-03-01'})
        self.assertEqual(status, 200, result)
        goal = result['data']['goal']
        self.assertEqual(goal['required_monthly_cents'], 50000)
        status, result = self.request('POST', '/api/scenarios', {'confirmed': True, 'percent': 20})
        scenario = result['data']['scenario']
        status, result = self.request('POST', '/api/goals/link', {'confirmed': True, 'goal_id': goal['id'], 'scenario_id': scenario['id']})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['data']['goal']['modeled_scenario_contribution_cents'], 4514)
        self.assertEqual(result['data']['host_action']['type'], 'attach_modeled_contribution')
        self.assertEqual(len(self.request('GET', '/api/goals')[1]['data']['goals']), 1)
        status, result = self.request('POST', '/api/rules', {'confirmed': True, 'transaction_ref': 'r1', 'role': 'flexible_essential', 'label': 'You added this'})
        self.assertEqual(status, 200, result)
        self.assertIn('audit_event', result['data'])
        self.assertEqual(self.request('GET', '/api/transactions?transaction_ref=r1')[1]['data']['transactions'][0]['role'], 'flexible_essential')
        self.assertEqual(self.request('POST', '/api/reset', {'confirmed': True})[0], 200)
        self.assertEqual(self.request('GET', '/api/goals')[1]['data']['goals'], [])

    def test_goal_host_handoff_uses_capped_goal_plan_contribution(self):
        for saved, expected in [(900, 100), (1000, 0)]:
            with self.subTest(saved=saved):
                status, created = self.request('POST', '/api/goals', {'confirmed': True, 'name': 'Small goal', 'target_cents': 1000, 'current_saved_cents': saved, 'target_date': '2027-03-01'})
                self.assertEqual(status, 200, created)
                goal = created['data']['goal']
                scenario = self.request('POST', '/api/scenarios', {'confirmed': True, 'percent': 20})[1]['data']['scenario']
                self.assertEqual(scenario['modeled_monthly_contribution_cents'], 4514)
                status, linked = self.request('POST', '/api/goals/link', {'confirmed': True, 'goal_id': goal['id'], 'scenario_id': scenario['id']})
                self.assertEqual(status, 200, linked)
                data = linked['data']
                self.assertEqual(data['goal']['modeled_scenario_contribution_cents'], expected)
                self.assertEqual(data['host_action']['cents'], expected)
                self.assertEqual(data['host_action']['cents'], data['goal']['modeled_scenario_contribution_cents'])
                self.assertFalse(data['host_action']['creates_transfer'])

    def test_unsupported_http_api_methods_return_json_405(self):
        server = create_server(self.app, host='127.0.0.1', port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        for method in ['PUT', 'PATCH', 'DELETE', 'OPTIONS', 'PROPFIND', 'HEAD']:
            with self.subTest(method=method):
                request = urllib.request.Request(f'http://127.0.0.1:{server.server_address[1]}/api/overview', method=method)
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code, 405)
                self.assertEqual(caught.exception.headers.get_content_type(), 'application/json')
                if method != 'HEAD':
                    error = json.load(caught.exception)
                    self.assertFalse(error['ok'])
                    self.assertEqual(error['error']['code'], 'method_not_allowed')

    def test_refresh_recovers_exclusion_and_flow_filter_matches_transactions(self):
        created = self.request('POST', '/api/scenarios', {'confirmed': True})[1]['data']['scenario']
        self.request('POST', '/api/scenarios/exclude', {'confirmed': True, 'scenario_id': created['id'], 'transaction_ref': 'r1'})
        fresh = Application(self.db, self.web)
        status, result = fresh.handle('GET', '/api/overview')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['data']['scenarios'][0]['excluded_transaction_refs'], ['r1'])
        rows = self.request('GET', '/api/transactions?role=fixed_obligation')[1]['data']['transactions']
        self.assertEqual(rows, [])

    def test_invalid_money_and_body_fields_return_validation_errors(self):
        for values in [{'percent': 'not-a-number'}, {'percent': True}, {'name': {}}, {'target_cents': 1}, {'actual_total_cents': 1}]:
            with self.subTest(values=values):
                status, result = self.request('POST', '/api/scenarios', {'confirmed': True, **values})
                self.assertEqual(status, 400, result)
                self.assertEqual(result['error']['code'], 'validation_error')

    def test_static_symlink_cannot_escape_web_root(self):
        outside = Path(self.temp.name)/'private.txt'; outside.write_text('private')
        (self.web/'escape.txt').symlink_to(outside)
        (self.web/'index.html').unlink(); (self.web/'index.html').symlink_to(outside)
        server = create_server(self.app, host='127.0.0.1', port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        for path in ['/', '/escape.txt']:
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(f'http://127.0.0.1:{server.server_address[1]}'+path)

    def test_forecast_accepts_validated_temporary_assumption_edits(self):
        conn = connect(self.db)
        conn.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', ('salary', 'CUST00001', 'A1', '2026-08-15', '2026-08-15T12:00:00', 'Salary', 100000, 200000, 'salary', None, None, 99, 'salary', '{}'))
        conn.commit(); conn.close()
        baseline = self.request('GET', '/api/forecast')[1]['data']
        recurring = next(item for item in baseline['recurring_items'] if item['transaction_type'] == 'salary')
        query = urlencode({'assumptions': json.dumps({recurring['id']: {'amount_cents': 200000, 'median_day': 16}})})
        status, result = self.request('GET', '/api/forecast?'+query)
        self.assertEqual(status, 200, result)
        payment = next(item for item in result['data']['scheduled_items'] if item['transaction_type'] == 'salary')
        self.assertEqual((payment['amount_cents'], payment['date']), (200000, '2026-09-16'))
        self.assertTrue(payment['assumption_edited'])
        for assumptions in ['[]', '{broken', json.dumps({recurring['id']: {'enabled': 'false'}})]:
            self.assertEqual(self.request('GET', '/api/forecast?'+urlencode({'assumptions': assumptions}))[0], 400)

    def test_overview_evidence_keeps_all_money_map_rows(self):
        conn = connect(self.db)
        conn.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', ('housing', 'CUST00001', 'A1', '2026-09-01', '2026-09-01T12:00:00', 'Housing', -10000, 90000, 'housing_payment', None, None, 98, 'housing', '{}'))
        conn.commit(); conn.close()
        status, result = self.request('GET', '/api/overview')
        self.assertEqual(status, 200, result)
        self.assertEqual(set(result['data']['transaction_refs']), {'housing', 'r1', 'r2'})

    def test_coach_is_read_only_and_offline(self):
        status, result = self.request('POST', '/api/coach', {'message': 'What changed in restaurants?'})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['data']['source'], 'deterministic')
        self.assertEqual(result['data']['intent'], 'explain_change')

    def test_safe_to_spend_and_investment_routes_are_explicit_scenarios(self):
        status, result = self.request('GET', '/api/safe-to-spend?as_of=2026-09-03&days=7&reserve_floor_cents=10000')
        self.assertEqual(status, 200)
        safe = result['data']
        self.assertEqual(safe['horizon_days'], 7)
        self.assertEqual(safe['reserve_floor_cents'], 10000)
        self.assertEqual(safe['reserve_floor_source'], 'explicit_request')
        self.assertEqual(safe['status'], 'scenario')
        self.assertIn('not a guarantee', safe['label'])
        self.assertEqual(self.request('GET', '/api/safe-to-spend?days=0')[0], 400)
        self.assertEqual(self.request('GET', '/api/safe-to-spend?reserve_floor_cents=-1')[0], 400)

        conn = connect(self.db)
        conn.execute('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', ('invest', 'CUST00001', 'A1', '2026-09-03', '2026-09-03T13:00:00', 'Invest Deposit', -5000, 95000, 'investment_deposit', None, None, 10, 'invest', '{}'))
        conn.commit(); conn.close()
        status, result = self.request('GET', '/api/investments?month=2026-09&months=12')
        self.assertEqual(status, 200)
        flows = result['data']
        self.assertEqual(flows['status'], 'observed')
        self.assertIn('not portfolio performance', flows['label'])
        self.assertGreater(flows['total_contributions_cents'], 0)
        self.assertNotIn('holdings', flows)

        status, selected = self.request('GET', '/api/safe-to-spend?month=2026-08')
        self.assertEqual(status, 200)
        self.assertEqual(selected['data']['reference_date'], '2026-08-31')
        self.assertEqual(selected['data']['reserve_floor_cents'], 50000)
        self.assertEqual(selected['data']['reserve_floor_source'], 'demo_default')
        self.assertFalse(selected['data']['available'])

    def test_coach_recognizes_safe_to_spend_and_investment_cashflows(self):
        safe = self.request('POST', '/api/coach', {'message': 'What is safe to spend this week?'})[1]['data']
        self.assertEqual(safe['intent'], 'safe_to_spend')
        self.assertTrue(safe['explanation_blocks'])
        investing = self.request('POST', '/api/coach', {'message': 'Show my investment contributions'})[1]['data']
        self.assertEqual(investing['intent'], 'investment_cashflow')
        self.assertTrue(investing['explanation_blocks'])

    def test_coach_locale_is_validated_and_localizes_offline_copy(self):
        status, result = self.request('POST', '/api/coach', {'message': 'Paljonko voin käyttää tällä viikolla?', 'locale': 'fi'})
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['locale'], 'fi')
        self.assertEqual(result['data']['response_language_source'], 'interface_locale_offline')
        self.assertIn('English', result['data']['offline_language_limitation'])
        self.assertEqual(result['data']['intent'], 'safe_to_spend')
        self.assertIn('vararahasi', result['data']['explanation_blocks'][0]['text'])

        status, result = self.request('POST', '/api/coach', {'message': 'Hjälp mig planera ett sparmål', 'locale': 'sv'})
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['intent'], 'plan_goal')
        self.assertIn('målbelopp', result['data']['clarification_question'])
        self.assertEqual(self.request('POST', '/api/coach', {'message': 'Hello', 'locale': 'de'})[0], 400)

    def test_overview_uses_sourced_default_reserve_without_promoting_utility_cards(self):
        status, result = self.request('GET', '/api/overview')
        self.assertEqual(status, 200)
        data = result['data']
        self.assertFalse(data['priority'].get('utility', False))
        self.assertNotIn(data['priority']['kind'], {'safe_to_spend', 'investment_cashflow'})
        for candidate in data['candidates']:
            for dimension in ('materiality', 'urgency', 'explainability', 'addressability'):
                self.assertGreaterEqual(candidate[dimension], 0)
                self.assertLessEqual(candidate[dimension], 1)
        safe_fact = next(fact for fact in data['facts'] if fact['label'].startswith('Estimated safe-to-spend'))
        self.assertEqual(safe_fact['reserve_floor_cents'], 50000)
        self.assertEqual(safe_fact['reserve_floor_source'], 'demo_default')
    def test_http_static_and_encoded_path_traversal(self):
        server = create_server(self.app, host='127.0.0.1', port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_address[1]}'
        with urllib.request.urlopen(origin+'/') as response:
            self.assertEqual(response.read(), b'<main>Coach</main>')
        for path in ['/%2e%2e/demo.sqlite3', '/..%2f..%2fetc/passwd', '/%252e%252e/secret']:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(origin+path)
            self.assertIn(caught.exception.code, [403, 404])
        request = urllib.request.Request(origin+'/api/coach', data=b'{broken', headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 400)


class RealDemoPriorityTests(unittest.TestCase):
    def test_five_personas_keep_personalized_and_diverse_priorities(self):
        database = Path(__file__).resolve().parents[1] / 'var' / 'scoach.sqlite3'
        app = Application(database)
        priorities = {}
        for customer_id in ('CUST00001', 'CUST00676', 'CUST05097', 'CUST00756', 'CUST00296'):
            status, response = app.handle('GET', f'/api/overview?customer_id={customer_id}')
            self.assertEqual(status, 200)
            priority = response['data']['priority']
            self.assertIsNotNone(priority)
            self.assertFalse(priority.get('utility', False))
            self.assertNotIn(priority['kind'], {'safe_to_spend', 'investment_cashflow'})
            priorities[customer_id] = priority['id']
        self.assertEqual(priorities['CUST00001'], 'restaurant_change')
        self.assertGreaterEqual(len(set(priorities.values())), 2)
