"""V4 lane C: question catalogue, answer cards, free-text matching and the agent fallback.

Runs on a temporary synthetic ledger (always) and, when available, on a copy of the demo
database (``var/scoach.sqlite3`` or the path in ``SCOACH_DEMO_DB``) for the brief's questions.
"""
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_helper import ScriptedTransport, answer, call
from scoach import catalogue, money_profile
from scoach.agent_tools import ToolContext, dispatch
from scoach.api import Application
from scoach.db import connect, initialize_schema

CID, OTHER, MONTH = 'CUST_CAT1', 'CUST_CAT2', '2026-09'
ROWS = [
    (3, 'Housing', -90_000, 'housing_payment', None, None),
    (5, 'Utilities', -6_000, 'utilities_payment', None, None),
    (8, 'Health', -4_500, 'purchase', 'M9', '5912'),
    (10, 'Groceries', -12_000, 'purchase', 'M1', '5411'),
    (12, 'Restaurants', -4_000, 'purchase', 'M2', '5812'),
    (14, 'Lifestyle', -6_500, 'purchase', 'M6', '5651'),
    (18, 'Entertainment', -3_000, 'purchase', 'M5', '7832'),
    (20, 'Groceries', -8_000, 'purchase', 'M1', '5411'),
    (22, 'Restaurants', -15_000, 'purchase', 'M3', '5812'),
    (24, 'Transportation', -2_500, 'purchase', 'M4', '4121'),
    (25, 'Salary', 300_000, 'salary', None, None),
    (26, 'Investments', -20_000, 'investment_deposit', None, None),
]
DEMO = Path(os.environ.get('SCOACH_DEMO_DB') or Path(__file__).resolve().parents[1] / 'var' / 'scoach.sqlite3')
DEV_WORDS = re.compile(r'deterministic|demo reserve|\bMCC\b|quartile|scenario|provenance|reference day|fixed_obligation|discretionary|flexible_essential|_cents', re.I)


def build_ledger(path):
    conn = connect(path)
    try:
        initialize_schema(conn)
        index = 0
        for customer, account, age in ((CID, 'ACC_CAT1', 34), (OTHER, 'ACC_CAT2', 58)):
            conn.execute('INSERT INTO customers VALUES(?,?,?,?)', (customer, '00100', age, '{}'))
            balance = 150_000
            for month in range(1, 10):
                for day, category, amount, kind, merchant, mcc in ROWS:
                    index += 1
                    balance += amount
                    conn.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                 (f'tx:{index}:cat', customer, account, f'2026-{month:02d}-{day:02d}', '01JAN26:12:00:00',
                                  category, amount, balance, kind, merchant, mcc, index, 'cat-hash', '{}'))
        conn.commit()
    finally:
        conn.close()


def card_text(card):
    return json.dumps({k: card.get(k) for k in ('title', 'headline', 'lines', 'caveat', 'followups', 'pickers', 'evidence', 'chart', 'profile_note')},
                      ensure_ascii=False)


class Fixture(unittest.TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {'GEMINI_API_KEY': '', 'DEEPSEEK_API_KEY': '', 'AGENT_PROVIDER': ''})
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'catalogue.sqlite3'
        build_ledger(self.db)
        self.conn = connect(self.db)
        self.addCleanup(self.conn.close)
        self.app = Application(self.db)

    def card(self, qid, locale='en', params=None, customer=CID, month=MONTH):
        return catalogue.answer(self.conn, customer, month, qid, params or {}, locale)

    def api(self, method, target, body=None, status=200, app=None):
        code, result = (app or self.app).handle(method, target, body)
        self.assertEqual(code, status, result)
        return result['data'] if result['ok'] else result['error']

    def save(self, key, value):
        money_profile.save_entry(self.conn, CID, key, value, 'you_told_me')
        self.conn.commit()


class FormattingTests(unittest.TestCase):
    def test_money_and_percent_formats(self):
        self.assertEqual(catalogue.money(113827, 'en'), '€1,138.27')
        self.assertEqual(catalogue.money(113827, 'fi'), '1 138,27 €')
        self.assertEqual(catalogue.money(113827, 'sv'), '1 138,27 €')
        self.assertEqual(catalogue.money(-50, 'en'), '−€0.50')
        self.assertEqual(catalogue.percent('9.6', 'en'), '9.6%')
        self.assertEqual(catalogue.percent('9.6', 'fi'), '9,6 %')
        self.assertEqual(catalogue.percent('20', 'sv'), '20 %')
        self.assertEqual(catalogue.month_label('2026-09', 'fi', 'in'), 'syyskuussa 2026')
        self.assertEqual(catalogue.date_label('2026-10-22', 'fi'), '22.10.2026')
        self.assertEqual(catalogue.date_label('2026-10-22', 'sv'), '22 okt. 2026')


class CatalogueShapeTests(Fixture):
    def test_groups_questions_and_starters(self):
        for locale in catalogue.LOCALES:
            data = self.api('GET', '/api/catalogue?customer_id=%s&locale=%s' % (CID, locale))
            self.assertEqual(len(data['groups']), 7)
            ids = [q['id'] for g in data['groups'] for q in g['questions']]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(25 <= len(ids) <= 30, len(ids))
            self.assertEqual(len(data['starters']), 6)
            self.assertTrue(set(data['starters']) <= set(ids))
            self.assertTrue(set(catalogue.BRIEF_QUESTIONS) <= set(data['starters']))
            self.assertTrue(all(g['title'] and all(q['text'] for q in g['questions']) for g in data['groups']))
        self.api('GET', '/api/catalogue?customer_id=%s&locale=de' % CID, status=400)
        self.api('GET', '/api/catalogue?customer_id=%s&bogus=1' % CID, status=400)

    def test_texts_exist_in_three_languages_and_differ(self):
        for question in catalogue.QUESTIONS.values():
            self.assertEqual(set(question.text), set(catalogue.LOCALES))
            self.assertNotEqual(question.text['en'], question.text['fi'], question.id)
            self.assertNotEqual(question.text['en'], question.text['sv'], question.id)
            self.assertTrue(2 <= len(question.followups) <= 3, question.id)
            for item in question.followups:
                self.assertIn(item if isinstance(item, str) else item[0], catalogue.QUESTIONS)

    def test_brief_questions_are_in_the_catalogue(self):
        texts = {q.text['en'] for q in catalogue.QUESTIONS.values()}
        for text in ('Where did my money go this month?', 'What kind of spender am I?',
                     'What can I safely spend this week?', 'How could I save more?'):
            self.assertIn(text, texts)

    def test_every_card_follows_the_contract_in_every_language(self):
        for qid in catalogue.QUESTIONS:
            for locale in catalogue.LOCALES:
                with self.subTest(question=qid, locale=locale):
                    card = self.card(qid, locale)
                    self.assertEqual(card['question_id'], qid)
                    self.assertTrue(card['title'])
                    self.assertEqual(set(card['headline']), {'label', 'value_text', 'value_cents'})
                    self.assertTrue(card['headline']['value_text'])
                    self.assertIn(type(card['headline']['value_cents']), (int, type(None)))
                    self.assertTrue(1 <= len(card['lines']) <= 4, card['lines'])
                    self.assertTrue(all(isinstance(line, str) and line for line in card['lines']))
                    self.assertTrue(2 <= len(card['followups']) <= 3)
                    self.assertTrue(all(f['id'] in catalogue.QUESTIONS and f['text'] for f in card['followups']))
                    if card['chart'] is not None:
                        self.assertIn(card['chart']['kind'], ('bars', 'trend', 'ring', 'progress'))
                        if card['chart']['kind'] == 'progress':
                            self.assertTrue({'current_cents', 'target_cents'} <= set(card['chart']['data']))
                        else:
                            self.assertIsInstance(card['chart']['data'], list)
                            self.assertTrue(all({'label', 'value_cents'} <= set(row) for row in card['chart']['data']))
                    for item in card['evidence']:
                        self.assertEqual(set(item), {'label', 'query'})
                        self.assertTrue({'start', 'end'} <= set(item['query']))
                    for picker in card['pickers']:
                        self.assertIn(picker['kind'], ('category', 'month', 'percent', 'amount', 'date'))
                        self.assertIn('name', picker)
                        self.assertIn('value', picker)
                    self.assertIsInstance(card['params_used'], dict)
                    self.assertIn('profile_note', card)
                    visible = json.dumps([card['title'], card['headline']['label'], card['headline']['value_text'], card['lines'],
                                          card['caveat'], [e['label'] for e in card['evidence']]], ensure_ascii=False)
                    self.assertNotRegex(visible, DEV_WORDS)
                    if locale == 'en':
                        self.assertNotRegex(visible, r'\d,\d\d €')
                    else:
                        self.assertNotRegex(visible, r'€\d')
                        self.assertNotRegex(visible, r'\d\.\d%')
                        self.assertNotIn('Using what you told me', visible)

    def test_evidence_queries_open_in_the_transactions_endpoint(self):
        for qid in ('money.where', 'room.week', 'spend.leaks', 'me.peers'):
            for item in self.card(qid)['evidence']:
                query = '&'.join('%s=%s' % (k, v) for k, v in item['query'].items())
                data = self.api('GET', '/api/transactions?customer_id=%s&%s' % (CID, query))
                self.assertTrue(data['transactions'], (qid, item))


class BriefAnswerTests(Fixture):
    """The four brief questions and the six starters answer with the tools' own numbers."""

    def tool(self, name, args=None):
        ctx = ToolContext(self.conn, CID, MONTH)
        return dispatch(self.conn, CID, ctx, name, args or {})

    def test_where_did_my_money_go(self):
        overview = self.tool('get_overview', {'month': MONTH})
        for locale in catalogue.LOCALES:
            card = self.card('money.where', locale)
            self.assertEqual(card['headline']['value_cents'], overview['consumption_cents'])
            self.assertEqual(card['headline']['value_text'], catalogue.money(overview['consumption_cents'], locale))
            self.assertEqual(card['chart']['kind'], 'bars')
            self.assertEqual(card['chart']['data'][0]['value_cents'], overview['top_categories'][0]['total_cents'])
        self.assertIn('Housing', ' '.join(self.card('money.where')['lines']))
        self.assertIn('Asuminen', ' '.join(self.card('money.where', 'fi')['lines']))

    def test_what_kind_of_spender(self):
        from scoach.spender import ARCHETYPE_LABELS
        profile = self.tool('spender_profile')
        for locale in catalogue.LOCALES:
            card = self.card('spend.spender', locale)
            self.assertEqual(card['headline']['value_text'], ARCHETYPE_LABELS[profile['archetype']][locale])
            self.assertTrue(card['caveat'])
        self.assertTrue(any(line.startswith('Strength:') for line in self.card('spend.spender')['lines']))
        self.assertTrue(any(line.startswith('Vahvuus:') for line in self.card('spend.spender', 'fi')['lines']))

    def test_safely_spend_this_week_is_until_payday(self):
        plan = catalogue._plan(self.conn, CID, ToolContext(self.conn, CID, MONTH).reference_date)
        for locale in catalogue.LOCALES:
            card = self.card('room.week', locale)
            self.assertEqual(card['headline']['value_cents'], plan['per_day_cents'])
            self.assertIn(catalogue.date_label(plan['next_payday'], locale), card['headline']['label'])
            self.assertIn(catalogue.money(plan['per_day_cents'] * min(7, plan['days_to_payday']), locale), card['lines'][0])
            self.assertTrue(card['caveat'])
        self.assertNotIn('7 days, through', card_text(self.card('room.week')))

    def test_how_could_i_save_more_answers_with_a_number(self):
        card = self.card('room.save_more')
        self.assertEqual(card['params_used']['category'], 'Restaurants')
        self.assertEqual(card['params_used']['percent'], 20)
        # Restaurants €190.00 a month over 6 months: 20 % frees €38.00 a month, €456.00 a year.
        self.assertEqual(card['headline']['value_cents'], 3_800)
        self.assertIn('€456.00', card['lines'][0])
        fi = self.card('room.save_more', 'fi', {'category': 'Lifestyle', 'percent': 10})
        self.assertEqual(fi['headline']['value_text'], '6,50 €')
        self.assertIn('Ostokset', fi['lines'][0])

    def test_starters_answer_in_every_language(self):
        for qid in catalogue.STARTERS:
            for locale in catalogue.LOCALES:
                card = self.card(qid, locale)
                self.assertNotEqual(card['headline']['value_text'], '—', (qid, locale))
                self.assertTrue(card['evidence'], (qid, locale))

    def test_pickers_change_the_answer(self):
        september = self.card('money.category', params={'category': 'Groceries'})
        self.assertEqual(september['headline']['value_cents'], 20_000)
        self.assertEqual(september['params_used'], {'category': 'Groceries', 'month': MONTH})
        cut = self.card('room.cut', params={'category': 'Restaurants', 'percent': 30})
        self.assertEqual(cut['headline']['value_cents'], 5_700)
        self.assertEqual(cut['actions'][0]['kind'], 'save_scenario')
        goal = self.card('goals.new', params={'amount_cents': 300_000, 'target_date': '2027-06-30', 'name': 'Italy'})
        self.assertEqual(goal['headline']['value_cents'], 33_334)
        self.assertEqual(goal['actions'][0], {'kind': 'create_goal', 'label': 'Review goal',
                                               'params': {'name': 'Italy', 'target_cents': 300_000, 'target_date': '2027-06-30'}})
        empty = self.card('goals.new')
        self.assertEqual(empty['headline']['value_text'], '—')
        self.assertEqual([p['kind'] for p in empty['pickers']], ['amount', 'date'])

    def test_invalid_params_are_rejected(self):
        for qid, params in (('money.category', {'category': 'Invented'}), ('room.cut', {'percent': 500}),
                            ('money.where', {'month': '2019-01'}), ('money.where', {'colour': 'red'}),
                            ('goals.new', {'amount_cents': -5, 'target_date': '2027-01-01'})):
            with self.subTest(question=qid, params=params):
                with self.assertRaises(ValueError):
                    self.card(qid, params=params)
        with self.assertRaises(ValueError):
            self.card('nope')


class PersonalizationTests(Fixture):
    def test_no_profile_means_no_profile_note(self):
        for qid in ('room.week', 'room.save_more', 'goals.buffer'):
            card = self.card(qid)
            self.assertIsNone(card['profile_note'])
            self.assertFalse(any('told me' in line for line in card['lines']))

    def test_saving_target_changes_the_safe_to_spend_card(self):
        before = self.card('room.week')
        self.save('saving_rate_target_pct', 20)
        after = self.card('room.week')
        self.assertLessEqual(after['headline']['value_cents'], before['headline']['value_cents'])
        self.assertEqual(after['profile_note'], 'Using what you told me: saving target 20% of income.')
        self.assertNotIn(after['profile_note'], after['lines'])
        self.assertLessEqual(len(after['lines']), 4)
        self.assertIn('saving target €600.00', ' '.join(after['lines']))
        self.assertEqual(self.card('room.week', 'fi')['profile_note'], 'Käytin kertomaasi: säästötavoite 20 % tuloista.')
        self.assertTrue(self.card('room.week', 'sv')['profile_note'].startswith('Jag utgick från det du berättat'))

    def test_protected_category_is_never_suggested_for_cuts(self):
        self.save('protected_categories', ['Restaurants'])
        words = re.compile(r'restaurant|eating out|ravintol|restaurang', re.I)
        for locale in catalogue.LOCALES:
            card = self.card('room.save_more', locale)
            self.assertNotEqual(card['params_used']['category'], 'Restaurants')
            for line in card['lines'][:-1]:
                self.assertNotRegex(line, words, locale)
            self.assertRegex(card['profile_note'], words)
            self.assertNotRegex(json.dumps([card['chart'], card['pickers'], card['headline']], ensure_ascii=False), words)
            cut = self.card('room.cut', locale, {'category': 'Restaurants'})
            self.assertEqual(cut['actions'], [])
            self.assertIsNone(cut['headline']['value_cents'])
            self.assertNotIn('Restaurants', [o['value'] for o in cut['pickers'][0]['options']])
        default_cut = self.card('room.cut')
        self.assertNotEqual(default_cut['params_used']['category'], 'Restaurants')

    def test_what_if_tool_refuses_a_protected_category(self):
        self.save('protected_categories', ['Restaurants'])
        ctx = ToolContext(self.conn, CID, MONTH)
        with self.assertRaisesRegex(ValueError, 'asked not to suggest cutting'):
            dispatch(self.conn, CID, ctx, 'what_if_reduce', {'category': 'Restaurants', 'percent': 20})
        dispatch(self.conn, CID, ctx, 'what_if_reduce', {'category': 'Lifestyle', 'percent': 20})

    def test_steady_mode_is_gentler_and_reserve_first(self):
        normal = self.card('room.week')
        self.save('life_stage', 'between_jobs')
        self.save('life_event', {'type': 'job_loss', 'since': '2026-09-01'})
        steady = self.card('room.week')
        self.assertTrue(steady['lines'][0].startswith('Your safety cushion comes first'))
        self.assertLessEqual(steady['headline']['value_cents'], normal['headline']['value_cents'])
        self.assertIn('steady mode (lost your job)', steady['profile_note'])
        self.assertIn('between jobs', steady['profile_note'])
        self.assertTrue(self.card('room.week', 'fi')['lines'][0].startswith('Turvatyynysi on etusijalla'))
        save_more = self.card('room.save_more')
        self.assertEqual(save_more['params_used']['percent'], 10)
        self.assertTrue(save_more['lines'][0].startswith('Your safety cushion comes first'))
        spender = self.card('spend.spender')
        self.assertFalse(any(line.startswith('Worth a look') for line in spender['lines']))
        buffer = self.card('goals.buffer')
        self.assertEqual(buffer['params_used']['months'], 6)
        self.assertEqual(self.card('me.life_change')['headline']['value_text'], 'Steady mode')

    def test_steady_mode_cards_never_offer_saving(self):
        # V5 fix (lane CO): no saving follow-up, no "could go to savings" line or bar part, one vocabulary.
        saving = {'room.save_now', 'room.save_more', 'room.cut', 'goals.new'}
        self.assertIn('room.save_now', [item['id'] for item in self.card('room.week')['followups']])
        self.save('life_event', {'type': 'job_loss', 'since': '2026-09-01'})
        for qid in ('room.week', 'room.payday', 'money.where', 'spend.spender', 'goals.progress'):
            card = self.card(qid)
            ids = [item['id'] for item in card['followups']]
            self.assertFalse(saving & set(ids), (qid, ids))
            self.assertEqual(len(ids), len(set(ids)))
            self.assertNotIn(qid, ids)
        week = self.card('room.week')
        self.assertFalse(any('savings' in line for line in week['lines']))
        self.assertFalse(any(row['label'] == 'Could be saved' for row in (week['chart'] or {}).get('data', [])))
        self.assertEqual(week['profile_note'].count('Using what you told me'), 1)
        self.assertIn('rauhallinen tahti', self.card('room.week', 'fi')['profile_note'])
        self.assertIn('lugnt tempo', self.card('room.week', 'sv')['profile_note'])

    def test_what_do_you_know_lists_the_profile(self):
        self.assertEqual(self.card('me.known')['headline']['value_text'], '0')
        self.save('protected_categories', ['Restaurants'])
        self.save('upcoming', {'what': 'Wedding', 'month': '2027-06'})
        card = self.card('me.known', 'sv')
        text = ' '.join(card['lines'])
        self.assertIn('Restaurang', text)
        self.assertIn('Wedding (juni 2027)', text)

    def test_profile_is_customer_scoped(self):
        self.save('saving_rate_target_pct', 20)
        self.assertIsNone(self.card('room.week', customer=OTHER)['profile_note'])


TRICKY = [
    ('en', 'Where did my money go this month?', 'money.where'),
    ('en', 'What can I safely spend this week?', 'room.week'),
    ('en', 'What can I spend?', 'room.week'),
    ('en', 'I want to save 2000 euros for a trip to Japan by next summer', 'goals.new'),
    ('en', 'What if I spent 10% less on shopping?', 'room.cut'),
    ('en', 'Show me my transactions from last week', 'spend.recent'),
    ('sv', 'Hur mycket spenderade jag på mat?', 'money.category'),
    ('en', 'Am I careful with money?', 'spend.spender'),
    ('en', 'What is a tax card?', 'extra.taxcard'),
    ('en', 'When do I get my tax refund?', 'extra.tax'),
    ('en', 'How do I compare with others my age?', 'me.peers'),
    ('fi', 'Riittävätkö rahani palkkapäivään asti?', 'room.payday'),
    ('fi', 'Mihin rahani menivät?', 'money.where'),
    ('fi', 'Millainen kuluttaja olen?', 'spend.spender'),
    ('sv', 'Vart tog mina pengar vägen?', 'money.where'),
    ('en', 'How much did I spend on restaurants in August?', 'money.category'),
    ('fi', 'Paljonko voin käyttää tällä viikolla?', 'room.week'),
    ('en', 'I want to save €3,000 for Italy by next June.', 'goals.new'),
    ('en', 'How could I save more?', 'room.save_more'),
    ('en', 'Explain the three baskets', 'extra.baskets'),
    ('en', 'What bills are coming up?', 'bills.upcoming'),
    ('en', 'What is my biggest money leak?', 'spend.leaks'),
    ('sv', 'Hur mycket kan jag spara?', 'room.save_now'),
    ('en', 'How much VAT did I pay on groceries?', 'extra.vat'),
]


class MatchTests(Fixture):
    def match(self, message, locale='en'):
        return catalogue.match_message(message, locale, today='2026-09-26', observed=('2026-01-03', '2026-09-26'))

    def test_tricky_messages_get_sensible_suggestions(self):
        for locale, message, expected in TRICKY:
            with self.subTest(message=message):
                result = self.match(message, locale)
                self.assertEqual(result['suggestions'][0]['id'], expected, result)
                self.assertLessEqual(len(result['suggestions']), 3)
                self.assertTrue(all(s['text'] == catalogue.QUESTIONS[s['id']].text[locale] for s in result['suggestions']))

    def test_substring_traps_do_not_route_to_goals(self):
        for message in ('Is my phone bill too high?', 'Am I careful with money?', 'Vad kostar mitt mobilabonnemang?'):
            ids = [s['id'] for s in self.match(message)['suggestions']]
            self.assertNotIn('goals.new', ids, message)

    def test_slots_are_prefilled_from_the_message(self):
        japan = self.match('I want to save 2000 euros for a trip to Japan by next summer')['suggestions'][0]
        self.assertEqual(japan['params'], {'amount_cents': 200_000, 'target_date': '2027-06-30', 'name': 'Trip to Japan'})
        shopping = self.match('What if I spent 10% less on shopping?')['suggestions'][0]
        self.assertEqual(shopping['params'], {'category': 'Lifestyle', 'percent': 10})
        august = self.match('How much did I spend on restaurants in August?')['suggestions'][0]
        self.assertEqual(august['params'], {'category': 'Restaurants', 'month': '2026-08'})

    def test_life_events_and_distress_are_supported_in_three_languages(self):
        cases = [('en', 'I lost my job last week', 'life_event'), ('fi', 'Menetin työpaikkani', 'life_event'),
                 ('sv', 'Jag har förlorat jobbet', 'life_event'), ('en', "We're having a baby!", 'life_event'),
                 ('en', 'We are getting a divorce', 'life_event'), ('en', "I'm so stressed about money", 'distress'),
                 ('fi', 'Olen huolissani rahoista', 'distress'), ('sv', 'Jag är orolig för pengarna', 'distress')]
        for locale, message, hint in cases:
            with self.subTest(message=message):
                data = self.api('POST', '/api/catalogue/match?customer_id=%s&month=%s' % (CID, MONTH), {'message': message, 'locale': locale})
                self.assertTrue(data['supportive'])
                self.assertEqual(data['intent_hint'], hint)
                self.assertTrue(1 <= len(data['suggestions']) <= 3)
        job = self.match('I lost my job')
        self.assertEqual([s['id'] for s in job['suggestions']], ['room.week', 'goals.buffer', 'me.life_change'])
        self.assertTrue(money_profile.get_profile(self.conn, CID)['empty'])

    def test_smalltalk_and_unknown_never_answer(self):
        for message in ('ok thanks', 'kiitos', 'tack så mycket', 'blorp zzz'):
            result = self.match(message)
            self.assertFalse(result['confident'])
            self.assertEqual(len(result['suggestions']), 3)
            self.assertIsNone(result['supportive'])

    def test_extract_amount_and_date(self):
        cases = [
            ('save €2,000 for a trip by June', 'en', 200_000, '2027-06-30'),
            ('I want to save 3000 euros by December 2026', 'en', 300_000, '2026-12-31'),
            ('säästää 5 000 euroa kesäkuuhun mennessä', 'fi', 500_000, '2027-06-30'),
            ('spara 1500 € till nästa sommar', 'sv', 150_000, '2027-06-30'),
            ('save 2k in 6 months', 'en', 200_000, '2027-03-31'),
            ('a goal for next year of 800€', 'en', 80_000, '2027-12-31'),
            ('I want a holiday', 'en', None, None),
        ]
        for message, locale, cents, target in cases:
            with self.subTest(message=message):
                result = catalogue.extract_amount_date(message, locale, today='2026-09-30')
                self.assertEqual((result['amount_cents'], result['target_date']), (cents, target))

    def test_match_validates_input(self):
        self.api('POST', '/api/catalogue/match?customer_id=%s' % CID, {'message': ''}, status=400)
        self.api('POST', '/api/catalogue/match?customer_id=%s' % CID, {'message': 'x', 'locale': 'de'}, status=400)
        self.api('POST', '/api/catalogue/match?customer_id=%s' % CID, {'message': 'x', 'other': 1}, status=400)


class RouteTests(Fixture):
    def test_answer_route_takes_customer_and_month_in_the_query(self):
        data = self.api('POST', '/api/catalogue/answer?customer_id=%s&month=2026-08' % CID, {'question_id': 'money.where', 'locale': 'fi'})
        self.assertEqual(data['card']['params_used'], {'month': '2026-08'})
        self.assertIn('elokuussa 2026', data['card']['title'])
        data = self.api('POST', '/api/catalogue/answer?customer_id=%s&month=2026-09' % CID,
                        {'question_id': 'money.category', 'params': {'category': 'Groceries', 'month': '2026-07'}})
        self.assertEqual(data['card']['params_used'], {'category': 'Groceries', 'month': '2026-07'})
        self.assertEqual(data['card']['headline']['value_cents'], 20_000)

    def test_answer_route_validation(self):
        base = '/api/catalogue/answer?customer_id=%s&month=%s' % (CID, MONTH)
        self.api('POST', base, {'question_id': 'nope'}, status=400)
        self.api('POST', base, {}, status=400)
        self.api('POST', base, {'question_id': 'money.where', 'params': 'x'}, status=400)
        self.api('POST', base, {'question_id': 'money.where', 'locale': 'de'}, status=400)
        self.api('POST', '/api/catalogue/answer?customer_id=NOPE', {'question_id': 'money.where'}, status=404)
        self.api('GET', base, status=405)

    def test_answers_never_write(self):
        for qid in catalogue.QUESTIONS:
            self.api('POST', '/api/catalogue/answer?customer_id=%s&month=%s' % (CID, MONTH), {'question_id': qid})
        conn = connect(self.db)
        try:
            for table in ('goals', 'scenarios', 'profile_entries', 'audit_events'):
                self.assertEqual(conn.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0, table)
        finally:
            conn.close()


class AgentFallbackTests(Fixture):
    def agent(self, message, transport=None, locale='en'):
        app = Application(self.db, agent_transport=transport)
        return self.api('POST', '/api/agent', {'customer_id': CID, 'month': MONTH, 'message': message, 'locale': locale}, app=app)

    def test_offline_exact_question_returns_its_card(self):
        data = self.agent('What can I safely spend this week?')
        self.assertEqual((data['source'], data['fallback_reason']), ('catalogue', 'not_configured'))
        self.assertEqual(data['card']['question_id'], 'room.week')
        self.assertEqual(data['card']['headline']['value_cents'], self.card('room.week')['headline']['value_cents'])
        self.assertNotIn('legacy', data)

    def test_offline_ambiguous_or_parametrised_question_only_suggests(self):
        for message in ('How much did I spend on restaurants in August?', 'Is my phone bill too high?',
                        'I want to save €3,000 for Italy by next June.', 'hmm'):
            with self.subTest(message=message):
                data = self.agent(message)
                self.assertEqual(data['source'], 'catalogue')
                self.assertIsNone(data['card'])
                self.assertTrue(data['suggestions'])
        goal = self.agent('I want to save €3,000 for Italy by next June.')
        self.assertEqual(goal['intent_hint'], 'goal')
        self.assertEqual(goal['suggestions'][0]['params']['amount_cents'], 300_000)

    def test_offline_life_event_is_supportive_in_finnish(self):
        data = self.agent('Menetin työni', locale='fi')
        self.assertTrue(data['supportive'].startswith('Ikävä kuulla'))
        self.assertIsNone(data['card'])
        self.assertEqual(data['suggestions'][0]['text'], catalogue.QUESTIONS['room.week'].text['fi'])

    def test_model_failure_falls_back_to_the_catalogue(self):
        data = self.agent('Where did my money go this month?', ScriptedTransport(RuntimeError('down')))
        self.assertEqual((data['source'], data['fallback_reason']), ('catalogue', 'unavailable'))
        self.assertEqual(data['card']['question_id'], 'money.where')

    def test_ai_answers_carry_the_same_cards(self):
        plan = catalogue._plan(self.conn, CID, ToolContext(self.conn, CID, MONTH).reference_date)
        lead = 'You can spend about €%s a day until payday. It is an estimate.' % format(plan['per_day_cents'] / 100, '.2f')
        transport = ScriptedTransport(call('safe_to_spend'), call('spender_profile'), answer(lead))
        data = self.agent('What can I spend and what kind of spender am I?', transport)
        self.assertEqual(data['source'], 'agent')
        self.assertEqual([c['question_id'] for c in data['cards']], ['room.week', 'spend.spender'])
        self.assertEqual(data['cards'][0]['headline'], {**self.card('room.week')['headline'], 'value_display': data['cards'][0]['headline']['value_display']})
        self.assertTrue(all('args' not in step for step in data['steps']))

    def test_tool_mapping(self):
        self.assertEqual(catalogue.question_for_tool('spending_total', {'start': '2026-09-01', 'end': '2026-09-30', 'category': 'Groceries'}),
                         ('money.category', {'category': 'Groceries', 'month': '2026-09'}))
        self.assertIsNone(catalogue.question_for_tool('spending_total', {'start': '2026-09-01', 'end': '2026-10-15', 'category': 'Groceries'}))
        self.assertIsNone(catalogue.question_for_tool('calculate', {'expression': '1+1'}))
        self.assertEqual(catalogue.question_for_tool('what_if_reduce', {'category': 'Restaurants', 'percent': 20})[0], 'room.cut')
        cards = catalogue.cards_for_tool_calls(self.conn, CID, MONTH, 'sv', [('calculate', {}), ('get_overview', {}), ('get_overview', {'month': '2026-08'}),
                                                                            ('recurring_payments', {})])
        self.assertEqual([c['question_id'] for c in cards], ['money.where', 'bills.recurring'])


@unittest.skipUnless(DEMO.is_file(), 'demo database not available (set SCOACH_DEMO_DB)')
class DemoBriefTests(unittest.TestCase):
    """Alex (CUST00001), September 2026: the brief's four questions in EN/FI/SV via the catalogue."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'demo.sqlite3'
        shutil.copyfile(DEMO, self.db)
        self.conn = connect(self.db)
        self.addCleanup(self.conn.close)

    def test_brief_questions_and_starters(self):
        ctx = ToolContext(self.conn, 'CUST00001', MONTH)
        overview = dispatch(self.conn, 'CUST00001', ctx, 'get_overview', {'month': MONTH})
        plan = catalogue._plan(self.conn, 'CUST00001', ctx.reference_date)
        for locale in catalogue.LOCALES:
            where = catalogue.answer(self.conn, 'CUST00001', MONTH, 'money.where', {}, locale)
            self.assertEqual(where['headline']['value_cents'], overview['consumption_cents'])
            week = catalogue.answer(self.conn, 'CUST00001', MONTH, 'room.week', {}, locale)
            self.assertEqual(week['headline']['value_cents'], plan['per_day_cents'])
            spender = catalogue.answer(self.conn, 'CUST00001', MONTH, 'spend.spender', {}, locale)
            self.assertNotEqual(spender['headline']['value_text'], '—')
            save = catalogue.answer(self.conn, 'CUST00001', MONTH, 'room.save_more', {}, locale)
            self.assertGreater(save['headline']['value_cents'], 0)
            for qid in catalogue.STARTERS:
                self.assertNotEqual(catalogue.answer(self.conn, 'CUST00001', MONTH, qid, {}, locale)['headline']['value_text'], '—')
        self.assertEqual(catalogue.answer(self.conn, 'CUST00001', MONTH, 'money.where', {}, 'fi')['headline']['value_text'], '1 878,66 €')


if __name__ == '__main__':
    unittest.main()
