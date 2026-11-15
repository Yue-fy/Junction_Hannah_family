"""V3 HTTP endpoints on a temporary copy of the demo database (never the original)."""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scoach.api import Application, offline_safe_to_spend
from scoach.db import connect
from agent_helper import ScriptedTransport, answer

DEMO = Path(__file__).resolve().parents[1] / 'var' / 'scoach.sqlite3'
VIEWER = Path(__file__).resolve().parents[1] / 'web' / 'year-review.js'
OTHER = 'CUST00676'


@unittest.skipUnless(DEMO.is_file(), 'demo database not built')
class V3APITests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {'GEMINI_API_KEY': '', 'DEEPSEEK_API_KEY': '', 'AGENT_PROVIDER': ''})
        environment.start(); self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'demo.sqlite3'
        shutil.copyfile(DEMO, self.db)
        self.app = Application(self.db)

    def get(self, target, status=200):
        code, result = self.app.handle('GET', target)
        self.assertEqual(code, status, result)
        return result['data'] if result['ok'] else result['error']

    def post(self, path, body, status=200):
        code, result = self.app.handle('POST', path, body)
        self.assertEqual(code, status, result)
        return result['data'] if result['ok'] else result['error']

    def write(self, path, body, status=200):
        return self.post(path, {**body, 'confirmed': True}, status)

    # Read endpoints -----------------------------------------------------------------------
    def test_spender_profile_uses_complete_month(self):
        data = self.get('/api/spender-profile?month=2026-09&months=6')
        self.assertEqual(set(data) >= {'profile', 'buffer', 'end_month'}, True)
        self.assertTrue(data['profile']['available'])
        self.assertIn('suggested_monthly_set_aside_cents', data['buffer'])
        self.get('/api/spender-profile?months=99', 400)
        self.get('/api/spender-profile?bogus=1', 400)

    def test_explore_and_validation(self):
        data = self.get('/api/explore?start=2026-01-01&end=2026-09-30&group_by=category&top=3')
        self.assertLessEqual(len(data['rows']), 3)
        self.assertTrue(all(type(row['value_cents']) is int and 'key' in row for row in data['rows']))
        weekday = self.get('/api/explore?start=2026-01-01&end=2026-09-30&group_by=weekday&category=Groceries')
        self.assertEqual(weekday['filters']['category'], 'Groceries')
        self.get('/api/explore?start=2026-01-01&end=2026-09-30', 400)
        self.get('/api/explore?start=2026-01-01&end=2026-09-30&group_by=colour', 400)
        self.get('/api/explore?start=2026-01-01&end=2026-09-30&group_by=category&category=Nope', 400)
        self.get('/api/explore?start=2026-01-01&end=2026-09-30&group_by=category&top=40', 400)

    def test_cashflow_series_and_summary(self):
        series = self.get('/api/cashflow?start_month=2025-01&end_month=2026-09&granularity=year')
        self.assertEqual([row['period'] for row in series['periods']], ['2025', '2026'])
        summary = self.get('/api/cashflow/summary?start_month=2025-01&end_month=2026-09&granularity=month')
        self.assertIn('saving_rate_change', summary['comparisons'])
        self.get('/api/cashflow?start_month=2025-01&end_month=2026-09&granularity=week', 400)
        self.get('/api/cashflow?start_month=2025-01&end_month=2026-09&foo=1', 400)

    def test_year_review_story_cards_match_viewer_fact_names(self):
        options = self.get('/api/year-review/options')
        self.assertEqual(options['years'], options['options'])
        self.assertTrue(any(item['year'] == 2025 and item['complete'] for item in options['years']))
        data = self.get('/api/year-review?year=2025&locale=fi')
        story = data['story_cards']
        self.assertEqual((story['year'], story['complete'], story['available']), (2025, True, True))
        # Parse the viewer's documented fact names per kind and check each card uses only those (plus extras we document).
        header = VIEWER.read_text().split('*/', 1)[0]
        documented = {}
        for line in header.splitlines():
            match = re.match(r'\s*\*\s+(\w+)\s+(.+)$', line)
            if match and match.group(1) in {'intro', 'money_in_out', 'saved', 'top_category', 'baskets', 'little_leaks', 'peak_month', 'busiest_day', 'favourite_weekday_or_mcc', 'archetype', 'closing'}:
                documented[match.group(1)] = set(re.findall(r'[a-z_]+', match.group(2).replace('*_percent', '')))
        extras = {'peak_month': {'busiest_day_date', 'busiest_day_cents'}, 'little_leaks': {'share_percent'},
                  'favourite_weekday_or_mcc': {'weekday_count'},
                  'baskets': {'must_pays_percent', 'surprise_must_pays_percent', 'little_leaks_percent'}}
        kinds = [card['kind'] for card in story['cards']]
        self.assertEqual(kinds[0], 'intro'); self.assertEqual(kinds[-1], 'closing')
        for card in story['cards']:
            facts = {key for key in card['facts'] if not key.endswith('_display')}
            self.assertLessEqual(facts, documented[card['kind']] | extras.get(card['kind'], set()), card)
            self.assertTrue(card['id'].startswith('2025-'))
        by_kind = {card['kind']: card['facts'] for card in story['cards']}
        self.assertEqual(by_kind['money_in_out']['net_cents'], data['money_in_cents'] - data['money_out_cents'])
        self.assertEqual(by_kind['saved']['saved_cents'], data['saved_cents'])
        self.assertEqual(by_kind['top_category']['amount_cents'], data['top_category']['cents'])
        self.assertEqual(by_kind['baskets']['must_pays_cents'] + by_kind['baskets']['surprise_must_pays_cents'] + by_kind['baskets']['little_leaks_cents'], data['money_out_cents'])
        self.assertEqual(by_kind['peak_month']['month'], data['biggest_month']['month'])
        self.assertIsInstance(by_kind['favourite_weekday_or_mcc']['weekday'], int)
        self.assertNotIn('_', by_kind['archetype']['archetype_label'])  # display name, not the id
        self.assertEqual(by_kind['archetype']['archetype_label'], data['archetype']['archetype_labels']['fi'])
        self.get('/api/year-review?year=1999', 400)
        self.get('/api/year-review?year=2025&locale=de', 400)

    def test_year_review_captions_deterministic_without_model_and_verified_with_model(self):
        self.assertEqual(self.post('/api/year-review/captions', {'year': 2025}),
                         {'captions': {}, 'closing_message': None, 'source': 'deterministic'})
        good = json.dumps({'captions': {'2025-intro': 'Here is your 2025.', 'unknown': 'x'}, 'closing_message': 'You saved €2,817.83.'})
        self.app.agent_transport = ScriptedTransport(answer(good))
        result = self.post('/api/year-review/captions', {'year': 2025, 'locale': 'en'})
        self.assertEqual(result['source'], 'agent')
        self.assertEqual(result['captions'], {'2025-intro': 'Here is your 2025.'})
        bad = json.dumps({'captions': {'2025-intro': 'You spent €99,999 on cake.'}, 'closing_message': 'Bye'})
        self.app.agent_transport = ScriptedTransport(answer(bad))
        self.assertEqual(self.post('/api/year-review/captions', {'year': 2025})['source'], 'deterministic')
        self.app.agent_transport = ScriptedTransport(RuntimeError('down'))
        self.assertEqual(self.post('/api/year-review/captions', {'year': 2025})['source'], 'deterministic')
        self.app.agent_transport = ScriptedTransport(answer('not json'))
        self.assertEqual(self.post('/api/year-review/captions', {'year': 2025})['source'], 'deterministic')
        self.post('/api/year-review/captions', {}, 400)
        self.post('/api/year-review/captions', {'year': '2025'}, 400)

    def test_tax_and_vat_card(self):
        data = self.get('/api/tax')
        self.assertEqual(data['tax_year'], 2026)
        self.assertIsNone(data['tax_entry_id'])
        self.assertFalse(data['withholding']['available'])
        self.assertEqual(data['cycle']['label'], data['cycle']['stage_label'])
        self.assertIn('refund_seen', data)
        saved = self.write('/api/profile/entries', {'key': 'tax', 'value': {'tax_year': 2026, 'base_rate_bp': 2000, 'gross_monthly_cents': 300000}})
        data = self.get('/api/tax?tax_year=2026')
        self.assertEqual(data['tax_entry_id'], saved['entry']['id'])
        self.assertTrue(data['withholding']['available'])
        self.assertIsNone(self.get('/api/tax?tax_year=2025')['tax_entry_id'])
        self.get('/api/tax?tax_year=abc', 400)
        card = self.get('/api/vat/card?month=2026-09')
        self.assertTrue({'estimated_vat_cents', 'spending_cents', 'category', 'rate_label'} <= set(card))
        self.get('/api/vat/card?month=2026-09&start=2026-09-01', 400)

    # Writes -------------------------------------------------------------------------------
    def test_profile_crud_confirmation_scope_and_undo(self):
        self.write('/api/profile/entries', {'key': 'life_stage', 'value': 'between_jobs'}, 200)
        self.post('/api/profile/entries', {'key': 'life_stage', 'value': 'working'}, 400)  # not confirmed
        self.write('/api/profile/entries', {'key': 'life_stage', 'value': 'astronaut'}, 400)
        self.write('/api/profile/entries', {'key': 'nope', 'value': 1}, 400)
        self.write('/api/profile/entries', {'key': 'note', 'value': 'x', 'source': 'from_your_transactions'}, 400)
        self.write('/api/profile/entries', {'key': 'note', 'value': 'x', 'extra': 1}, 400)
        self.write('/api/profile/entries', {'key': 'note', 'value': 'x', 'provenance': 'gemini'}, 400)
        debt = self.write('/api/profile/entries', {'key': 'debts', 'value': {'type': 'mortgage', 'monthly_payment_cents': 90000},
                                                   'source': 'from_our_chat', 'note': 'From chat', 'provenance': 'gemini_proposed_user_confirmed'})
        entry_id = debt['entry']['id']
        profile = self.get('/api/profile')
        self.assertEqual({e['key'] for e in profile['profile']['entries']}, {'life_stage', 'debts'})
        self.assertIsInstance(profile['suggestions'], list)
        updated = self.write('/api/profile/entries/update', {'entry_id': entry_id, 'value': {'type': 'mortgage', 'monthly_payment_cents': 95000}, 'active': True})
        self.assertEqual(updated['entry']['value']['monthly_payment_cents'], 95000)
        self.write('/api/profile/entries/update', {'entry_id': entry_id}, 400)
        self.write('/api/profile/entries/update', {'entry_id': entry_id, 'active': 'yes'}, 400)
        # Another customer cannot touch this entry.
        self.assertEqual(self.write('/api/profile/entries/delete', {'entry_id': entry_id, 'customer_id': OTHER}, 404)['code'], 'unknown_reference')
        self.write('/api/profile/entries/update', {'entry_id': entry_id, 'note': 'x', 'customer_id': OTHER}, 404)
        self.write('/api/profile/entries/delete', {'entry_id': entry_id})
        self.assertNotIn(entry_id, [e['id'] for e in self.get('/api/profile')['profile']['entries']])
        self.write('/api/undo', {})
        self.assertIn(entry_id, [e['id'] for e in self.get('/api/profile')['profile']['entries']])
        forgotten = self.write('/api/profile/forget', {})
        self.assertGreaterEqual(forgotten['deleted_count'], 2)
        self.assertTrue(self.get('/api/profile')['profile']['empty'])
        self.write('/api/undo', {})
        self.assertFalse(self.get('/api/profile')['profile']['empty'])

    def test_suggestions_confirm_dismiss_and_migrate(self):
        suggestions = self.get('/api/profile/suggestions')['suggestions']
        self.assertGreaterEqual(len(suggestions), 2)
        self.write('/api/profile/suggestions/dismiss', {'suggestion_id': suggestions[0]['id']})
        self.write('/api/profile/suggestions/dismiss', {'suggestion_id': suggestions[0]['id']}, 404)
        confirmed = self.write('/api/profile/suggestions/confirm', {'suggestion_id': suggestions[1]['id']})
        self.assertEqual(confirmed['entry']['source'], 'from_your_transactions')
        self.write('/api/profile/suggestions/confirm', {'suggestion_id': 'sugg:unknown'}, 404)
        self.write('/api/profile/suggestions/confirm', {'suggestion_id': suggestions[1]['id'], 'customer_id': OTHER}, 404)
        migrated = self.write('/api/profile/migrate-local', {'local': {'notes': ['I like long walks'], 'style': 'direct', 'onboarding_complete': True}})
        self.assertTrue(migrated['imported'])
        self.write('/api/profile/migrate-local', {'local': ['x']}, 400)
        self.post('/api/profile/migrate-local', {'local': {}}, 400)

    def test_year_review_save_conforms_to_profile_shape(self):
        saved = self.write('/api/year-review/save', {'year': 2025, 'captions': {'2025-intro': 'Hi'}, 'closing_message': 'Bye'})
        value = saved['entry']['value']
        self.assertEqual(saved['entry']['source'], 'year_review')
        self.assertEqual((value['year'], value['captions'], value['closing']), (2025, {'2025-intro': 'Hi'}, 'Bye'))
        self.assertTrue({'money_in_cents', 'money_out_cents', 'saved_cents', 'archetype_label'} <= set(value['facts']))
        again = self.write('/api/year-review/save', {'year': 2025, 'closing_message': None})
        self.assertEqual(again['replaced_entry_ids'], [saved['entry']['id']])
        self.post('/api/year-review/save', {'year': 2025}, 400)
        self.write('/api/year-review/save', {'year': 2025, 'captions': 'nice'}, 400)
        self.write('/api/profile/entries', {'key': 'year_review', 'value': {'year': 2025, 'facts': {}}}, 400)

    def test_goal_update_accepts_fields_object(self):
        created = self.write('/api/goals', {'name': 'Bike', 'target_cents': 100000, 'target_date': '2027-06-30'})
        goal_id = created['goal']['id']
        updated = self.write('/api/goals/update', {'goal_id': goal_id, 'fields': {'target_cents': 250000, 'name': 'New bike'}})
        self.assertEqual((updated['goal']['target_cents'], updated['goal']['name']), (250000, 'New bike'))
        for fields in ({}, {'colour': 'red'}, {'target_cents': -1}, {'target_cents': '250000'}, {'target_date': '2027/06/30'}, {'name': ''}):
            self.write('/api/goals/update', {'goal_id': goal_id, 'fields': fields}, 400)
        self.post('/api/goals/update', {'goal_id': goal_id, 'fields': {'target_cents': 1}}, 400)
        self.write('/api/goals/update', {'goal_id': goal_id, 'fields': {'target_cents': 1}, 'customer_id': OTHER}, 404)
        self.write('/api/goals/delete', {'goal_id': goal_id})
        self.write('/api/undo', {})
        self.assertIn(goal_id, [goal['id'] for goal in self.get('/api/goals')['goals']])

    def test_offline_safe_to_spend_uses_until_payday(self):
        conn = connect(self.db)
        try:
            result = offline_safe_to_spend(conn, 'CUST00001', '2026-09-30')
        finally:
            conn.close()
        self.assertEqual(result['safe_to_spend_cents'], result['this_week_cents'])
        self.assertEqual(result['horizon_end'], result['next_payday'])
        self.assertEqual(result['horizon_days'], min(7, result['days_until_payday']))
        self.assertEqual(result['scheduled_outflows_cents'], result['committed_cents'])
        self.assertLess(result['safe_to_spend_cents'], result['starting_balance_cents'] // 2)
        answer_data = self.post('/api/coach', {'message': 'What is safe for me to spend this week?', 'month': '2026-09'})
        self.assertEqual(answer_data['tool_kind'], 'safe_to_spend')
        self.assertEqual(answer_data['tool_result']['safe_to_spend_cents'], result['this_week_cents'])
        # Profile saving target reduces the amount.
        self.write('/api/profile/entries', {'key': 'saving_rate_target_pct', 'value': 20})
        with_target = self.post('/api/coach', {'message': 'What is safe for me to spend this week?', 'month': '2026-09'})
        self.assertLess(with_target['tool_result']['safe_to_spend_cents'], result['this_week_cents'])


if __name__ == '__main__':
    unittest.main()
