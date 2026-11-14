"""Behavior contracts for the category ring and progressive financial overview."""
import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[1] / 'web'


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.nodes = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


class RedesignVisualTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for the chart behavior checks')
    def test_category_ring_filters_empty_rows_and_preserves_exact_selection_labels(self):
        source = (WEB / 'charts.js').read_text()
        harness = '''
import assert from 'node:assert/strict';
const chart=await import('data:text/javascript;base64,'+Buffer.from(SOURCE).toString('base64'));
chart.configureCharts({locale:'en-IE',translate:key=>key});
const ring=chart.spendingRing([
 {category:'Restaurants',label:'Eating out',total_cents:2000},
 {category:'Groceries',label:'Groceries',total_cents:3000},
 {category:'Zero',total_cents:0}, {category:'Negative',total_cents:-100},
 {category:'Missing'}, {category:'Nonfinite',total_cents:Infinity}
], 'Groceries');
assert.equal((ring.match(/class="ring-segment"/g)||[]).length,2);
assert.equal((ring.match(/tabindex="0"/g)||[]).length,2);
assert.ok(ring.includes('role="group"'));
assert.ok(ring.includes('role="button"'));
assert.match(ring,/aria-label="Eating out: €20.00 · 40%"/);
assert.match(ring,/aria-pressed="true" data-spending-category="Groceries"/);
assert.match(ring,/aria-pressed="false" data-spending-category="Restaurants"/);
assert.ok(ring.includes('has-selection'));
assert.ok(!ring.includes('NaN'));
assert.ok(!ring.includes('Infinity'));
assert.ok(!ring.includes('data-spending-category="Zero"'));
const noSelection=chart.spendingRing([{category:'Restaurants',total_cents:2000}],'Unavailable');
assert.ok(!noSelection.includes('has-selection'));
assert.ok(chart.spendingRing([]).includes('No recorded spending'));
assert.equal(Object.keys(chart.categoryPalette).length,10);
'''
        result = subprocess.run(['node', '--input-type=module', '-e', 'const SOURCE=' + json.dumps(source) + ';\n' + harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the chart behavior checks')
    def test_category_labels_are_escaped_in_interactive_chart_markup(self):
        source = (WEB / 'charts.js').read_text()
        harness = '''
import assert from 'node:assert/strict';
const chart=await import('data:text/javascript;base64,'+Buffer.from(SOURCE).toString('base64'));
const ring=chart.spendingRing([{category:'<img src=x>',label:'" onfocus="bad',total_cents:125}]);
assert.ok(!ring.includes('<img'));
assert.ok(!ring.includes('aria-label="" onfocus'));
assert.ok(ring.includes('&lt;img src=x&gt;'));
assert.ok(ring.includes('&quot; onfocus=&quot;bad'));
assert.ok(!chart.categoryIcon('<script>').includes('<script>'));
'''
        result = subprocess.run(['node', '--input-type=module', '-e', 'const SOURCE=' + json.dumps(source) + ';\n' + harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_overview_has_distinct_spending_balance_coaching_and_journal_landmarks(self):
        doc = Elements((WEB / 'index.html').read_text())
        ids = [attrs['id'] for _, attrs in doc.nodes if 'id' in attrs]
        self.assertEqual(len(ids), len(set(ids)), 'Moved account information must not create duplicate IDs')
        required = {'balance-card', 'home-coach-card', 'home-coach-question', 'spending-donut', 'spending-categories', 'spending-total', 'spending-selection', 'journal-view', 'journal-timeline', 'notebook-content', 'goal-milestone'}
        self.assertTrue(required.issubset(ids))
        self.assertTrue(any(attrs.get('data-view') == 'journal' for _, attrs in doc.nodes))
        self.assertTrue(any(attrs.get('id') == 'spending-selection' and attrs.get('aria-live') == 'polite' for _, attrs in doc.nodes))
        self.assertTrue(any(tag == 'details' and 'basket-explanation' in attrs.get('class', '') for tag, attrs in doc.nodes))
        self.assertGreaterEqual(sum('data-open-coach' in attrs for _, attrs in doc.nodes), 2)


if __name__ == '__main__':
    unittest.main()
