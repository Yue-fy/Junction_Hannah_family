"""V5 lane TR: "How spending changes over time" is a line chart with a hover/tap/keyboard tooltip.

Node checks pin the chart markup, the summary sentence, the tooltip and the EN/FI/SV copy. The browser class
(Playwright + Chrome + demo database) drives a real page: mouse hover, phone tap, keyboard focus and arrows,
Escape, the period control and that the old per-month comparison card and developer blocks are gone.
"""
import json
import shutil
import subprocess
import threading
import tempfile
import unittest
from pathlib import Path

from tests.test_v4_fixes_browser import READY, REASON, CHROME, DATABASE

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
ROWS = [{'month': f'2025-{m:02d}', 'total_cents': c} for m, c in
        [(10, 210000), (11, 195000), (12, 274000), ]] + [{'month': f'2026-{m:02d}', 'total_cents': c} for m, c in
        [(1, 228000), (2, 178000), (3, 159000), (4, 203000), (5, 212000), (6, 159000), (7, 235443), (8, 254000), (9, 187866)]]


@unittest.skipUnless(shutil.which('node'), 'Node is required for chart checks')
class TrendV5NodeTests(unittest.TestCase):
    def node(self, body):
        script = ('import assert from "node:assert/strict";\n'
                  f'const charts = await import({json.dumps((WEB / "charts.js").as_uri())});\n'
                  f'const trend = await import({json.dumps((WEB / "trend-v5.js").as_uri())});\n'
                  f'const i18n = await import({json.dumps((WEB / "i18n.js").as_uri())});\n'
                  f'const rows = {json.dumps(ROWS)};\n' + body)
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_line_chart_has_one_focusable_point_per_month_with_roving_tabindex(self):
        self.node('''
const svg = charts.lineChart(rows, {width: 360, height: 210, describedBy: 'tip-1'});
assert.match(svg, /viewBox="0 0 360 210"/, 'drawn in real pixels so text keeps its size');
assert.equal((svg.match(/class="lc-pt/g) || []).length, 12);
assert.equal((svg.match(/tabindex="0"/g) || []).length, 1, 'one tab stop; arrows move between months');
assert.match(svg, /<g class="lc-pt is-latest" role="button" tabindex="0" data-index="11"/);
assert.match(svg, /aria-label="September 2026: €1,878.66"/);
assert.match(svg, /aria-describedby="tip-1"/);
assert.equal((svg.match(/class="lc-line"/g) || []).length, 1, 'one clean line, no bars');
assert.ok(!svg.includes('chart-bar'), 'no bar marks');
assert.match(svg, /class="lc-cross"/);
const grid = (svg.match(/class="lc-ylabel"/g) || []).length;
assert.ok(grid >= 2 && grid <= 4, 'two to four light gridline labels, got ' + grid);
assert.match(svg, />€1k</); assert.match(svg, />€3k</); // one axis style: lowercase k in English
assert.match(svg, /class="lc-value"[^>]*>€1.9k</, 'the newest month is labelled directly');
assert.ok((svg.match(/class="lc-xlabel/g) || []).length <= 8, 'month names never crowd a phone');
assert.match(svg, />Sept</, 'newest month is always named');
// Every hit area spans the column (touch target) and together they cover the full width.
const hits = [...svg.matchAll(/class="lc-hit" x="([\\d.]+)" y="0" width="([\\d.]+)"/g)].map(m => [+m[1], +m[2]]);
assert.equal(hits[0][0], 0); assert.ok(Math.abs(hits.at(-1)[0] + hits.at(-1)[1] - 360) < 0.2);
assert.ok(hits.every(([, w]) => w >= 24), 'hit areas are at least 24px wide');
''')

    def test_line_chart_active_and_empty_and_escaping(self):
        self.node('''
const active = charts.lineChart(rows, {activeIndex: 3, focusIndex: 3});
assert.match(active, /class="line-chart has-active"/);
assert.match(active, /<g class="lc-pt is-active" role="button" tabindex="0" data-index="3"/);
assert.match(charts.lineChart([]), /empty-state/);
assert.match(charts.lineChart([{month: '2026-01', total_cents: null}]), /empty-state/);
const one = charts.lineChart([{month: '2026-09', total_cents: 5000}]);
assert.equal((one.match(/class="lc-pt/g) || []).length, 1);
const odd = charts.lineChart([{label: '<b>x</b>', total_cents: 100}, {label: 'y', total_cents: 200}], {labels: ['<i>', 'ok']});
assert.ok(!odd.includes('<b>') && !odd.includes('<i>'), 'labels are escaped');
assert.ok(!charts.lineChart(rows).includes('month before'), 'no previous-month comparison');
''')

    def test_summary_sentence_kinds(self):
        out = self.node('''
const t = (key, v) => key + JSON.stringify(v || {});
const f = cents => String(Math.round(cents / 100));
const S = list => trend.trendSummary(list.map((c, i) => ({month: '2026-0' + (i + 1), total_cents: c})), {t, format: f});
assert.equal(S([]).kind, 'none');
assert.equal(S([100000]).kind, 'one');
assert.equal(S([200000, 210000, 195000, 205000, 220000, 200000]).kind, 'steady');
assert.match(S([200000, 210000, 195000, 205000, 220000, 200000]).text, /"low":"1950","high":"2200"/);
assert.equal(S([150000, 160000, 210000, 220000]).kind, 'up');
assert.equal(S([220000, 210000, 160000, 150000]).kind, 'down');
assert.equal(S([200000, 120000, 300000, 210000, 130000, 290000]).kind, 'varied');
assert.equal(S([200000, 100000, 150000]).kind, 'varied', 'three months are too few for a direction');
console.log(trend.salarySentence(241000, {t, format: f}) + '|' + trend.salarySentence(null, {t}));
''')
        self.assertIn('v5.tr.salary{"amount":"2410"}|', out)

    def test_summary_reads_naturally_in_every_language(self):
        out = self.node('''
const lines = [];
for (const [locale, tag] of [['en', 'en-FI'], ['fi', 'fi-FI'], ['sv', 'sv-FI']]) {
  const i = i18n.createI18n({storage: null, navigatorLanguages: [locale]});
  i.setLocale?.(locale);
  charts.configureCharts({locale: tag, translate: i.t});
  lines.push(trend.trendSummary(rows, {t: i.t, monthLabel: m => m}).text);
}
console.log(JSON.stringify(lines));
''')
        en, fi, sv = json.loads(out)
        self.assertEqual(en, 'Your spending has moved between €1,590 and €2,740 a month; 2025-12 was the biggest month.')
        self.assertIn('1 590 €–2 740 €', fi.replace(' ', ' '))
        self.assertTrue(fi.startswith('Menosi ovat vaihdelleet'), fi)
        self.assertTrue(sv.startswith('Dina utgifter har varierat mellan'), sv)

    def test_tooltip_shows_month_total_and_top_two_categories(self):
        self.node('''
const t = key => ({'v5.tr.tip.spent': 'spent', 'v5.tr.tip.loading': 'Loading', 'v5.tr.tip.none': 'None', 'v5.tr.tip.transactions': 'See transactions'})[key] || key;
const money = c => '€' + (c / 100).toFixed(2), monthLabel = m => 'Month ' + m;
const cats = [{label: 'Groceries', total_cents: 61020}, {label: 'Housing <b>', total_cents: 53741}, {label: 'Transport', total_cents: 52770}];
const html = trend.trendTooltipHTML({month: '2026-05', total_cents: 212515}, {t, money, monthLabel, categories: cats});
assert.match(html, /Month 2026-05/); assert.match(html, /<strong>€2125.15<\\/strong> <span>spent/);
assert.match(html, /Groceries/); assert.match(html, /Housing &lt;b&gt;/); assert.ok(!html.includes('Transport'), 'top two only');
assert.ok(!html.includes('data-chart-transactions'), 'hover tooltip has no button');
assert.ok(!/more than|less than|month before/.test(html), 'no previous-month comparison');
const pinned = trend.trendTooltipHTML({month: '2026-05', total_cents: 1}, {t, money, monthLabel, categories: [], pinned: true});
assert.match(pinned, /None/); assert.match(pinned, /data-chart-transactions="2026-05"/);
assert.match(trend.trendTooltipHTML({month: '2026-05', total_cents: 1}, {t, money, monthLabel}), /Loading/);
const label = trend.pointLabel({month: '2026-05', total_cents: 212515}, {t: (k, v) => v.month + ': ' + v.amount, money, monthLabel, categories: cats});
assert.equal(label, 'Month 2026-05: €2125.15. Groceries €610.20, Housing <b> €537.41');
''')

    def test_every_new_string_exists_in_en_fi_sv(self):
        self.node('''
const keys = Object.keys(i18n.MESSAGES.en).filter(key => key.startsWith('v5.tr.'));
assert.ok(keys.length >= 14, 'found ' + keys.length);
for (const key of keys) for (const locale of ['fi', 'sv']) {
  assert.ok(i18n.MESSAGES[locale][key], locale + ' ' + key);
  assert.notEqual(i18n.MESSAGES[locale][key], i18n.MESSAGES.en[key], locale + ' ' + key + ' is untranslated');
}
const used = new Set([...(await import('node:fs')).readFileSync(''' + json.dumps(str(WEB / 'trend-v5.js')) + ''', 'utf8').matchAll(/'(v5\\.tr\\.[\\w.]*\\w)'/g)].map(m => m[1]));
for (const key of used) assert.ok(i18n.MESSAGES.en[key], 'missing ' + key);
''')

    def test_wiring_replaces_bars_detail_card_and_developer_blocks(self):
        index = (WEB / 'index.html').read_text()
        self.assertIn('href="/trend-v5.css"', index)
        v3 = (WEB / 'v3.js').read_text()
        self.assertIn("from './trend-v5.js'", v3)
        self.assertNotIn('chartDetailPanel', v3)
        self.assertNotIn('showTrendDetail', v3)
        app = (WEB / 'app.js').read_text()
        body = app[app.index('function renderTrends()'):app.index('function renderGoals()')]
        v5 = body[body.index('if(v3)'):body.index('return;}')]
        for gone in ('trends.salaryMedians', 'trends.annual', 'trends.sameMonth', 'trends.yoy'):
            self.assertNotIn(gone, v5)
        self.assertIn('evidence.formula', v5)


@unittest.skipUnless(READY, REASON)
class TrendV5BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from scoach.api import Application, create_server
        cls.tmp = tempfile.mkdtemp(prefix='scoach-v5tr-')
        database = Path(cls.tmp) / 'scoach.sqlite3'
        shutil.copyfile(DATABASE, database)
        cls.server = create_server(Application(database), port=0)
        cls.server.handle_error = lambda *args: None
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/#spending'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def open(self, width, height, touch=False):
        context = self.browser.new_context(viewport={'width': width, 'height': height}, has_touch=touch, is_mobile=touch)
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(self.url)
        page.wait_for_selector('#trend-chart .lc-pt', state='attached', timeout=15000)
        page.evaluate("document.getElementById('history-details').open = true")
        page.locator('#history-details').scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        self.addCleanup(lambda: self.assertEqual(errors, []))
        return page

    def tip(self, page):
        return page.locator('#trend-chart .trend5-tip')

    def readout(self, page):
        # Wide mouse screens keep a readout row under the chart: a hint while idle, a month when one is active.
        return page.locator('#trend-chart .trend5-tip:not(.is-idle)')

    def overlaps_a_point(self, page):
        return page.evaluate("""() => { const t = document.querySelector('#trend-chart .trend5-tip').getBoundingClientRect();
            return [...document.querySelectorAll('#trend-chart .lc-dot')].some(d => { const r = d.getBoundingClientRect();
            return r.right > t.left && r.left < t.right && r.bottom > t.top && r.top < t.bottom; }); }""")

    def test_mouse_hover_shows_tooltip_and_leaving_hides_it(self):
        page = self.open(1280, 800)
        self.assertEqual(page.locator('#trend-chart .chart-detail, #trend-detail .chart-detail').count(), 0)
        self.assertEqual(page.locator('.trend-facts h3').count(), 0, 'no "Salary, on its own" / same-month blocks')
        box = page.locator('#trend-chart .lc-pt').nth(9).locator('.lc-dot').bounding_box()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 30)
        tip = self.readout(page)
        tip.wait_for(state='visible')
        page.wait_for_function("document.querySelectorAll('#trend-chart .trend5-tip-cats li').length === 2")
        self.assertRegex(tip.inner_text(), r'2026')
        self.assertNotIn('month before', tip.inner_text())
        self.assertEqual(tip.locator('button').count(), 0)
        width = page.locator('#trend-chart').bounding_box()['width']
        tip_box = tip.bounding_box()
        self.assertGreaterEqual(tip_box['x'], page.locator('#trend-chart').bounding_box()['x'] - 1)
        self.assertLessEqual(tip_box['x'] + tip_box['width'], page.locator('#trend-chart').bounding_box()['x'] + width + 1)
        self.assertFalse(self.overlaps_a_point(page), 'the readout never covers a month')
        page.mouse.move(5, 5)
        tip.wait_for(state='hidden')
        cls = self.tip(page).get_attribute('class') or ''
        # The side-by-side desktop layout can make the chart narrow enough for the docked readout,
        # which hides on leave instead of showing the idle hint; both keep the line uncovered.
        self.assertTrue('is-idle' in cls or ('is-docked' in cls and self.tip(page).is_hidden()), cls)
        self.assertGreater(len(page.locator('#trend-description').inner_text()), 20)

    def test_tap_on_phone_pins_tooltip_with_transactions_and_outside_tap_closes(self):
        page = self.open(375, 812, touch=True)
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 375)
        page.locator('#trend-chart .lc-pt').nth(3).tap()
        tip = self.tip(page)
        tip.wait_for(state='visible')
        box, chart = tip.bounding_box(), page.locator('#trend-chart').bounding_box()
        self.assertGreaterEqual(box['x'], chart['x'] - 1)
        self.assertLessEqual(box['x'] + box['width'], chart['x'] + chart['width'] + 1)
        button = tip.locator('[data-chart-transactions]')
        self.assertEqual(button.get_attribute('data-chart-transactions'), '2026-01')
        button.tap()
        page.wait_for_selector('#transactions-dialog[open]')
        page.keyboard.press('Escape')
        page.locator('#trend-description').tap()
        tip.wait_for(state='hidden')

    def test_keyboard_focus_arrows_and_escape(self):
        page = self.open(768, 1024)
        page.locator('#trend-chart .lc-pt[tabindex="0"]').focus()
        tip = self.readout(page)
        tip.wait_for(state='visible')
        self.assertIn('2026', tip.inner_text())
        page.keyboard.press('ArrowLeft')
        self.assertEqual(page.evaluate("document.activeElement.dataset.index"), '10')
        self.assertEqual(page.locator('#trend-chart .lc-pt[tabindex="0"]').get_attribute('data-index'), '10')
        page.keyboard.press('Home')
        self.assertEqual(page.evaluate("document.activeElement.dataset.index"), '0')
        page.keyboard.press('Escape')
        tip.wait_for(state='hidden')
        page.keyboard.press('Enter')
        tip.wait_for(state='visible')
        page.keyboard.press('Tab')
        self.assertTrue(page.evaluate("document.activeElement.hasAttribute('data-chart-transactions')"))

    def test_phone_readout_is_docked_and_one_tap_switches_months(self):
        page = self.open(320, 640, touch=True)
        page.locator('#trend-chart .lc-pt').nth(9).tap()
        tip = self.tip(page)
        tip.wait_for(state='visible')
        self.assertIn('is-docked', tip.get_attribute('class'))
        self.assertFalse(self.overlaps_a_point(page), 'the docked readout sits under the chart')
        self.assertIn('July 2026', tip.inner_text())
        box = page.locator('#trend-chart .lc-pt').nth(8).locator('.lc-dot').bounding_box()
        page.touchscreen.tap(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.wait_for_function("document.querySelector('#trend-chart .trend5-tip').textContent.includes('June 2026')")

    def test_period_control_redraws_the_line(self):
        page = self.open(390, 844, touch=True)
        page.locator('[data-period-months="6"]').tap()
        page.wait_for_function("document.querySelectorAll('#trend-chart .lc-pt').length === 6", timeout=15000)
        page.locator('[data-period-months="3"]').tap()
        page.wait_for_function("document.querySelectorAll('#trend-chart .lc-pt').length === 3", timeout=15000)


if __name__ == '__main__':
    unittest.main()
