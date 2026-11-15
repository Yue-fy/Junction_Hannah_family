"""Lane G personalization guard (docs/V4_SPEC.md, "Global rule added by the owner").

Pins the personalization behaviours every V4 lane must keep, end to end through the HTTP
application (``Application.handle``) on a temporary synthetic ledger, never the demo database:

* money profile entries with sources: visible, editable, deletable, undoable, customer-scoped;
* profile entries change the numbers (saving target, debts, regular investing; deleting restores);
* steady mode after job loss / income drop / large loss: reserve, no planned saving, prompt mode, turn off;
* protected categories: told to the AI coach as "do not suggest cutting";
* "Things I noticed": nothing saved by reading, Keep saves with its source, Not this hides it;
* forget everything (and undo);
* goal and profile note from chat: a review card first, saved only by a confirmed POST;
* local preference consent in the browser store (web/experience.js);
* the UI renders the API's profile (sources, steady banner, Keep / Not this, forget, intro entry point)
  and the "recorded" notices exist in EN, FI and SV.

V4 contracts that other lanes are still building are guarded and switch on by themselves when merged:
``forecast.spending_plan`` (lane N), ``/api/catalogue`` cards (lane C) and optional plans stored as
money-profile entries (lane P). See docs/PERSONALIZATION.md.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_helper import ScriptedTransport, answer, call
from scoach import forecast, money_profile
from scoach.api import Application, planning_profile
from scoach.db import connect, initialize_schema

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
CID = 'CUST_PG1'
OTHER = 'CUST_PG2'
AS_OF = '2026-09-26'          # last recorded day of the synthetic ledger
MONTH = '2026-09'
SALARY_CENTS = 300_000        # same every month, on the 25th
HOUSING_CENTS = 90_000        # on the 3rd, so it falls before the next payday
NODE = shutil.which('node')

# One month of the synthetic ledger: (day, category, amount_cents, transaction_type, merchant, mcc).
# Restaurants are the largest discretionary category, so a cut suggestion would naturally pick them.
MONTH_ROWS = [
    (3, 'Housing', -HOUSING_CENTS, 'housing_payment', None, None),
    (5, 'Utilities', -6_000, 'utilities_payment', None, None),
    (10, 'Groceries', -12_000, 'purchase', 'M1', '5411'),
    (12, 'Restaurants', -4_000, 'purchase', 'M2', '5812'),
    (18, 'Entertainment', -3_000, 'purchase', 'M5', '7832'),
    (20, 'Groceries', -8_000, 'purchase', 'M1', '5411'),
    (22, 'Restaurants', -15_000, 'purchase', 'M3', '5812'),
    (24, 'Transportation', -2_500, 'purchase', 'M4', '4121'),
    (25, 'Salary', SALARY_CENTS, 'salary', None, None),
    (26, 'Investments', -20_000, 'investment_deposit', None, None),
]


def build_ledger(path):
    """Two synthetic customers with nine identical months (2026-01..2026-09); returns nothing."""
    conn = connect(path)
    try:
        initialize_schema(conn)
        index = 0
        for customer, account in ((CID, 'ACC_PG1'), (OTHER, 'ACC_PG2')):
            conn.execute('INSERT INTO customers VALUES(?,?,?,?)', (customer, '00100', 34, '{}'))
            balance = 150_000
            for month in range(1, 10):
                for day, category, amount, kind, merchant, mcc in MONTH_ROWS:
                    index += 1
                    balance += amount
                    conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                 (f'tx:{index}:pg', customer, account, f'2026-{month:02d}-{day:02d}', '01JAN26:12:00:00',
                                  category, amount, balance, kind, merchant, mcc, index, 'pg-hash', '{}'))
        conn.commit()
    finally:
        conn.close()


def run_node(script):
    """Run an ES module snippet with node; returns CompletedProcess."""
    return subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT, capture_output=True, text=True, check=False)


class PersonalizationFixture(unittest.TestCase):
    """Temporary synthetic database behind the real HTTP application; no model keys."""

    def setUp(self):
        environment = patch.dict('os.environ', {'GEMINI_API_KEY': '', 'DEEPSEEK_API_KEY': '', 'AGENT_PROVIDER': ''})
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'personalization.sqlite3'
        build_ledger(self.db)
        self.app = Application(self.db)

    # -- HTTP helpers -------------------------------------------------------------------------
    def call_api(self, method, target, body=None, status=200, app=None):
        code, result = (app or self.app).handle(method, target, body)
        self.assertEqual(code, status, result)
        return result['data'] if result['ok'] else result['error']

    def get(self, path, status=200, customer=CID, **query):
        query = {'customer_id': customer, **query}
        target = path + '?' + '&'.join(f'{k}={v}' for k, v in query.items())
        return self.call_api('GET', target, status=status)

    def post(self, path, body, status=200, customer=CID, app=None):
        return self.call_api('POST', path, {'customer_id': customer, 'month': MONTH, **body}, status=status, app=app)

    def write(self, path, body, status=200, customer=CID):
        return self.post(path, {**body, 'confirmed': True}, status=status, customer=customer)

    def save(self, key, value, **extra):
        return self.write('/api/profile/entries', {'key': key, 'value': value, **extra})['entry']

    def profile(self, customer=CID):
        return self.get('/api/profile', customer=customer)

    def until_payday(self, customer=CID):
        return self.get('/api/safe-to-spend', customer=customer, horizon='until_payday')

    def endpoint_exists(self, method, path):
        code, result = self.app.handle(method, path + '?customer_id=' + CID, {} if method == 'POST' else None)
        return not (code == 404 and result.get('error', {}).get('code') == 'not_found')

    def agent(self, *responses, message='Hello'):
        fake = ScriptedTransport(*responses)
        data = self.post('/api/agent', {'message': message}, app=Application(self.db, agent_transport=fake))
        return data, fake

    def goal_count(self):
        conn = connect(self.db)
        try:
            return conn.execute('SELECT count(*) FROM goals WHERE customer_id=?', (CID,)).fetchone()[0]
        finally:
            conn.close()

    def node(self, body):
        if not NODE:
            self.skipTest('node is required for the UI half of this check')
        result = run_node('import assert from "node:assert/strict";\n' + body)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def render_profile(self, data, checks, locale='en'):
        """Render the API's /api/profile response with web/money-profile.js and run JS assertions on `html`."""
        return self.node(
            'const p = await import(' + json.dumps((WEB / 'money-profile.js').as_uri()) + ');\n'
            'const data = ' + json.dumps(data) + ';\n'
            'const locale = ' + json.dumps(locale) + ';\n'
            'const t = key => p.pm(locale, key);\n'
            'const html = p.renderProfilePage(data.profile, data.suggestions, locale, {});\n' + checks)


# ---------------------------------------------------------------------------------- active now

class ProfileEntriesStayVisibleAndEditable(PersonalizationFixture):
    """Money profile: entries with sources; view, edit, delete, undo; customer scope."""

    def test_entries_show_their_source_and_can_be_edited_deleted_and_restored(self):
        told = self.save('saving_rate_target_pct', 15)
        chat = self.save('debts', {'type': 'mortgage', 'monthly_payment_cents': 70_000}, source='from_our_chat',
                         note='From our chat', provenance='gemini_proposed_user_confirmed')
        data = self.profile()
        by_id = {entry['id']: entry for entry in data['profile']['entries']}
        self.assertEqual((by_id[told['id']]['source'], by_id[told['id']]['source_label']), ('you_told_me', 'You told me'))
        self.assertEqual((by_id[chat['id']]['source'], by_id[chat['id']]['source_label']), ('from_our_chat', 'From our chat'))
        self.assertTrue(all(entry['created_at'] and entry['updated_at'] for entry in by_id.values()))

        updated = self.write('/api/profile/entries/update', {'entry_id': told['id'], 'value': 20})['entry']
        self.assertEqual(updated['value'], 20)
        self.write('/api/profile/entries/delete', {'entry_id': chat['id']})
        self.assertNotIn(chat['id'], [e['id'] for e in self.profile()['profile']['entries']])
        self.write('/api/undo', {})
        self.assertIn(chat['id'], [e['id'] for e in self.profile()['profile']['entries']])

    def test_profile_is_private_to_the_customer(self):
        entry = self.save('note', 'Saving for a sauna')
        self.assertTrue(self.profile(customer=OTHER)['profile']['empty'])
        self.assertEqual(self.write('/api/profile/entries/delete', {'entry_id': entry['id']}, status=404, customer=OTHER)['code'], 'unknown_reference')
        self.write('/api/profile/entries/update', {'entry_id': entry['id'], 'note': 'x'}, status=404, customer=OTHER)
        self.assertIn(entry['id'], [e['id'] for e in self.profile()['profile']['entries']])

    def test_every_personal_write_needs_explicit_confirmation(self):
        entry = self.save('note', 'Keep this')
        suggestion = self.get('/api/profile/suggestions')['suggestions'][0]['id']
        attempts = [
            ('/api/profile/entries', {'key': 'note', 'value': 'x'}),
            ('/api/profile/entries/update', {'entry_id': entry['id'], 'note': 'changed'}),
            ('/api/profile/entries/delete', {'entry_id': entry['id']}),
            ('/api/profile/forget', {}),
            ('/api/profile/suggestions/confirm', {'suggestion_id': suggestion}),
            ('/api/profile/suggestions/dismiss', {'suggestion_id': suggestion}),
            ('/api/profile/migrate-local', {'local': {'notes': ['From the old notebook']}}),
            ('/api/goals', {'name': 'Trip', 'target_cents': 200_000, 'target_date': '2027-06-30'}),
        ]
        for path, body in attempts:
            with self.subTest(path=path):
                error = self.post(path, body, status=400)
                self.assertIn('confirm', error['message'].lower())
                self.post(path, {**body, 'confirmed': False}, status=400)
        data = self.profile()
        self.assertEqual([(e['key'], e['value'], e['note']) for e in data['profile']['entries']], [('note', 'Keep this', None)])
        self.assertEqual(len(self.get('/api/profile/suggestions')['suggestions']), len(data['suggestions']))
        self.assertEqual(self.goal_count(), 0)

    def test_profile_page_renders_what_the_api_returns(self):
        self.save('saving_rate_target_pct', 15)
        self.save('protected_categories', ['Restaurants'])
        self.save('note', 'We are saving for a sauna', source='from_our_chat')
        data = self.profile()
        for locale in ('en', 'fi', 'sv'):
            with self.subTest(locale=locale):
                self.render_profile(data, r'''
for (const entry of data.profile.entries) {
  assert.ok(html.includes('data-profile-entry="' + entry.id + '"'), entry.key);
  assert.ok(html.includes('data-profile-edit="' + entry.id + '"'), 'edit ' + entry.key);
  assert.ok(html.includes('data-profile-delete="' + entry.id + '"'), 'delete ' + entry.key);
}
assert.ok(html.includes(p.escapeHtml(t('source.you_told_me'))), 'you told me label');
assert.ok(html.includes(p.escapeHtml(t('source.from_our_chat'))), 'from our chat label');
assert.ok(html.includes(p.escapeHtml(t('key.protected_categories'))), 'protected categories shown');
assert.ok(html.includes('data-profile-add'), 'add something');
assert.ok(html.includes('data-profile-forget'), 'forget everything');
// The 8-question intro must stay reachable from Me even when Coach stops auto-opening it (lane U).
assert.ok(html.includes('data-profile-onboarding'), 'intro entry point');
''', locale)

    def test_empty_profile_page_still_offers_the_intro(self):
        self.render_profile(self.profile(), r'''
assert.ok(html.includes('data-profile-empty'));
assert.ok(html.includes('data-profile-onboarding'));
assert.ok(html.includes('data-profile-forget'));
''')


class ProfileChangesTheNumbers(PersonalizationFixture):
    """Saving target, debts and regular investing change safe-to-spend; deleting restores it."""

    def test_saving_target_holds_back_the_planned_saving(self):
        base = self.until_payday()
        self.assertEqual(base['planned_saving_cents'], 0)
        entry = self.save('saving_rate_target_pct', 20)
        with_target = self.until_payday()
        self.assertEqual(with_target['planned_saving_cents'], SALARY_CENTS * 20 // 100)
        self.assertEqual(base['free_cents'] - with_target['free_cents'], SALARY_CENTS * 20 // 100)
        # Lane N cap: when free money is far above a comfortable pace (as here), the target comes out of
        # what could be saved; the pace never goes up, and it falls once free money is below the cap.
        self.assertLessEqual(with_target['per_day_cents'], base['per_day_cents'])
        self.assertEqual(base['extra_cents'] - with_target['extra_cents'], SALARY_CENTS * 20 // 100)
        self.assertIn('20', with_target['planned_saving_basis'])
        self.write('/api/profile/entries/delete', {'entry_id': entry['id']})
        self.assertEqual(self.until_payday()['free_cents'], base['free_cents'])

    def test_declared_loan_and_investing_are_held_back_once(self):
        base = self.until_payday()
        loan = self.save('debts', {'type': 'car_loan', 'monthly_payment_cents': 25_000})
        with_loan = self.until_payday()
        declared = [item for item in with_loan['committed_items'] if item['source'] == 'declared']
        self.assertEqual([(i['transaction_type'], i['amount_cents']) for i in declared], [('debt', 25_000)])
        self.assertEqual(with_loan['committed_cents'] - base['committed_cents'], 25_000)
        self.assertEqual(base['free_cents'] - with_loan['free_cents'], 25_000)
        self.save('regular_investing', {'active': True, 'monthly_cents': 12_000})
        with_both = self.until_payday()
        self.assertEqual(with_both['committed_cents'] - base['committed_cents'], 37_000)
        self.write('/api/profile/forget', {})
        self.assertEqual(self.until_payday()['committed_cents'], base['committed_cents'])
        self.assertTrue(loan['id'])

    def test_a_mortgage_confirmed_from_the_housing_payment_is_not_counted_twice(self):
        base = self.until_payday()
        housing = next(s for s in self.get('/api/profile/suggestions')['suggestions'] if s['kind'] == 'housing')
        self.assertEqual(housing['value']['typical_monthly_cents'], HOUSING_CENTS)
        saved = self.write('/api/profile/suggestions/confirm', {'suggestion_id': housing['id'], 'key': 'debts'})['entry']
        self.assertEqual((saved['key'], saved['value']['type'], saved['source']), ('debts', 'mortgage', 'from_your_transactions'))
        after = self.until_payday()
        self.assertEqual(after['committed_cents'], base['committed_cents'])
        self.assertEqual([item['amount_cents'] for item in after['skipped_declared_items']], [HOUSING_CENTS])

    def test_the_ai_tool_and_the_offline_coach_see_the_same_profile_numbers(self):
        self.save('saving_rate_target_pct', 20)
        api = self.until_payday()
        conn = connect(self.db)
        try:
            from scoach.agent_tools import ToolContext, dispatch
            ctx = ToolContext(conn, CID, MONTH, message='What can I safely spend this week?')
            tool = dispatch(conn, CID, ctx, 'safe_to_spend', {})
            direct = forecast.safe_until_payday(conn, CID, as_of=AS_OF, profile=planning_profile(conn, CID, AS_OF))
        finally:
            conn.close()
        for key in ('planned_saving_cents', 'per_day_cents', 'this_week_cents', 'free_cents'):
            self.assertEqual(tool[key], api[key], key)
            self.assertEqual(direct[key], api[key], key)
        offline = self.post('/api/coach', {'message': 'What is safe for me to spend this week?'})
        self.assertEqual(offline['tool_kind'], 'safe_to_spend')
        self.assertEqual(offline['tool_result']['this_week_cents'], api['this_week_cents'])
        self.assertEqual(offline['tool_result']['planned_saving_cents'], api['planned_saving_cents'])

    def test_targets_reach_the_planning_inputs(self):
        self.save('saving_rate_target_pct', 12.5)
        self.save('emergency_fund_target_months', 3)
        self.save('debts', {'type': 'student_loan', 'monthly_payment_cents': 9_000})
        conn = connect(self.db)
        try:
            inputs = planning_profile(conn, CID, AS_OF)
        finally:
            conn.close()
        self.assertEqual((inputs['saving_rate_target_pct'], inputs['emergency_fund_target_months']), (12.5, 3))
        self.assertEqual(inputs['debts_monthly_total_cents'], 9_000)
        self.assertEqual(inputs['coaching_mode'], 'normal')


class SteadyModeAfterALoss(PersonalizationFixture):
    """Job loss / income drop / large loss: steady mode, bigger reserve, no planned saving, gentler coach."""

    MODE_STEADY = re.compile(r'mode\W+(?:is\W+)?steady', re.IGNORECASE)

    def test_job_loss_turns_on_steady_mode_and_raises_the_reserve(self):
        self.save('saving_rate_target_pct', 20)
        normal = self.until_payday()
        self.assertFalse(normal['steady_mode'])
        event = self.save('life_event', {'type': 'job_loss', 'since': '2026-09-01'})
        data = self.profile()
        self.assertEqual(data['profile']['mode'], 'steady')
        self.assertEqual(data['profile']['mode_reason']['entry_id'], event['id'])
        steady = self.until_payday()
        self.assertTrue(steady['steady_mode'])
        self.assertEqual(steady['reserve_floor_source'], 'steady_mode_must_pays')
        self.assertGreater(steady['reserve_floor_cents'], normal['reserve_floor_cents'])
        self.assertGreaterEqual(steady['reserve_floor_cents'], steady['must_pays_monthly_cents'])
        self.assertEqual(steady['planned_saving_cents'], 0)       # no saving pressure while steady
        self.assertTrue(any('steady' in line.lower() for line in steady['assumptions']))

        # Turning steady mode off (the banner's "Turn off") restores the normal plan.
        self.write('/api/profile/entries/update', {'entry_id': event['id'], 'active': False})
        self.assertEqual(self.profile()['profile']['mode'], 'normal')
        back = self.until_payday()
        self.assertEqual((back['steady_mode'], back['reserve_floor_cents'], back['planned_saving_cents']),
                         (False, normal['reserve_floor_cents'], normal['planned_saving_cents']))

    def test_only_loss_events_switch_steady_mode_and_it_ends(self):
        self.save('life_event', {'type': 'new_child', 'since': '2026-08-01'})
        self.assertEqual(self.profile()['profile']['mode'], 'normal')
        ended = self.save('life_event', {'type': 'income_drop', 'since': '2026-06-01', 'ended': '2026-09-01'})
        self.assertEqual(self.profile()['profile']['mode'], 'normal')
        self.write('/api/profile/entries/delete', {'entry_id': ended['id']})
        self.save('life_event', {'type': 'large_loss', 'since': '2026-04-01'})
        profile = self.profile()['profile']
        self.assertEqual(profile['mode'], 'steady')
        self.assertEqual(money_profile.coaching_mode(profile, '2026-10-01'), 'normal')   # six months later

    def test_ai_coach_is_told_the_mode_and_the_steady_rules(self):
        _, fake = self.agent(answer('Hello there.'))
        system = fake.requests[0]['system']
        self.assertIsNone(self.MODE_STEADY.search(system))
        self.save('life_event', {'type': 'job_loss', 'since': '2026-09-01'})
        _, fake = self.agent(answer('I am here to help.'))
        system = fake.requests[0]['system']
        self.assertIsNotNone(self.MODE_STEADY.search(system))
        self.assertIn('job loss', system)
        self.assertRegex(system.lower(), r'steady mode.{0,80}(supportive|reassurance)')

    def test_profile_page_shows_the_steady_banner_with_turn_off(self):
        event = self.save('life_event', {'type': 'job_loss', 'since': '2026-09-01'})
        data = self.profile()
        for locale in ('en', 'fi', 'sv'):
            with self.subTest(locale=locale):
                self.render_profile(data, r'''
assert.ok(html.includes('data-profile-banner="steady"'));
assert.ok(html.includes(p.escapeHtml(t('steady.title'))));
assert.ok(html.includes(p.escapeHtml(t('steady.reason.job_loss'))));
assert.ok(html.includes('data-profile-mode-off="''' + event['id'] + r'''"'));
''', locale)
        self.write('/api/profile/entries/update', {'entry_id': event['id'], 'active': False})
        self.render_profile(self.profile(), "assert.ok(!html.includes('data-profile-banner'));")


class ProtectedCategoriesAreRespected(PersonalizationFixture):
    """Spending the customer leaves alone is never put forward for a cut by the coach."""

    def test_ai_coach_is_told_not_to_suggest_cutting_protected_spending(self):
        _, fake = self.agent(answer('Hello there.'))
        self.assertNotIn('Restaurants', fake.requests[0]['system'].split('How you work')[0])
        entry = self.save('protected_categories', ['Restaurants', 'Travel'])
        _, fake = self.agent(answer('Hello there.'))
        system = fake.requests[0]['system']
        self.assertIn('Protected categories (do not suggest cutting): Restaurants, Travel', system)
        tool_profile = None
        conn = connect(self.db)
        try:
            from scoach.agent_tools import ToolContext, dispatch
            tool_profile = dispatch(conn, CID, ToolContext(conn, CID, MONTH, message='What do you know about me?'), 'get_profile', {})
        finally:
            conn.close()
        self.assertIn('do not suggest cutting', tool_profile['summary'])
        self.write('/api/profile/entries/delete', {'entry_id': entry['id']})
        _, fake = self.agent(answer('Hello there.'))
        self.assertNotIn('Protected categories', fake.requests[0]['system'])

    def test_protected_category_names_are_validated(self):
        for bad in (['x' * 41], ['<script>'], 'Restaurants', [1]):
            with self.subTest(value=bad):
                self.write('/api/profile/entries', {'key': 'protected_categories', 'value': bad}, status=400)

    def test_local_preference_proposes_protecting_and_needs_confirmation(self):
        self.node(
            'const e = await import(' + json.dumps((WEB / 'experience.js').as_uri()) + ');\n' + r'''
const proposal = e.suggestedMemory("Don't cut restaurants", 'en');
assert.deepEqual([proposal.field, proposal.value], ['protected_category', 'Restaurants']);
assert.equal(e.suggestedMemory('Should I cut restaurants?', 'en'), null);  // a question is not a preference
const fi = e.suggestedMemory('En halua vähentää ravintola', 'fi');
assert.equal(fi?.value, 'Restaurants');
''')


class ThingsINoticed(PersonalizationFixture):
    """Suggestions from transactions: reading saves nothing; Keep saves with its source; Not this hides it."""

    def test_reading_suggestions_never_saves_anything(self):
        for _ in range(2):
            suggestions = self.get('/api/profile/suggestions')['suggestions']
            self.profile()
        self.assertTrue(self.profile()['profile']['empty'])
        kinds = {s['kind'] for s in suggestions}
        self.assertTrue({'salary', 'housing', 'regular_investing'} <= kinds, kinds)
        for item in suggestions:
            self.assertTrue(item['question'].rstrip().endswith('?'), item['question'])
            self.assertEqual(item['source'], 'from_your_transactions')
            self.assertTrue(item['evidence']['label'])

    def test_keep_saves_with_source_and_not_this_hides_for_good(self):
        suggestions = {s['kind']: s for s in self.get('/api/profile/suggestions')['suggestions']}
        kept = self.write('/api/profile/suggestions/confirm', {'suggestion_id': suggestions['regular_investing']['id']})['entry']
        self.assertEqual((kept['key'], kept['source'], kept['value']['active'], kept['value']['monthly_cents']),
                         ('regular_investing', 'from_your_transactions', True, 20_000))
        self.write('/api/profile/suggestions/dismiss', {'suggestion_id': suggestions['salary']['id']})
        data = self.profile()
        self.assertEqual([e['key'] for e in data['profile']['entries']], ['regular_investing'])   # dismissal is not an entry
        remaining = {s['id'] for s in data['suggestions']}
        self.assertNotIn(suggestions['regular_investing']['id'], remaining)
        self.assertNotIn(suggestions['salary']['id'], remaining)
        self.write('/api/profile/suggestions/dismiss', {'suggestion_id': suggestions['salary']['id']}, status=404)
        # Keeping a suggestion changes the plan like any other entry.
        self.assertEqual(self.until_payday()['skipped_declared_items'][0]['amount_cents'], 20_000)
        # Undo brings a dismissed suggestion back.
        self.write('/api/undo', {})
        self.assertIn(suggestions['salary']['id'], {s['id'] for s in self.get('/api/profile/suggestions')['suggestions']})

    def test_other_customers_cannot_answer_my_suggestions(self):
        mine = self.get('/api/profile/suggestions')['suggestions'][0]['id']
        self.write('/api/profile/suggestions/confirm', {'suggestion_id': mine}, status=404, customer=OTHER)
        self.assertTrue(self.profile(customer=OTHER)['profile']['empty'])

    def test_profile_page_renders_keep_and_not_this_for_each_suggestion(self):
        data = self.profile()
        self.assertTrue(data['suggestions'])
        for locale in ('en', 'fi', 'sv'):
            with self.subTest(locale=locale):
                self.render_profile(data, r'''
assert.ok(html.includes('data-profile-section="noticed"'));
assert.ok(html.includes(p.escapeHtml(t('noticed.title'))));
assert.ok(html.includes(p.escapeHtml(t('noticed.help'))));
for (const item of data.suggestions) {
  assert.ok(html.includes('data-suggestion-keep="' + item.id + '"'), 'keep ' + item.kind);
  assert.ok(html.includes('data-suggestion-dismiss="' + item.id + '"'), 'not this ' + item.kind);
}
''', locale)


class ForgetEverything(PersonalizationFixture):

    def test_forget_all_clears_profile_dismissals_numbers_and_prompt_and_can_be_undone(self):
        base = self.until_payday()
        self.save('saving_rate_target_pct', 20)
        self.save('life_event', {'type': 'job_loss', 'since': '2026-09-01'})
        self.save('note', 'Saving for a sauna')
        salary = next(s for s in self.get('/api/profile/suggestions')['suggestions'] if s['kind'] == 'salary')
        self.write('/api/profile/suggestions/dismiss', {'suggestion_id': salary['id']})
        self.assertNotEqual(self.until_payday()['reserve_floor_cents'], base['reserve_floor_cents'])

        forgotten = self.write('/api/profile/forget', {})
        self.assertGreaterEqual(forgotten['deleted_count'], 4)
        data = self.profile()
        self.assertTrue(data['profile']['empty'])
        self.assertEqual(data['profile']['mode'], 'normal')
        self.assertIn(salary['id'], {s['id'] for s in data['suggestions']})       # dismissals forgotten too
        after = self.until_payday()
        for key in ('reserve_floor_cents', 'planned_saving_cents', 'free_cents', 'steady_mode'):
            self.assertEqual(after[key], base[key], key)
        _, fake = self.agent(answer('Hello there.'))
        self.assertIn('nothing shared yet', fake.requests[0]['system'])
        self.assertNotIn('sauna', fake.requests[0]['system'])

        self.write('/api/undo', {})
        self.assertEqual(self.profile()['profile']['mode'], 'steady')


class ReviewBeforeSavingFromChat(PersonalizationFixture):
    """The coach proposes; only the customer's confirmed POST saves (goal or profile note)."""

    def test_goal_from_chat_is_a_review_card_until_confirmed(self):
        message = 'Help me save 2000 euros for a trip by the end of June 2027'
        data, _ = self.agent(call('goal_plan', name='Trip', target_cents=200_000, target_date='2027-06-30'),
                             call('propose_action', kind='create_goal', params={'name': 'Trip', 'target_cents': 200_000, 'target_date': '2027-06-30'}),
                             answer('I prepared a goal for you to review before anything is saved.'), message=message)
        self.assertEqual(data['source'], 'agent')
        self.assertEqual([(a['kind'], a['params']) for a in data['actions']],
                         [('create_goal', {'name': 'Trip', 'target_cents': 200_000, 'target_date': '2027-06-30'})])
        self.assertEqual(self.goal_count(), 0)
        self.post('/api/goals', {**data['actions'][0]['params']}, status=400)          # not confirmed
        saved = self.write('/api/goals', {**data['actions'][0]['params'], 'provenance': 'gemini_proposed_user_confirmed'})
        self.assertEqual(self.goal_count(), 1)
        self.assertEqual(saved['audit_event']['provenance'], 'gemini_proposed_user_confirmed')
        self.assertIn('Trip', [goal['name'] for goal in self.get('/api/goals')['goals']])

    def test_profile_fact_from_chat_is_a_review_card_then_recorded_with_its_source(self):
        message = 'I lost my job this month and we pay 700 a month for our mortgage.'
        entries = [{'key': 'life_event', 'value': '{"type": "job_loss", "since": "2026-09"}', 'note': 'Told in chat'},
                   {'key': 'debts', 'value': '{"type": "mortgage", "monthly_payment_cents": 70000}'}]
        data, _ = self.agent(call('propose_profile_update', entries=entries),
                             answer('I am sorry to hear that. I prepared two notes for you to review.'), message=message)
        self.assertEqual([a['kind'] for a in data['actions']], ['update_profile'])
        proposed = data['actions'][0]['params']['entries']
        self.assertEqual(proposed[0]['value'], {'type': 'job_loss', 'since': '2026-09-01'})
        self.assertTrue(self.profile()['profile']['empty'])                            # nothing stored yet
        self.assertEqual(self.until_payday()['steady_mode'], False)

        # What the chat review card's Save does (web/v3.js handleAgentAction 'update_profile').
        for entry in proposed:
            body = {'key': entry['key'], 'value': entry['value'], 'source': 'from_our_chat',
                    'provenance': 'gemini_proposed_user_confirmed', **({'note': entry['note']} if entry.get('note') else {})}
            recorded = self.write('/api/profile/entries', body)
            self.assertEqual(recorded['audit_event']['provenance'], 'gemini_proposed_user_confirmed')
            self.assertEqual(recorded['entry']['source_label'], 'From our chat')
        profile = self.profile()['profile']
        self.assertEqual(profile['mode'], 'steady')
        self.assertTrue(self.until_payday()['steady_mode'])
        _, fake = self.agent(answer('Hello again.'))
        self.assertIn('mortgage €700 a month', fake.requests[0]['system'])

    def test_profile_proposals_cannot_invent_amounts(self):
        entries = [{'key': 'debts', 'value': '{"type": "mortgage", "monthly_payment_cents": 123400}'}]
        data, _ = self.agent(call('propose_profile_update', entries=entries), answer('Noted for review.'),
                             message='We have a mortgage.')
        self.assertEqual(data.get('actions') or [], [])
        self.assertTrue(self.profile()['profile']['empty'])


class LocalPreferenceConsent(PersonalizationFixture):
    """web/experience.js: preferences and wishes stay in this visit unless the customer opts in."""

    def test_browser_memory_only_with_consent(self):
        self.node(
            'const e = await import(' + json.dumps((WEB / 'experience.js').as_uri()) + ');\n' + r'''
const backing = new Map();
const storage = {getItem: k => backing.has(k) ? backing.get(k) : null, setItem: (k, v) => backing.set(k, String(v)), removeItem: k => backing.delete(k)};
const key = e.PROFILE_PREFIX + 'CUST_PG1';
const store = e.createExperienceStore(storage, 'CUST_PG1');
store.save({protected_category: 'Restaurants', style: 'direct', consent: true});   // save() cannot grant consent
assert.equal(store.load().protected_category, 'Restaurants');               // useful for this visit
assert.equal(store.load().consent, false);
assert.equal(backing.has(key), false);                                       // nothing written to the browser
store.addWish({title: 'Sauna', template: 'custom'});
assert.equal(backing.has(key), false);
store.setConsent(true);
assert.ok(store.isPersisted());
const saved = JSON.parse(backing.get(key)).profile;
assert.deepEqual([saved.protected_category, saved.style, saved.wishes.length], ['Restaurants', 'direct', 1]);
store.addNote({text: 'Remember the sauna', source: 'user'});
assert.equal(JSON.parse(backing.get(key)).profile.notes.length, 1);
// Revoking consent clears what was remembered.
store.setConsent(false);
assert.equal(store.load().protected_category, 'none');
assert.ok(!backing.get(key) || JSON.parse(backing.get(key)).profile.consent === false);
// Forget clears everything, including the tour flag.
store.setConsent(true); store.save({style: 'direct'}); store.markOnboarded();
store.forget();
assert.equal(store.load().style, 'gentle');
assert.equal(store.isOnboarded(), false);
assert.equal(backing.has(e.TOUR_PREFIX + 'CUST_PG1'), false);
// Another persona never sees this one's memory.
store.setConsent(true); store.save({protected_category: 'Travel'});
assert.equal(e.createExperienceStore(storage, 'CUST_PG2').load().protected_category, 'none');
''')

    def test_moving_browser_notes_into_the_profile_is_confirmed_and_deduplicated(self):
        local = {'notes': ['I like long walks', 'I like long walks'], 'style': 'direct', 'protected_category': 'Restaurants',
                 'onboarding_complete': True}
        moved = self.write('/api/profile/migrate-local', {'local': local})
        self.assertEqual(sorted(e['key'] for e in moved['imported']), ['coaching_style', 'note', 'protected_categories'])
        self.assertTrue(all(e['source'] == 'you_told_me' for e in moved['imported']))
        again = self.write('/api/profile/migrate-local', {'local': local})
        self.assertEqual(again['imported'], [])


class RecordedNoticesAreLocalized(unittest.TestCase):
    """The 'coach recorded this' and review-card copy exists in EN, FI and SV."""

    def test_notice_and_profile_copy_in_three_languages(self):
        if not NODE:
            self.skipTest('node is required')
        script = ('import assert from "node:assert/strict";\n'
                  'const i = await import(' + json.dumps((WEB / 'i18n.js').as_uri()) + ');\n'
                  'const p = await import(' + json.dumps((WEB / 'money-profile.js').as_uri()) + ');\n' + r'''
for (const key of ['v3.onboarding.saved', 'v3.profile.noteTitle', 'v3.profile.forgetTitle', 'v3.profile.forgetIntro', 'v3.profile.deleteTitle']) {
  for (const l of ['en', 'fi', 'sv']) assert.ok(typeof i.MESSAGES[l][key] === 'string' && i.MESSAGES[l][key].trim(), l + ' ' + key);
  assert.notEqual(i.MESSAGES.fi[key], i.MESSAGES.en[key], 'fi translated ' + key);
  assert.notEqual(i.MESSAGES.sv[key], i.MESSAGES.en[key], 'sv translated ' + key);
}
for (const key of ['noticed.title', 'noticed.help', 'noticed.keep', 'noticed.dismiss', 'steady.title', 'steady.off', 'steady.help',
                   'actions.forget', 'actions.forgetHelp', 'actions.add', 'actions.onboarding', 'source.you_told_me',
                   'source.from_your_transactions', 'source.from_our_chat', 'key.protected_categories', 'key.saving_rate_target_pct',
                   'key.emergency_fund_target_months', 'key.debts', 'key.life_event']) {
  for (const l of ['fi', 'sv']) assert.notEqual(p.pm(l, key), p.pm('en', key), l + ' translated ' + key);
}
''')
        result = run_node(script)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


# ---------------------------------------------------------------------------------- guarded V4

@unittest.skipUnless(hasattr(forecast, 'spending_plan'), 'lane N forecast.spending_plan not merged yet')
class SpendingPlanKeepsPersonalization(PersonalizationFixture):
    """Lane N: ONE safe-to-spend (spending_plan) must still be shaped by the money profile."""

    def plan(self):
        conn = connect(self.db)
        try:
            return forecast.spending_plan(conn, CID, as_of=AS_OF, profile=planning_profile(conn, CID, AS_OF))
        finally:
            conn.close()

    @staticmethod
    def held(plan, kind=None):
        return [item for item in plan['held_back'] if kind is None or item['kind'] == kind]

    def test_api_returns_the_plan_and_it_matches_the_function(self):
        self.save('saving_rate_target_pct', 20)
        api = self.get('/api/safe-to-spend')
        self.assertIn('held_back', api)
        plan = self.plan()
        for key in ('free_cents', 'per_day_cents', 'buffer_cents', 'reserve_floor_cents'):
            self.assertEqual(api[key], plan[key], key)

    def test_saving_target_is_held_back(self):
        base = self.plan()
        self.save('saving_rate_target_pct', 20)
        plan = self.plan()
        self.assertEqual(sum(i['amount_cents'] for i in plan['held_back']) - sum(i['amount_cents'] for i in base['held_back']),
                         SALARY_CENTS * 20 // 100)
        self.assertIn(SALARY_CENTS * 20 // 100, [i['amount_cents'] for i in plan['held_back']])
        self.assertLessEqual(plan['free_cents'], base['free_cents'] - SALARY_CENTS * 20 // 100)

    def test_declared_loan_is_held_back_as_a_loan(self):
        base = self.plan()
        self.save('debts', {'type': 'car_loan', 'monthly_payment_cents': 25_000})
        plan = self.plan()
        self.assertIn(25_000, [i['amount_cents'] for i in self.held(plan, 'loan')])
        self.assertLessEqual(plan['free_cents'], base['free_cents'] - 25_000)

    def test_steady_mode_raises_the_reserve_and_drops_planned_saving(self):
        self.save('saving_rate_target_pct', 20)
        normal = self.plan()
        self.save('life_event', {'type': 'job_loss', 'since': '2026-09-01'})
        steady = self.plan()
        self.assertGreater(steady['reserve_floor_cents'], normal['reserve_floor_cents'])
        self.assertNotIn(SALARY_CENTS * 20 // 100, [i['amount_cents'] for i in self.held(steady, 'goal')])
        self.assertLessEqual(steady['per_day_cents'], normal['per_day_cents'] + SALARY_CENTS * 20 // 100)

    def test_forget_all_returns_to_the_unpersonalised_plan(self):
        base = self.plan()
        self.save('saving_rate_target_pct', 20)
        self.save('debts', {'type': 'car_loan', 'monthly_payment_cents': 25_000})
        self.write('/api/profile/forget', {})
        after = self.plan()
        self.assertEqual((after['free_cents'], after['per_day_cents'], after['reserve_floor_cents']),
                         (base['free_cents'], base['per_day_cents'], base['reserve_floor_cents']))


class CatalogueCardsKeepPersonalization(PersonalizationFixture):
    """Lane C: catalogue cards say when they use the profile and never suggest cutting protected spending."""

    USING_PROFILE = 'Using what you told me'

    def setUp(self):
        super().setUp()
        if not self.endpoint_exists('GET', '/api/catalogue'):
            self.skipTest('lane C /api/catalogue not merged yet')

    def question(self, pattern, locale='en'):
        data = self.get('/api/catalogue', locale=locale)
        for group in data['groups']:
            for item in group['questions']:
                if re.search(pattern, item['text'], re.IGNORECASE):
                    return item['id']
        self.fail('No catalogue question matches ' + pattern)

    def contract_post(self, path, body):
        """Lane C contract: customer and month in the query string, the rest in the JSON body."""
        return self.call_api('POST', path + '?customer_id=' + CID + '&month=' + MONTH, body)

    def card(self, question_id, locale='en'):
        return self.contract_post('/api/catalogue/answer', {'question_id': question_id, 'locale': locale})['card']

    @staticmethod
    def text(card):
        return json.dumps({k: card.get(k) for k in ('title', 'headline', 'lines', 'caveat', 'followups', 'pickers')}, ensure_ascii=False)

    def test_safe_to_spend_card_says_it_uses_the_profile(self):
        qid = self.question(r'safely spend|until payday')
        plain = self.card(qid)
        self.assertNotIn(self.USING_PROFILE, self.text(plain))
        plain_fi, plain_sv = self.card(qid, 'fi'), self.card(qid, 'sv')
        self.save('saving_rate_target_pct', 20)
        personal = self.card(qid)
        self.assertIsNone(plain.get('profile_note'))
        self.assertTrue((personal.get('profile_note') or '').startswith(self.USING_PROFILE), personal.get('profile_note'))
        self.assertLessEqual(len(personal['lines']), 4)
        for locale, before in (('fi', plain_fi), ('sv', plain_sv)):
            after = self.card(qid, locale)
            self.assertIsNone(before.get('profile_note'), locale)
            self.assertTrue(after.get('profile_note'), locale)
            self.assertNotIn(self.USING_PROFILE, (after.get('profile_note') or '') + self.text(after), locale)

    def test_save_more_card_never_suggests_cutting_protected_spending(self):
        qid = self.question(r'save more')
        self.save('protected_categories', ['Restaurants'])
        words = re.compile(r'restaurant|eating out|ravintol|ulkona sy|restaurang', re.IGNORECASE)
        english = self.card(qid)
        for locale in ('en', 'fi', 'sv'):
            card = english if locale == 'en' else self.card(qid, locale)
            for picker in card.get('pickers') or []:
                self.assertNotRegex(json.dumps(picker.get('value'), ensure_ascii=False), words, locale)
            for followup in card.get('followups') or []:
                self.assertNotRegex(followup['text'], words, locale)
            self.assertNotRegex(json.dumps(card.get('headline'), ensure_ascii=False), words, locale)
            self.assertNotRegex(json.dumps(card.get('chart'), ensure_ascii=False), words, locale)
            for line in card['lines']:
                # Naming the protected category is fine only in profile_note, which explains the profile was used.
                self.assertNotRegex(line, words, locale)

    def test_life_event_message_gets_a_supportive_line_and_a_way_to_tell_the_coach(self):
        for locale, message in (('en', 'I lost my job last week'), ('fi', 'Menetin työpaikkani'), ('sv', 'Jag har förlorat jobbet')):
            data = self.contract_post('/api/catalogue/match', {'message': message, 'locale': locale})
            self.assertTrue(data['supportive'], locale)
            self.assertTrue(data['suggestions'], locale)
            self.assertLessEqual(len(data['suggestions']), 3)
        self.assertTrue(self.profile()['profile']['empty'])     # matching never saves a life event by itself


class OptionalPlansLiveInTheProfile(PersonalizationFixture):
    """Lane P: plans are money-profile entries: confirmed, visible, forgettable, undoable."""

    MORTGAGE = {'principal_cents': 15_000_000, 'loan_type': 'annuity', 'reference_rate': 'euribor_12m',
                'reference_rate_bp': 250, 'margin_bp': 60, 'remaining_months': 240}

    def setUp(self):
        super().setUp()
        if 'plan_mortgage' not in money_profile.KEYS:
            self.skipTest('lane P plan_mortgage profile key not merged yet')

    def save_plan(self):
        code, result = self.app.handle('POST', '/api/profile/entries', {'customer_id': CID, 'month': MONTH, 'confirmed': True,
                                                                       'key': 'plan_mortgage', 'value': self.MORTGAGE})
        if code == 400:
            self.skipTest('sample plan_mortgage value no longer matches lane P validation: ' + result['error']['message'])
        self.assertEqual(code, 200, result)
        return result['data']['entry']

    def test_plan_needs_confirmation_and_is_part_of_the_profile(self):
        self.post('/api/profile/entries', {'key': 'plan_mortgage', 'value': self.MORTGAGE}, status=400)
        entry = self.save_plan()
        self.assertIn(entry['id'], [e['id'] for e in self.profile()['profile']['entries']])
        if self.endpoint_exists('GET', '/api/plans'):
            self.assertIn('mortgage', json.dumps(self.get('/api/plans')))
        self.write('/api/profile/forget', {})
        self.assertTrue(self.profile()['profile']['empty'])
        self.write('/api/undo', {})
        self.assertIn(entry['id'], [e['id'] for e in self.profile()['profile']['entries']])

    def test_saving_a_plan_through_its_own_endpoint_needs_confirmation(self):
        if not self.endpoint_exists('POST', '/api/plans/mortgage'):
            self.skipTest('lane P /api/plans/mortgage not merged yet')
        error = self.post('/api/plans/mortgage', {'plan': dict(self.MORTGAGE)}, status=400)
        self.assertIn('confirm', error['message'].lower())
        self.assertTrue(self.profile()['profile']['empty'])
        code, result = self.app.handle('POST', '/api/plans/mortgage', {'customer_id': CID, 'month': MONTH, 'confirmed': True,
                                                                      'plan': dict(self.MORTGAGE)})
        if code == 400:
            self.skipTest('sample mortgage plan no longer matches lane P validation: ' + result['error']['message'])
        self.assertEqual(code, 200, result)
        self.assertIn('plan_mortgage', [e['key'] for e in self.profile()['profile']['entries']])


if __name__ == '__main__':
    unittest.main()
