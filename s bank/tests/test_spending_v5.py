"""V5 lane SP: the Spending tab structure.

Static checks pin the markup (one heading, ring card with the basket chips under the categories, a folded "More"
card holding money in/out, money by group, savings transfers and VAT) and the EN/FI/SV copy. A node check runs the
glue module on a tiny fake DOM. The rendered checks (Playwright + Chrome + demo DB) pin the order on screen, the
folds, the category → transactions sheet tap, one explanation line for the baskets and no overflow at four sizes.
"""
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
DATABASE = ROOT / 'var' / 'scoach.sqlite3'
CHROME = os.environ.get('SCOACH_CHROME', '/usr/bin/google-chrome')
SP_KEYS = ('v5.sp.where', 'v5.sp.baskets', 'v5.sp.basketsIntro', 'v5.sp.more', 'v5.sp.moreHint', 'v5.sp.byType', 'v5.sp.byTypeHelp')


class Tree(HTMLParser):
    """Start tags with their ancestor chain (ids/classes), enough to check nesting and order."""
    VOID = {'meta', 'link', 'br', 'img', 'input', 'hr', 'source', 'area', 'base', 'col', 'embed', 'track', 'wbr', 'path', 'circle', 'rect', 'line', 'polyline'}

    def __init__(self, source):
        super().__init__()
        self.stack, self.nodes = [], []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.nodes.append((tag, attrs, [a for _, a in self.stack]))
        if tag not in self.VOID:
            self.stack.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs), [a for _, a in self.stack]))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def index(self, node_id):
        for i, (_, attrs, _) in enumerate(self.nodes):
            if attrs.get('id') == node_id:
                return i
        raise AssertionError(f'#{node_id} missing')

    def ancestors(self, node_id):
        return self.nodes[self.index(node_id)][2]

    def inside(self, node_id, ancestor_id):
        return any(a.get('id') == ancestor_id for a in self.ancestors(node_id))


class SpendingMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (WEB / 'index.html').read_text()
        cls.tree = Tree(cls.html)
        start = cls.html.index('<section id="trends-view"')
        cls.view = cls.html[start:cls.html.index('<section id="coach-view"')]

    def test_one_plain_heading_without_eyebrow_or_duplicate_titles(self):
        self.assertEqual(self.view.count('<h1'), 1)
        self.assertNotIn('data-v2="spending.eyebrow"', self.view)
        self.assertNotIn('data-ux="spending.eyebrow"', self.view)
        self.assertNotIn('data-v2="spending.help"', self.view)
        self.assertNotIn('spending-filter', self.view, 'The basket chips are no longer hidden in a "Filter spending" fold')
        self.assertNotIn('Spending, made clear', self.view)

    def test_ring_card_holds_basket_chips_above_the_ring_with_one_line(self):
        t = self.tree
        for node in ('spending-donut', 'spending-categories', 'spending-groups', 'spending-group-help', 'spending-selection'):
            self.assertTrue(t.inside(node, 'spending-card'), node)
        self.assertLess(t.index('spending-donut'), t.index('spending-categories'))
        # V5 fix (lane SP2): the chips sit above the ring they filter, so the change happens next to the finger.
        self.assertLess(t.index('spending-groups'), t.index('spending-donut'))
        self.assertIn('data-i18n="v5.sp.basketsIntro"', self.view)
        self.assertEqual(self.view.count('data-spending-group='), 4)

    def test_more_card_is_last_folded_and_holds_the_secondary_blocks(self):
        t = self.tree
        more = t.nodes[t.index('spending-more')]
        self.assertEqual(more[0], 'details')
        self.assertNotIn('open', more[1], '"More" starts folded')
        for node in ('investment-analysis', 'vat-analysis', 'vat-tile'):
            self.assertTrue(t.inside(node, 'spending-more'), node)
        basket = [n for n in t.nodes if 'basket-explanation' in n[1].get('class', '')]
        self.assertEqual(len(basket), 1)
        self.assertTrue(any(a.get('id') == 'spending-more' for a in basket[0][2]))
        self.assertFalse(t.inside('spending-card', 'spending-more'))
        self.assertFalse(t.inside('history-details', 'spending-more'))
        self.assertGreater(t.index('spending-more'), t.index('runway-chart'))
        self.assertGreater(t.index('spending-more'), t.index('history-details'))

    def test_ids_stay_unique_and_existing_hooks_survive(self):
        ids = [a['id'] for _, a, _ in self.tree.nodes if 'id' in a]
        self.assertEqual(len(ids), len(set(ids)))
        for node in ('trend-range', 'trend-range-control', 'map-period', 'trend-period', 'money-flow', 'flow-legend', 'safe-card',
                     'safe-content', 'cashflow-analysis', 'forecast-analysis', 'trend-chart', 'runway-chart', 'trend-comparison'):
            self.assertIn(node, ids)

    def test_glue_is_loaded_from_app_and_styles_from_the_glue(self):
        app = (WEB / 'app.js').read_text()
        self.assertIn("from './spending-v5.js'", app)
        self.assertIn('arrangeSpending(document)', app)
        self.assertIn("'spending-v5.css'", (WEB / 'spending-v5.js').read_text())
        self.assertTrue((WEB / 'spending-v5.css').is_file())


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class SpendingCopyAndGlueTests(unittest.TestCase):
    def node(self, script):
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, cwd=WEB)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_every_new_string_exists_in_en_fi_sv(self):
        out = self.node("import {MESSAGES} from './i18n.js';console.log(JSON.stringify(Object.fromEntries(['en','fi','sv'].map(l=>[l,Object.fromEntries(Object.entries(MESSAGES[l]).filter(([k])=>k.startsWith('v5.sp.')))]))));")
        data = json.loads(out)
        for key in SP_KEYS:
            values = [data[locale].get(key) for locale in ('en', 'fi', 'sv')]
            self.assertTrue(all(values), key)
            self.assertEqual(len(set(values)), 3, f'{key} is not translated')
        for locale in ('en', 'fi', 'sv'):
            for value in data[locale].values():
                self.assertNotRegex(value.lower(), r'deterministic|scenario|quartile|mcc|provenance|demo')

    def test_glue_orders_blocks_and_folds_more_on_a_fake_dom(self):
        script = r'''
import assert from 'node:assert/strict';
import {arrangeSpending, SPENDING_ORDER, MORE_ORDER} from './spending-v5.js';
class Node{constructor(id,cls=''){this.id=id;this.children=[];this.parentNode=null;this.hidden=false;this.open=true;this.dataset={};this.cls=new Set(cls.split(' ').filter(Boolean));this.classList={add:(...c)=>c.forEach(x=>this.cls.add(x)),contains:c=>this.cls.has(c)};}
 appendChild(n){n.parentNode?.children.splice(n.parentNode.children.indexOf(n),1);this.children.push(n);n.parentNode=this;return n;}
 insertBefore(n,ref){n.parentNode?.children.splice(n.parentNode.children.indexOf(n),1);this.children.splice(this.children.indexOf(ref),0,n);n.parentNode=this;return n;}
 closest(sel){let n=this;while(n){if(sel==='section'&&n.tag==='section')return n;n=n.parentNode;}return null;}}
const all={};const mk=(id,cls,tag)=>{const n=new Node(id,cls);n.tag=tag;if(id)all[id]=n;return n;};
const view=mk('trends-view','','section'),more=mk('spending-more','','details'),list=mk('spending-more-list','','div');more.appendChild(list);
const card=mk('spending-card','','section'),hist=mk('history-details','','details'),cash=mk('cashflow-analysis','','details'),fold=mk('forecast-analysis','','details');
const preview=mk('','preview-card','section'),chart=mk('runway-chart','','div');preview.appendChild(chart);fold.appendChild(mk('safe-card','','section'));fold.appendChild(preview);
const basket=mk('','basket-explanation','details'),inv=mk('investment-analysis','','details'),vat=mk('vat-analysis','','details');
list.appendChild(basket);list.appendChild(inv);list.appendChild(vat);hist.open=false;
for(const n of [card,more,hist,cash,fold])view.appendChild(n);
const doc={getElementById:id=>all[id]||null,querySelector:sel=>sel.includes('basket-explanation')?basket:null};
const placed=arrangeSpending(doc);
assert.deepEqual(placed,['spending-card','history-details','spending-forecast','spending-more']);
const visible=view.children.filter(n=>!n.hidden).map(n=>n.id);
assert.deepEqual(visible,['spending-card','history-details','spending-forecast','spending-more']);
assert.equal(fold.hidden,true,'The old fold with the weekly amount is hidden');
assert.equal(hist.open,true,'Spending over time starts open');
assert.deepEqual(list.children.map(n=>n.id||'basket'),['cashflow-analysis','basket','investment-analysis','vat-analysis']);
assert.equal(cash.open,false,'Money in vs out starts folded inside More');
assert.ok(preview.classList.contains('sp5-card'));
hist.open=false;cash.open=true;arrangeSpending(doc);
assert.equal(hist.open,false,'A second run keeps what the customer chose');assert.equal(cash.open,true);
assert.deepEqual(arrangeSpending({}),[]);
'''
        self.node(script)


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class SpendingSheetAndFormHelperTests(unittest.TestCase):
    """V5 fix wave, lane SP2: the category sheet and the assumptions form are pure helpers in spending-v5.js."""
    def node(self, script):
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, cwd=WEB)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_sheet_title_total_plurals_and_compact_rows(self):
        self.node(r"""
import assert from 'node:assert/strict';
import {MESSAGES} from './i18n.js';
import {transactionSheet, periodText, pluralKey} from './spending-v5.js';
const tr = locale => (key, v = {}) => String(MESSAGES[locale][key] ?? key).replace(/\{(\w+)\}/g, (_, k) => v[k] ?? '');
const money = c => '€' + (c / 100).toFixed(2);
const base = {money, categoryName: c => c === 'Groceries' ? 'Groceries' : c, monthLabel: m => m === '2026-09' ? 'September 2026' : m};
const rows = [
  {transaction_ref: 'a', date: '2026-09-02', timestamp: '02SEP26:16:51:38', category: 'Groceries', amount_cents: -10809, transaction_type: 'purchase'},
  {transaction_ref: 'b<', date: '2026-09-05', timestamp: '05SEP26:20:15:24', category: 'Groceries', amount_cents: -9252, transaction_type: 'purchase'}];
const scope = {category: 'Groceries', start: '2026-09-01', end: '2026-09-30'};
const en = transactionSheet(rows, {...base, scope, t: tr('en')});
assert.equal(en.title, 'Groceries · September 2026');
assert.equal(en.summary, '2 purchases · €200.61');
assert.ok(!/rows|Observed/.test(en.title + en.summary));
assert.equal((en.list.match(/class="transaction-row tx5-row" data-transaction=/g) || []).length, 2, 'the whole row is the button');
assert.ok(!en.list.includes('>Groceries<'), 'the category is in the title, not repeated on every row');
assert.match(en.list, /Wed 2 Sept/); assert.match(en.list, /16:51/); assert.match(en.list, /b&lt;/);
assert.ok(en.footnote);
const one = transactionSheet(rows.slice(0, 1), {...base, scope, t: tr('en')});
assert.equal(one.summary, '1 purchase · €108.09');
assert.equal(transactionSheet(rows.slice(0, 1), {...base, scope, t: tr('fi'), localeTag: 'fi-FI'}).summary, '1 ostos · €108.09');
const housing = [{transaction_ref: 'h', date: '2026-09-05', category: 'Housing', amount_cents: -53934, transaction_type: 'housing_payment'}];
assert.match(transactionSheet(housing, {...base, scope: {category: 'Housing', start: '2026-09-01', end: '2026-09-30'}, t: tr('sv')}).summary, /^1 transaktion ·/);
assert.match(transactionSheet([...housing, ...housing], {...base, scope: {category: 'Housing', start: '2026-09-01', end: '2026-09-30'}, t: tr('fi')}).summary, /^2 tapahtumaa ·/);
assert.equal(pluralKey('v5.sp.viewTx', 1), 'v5.sp.viewTx.one'); assert.equal(pluralKey('v5.sp.viewTx', 5), 'v5.sp.viewTx.other');
assert.equal(tr('fi')('v5.sp.viewTx.one', {count: 1}), 'Näytä 1 tapahtuma');
assert.equal(tr('sv')('v5.sp.viewTx.one', {count: 1}), 'Visa 1 transaktion');
assert.equal(periodText('2026-09-01', '2026-09-14'), '1–14 Sept 2026');
assert.equal(periodText('2026-09-01', '2026-09-14', {localeTag: 'fi-FI'}), '1.–14.9.2026');
""")

    def test_assumptions_form_names_items_and_shows_positive_amounts(self):
        self.node(r"""
import assert from 'node:assert/strict';
import {MESSAGES} from './i18n.js';
import {assumptionsFormHTML} from './spending-v5.js';
const t = (key, v = {}) => String(MESSAGES.en[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => v[k] ?? '');
const items = [
  {id: 'r', transaction_type: 'housing_payment', category: 'Housing', role: 'fixed_obligation', amount_cents: -52838, median_day: 5},
  {id: 's', transaction_type: 'salary', category: 'Salary', role: 'income', amount_cents: 236488, median_day: 15},
  {id: 'u', transaction_type: 'utilities_payment', category: 'Utilities', role: 'fixed_obligation', amount_cents: -11757, median_day: 17}];
const html = assumptionsFormHTML(items, {t, categoryName: c => c});
for (const name of ['Rent', 'Salary', 'Home bills']) assert.match(html, new RegExp('class="fa5-name">' + name + '<'));
assert.ok(!html.includes('Must-pays'), 'no unnamed duplicate group titles');
assert.ok(!/value="-/.test(html), 'amounts are positive');
assert.match(html, /value="528.38"/); assert.match(html, /value="2364.88"/);
assert.match(html, /data-sign="-1"/); assert.match(html, /data-sign="1"/);
assert.equal((html.match(/id="apply-preview"/g) || []).length, 1);
assert.ok(!html.includes('forecast-method'), 'one "How is this worked out?" (in the card), not a second one here');
assert.match(assumptionsFormHTML(items, {t, categoryName: c => c, localeTag: 'fi-FI'}), /value="528,38"/);
""")


def _browser_ready():
    if importlib.util.find_spec('playwright') is None:
        return False, 'Python Playwright is not installed'
    if not Path(CHROME).exists():
        return False, 'Google Chrome is not installed'
    if not DATABASE.is_file() or DATABASE.stat().st_size == 0:
        return False, 'Build the demo database first'
    try:
        with sqlite3.connect(DATABASE) as conn:
            conn.execute('SELECT 1 FROM transactions LIMIT 1')
    except sqlite3.Error:
        return False, 'Build the demo database first'
    return True, ''


READY, REASON = _browser_ready()


@unittest.skipUnless(READY, REASON)
class SpendingBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from scoach.api import Application, create_server
        cls.tmp = tempfile.mkdtemp(prefix='scoach-sp5-')
        database = Path(cls.tmp) / 'scoach.sqlite3'
        shutil.copyfile(DATABASE, database)
        cls.server = create_server(Application(database), port=0)
        cls.server.handle_error = lambda *args: None
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 390, 'height': 844})
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def open(self):
        self.page.goto(self.url + '#spending')
        self.page.wait_for_selector('#spending-categories .category-row', timeout=20000)
        self.page.wait_for_timeout(300)

    def visible_blocks(self):
        return self.page.evaluate("[...document.querySelectorAll('#trends-view > *')].filter(n => n.getClientRects().length).map(n => n.id || n.className)")

    def test_sections_appear_in_the_calm_order(self):
        self.open()
        self.assertEqual(self.visible_blocks(), ['page-heading sp5-heading', 'spending-card', 'history-details', 'spending-forecast', 'spending-more'])
        self.assertTrue(self.page.evaluate("document.querySelector('#history-details').open"))
        self.assertFalse(self.page.evaluate("document.querySelector('#spending-more').open"))
        self.assertTrue(self.page.is_hidden('#safe-card'), 'The weekly amount lives on Home, not repeated here')
        inner = self.page.eval_on_selector_all('#spending-more-list > details', 'nodes => nodes.map(n => [n.id || "basket", n.open])')
        self.assertEqual(inner, [['cashflow-analysis', False], ['basket', False], ['investment-analysis', False], ['vat-analysis', False]])
        headings = self.page.eval_on_selector_all('#trends-view details > summary', 'nodes => nodes.map(n => n.textContent.trim())')
        titles = self.page.eval_on_selector_all('#trends-view details h2', 'nodes => nodes.map(n => n.textContent.trim())')
        self.assertFalse(set(headings) & set(titles), 'An accordion repeats its title as a heading')

    def test_cards_share_one_visual_system(self):
        self.open()
        styles = self.page.evaluate("""['spending-card','history-details','spending-forecast','spending-more'].map(id => {
            const s = getComputedStyle(document.getElementById(id));
            return [s.borderTopLeftRadius, s.paddingLeft, s.borderTopWidth, s.backgroundColor];})""")
        self.assertEqual(len({tuple(s) for s in styles}), 1, styles)
        lefts = self.page.evaluate("['spending-card','history-details','spending-forecast','spending-more'].map(id => Math.round(document.getElementById(id).getBoundingClientRect().left))")
        self.assertEqual(len(set(lefts)), 1)

    def test_category_row_opens_the_transactions_sheet(self):
        self.open()
        self.page.click('#spending-categories .category-row >> nth=0')
        self.page.wait_for_function("document.getElementById('transactions-dialog').open", timeout=10000)
        self.page.wait_for_selector('#transaction-list .transaction-row, #transaction-list li, #transaction-list article', timeout=10000)

    def test_baskets_show_exactly_one_explanation_line(self):
        self.open()
        def shown():
            return self.page.eval_on_selector_all('.sp5-basket-line', 'nodes => nodes.filter(n => n.getClientRects().length).length')
        self.assertEqual(shown(), 1)
        self.page.click('[data-spending-group=leaks]')
        self.page.wait_for_timeout(200)
        self.assertEqual(shown(), 1)
        self.assertTrue(self.page.is_visible('#spending-group-help'))
        self.assertEqual(self.page.get_attribute('[data-spending-group=leaks]', 'aria-pressed'), 'true')

    def test_category_sheet_is_titled_compact_and_whole_row_tappable(self):
        self.open()
        self.page.click('#spending-categories .category-row >> nth=2')
        self.page.wait_for_selector('#transaction-list .tx5-row', timeout=10000)
        title = self.page.text_content('#transactions-title').strip()
        self.assertRegex(title, r'^\S.* · September 2026$')
        self.assertNotRegex(self.page.text_content('#transaction-summary'), r'rows|Observed')
        heights = self.page.eval_on_selector_all('#transaction-list .tx5-row', 'n => n.map(x => x.getBoundingClientRect().height)')
        self.assertTrue(all(h <= 72 for h in heights), heights)
        self.assertEqual(self.page.locator('#transaction-list .tx5-row .text-button').count(), 0)

    def test_basket_chips_above_ring_and_trend_follows_basket(self):
        self.open()
        chips = self.page.locator('#spending-groups').bounding_box()
        ring = self.page.locator('#spending-donut').bounding_box()
        self.assertLess(chips['y'], ring['y'])
        self.page.click('[data-spending-group=leaks]')
        self.page.wait_for_selector('#trend-scope:not([hidden])')
        self.assertIn('Little leaks', self.page.text_content('#trend-scope'))
        self.assertIn('of little leaks', self.page.text_content('#spending-categories'))
        self.page.click('#trend-scope [data-spending-group=all]')
        self.page.wait_for_selector('#trend-scope', state='hidden')
        self.assertEqual(self.page.get_attribute('[data-spending-group=all] >> nth=0', 'aria-pressed'), 'true')

    def test_cashflow_chart_draws_at_real_width_without_clipping(self):
        for width in (320, 1280):
            self.page.set_viewport_size({'width': width, 'height': 800})
            self.open()
            self.page.evaluate("document.querySelector('#spending-more').open = true; document.querySelector('#cashflow-analysis').open = true")
            self.page.wait_for_selector('#cashflow-chart .cf5-svg', timeout=15000)
            self.page.wait_for_timeout(300)
            box = self.page.locator('#cashflow-chart').bounding_box()
            svg = self.page.locator('#cashflow-chart .cf5-svg').bounding_box()
            self.assertLessEqual(abs(svg['width'] - box['width']), 2, 'drawn at the column width, not scaled')
            sizes = self.page.eval_on_selector_all('#cashflow-chart .cf5-svg text', 'n => n.map(x => parseFloat(getComputedStyle(x).fontSize))')
            self.assertTrue(all(10 <= size <= 14 for size in sizes), sizes)
            inside = self.page.evaluate("""() => { const c = document.querySelector('#cashflow-chart').getBoundingClientRect();
                return [...document.querySelectorAll('#cashflow-chart text, #cashflow-chart .cf5-key')].every(n => { const r = n.getBoundingClientRect();
                return r.left >= c.left - 1 && r.right <= c.right + 1; }); }""")
            self.assertTrue(inside, f'a label is clipped at {width}')
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

    def test_no_horizontal_overflow_and_finnish_copy(self):
        for width, height in ((375, 812), (390, 844), (768, 1024), (1280, 800)):
            self.page.set_viewport_size({'width': width, 'height': height})
            self.open()
            self.page.evaluate("document.querySelector('#spending-more').open = true")
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow at {width}')
        self.page.select_option('#language', 'fi')
        self.page.wait_for_timeout(500)
        self.assertEqual(self.page.text_content('#money-title').strip(), 'Mihin rahat menivät')
        self.assertEqual(self.page.text_content('#spending-more .sp5-more-title').strip(), 'Lisää raha-asioistasi')


if __name__ == '__main__':
    unittest.main()
