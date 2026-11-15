"""V5 fix wave, lane ME: Me page and profile forms (web/money-profile.js, web/draft-card.js, web/session.js).

Pure Node checks plus an API round trip that saves every "Add something" key in the exact shape the form produces.
The browser end-to-end walk (EN/FI, 375 and 1280) lives in the lane report; these tests keep the contract.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
PRELUDE = (
    'import assert from "node:assert/strict";\n'
    'const p = await import(' + json.dumps((WEB / 'money-profile.js').as_uri()) + ');\n'
    'const dc = await import(' + json.dumps((WEB / 'draft-card.js').as_uri()) + ');\n'
    'const ss = await import(' + json.dumps((WEB / 'session.js').as_uri()) + ');\n'
    'const H = {money: c => "EUR" + (c / 100).toFixed(2), dateLabel: d => "D:" + String(d).slice(0, 10), monthLabel: m => "M:" + m};\n'
)


def node(body):
    return subprocess.run(['node', '--input-type=module', '-e', PRELUDE + body], capture_output=True, text=True)


class MeV5fTest(unittest.TestCase):
    def run_js(self, body):
        result = node(body)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def test_form_values_validate_on_the_server(self):
        """Every Add-something key: draft spec -> filled values -> draftValueToEntry -> money_profile.validate_entry."""
        filled = {
            'note': {'value': 'Birthday trip'}, 'upcoming': {'what': 'New bike', 'month': '2027-03', 'amount': '850'},
            'debts': {'type': 'car_loan', 'monthly': '250', 'remaining': '6 000'},
            'life_event': {'type': 'job_loss', 'since': '2026-09', 'note': ''},
            'saving_rate_target_pct': {'value': '12'}, 'emergency_fund_target_months': {'value': '3'},
            'regular_investing': {'active': 'yes', 'monthly': '100'}, 'life_stage': {'value': 'working'},
            'household': {'adults': '2', 'children': '1'}, 'income_stability': {'value': 'varies'},
            'risk_attitude': {'value': 'balanced'}, 'coaching_style': {'value': 'gentle'},
            'protected_categories': {'value': 'Travel, Restaurants'},
        }
        out = self.run_js('''
const filled = %s;
assert.deepEqual(Object.keys(filled).sort(), [...p.ADDABLE_KEYS].sort());
const result = {};
for (const [key, raw] of Object.entries(filled)) {
  const spec = p.draftSpecForEntry(key, 'en');
  const checked = dc.validateDraft(spec, raw, 'en');
  assert.ok(checked.valid, key + ' ' + JSON.stringify(checked.errors));
  const entry = p.draftValueToEntry(key, checked.values);
  assert.deepEqual(entry.errors, {}, key);
  result[key] = entry.value;
}
console.log(JSON.stringify(result));
''' % json.dumps(filled))
        from scoach import money_profile
        for key, value in json.loads(out).items():
            with self.subTest(key=key):
                money_profile.validate_entry(key, value)  # raises ValueError on a shape the API would reject

    def test_add_every_key_through_the_api(self):
        """Save, list, edit and delete each Add-something key on a copy of the demo database."""
        source = ROOT / 'var' / 'scoach.sqlite3'
        if not source.is_file():
            self.skipTest('demo database not built')
        from scoach import db, money_profile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'copy.sqlite3'
            shutil.copy(source, path)
            conn = db.connect(path)
            try:
                customer = 'CUST00001'
                values = {
                    'debts': {'type': 'car_loan', 'monthly_payment_cents': 25000},
                    'upcoming': {'what': 'New bike', 'month': '2027-03', 'amount_cents': 85000},
                    'life_event': {'type': 'moving', 'since': '2026-08'},
                    'note': 'Birthday trip',
                }
                for key, value in values.items():
                    saved = money_profile.save_entry(conn, customer, key, value, 'you_told_me')['entry']
                    profile = money_profile.get_profile(conn, customer, '2026-09-30')
                    self.assertIn(saved['id'], [e['id'] for e in profile['by_key'][key]])
                    money_profile.update_entry(conn, customer, saved['id'], value=value)
                    money_profile.delete_entry(conn, customer, saved['id'])
                event = money_profile.save_entry(conn, customer, 'life_event', {'type': 'job_loss', 'since': '2026-09'}, 'you_told_me')['entry']
                self.assertEqual(money_profile.get_profile(conn, customer, '2026-09-30')['mode'], 'steady')
                # "Turn off" = mark ended (the event stays); undo removes "ended"
                money_profile.update_entry(conn, customer, event['id'], value={**event['value'], 'ended': '2026-09-30'})
                after = money_profile.get_profile(conn, customer, '2026-09-30')
                self.assertEqual(after['mode'], 'normal')
                self.assertEqual(len(after['by_key']['life_event']), 1)
                money_profile.update_entry(conn, customer, event['id'], value=event['value'])
                self.assertEqual(money_profile.get_profile(conn, customer, '2026-09-30')['mode'], 'steady')
            finally:
                conn.close()

    def test_profile_page_steady_off_on_and_notice(self):
        self.run_js(r'''
const E = (id, key, value, extra = {}) => ({id, key, value, source:'you_told_me', active:true, updated_at:'2026-11-01T00:00:00Z', ...extra});
const steady = {mode:'steady', entries:[E('ev1', 'life_event', {type:'job_loss', since:'2026-09-01'})]};
const on = p.renderProfilePage(steady, [], 'en', H);
assert.ok(on.includes('data-profile-mode-off="ev1"') && on.includes('Turn off steady mode'));
assert.ok(!on.includes('data-profile-mode-on'));
const off = {mode:'normal', entries:[E('ev1', 'life_event', {type:'job_loss', since:'2026-09-01', ended:'2026-09-30'})]};
const html = p.renderProfilePage(off, [], 'fi', {...H, notice:{text:'Rauhallinen tahti on pois päältä.', undo:true}});
assert.ok(html.includes('data-profile-mode-on="ev1"') && html.includes('data-profile-undo') && html.includes('data-profile-notice'));
assert.ok(!html.includes('data-profile-banner="steady"'));
assert.equal(p.steadyReasonEntry(off), null);
for (const l of ['en', 'fi', 'sv']) { assert.ok(!/careful|varovai|försiktig/i.test(p.pm(l, 'steady.offIntro', {event:'x'}))); }
const actions = []; let handler;
const root = {addEventListener: (_, h) => { handler = h; }, contains: () => true};
p.attachProfilePage(root, {onAction: a => actions.push(a)});
const btn = attrs => ({closest: () => ({disabled:false, hasAttribute: n => n in attrs, getAttribute: n => attrs[n]})});
handler({target: btn({'data-profile-mode-on': 'ev1'})});
handler({target: btn({'data-profile-undo': ''})});
handler({target: btn({'data-suggestion-alt': 's1', 'data-alt-index': '1'})});
assert.deepEqual(actions, [{type:'mode_on', id:'ev1'}, {type:'undo'}, {type:'suggestion_alt', id:'s1', index:1}]);
''')

    def test_suggestions_choices_colon_and_filters(self):
        self.run_js(r'''
const housing = {id:'h', kind:'housing', key:'observation', value:{}, question:'Is this rent or a mortgage payment?',
  save_as:{key:'note', value:'I pay rent.'}, alternatives:[{label:'It is rent', key:'note', value:'I pay rent.'}, {label:'It is a mortgage', key:'debts', value:{type:'mortgage', monthly_payment_cents:97500}}]};
assert.deepEqual(p.suggestionChoices(housing, 'en', H).map(c => c.label), ['It is rent', 'It is a mortgage']);
const steadyQ = {id:'s', kind:'income_stability', key:'income_stability', value:'steady', question:'Would you call your income steady?', save_as:{key:'income_stability', value:'steady'}, alternatives:[]};
const page = p.renderProfilePage({mode:'normal', entries:[]}, [housing, steadyQ], 'fi', H);
assert.ok(page.includes('data-suggestion-alt="h"') && page.includes('It is a mortgage'));
assert.ok(page.includes('Tulojen tasaisuus: suunnilleen samat'), 'lower case after the colon');
assert.ok(page.includes('Valmentajasi on vasta tutustumassa sinuun'));
assert.equal(p.afterColon('Kyllä, 100 €'), 'kyllä, 100 €'); assert.equal(p.afterColon('EUR 5'), 'EUR 5');
// steady mode hides "is your income steady?"; a mortgage plan hides "rent or mortgage?"
assert.deepEqual(p.visibleSuggestions({mode:'steady', entries:[]}, [housing, steadyQ]).map(s => s.id), ['h']);
assert.deepEqual(p.visibleSuggestions({mode:'normal', entries:[{key:'plan_mortgage', active:true, value:{}}]}, [housing, steadyQ]).map(s => s.id), ['s']);
// one "Taxes" heading: the tax entry is named by its year
const tax = p.renderProfilePage({mode:'normal', entries:[{id:'t1', key:'tax', value:{tax_year:2026, base_rate_bp:2150}, active:true}]}, [], 'en', H);
assert.ok(tax.includes('Tax details for 2026') && !tax.includes('Tax year 2026:'));
''')

    def test_confirm_without_fields_has_no_change_button(self):
        self.run_js(r'''
const danger = dc.renderDraftCard({id:'d', kind:'profile', danger:true, title:'Forget everything?', intro:'x', fields:[]}, 'en');
assert.ok(!danger.includes('data-draft-change') && !danger.includes('Nothing is saved until'));
const plain = dc.renderDraftCard({id:'c', kind:'profile', title:'Turn off steady mode?', fields:[], saveLabel:'Turn off'}, 'fi');
assert.ok(!plain.includes('data-draft-change'));
const form = dc.renderDraftCard({id:'f', kind:'profile', fields:[{name:'a', label:'A', type:'text', value:'x'}]}, 'en');
assert.ok(form.includes('data-draft-change') && form.includes('Nothing is saved until'));
for (const l of ['en', 'fi', 'sv']) assert.ok(p.pm(l, 'forget.intro').length > 80 && p.pm(l, 'forget.confirm'));
''')

    def test_session_persistence_helpers(self):
        self.run_js(r'''
const mem = new Map(); const store = {getItem: k => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v), removeItem: k => mem.delete(k)};
assert.equal(ss.readSession(store), null);
ss.writeSession(store, {customerId:'CUST01331', month:'2026-08'});
assert.deepEqual(ss.readSession(store, ['CUST00001', 'CUST01331']), {customerId:'CUST01331', month:'2026-08'});
assert.equal(ss.readSession(store, ['CUST00001']), null, 'unknown persona ignored');
ss.writeSession(store, {customerId:'CUST01331', month:'bad'});
assert.deepEqual(ss.readSession(store), {customerId:'CUST01331', month:null});
mem.set(ss.SESSION_KEY, '{oops'); assert.equal(ss.readSession(store), null);
ss.writeSession(store, null); assert.equal(mem.size, 0);
assert.equal(ss.readSession({getItem: () => { throw new Error('blocked'); }}), null);
''')

    def test_app_restores_session_before_first_navigate(self):
        app = (WEB / 'app.js').read_text(encoding='utf-8')
        self.assertIn("from './session.js'", app)
        restore, navigate = app.index('readSession(sessionStore'), app.index("globalThis.addEventListener?.('popstate'")
        self.assertLess(restore, navigate)
        self.assertIn('writeSession(sessionStore,{customerId:context.customerId,month:context.month})', app)


if __name__ == '__main__':
    unittest.main()
