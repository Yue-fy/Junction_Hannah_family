"""V4 lane L: Finnish and Swedish text that customers see (server strings and web copy)."""
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from scoach import labels
from scoach import money_profile as mp
from scoach.query_scope import OPTION_COPY, clarify
from scoach.spender import ARCHETYPE_LABELS
from scoach.year_review import MCC_LABELS, MCC_LABELS_FI, MCC_LABELS_SV, mcc_label
from tests.core_helper import demo_connection

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'var' / 'scoach.sqlite3'
CID = 'CUST00001'
# Common English words that must not appear in a Finnish or Swedish sentence.
ENGLISH = re.compile(r"\b(?:the|and|your|you|is|of|salary|payments|months|right|every|about|investments|housing|rent|mortgage)\b",
                     re.IGNORECASE)
# Developer words that must not reach customers in any language (V4 spec, global rules).
DEVELOPER = re.compile(r'MCC|kvartiili|kvartil|quartile|skenaario|scenari|deterministi|demon vararaha|demobuffert|demopuskuri',
                       re.IGNORECASE)


def node(body):
    script = textwrap.dedent(body)
    result = subprocess.run(['node', '--input-type=module', '--eval', script], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    return result


class LabelsTests(unittest.TestCase):
    def test_money_and_percent_formats_follow_the_language(self):
        self.assertEqual(labels.euros(236488, 'en'), '€2,365')
        self.assertEqual(labels.euros(236488, 'fi'), '2 365 €')
        self.assertEqual(labels.euros(113827, 'sv', decimals=True), '1 138,27 €')
        self.assertEqual(labels.euros(113827, 'en', decimals=True), '€1,138.27')
        self.assertEqual(labels.percent(9.6, 'fi'), '9,6 %')
        self.assertEqual(labels.percent(9.6, 'en'), '9.6%')
        self.assertEqual(labels.percent(13.5, 'sv'), '13,5 %')

    def test_ordinals_and_dates(self):
        self.assertEqual([labels.day_ordinal(d, 'en') for d in (1, 2, 3, 5, 11, 22)], ['1st', '2nd', '3rd', '5th', '11th', '22nd'])
        self.assertEqual(labels.day_ordinal(5, 'fi'), '5.')
        self.assertEqual([labels.day_ordinal(d, 'sv') for d in (1, 2, 3, 11, 12, 21, 22, 25)],
                         ['1:a', '2:a', '3:e', '11:e', '12:e', '21:a', '22:a', '25:e'])
        self.assertEqual(labels.short_date('2026-08-05', 'fi'), '5.8.2026')
        self.assertEqual(labels.short_date('2026-08-05', 'en'), '2026-08-05')

    def test_category_labels_match_the_web_app(self):
        source = (ROOT / 'web' / 'experience.js').read_text(encoding='utf-8')
        for name, (en, fi, sv) in labels.CATEGORY_LABELS.items():
            match = re.search(r"'category\.%s':\['([^']*)','([^']*)','([^']*)'\]" % re.escape(name), source)
            if match:
                self.assertEqual(match.groups(), (en, fi, sv), name)
        self.assertEqual(labels.category_label('Groceries', 'fi'), 'Ruokaostokset')
        self.assertEqual(labels.category_label('Unknown thing', 'sv'), 'Unknown thing')


class ThingsINoticedTests(unittest.TestCase):
    def setUp(self):
        self.conn = demo_connection()

    def test_questions_are_finnish_and_swedish(self):
        for locale in ('fi', 'sv'):
            suggestions = mp.profile_suggestions(self.conn, CID, '2026-09-30', locale)
            self.assertTrue(suggestions)
            for item in suggestions:
                texts = [item['question'], item['evidence']['label']]
                texts += [alt['label'] for alt in item['alternatives']]
                if isinstance(item['save_as']['value'], str):
                    texts.append(item['save_as']['value'])
                for text in texts:
                    self.assertIsNone(ENGLISH.search(text), (locale, text))
                    self.assertNotIn('€2', text)  # FI/SV write "2 365 €", never "€2,365"
                self.assertTrue(item['question'].endswith('?'), item['question'])
        fi = {s['kind']: s for s in mp.profile_suggestions(self.conn, CID, '2026-09-30', 'fi')}
        self.assertIn('2 365 €', fi['salary']['question'])
        self.assertIn('kuun 5. päivän', fi['housing']['question'])

    def test_english_and_ids_are_unchanged(self):
        en = mp.profile_suggestions(self.conn, CID, '2026-09-30')
        fi = mp.profile_suggestions(self.conn, CID, '2026-09-30', 'fi')
        self.assertEqual([s['id'] for s in en], [s['id'] for s in fi])
        self.assertEqual([s['value'] for s in en], [s['value'] for s in fi])
        salary = next(s for s in en if s['kind'] == 'salary')
        self.assertEqual(salary['question'], 'Your salary arrives on different days each month and is about €2,365 after tax. Is that right?')
        self.assertEqual(salary['evidence']['label'], 'Salary payments in the last 6 complete months')

    def test_confirmed_note_is_saved_in_the_customers_language(self):
        housing = next(s for s in mp.profile_suggestions(self.conn, CID, '2026-09-30', 'sv') if s['kind'] == 'housing')
        saved = mp.confirm_suggestion(self.conn, CID, housing['id'], as_of='2026-09-30', locale='sv')
        self.assertEqual(saved['entry']['value'], 'Jag betalar ungefär 528 € i hyra per månad.')


@unittest.skipUnless(DEMO.is_file(), 'demo database not built')
class LocalizedEndpointTests(unittest.TestCase):
    def setUp(self):
        from scoach.api import Application
        environment = patch.dict('os.environ', {'GEMINI_API_KEY': '', 'DEEPSEEK_API_KEY': '', 'AGENT_PROVIDER': ''})
        environment.start(); self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        db = Path(self.temp.name) / 'demo.sqlite3'
        shutil.copyfile(DEMO, db)
        self.app = Application(db)

    def get(self, target):
        code, result = self.app.handle('GET', target)
        self.assertEqual(code, 200, result)
        return result['data']

    def test_profile_endpoint_takes_a_locale(self):
        data = self.get('/api/profile?customer_id=CUST00001&month=2026-09&locale=fi')
        self.assertTrue(all(s['question'].startswith(('Palkka', 'Maksat', 'Siirsit', 'Tililtäsi', 'Palkkasi'))
                            for s in data['suggestions']), [s['question'] for s in data['suggestions']])
        code, _ = self.app.handle('GET', '/api/profile?customer_id=CUST00001&month=2026-09&locale=de')
        self.assertEqual(code, 400)
        housing = next(s for s in data['suggestions'] if s['kind'] == 'housing')
        code, result = self.app.handle('POST', '/api/profile/suggestions/confirm?customer_id=CUST00001&month=2026-09',
                                       {'suggestion_id': housing['id'], 'locale': 'fi', 'confirmed': True})
        self.assertEqual(code, 200, result)
        self.assertTrue(result['data']['entry']['value'].startswith('Maksan vuokraa'))

    def test_year_cards_name_categories_and_style_in_the_language(self):
        for locale, grocery, style in (('fi', 'Ruokaostokset', 'Harvoin mutta isosti'), ('sv', 'Matinköp', 'Sällan men stort')):
            cards = {c['kind']: c['facts'] for c in self.get('/api/year-review?customer_id=CUST00001&year=2025&locale=' + locale)['story_cards']['cards']}
            self.assertEqual(cards['top_category']['category_label'], grocery)
            self.assertEqual(cards['top_category']['category'], 'Groceries')  # raw name kept for filters
            self.assertEqual(cards['favourite_weekday_or_mcc']['mcc_label'], grocery)
            self.assertEqual(cards['archetype']['archetype_label'], style)

    def test_finnish_and_swedish_chips_get_answers_offline(self):
        for (fi, sv) in OPTION_COPY.values():
            for locale, message in (('fi', fi), ('sv', sv)):
                code, result = self.app.handle('POST', '/api/coach?customer_id=CUST00001&month=2026-09',
                                               {'message': message, 'locale': locale})
                self.assertEqual(code, 200, result)
                data = result['data']
                self.assertNotEqual(data.get('clarification_code'), 'supported_scope', (locale, message, data.get('clarification_question')))
                self.assertNotEqual(data.get('clarification_code'), 'missing_category', (locale, message))


class ServerTablesTests(unittest.TestCase):
    def test_mcc_and_archetype_tables_are_complete(self):
        self.assertEqual(set(MCC_LABELS), set(MCC_LABELS_FI))
        self.assertEqual(set(MCC_LABELS), set(MCC_LABELS_SV))
        self.assertEqual(mcc_label('4121', 'fi'), 'Taksit')
        self.assertEqual(mcc_label('9999', 'sv'), 'Kod 9999')
        self.assertEqual(mcc_label('9999'), 'Code 9999')
        for labels_by_locale in ARCHETYPE_LABELS.values():
            self.assertEqual(set(labels_by_locale), {'en', 'fi', 'sv'})
            self.assertNotEqual(labels_by_locale['fi'], labels_by_locale['en'])

    def test_follow_up_chips_are_localized_and_answerable(self):
        for locale, index in (('fi', 0), ('sv', 1)):
            result = clarify({'interface_locale': locale}, 'x', 'q', 'k', 'f', tuple(OPTION_COPY))
            self.assertEqual(result['clarification_options'], [pair[index] for pair in OPTION_COPY.values()])
        self.assertEqual(clarify({'interface_locale': 'en'}, 'x', 'q', 'k', 'f', ('How much did I spend on groceries?',))['clarification_options'],
                         ['How much did I spend on groceries?'])



@unittest.skipUnless(shutil.which('node'), 'Node is required for the web modules')
class WebCopyTests(unittest.TestCase):
    def run_js(self, body):
        result = node(body)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return result.stdout

    def test_finnish_months_years_rates_and_decimals_read_naturally(self):
        self.run_js(f"""
            import assert from 'node:assert/strict';
            import {{ createI18n, interpolate }} from {json.dumps((ROOT / 'web' / 'i18n.js').as_uri())};
            const fi = createI18n({{storage: null, navigatorLanguages: ['fi']}});
            const sv = createI18n({{storage: null, navigatorLanguages: ['sv']}});
            const en = createI18n({{storage: null, navigatorLanguages: ['en']}});
            assert.equal(fi.t('home.recap.followup', {{period: 'syyskuu 2026'}}), 'Mihin suurin osa menoistani meni syyskuussa 2026?');
            assert.equal(fi.t('v3.cashflow.ask', {{period: '2025'}}), 'Miltä tuloni ja menoni näyttivät vuonna 2025?');
            assert.equal(fi.t('v3.trend.ask', {{month: 'helmikuu 2026'}}), 'Mitä menoilleni tapahtui helmikuussa 2026?');
            assert.equal(sv.t('home.recap.followup', {{period: 'september 2026'}}), 'Vart gick största delen av mina utgifter under september 2026?');
            const vat = {{vat: '73,85 €', spent: '386,06 €', category: 'Viihde', rate: '13.5% and 25.5%'}};
            assert.equal(fi.t('v3.vat.line', vat), 'Viihde: menoistasi 386,06 € noin 73,85 € oli arvonlisäveroa (13,5\\u00a0% ja 25,5\\u00a0%).');
            assert.ok(sv.t('v3.vat.line', vat).includes('(13,5\\u00a0% och 25,5\\u00a0%)'));
            assert.ok(en.t('v3.vat.line', vat).includes('(13.5% and 25.5%)'));
            assert.equal(interpolate('{{x:in}}', {{x: 'tammikuu 2026'}}, 'sv'), 'tammikuu 2026');
            assert.equal(fi.t('v2.home.title'), 'Rahaa sille, mikä on tärkeää.');
        """)

    def test_catalog_keys_match_and_no_developer_words_in_finnish_or_swedish(self):
        out = self.run_js(f"""
            import {{ MESSAGES }} from {json.dumps((ROOT / 'web' / 'i18n.js').as_uri())};
            import {{ PROFILE_MESSAGES }} from {json.dumps((ROOT / 'web' / 'money-profile.js').as_uri())};
            console.log(JSON.stringify({{i18n: MESSAGES, profile: PROFILE_MESSAGES}}));
        """)
        data = json.loads(out)
        for name, catalog in data.items():
            self.assertEqual(set(catalog['fi']), set(catalog['en']), name)
            self.assertEqual(set(catalog['sv']), set(catalog['en']), name)
            for locale in ('fi', 'sv'):
                for key, value in catalog[locale].items():
                    if key.startswith(('coach.debug.', 'persona.', 'app.')) or key in {'error.network', 'error.database', 'feedback.reset', 'v3.goal.deleteIntro', 'coach.otherLanguage'}:
                        continue
                    self.assertIsNone(DEVELOPER.search(value), (name, locale, key, value))
                    self.assertNotIn('%:', value, (locale, key))  # no "9.6 %:ssa"
        self.assertNotIn('Tilaa ', data['i18n']['fi']['v2.home.title'])
        self.assertEqual(data['profile']['fi']['noticed.keep'], 'Tallenna')

    def test_server_assumptions_are_translated_by_sentence_not_position(self):
        self.run_js(f"""
            import assert from 'node:assert/strict';
            import {{ localizeServerText }} from {json.dumps((ROOT / 'web' / 'i18n.js').as_uri())};
            const lines = ['Expected income is excluded until it arrives',
              'Next payday uses the usual salary day (22), moved to the month end in shorter months',
              '12.5% saving target of your last salary (2026-09, €2,364.88)',
              'Safe to save keeps back a busy (upper-quartile) month of everyday spending, scaled to the days until payday'];
            const fi = lines.map(line => localizeServerText(line, 'fi'));
            assert.ok(fi[1].includes('kuun 22. päivä'));
            assert.equal(fi[2], 'Säästötavoite: 12,5 % viimeisestä palkastasi.');
            for (const text of [...fi, ...lines.map(line => localizeServerText(line, 'sv'))]) {{
              assert.doesNotMatch(text, /\\b(the|and|your|quartile)\\b/i, text);
            }}
            assert.equal(localizeServerText(lines[0], 'en'), lines[0]);
            assert.equal(localizeServerText('Something new', 'fi'), 'Something new');
        """)

    @unittest.skip('V4 spending_plan sends localized assumption_texts; old English sentences were removed')
    def test_server_assumption_sentences_still_exist_in_forecast(self):
        source = (ROOT / 'scoach' / 'forecast.py').read_text(encoding='utf-8')
        for sentence in ('Expected income is excluded until it arrives', 'No saving target set, so nothing is set aside for saving'):
            self.assertIn(sentence, source)


class TaxAndVatTextTests(unittest.TestCase):
    """The "My taxes" card and the VAT tile come from server text (tax.py); FI/SV rebuild it."""

    def setUp(self):
        self.conn = demo_connection()

    def overview(self, tax):
        from scoach.tax import tax_overview
        return tax_overview(self.conn, CID, '2026-09-30', tax)['overview']

    def test_tax_card_text_is_finnish_and_swedish_with_local_numbers(self):
        from scoach.tax_text import localize_tax_overview
        tax = {'tax_year': 2026, 'base_rate_bp': 2400, 'gross_monthly_cents': 340000,
               'decision_result': 'back_tax', 'decision_amount_cents': 123456}
        english = self.overview(tax)
        self.assertIs(localize_tax_overview(english, 'en'), english)
        for locale in ('fi', 'sv'):
            local = localize_tax_overview(english, locale)
            texts = [local['footer'], local['withholding']['flow']['text'], local['cycle']['stage_label'],
                     *local['cycle']['tasks'], *local['withholding']['notes'], local['vat_card']['sentence']]
            for text in texts:
                self.assertIsNone(re.search(r'\b(?:the|and|your|Gross|withheld|MyTax)\b', text), (locale, text))
            self.assertIn('30 600,00 €', local['withholding']['flow']['text'])
            self.assertIn('1 234,56 €', local['cycle']['tasks'][0])
            self.assertEqual(local['withholding']['flow']['gross_cents'], english['withholding']['flow']['gross_cents'])
        self.assertIn('OmaVero', localize_tax_overview(english, 'fi')['footer'])
        self.assertIn('MinSkatt', localize_tax_overview(english, 'sv')['footer'])

    def test_vat_rates_use_decimal_comma_and_local_and(self):
        from scoach.tax_text import rate_text
        self.assertEqual(rate_text('13.5% and 25.5%', 'fi'), '13,5 % ja 25,5 %')
        self.assertEqual(rate_text('13.5% and 25.5%', 'sv'), '13,5 % och 25,5 %')
        self.assertEqual(rate_text('13.5% and 25.5%', 'en'), '13.5% and 25.5%')
        self.assertEqual(rate_text('10%', 'fi'), '10 %')

    @unittest.skipUnless(DEMO.is_file(), 'demo database not built')
    def test_tax_and_vat_endpoints_take_a_locale(self):
        from scoach.api import Application
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db = Path(temp.name) / 'demo.sqlite3'; shutil.copyfile(DEMO, db)
        app = Application(db)
        code, result = app.handle('GET', '/api/vat/card?customer_id=CUST00001&month=2026-09&locale=fi')
        self.assertEqual(code, 200, result)
        self.assertNotIn(' and ', result['data']['rate_label'])
        self.assertIn(',', result['data']['rate_label'])
        code, result = app.handle('GET', '/api/tax?customer_id=CUST00001&month=2026-09&locale=sv')
        self.assertEqual(code, 200, result)
        self.assertIn('MinSkatt', result['data']['footer'])
        self.assertEqual(result['data']['cycle']['label'], result['data']['cycle']['stage_label'])
