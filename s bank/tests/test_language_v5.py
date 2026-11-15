"""V5 language pass (lane LG): plurals after 1, one name per buffer concept, one category name,
axis number formats and the reviewed FI/SV wording (docs/V5_FIX_SPEC.md, critique qa-lang.md)."""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
sys.path.insert(0, str(ROOT))

from scoach import catalogue, forecast, labels  # noqa: E402


def run_node(test, body):
    """Import web modules (relative imports resolved) and run body with assert available."""
    if not shutil.which('node'):
        test.skipTest('Node is not installed')
    sources = {path.name: path.read_text() for path in WEB.glob('*.js')}
    script = 'const sources=' + json.dumps(sources) + r''';
import assert from 'node:assert/strict';
const dataURL=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
const resolved=new Map();
const load=file=>{if(!resolved.has(file))resolved.set(file,dataURL(sources[file].replace(/from ['"]\.\/([^'"]+)['"]/g,(_,name)=>'from "'+load(name)+'"')));return resolved.get(file);};
''' + body
    result = subprocess.run(['node', '--input-type=module'], input=script, capture_output=True, text=True, timeout=120)
    test.assertEqual(result.returncode, 0, result.stderr or result.stdout)
    return result.stdout


# Words that may not name anything in FI/SV except the two buffer concepts (spec: buffer vocabulary).
OLD_BUFFER_WORDS = re.compile(r'Puskurirahasto|Hätärahast|\bpuskuri(?!a)|Puskuri\b|Puskurisi|Vararahasi|Varovainen tila|Vakaa tila|'
                              r'Säkerhetsbuffert|säkerhetsbuffert|Överraskningsbuffert|överraskningsbuffert|Försiktigt läge|Stabilt läge|'
                              r'nödbuffert|\bBuffertmål')


class PluralTests(unittest.TestCase):
    def test_i18n_plural_choice(self):
        run_node(self, r'''
const i18n = await import(load('i18n.js'));
const fi = i18n.createI18n({storage: null, navigatorLanguages: ['fi']});
const sv = i18n.createI18n({storage: null, navigatorLanguages: ['sv']});
assert.equal(fi.t('transactions.summary', {label: 'Asuminen', count: 1}), 'Asuminen · 1 tapahtuma · Toteutunut');
assert.equal(fi.t('transactions.summary', {label: 'Asuminen', count: 3}), 'Asuminen · 3 tapahtumaa · Toteutunut');
assert.equal(sv.t('transactions.summary', {label: 'Boende', count: 1}), 'Boende · 1 transaktion · Utfall');
assert.equal(sv.t('transactions.summary', {label: 'Boende', count: 2}), 'Boende · 2 transaktioner · Utfall');
assert.equal(fi.t('chart.purchases', {count: 1}), '1 osto');
assert.equal(sv.t('v3.safe.perDay', {amount: '5 €', date: '1.10.', days: 1}).endsWith('(1 dag).'), true);
assert.equal(i18n.choosePlural('{n|one|other}', {n: '1'}), 'one');
assert.equal(i18n.choosePlural('{n|one|other}', {n: 1.5}), 'other');
const ex = await import(load('experience.js'));
assert.equal(ex.ux('fi', 'spending.rows', {count: 1}), 'Näytä 1 tapahtuma');
assert.equal(ex.ux('sv', 'spending.rows', {count: 1}), 'Visa 1 transaktion');
assert.equal(ex.ux('sv', 'spending.rows', {count: 4}), 'Visa 4 transaktioner');
const home = await import(load('home-v4.js'));
assert.equal(home.hm('sv', 'draft.preview', {amount: '50 €', months: 1}), 'Ungefär 50 € i månaden i 1 månad.');
''')


class VocabularyTests(unittest.TestCase):
    def test_web_catalogues_use_one_name_per_buffer(self):
        out = run_node(self, r'''
const i18n = await import(load('i18n.js'));
const home = await import(load('home-v4.js'));
const lines = [];
for (const lang of ['fi', 'sv']) {
  for (const [k, v] of Object.entries(i18n.MESSAGES[lang])) lines.push(lang + ' ' + k + ' ' + v);
  for (const [k, v] of Object.entries(home.HOME_MESSAGES[lang])) lines.push(lang + ' home.' + k + ' ' + v);
}
console.log(JSON.stringify(lines));
''')
        bad = [line for line in json.loads(out) if OLD_BUFFER_WORDS.search(line)]
        self.assertEqual(bad, [])
        catalog = json.loads(run_node(self, r'''
const i18n = await import(load('i18n.js'));
console.log(JSON.stringify({fi: i18n.MESSAGES.fi['v5.fc.cushionLabel'], sv: i18n.MESSAGES.sv['v5.fc.cushionLabel'],
  fiTax: i18n.MESSAGES.fi['taxPlan.reserve'], svTax: i18n.MESSAGES.sv['taxPlan.reserve']}));
'''))
        self.assertEqual(catalog, {'fi': 'Turvatyyny', 'sv': 'Säkerhetsmarginal', 'fiTax': 'Turvatyyny', 'svTax': 'Säkerhetsmarginal'})

    def test_module_and_server_sources_avoid_old_buffer_names(self):
        for path in [*WEB.glob('*.js'), *(ROOT / 'scoach').glob('*.py')]:
            text = path.read_text()
            # Matching patterns (regexes, keyword lists) may still recognise the words people type.
            text = '\n'.join(line for line in text.splitlines() if 'keywords=' not in line and not re.search(r"r'|/\\b|\(\?:", line))
            with self.subTest(path=path.name):
                self.assertIsNone(OLD_BUFFER_WORDS.search(text), path.name)

    def test_server_labels_name_the_buffers_and_steady_mode_consistently(self):
        self.assertEqual(forecast.HELD_BACK_LABELS['reserve'][1:], ('Turvatyyny', 'Säkerhetsmarginal'))
        self.assertTrue(forecast.HELD_BACK_LABELS['buffer'][1].startswith('Yllätyspuskuri'))
        self.assertTrue(forecast.HELD_BACK_LABELS['buffer'][2].startswith('Buffert för oväntat'))
        self.assertTrue(forecast._NOTES['steady'][1].startswith('Rauhallinen tahti'))
        self.assertTrue(forecast._NOTES['steady'][2].startswith('Lugnt tempo'))


class CategoryNameTests(unittest.TestCase):
    def test_one_name_per_category_in_finnish_and_swedish(self):
        for category, (_, fi, sv) in getattr(forecast, 'CATEGORY_LABELS', {}).items():
            if category in labels.CATEGORY_LABELS and category not in ('Housing', 'Utilities'):  # bill names there
                with self.subTest(category=category):
                    self.assertEqual((fi, sv), labels.CATEGORY_LABELS[category][1:])
        for category, names in catalogue.CATEGORY_LABELS.items():
            self.assertEqual((names['fi'], names['sv']), labels.CATEGORY_LABELS[category][1:])
        self.assertEqual(labels.category_label('Restaurants', 'sv'), 'Restauranger')
        self.assertEqual(labels.category_label('Entertainment', 'sv'), 'Nöjen')


class FormatTests(unittest.TestCase):
    def test_axis_labels_write_full_thousands_in_finnish_and_swedish(self):
        run_node(self, r'''
const charts = await import(load('charts.js'));
const mortgage = await import(load('plans-mortgage.js'));
const nb = s => s.replace(/[  ]/g, ' ');
charts.configureCharts({locale: 'sv-FI', translate: null});
assert.equal(nb(charts.compactEuro(100000)), '1 000 €');
charts.configureCharts({locale: 'fi-FI', translate: null});
assert.equal(nb(charts.compactEuro(180000)), '1 800 €');
charts.configureCharts({locale: 'en-FI', translate: null});
assert.match(charts.compactEuro(180000), /K|k/);
assert.equal(nb(mortgage.compactEuros(18000000, 'sv')), '180 000 €');
assert.equal(nb(mortgage.compactEuros(18000000, 'fi')), '180 000 €');
assert.equal(mortgage.compactEuros(18000000, 'en'), '€180k');
''')

    def test_reviewed_wording(self):
        out = json.loads(run_node(self, r'''
const i18n = await import(load('i18n.js'));
const home = await import(load('home-v4.js'));
const yr = await import(load('year-review.js'));
const fi = i18n.MESSAGES.fi, sv = i18n.MESSAGES.sv;
console.log(JSON.stringify({vs: home.HOME_MESSAGES.sv['month.vs'], demo: [fi['v2.demo.open'], sv['v2.demo.open']],
  intro: yr.yr('sv', 'label.intro'), tight: sv['v5.fc.tightest'], vehicle: [fi['goal.template.vehicle'], sv['goal.template.vehicle']]}));
'''))
        self.assertEqual(out['vs'], '{amount} jfr {month}')
        self.assertEqual(out['demo'], ['Kokeile tarinaa', 'Prova en berättelse'])
        self.assertNotIn('pengar', out['intro'])
        self.assertTrue(out['tight'].startswith('Lägsta saldot'))
        self.assertEqual(out['vehicle'], ['Auto', 'En bil'])


if __name__ == '__main__':
    unittest.main()
