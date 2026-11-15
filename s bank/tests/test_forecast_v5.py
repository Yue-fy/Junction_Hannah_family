"""V5 lane FC: the 30-day balance chart — events, plain summary, chart markup and page wiring.

The fixture is Alex's real /api/forecast (as of 30 Sep 2026, trimmed): rent 5 Oct, payday 15 Oct,
home bills 17 Oct (€117.57, below the big-bill line), lowest €3,541.14 on 14 Oct.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
FIXTURE = json.loads((Path(__file__).with_name('forecast_v5_fixture.json')).read_text())


def run_node(body):
    if not shutil.which('node'):
        raise unittest.SkipTest('Node is not installed')
    modules = {name: (WEB / name).read_text() for name in ('forecast-v5.js', 'charts.js', 'i18n.js')}
    script = (
        'import assert from "node:assert/strict";\n'
        'const src=' + json.dumps(modules) + ';\n'
        'const load=name=>import("data:text/javascript;base64,"+Buffer.from(src[name]).toString("base64"));\n'
        'const fc=await load("forecast-v5.js"), charts=await load("charts.js"), i18n=await load("i18n.js");\n'
        'const FIXTURE=' + json.dumps(FIXTURE) + ';\n'
        'const tFor=locale=>(key,values)=>i18n.interpolate(i18n.MESSAGES[locale][key]??key,values,locale);\n'
        'const tags={en:"en-FI",fi:"fi-FI",sv:"sv-FI"};\n'
        'const rows=[...FIXTURE.observed.map(r=>({...r,status:"observed"})),...FIXTURE.projected.map(r=>({...r,status:"scenario"}))];\n'
        + body
    )
    result = subprocess.run(['node', '--input-type=module'], input=script, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise AssertionError(result.stderr[-4000:])
    return result.stdout


class ForecastModelTest(unittest.TestCase):
    def test_events_mark_payday_and_rent_but_not_small_bills(self):
        out = run_node('''
const events=fc.forecastEvents(FIXTURE);
console.log(JSON.stringify(events.map(e=>[e.date,e.kind,e.amount_cents])));
''')
        self.assertEqual(json.loads(out), [['2026-10-05', 'rent', -52838], ['2026-10-15', 'payday', 236488]])

    def test_big_bills_and_loans_are_marked_and_same_day_items_merge(self):
        out = run_node('''
const f=structuredClone(FIXTURE);
f.scheduled_items.push({id:'loan',transaction_type:'loan_payment',category:'Financing',role:'fixed_obligation',amount_cents:-9000});
f.scheduled_items.find(i=>i.transaction_type==='utilities_payment').amount_cents=-30000;
f.projected.find(r=>r.date==='2026-10-15').scheduled_item_ids.push('loan');
const events=fc.forecastEvents(f);
console.log(JSON.stringify(events.map(e=>[e.date,e.kind,e.items.map(i=>i.kind)])));
''')
        self.assertEqual(json.loads(out), [['2026-10-05', 'rent', ['rent']], ['2026-10-15', 'payday', ['payday', 'loan']], ['2026-10-17', 'homeBills', ['homeBills']]])

    def test_outlook_finds_the_tightest_day_before_payday(self):
        out = run_node('''
const o=fc.forecastOutlook(FIXTURE,{cushionCents:50000});
console.log(JSON.stringify(o));
''')
        outlook = json.loads(out)
        self.assertEqual(outlook['lowest'], {'date': '2026-10-14', 'balance_cents': 354114})
        self.assertTrue(outlook['beforePayday'])
        self.assertEqual(outlook['status'], 'clear')
        self.assertEqual(outlook['nextPayday'], '2026-10-15')

    def test_outlook_status_for_cushion_and_below_zero(self):
        out = run_node('''
const shift=(f,delta)=>({...f,projected:f.projected.map(r=>({...r,balance_cents:r.balance_cents+delta}))});
const cushion=fc.forecastOutlook(shift(FIXTURE,-320000),{cushionCents:50000});
const negative=fc.forecastOutlook(shift(FIXTURE,-400000),{cushionCents:50000});
const noCushion=fc.forecastOutlook(FIXTURE);
console.log(JSON.stringify([cushion.status,cushion.firstBelowCushionDate,negative.status,negative.firstNegativeDate,noCushion.status,noCushion.cushion_cents]));
''')
        self.assertEqual(json.loads(out), ['cushion', '2026-10-11', 'negative', '2026-10-05', 'clear', None])

    def test_outlook_is_null_without_projection(self):
        out = run_node('console.log(JSON.stringify([fc.forecastOutlook(null),fc.forecastOutlook({projected:[]}),fc.forecastSentence(null,{t:k=>k})]));')
        self.assertEqual(json.loads(out), [None, None, ''])


class ForecastSentenceTest(unittest.TestCase):
    def test_summary_sentence_in_three_languages(self):
        out = run_node('''
const o=fc.forecastOutlook(FIXTURE,{cushionCents:50000});
console.log(JSON.stringify(Object.fromEntries(['en','fi','sv'].map(l=>[l,fc.forecastSentence(o,{t:tFor(l),localeTag:tags[l]})]))));
''')
        text = json.loads(out)
        self.assertEqual(text['en'], 'Tightest day: €3,541 on Wed 14 Oct, the day before payday. You stay above your safety cushion.')
        self.assertIn('3 541 €', text['fi'])
        self.assertIn('palkkapäivää', text['fi'])
        self.assertIn('turvatyyny', text['fi'])
        self.assertIn('lönedagen', text['sv'])
        self.assertIn('säkerhetsmarginal', text['sv'])

    def test_gentle_warnings(self):
        out = run_node('''
const shift=(f,delta)=>({...f,projected:f.projected.map(r=>({...r,balance_cents:r.balance_cents+delta}))});
const t=tFor('en');
console.log(JSON.stringify([
 fc.forecastSentence(fc.forecastOutlook(shift(FIXTURE,-320000),{cushionCents:50000}),{t}),
 fc.forecastSentence(fc.forecastOutlook(shift(FIXTURE,-400000),{cushionCents:50000}),{t}),
 fc.forecastSentence(fc.forecastOutlook(FIXTURE),{t})]));
''')
        cushion, negative, plain = json.loads(out)
        self.assertIn('under your €500 safety cushion', cushion)
        self.assertIn('below zero from Mon 5 Oct', negative)
        self.assertTrue(plain.endswith('Your balance stays above zero.'))
        for sentence in (cushion, negative, plain):
            self.assertNotRegex(sentence.lower(), r'scenario|probability|pattern|deterministic|\{')


class RunwayChartTest(unittest.TestCase):
    def chart(self, extra='', locale='en'):
        return run_node(f'''
charts.configureCharts({{locale:tags['{locale}'],translate:tFor('{locale}')}});
const events=fc.forecastEvents(FIXTURE);
const html=charts.runwayChart(rows,{{interactive:true,width:358,events,cushionCents:50000{extra}}});
console.log(html);
''')

    def test_interactive_chart_is_drawn_at_the_column_width_with_plain_labels(self):
        html = self.chart()
        self.assertIn('width="358"', html)
        self.assertIn('viewBox="0 0 358 ', html)
        self.assertNotIn('Pattern-based', html)
        self.assertNotIn('Historical variation', html)
        self.assertNotIn('€5,978', html)  # the old misleading y-axis max is gone
        axis = re.findall(r'class="fc-axis"[^>]*>([^<]+)<', html)
        self.assertTrue(2 <= len(axis) <= 3, axis)
        self.assertTrue(all(re.fullmatch(r'€\d+(\.\d)?k', label) for label in axis), axis)
        for text in ('>Payday<', '>15 Oct<', '>Rent<', '>5 Oct<', 'Lowest €3,541'):
            self.assertIn(text, html)
        self.assertIn('class="fc-band"', html)
        self.assertIn('stroke-dasharray', html)
        self.assertIn('fc-line--observed', html)

    def test_day_readout_data_covers_every_day(self):
        html = self.chart()
        raw = re.search(r'data-fc-points="([^"]+)"', html).group(1)
        points = json.loads(raw.replace('&quot;', '"').replace('&#39;', "'").replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&'))
        self.assertEqual(len(points), len(FIXTURE['observed']) + len(FIXTURE['projected']))
        xs = [point['x'] for point in points]
        self.assertEqual(xs, sorted(xs))
        self.assertTrue(all(0 <= x <= 358 for x in xs))
        low = [point for point in points if point.get('low')]
        self.assertEqual([(p['d'], p['v']) for p in low], [('Wed 14 Oct', '€3,541')])
        payday = next(p for p in points if p['d'] == 'Thu 15 Oct')
        self.assertEqual(payday['e'], 'Payday +€2,365')
        self.assertTrue(payday['r'].startswith('Usually €'))
        self.assertEqual(points[0]['k'], 'so far')
        self.assertIn('role="status"', html)
        self.assertIn('tabindex="0"', html)

    def test_finnish_chart_labels(self):
        html = self.chart(locale='fi')
        for text in ('>Palkkapäivä<', '>Vuokra<', 'Alin', 'Saldosi seuraavat 30 päivää'):
            self.assertIn(text, html)

    def test_legacy_callers_still_get_a_scalable_chart(self):
        out = run_node('''
const html=charts.runwayChart([{balance_cents:100,date:'2026-09-30'},{balance_cents:90,date:'2026-10-01',status:'scenario'}]);
assert.match(html,/viewBox="0 0 330 /);assert.match(html,/stroke-dasharray/);assert.doesNotMatch(html,/data-fc-points/);
assert.match(charts.runwayChart([]),/empty-state/);
console.log('ok');
''')
        self.assertIn('ok', out)

    def test_cushion_line_appears_when_the_balance_gets_close(self):
        out = run_node('''
const f={...FIXTURE,projected:FIXTURE.projected.map(r=>({...r,balance_cents:r.balance_cents-310000,historical_flexible_scenarios:null}))};
const rows2=[...f.projected.map(r=>({...r,status:'scenario'}))];
const near=charts.runwayChart(rows2,{interactive:true,width:358,events:fc.forecastEvents(f),cushionCents:50000});
const far=charts.runwayChart(rows,{interactive:true,width:358,events:fc.forecastEvents(FIXTURE),cushionCents:50000});
console.log(JSON.stringify([near.includes('fc-cushion'),far.includes('fc-cushion'),near.includes('fc-low--watch')]));
''')
        self.assertEqual(json.loads(out), [True, False, True])

    def test_negative_balance_draws_a_zero_line_and_alert_dot(self):
        out = run_node('''
const f={...FIXTURE,projected:FIXTURE.projected.map(r=>({...r,balance_cents:r.balance_cents-420000}))};
const html=charts.runwayChart(f.projected.map(r=>({...r,status:'scenario'})),{interactive:true,width:358,events:fc.forecastEvents(f),cushionCents:50000});
console.log(JSON.stringify([html.includes('fc-grid--zero'),html.includes('fc-low--alert'),/>−?€0</.test(html)||html.includes('>€0<')]));
''')
        self.assertEqual(json.loads(out), [True, True, True])


class ForecastPageTest(unittest.TestCase):
    def test_card_markup_uses_plain_wording(self):
        html = (WEB / 'index.html').read_text()
        card = html[html.index('class="preview-card fc-card"'):html.index('id="forecast-assumptions"')]
        for token in ('data-i18n="v5.fc.title"', 'id="forecast-summary"', 'id="runway-chart"', 'v5.fc.soFar', 'v5.fc.expected', 'v5.fc.usualRange'):
            self.assertIn(token, card)
        for gone in ('forecast.observedLine', 'forecast.estimatedLine', 'Estimated balance', 'Observed balance'):
            self.assertNotIn(gone, card)
        self.assertIn('href="/forecast-v5.css"', html)

    def test_app_renders_summary_and_wires_the_readout(self):
        source = (WEB / 'app.js').read_text()
        self.assertIn("from './forecast-v5.js'", source)
        region = source[source.index('function renderForecastChart'):source.index('function renderForecast()')]
        for token in ('forecastEvents(f)', 'forecastOutlook(', 'forecastSentence(', 'attachForecastChart(host)', 'watchWidth(host', 'interactive:true', 'reserve_floor_cents'):
            self.assertIn(token, region)

    def test_every_fc_string_exists_in_three_languages(self):
        out = run_node('''
const keys=Object.keys(i18n.MESSAGES.en).filter(k=>k.startsWith('v5.fc.'));
const bad=keys.filter(k=>!i18n.MESSAGES.fi[k]||!i18n.MESSAGES.sv[k]||i18n.MESSAGES.fi[k]===i18n.MESSAGES.en[k]&&k!=='v5.fc.event.payday');
console.log(JSON.stringify({count:keys.length,bad}));
''')
        result = json.loads(out)
        self.assertGreaterEqual(result['count'], 20)
        self.assertEqual(result['bad'], [])

    def test_no_developer_wording_in_fc_strings(self):
        source = (WEB / 'i18n.js').read_text()
        block = source[source.index('const V5_FC_MESSAGES'):source.index('for (const [key, values] of Object.entries(V5_FC_MESSAGES))')]
        for word in ('scenario', 'probability', 'deterministic', 'pattern-based', 'quartile', 'p25', 'p75'):
            self.assertNotIn(word, block.lower())


if __name__ == '__main__':
    unittest.main()
