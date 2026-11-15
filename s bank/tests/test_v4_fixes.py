"""V4 lane F: broken and confusing things, checked without a browser (Node runs the real ES modules).

Rendered checks of the same fixes live in test_v4_fixes_browser.py.
"""
import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

import test_web_contract as contracts

WEB = Path(__file__).resolve().parents[1] / 'web'
DEVELOPER_WORDS = re.compile(r'determin|demo reserve|\bMCC\b|quartile|provenance|reference date|mapping coverage|'
                             r'recurring-pattern|free cash flow|monthly capacity|planning gap|scenario', re.I)


def node_module(test, name, body):
    if not shutil.which('node'):
        test.skipTest('Node is not installed')
    sources = {path.name: path.read_text() for path in WEB.glob('*.js')}
    # Resolve sibling imports so a module can import its neighbours.
    script = 'const sources=' + json.dumps(sources) + ''';
const dataURL=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
const resolved=new Map();
const resolveModule=file=>{if(!resolved.has(file))resolved.set(file,dataURL(sources[file].replace(/from ['"]\\.\\/([^'"]+)['"]/g,(_,n)=>'from "'+resolveModule(n)+'"')));return resolved.get(file);};
const module=await import(resolveModule(''' + json.dumps(name) + '''));
import assert from 'node:assert/strict';
''' + body
    result = subprocess.run(['node', '--input-type=module'], input=script, capture_output=True, text=True, timeout=60)
    test.assertEqual(result.returncode, 0, result.stderr[-4000:])


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class V4FixesTests(unittest.TestCase):
    node_app = contracts.WebContractTests.node_app
    read = contracts.WebContractTests.read

    # ---------- copy ----------
    def test_english_catalogue_has_no_developer_words(self):
        node_module(self, 'i18n.js', r'''
const leaks=Object.entries(module.MESSAGES.en).filter(([key,value])=>''' + 'new RegExp(' + json.dumps(DEVELOPER_WORDS.pattern) + r''','i').test(value));
assert.deepEqual(leaks,[],'Developer wording is visible: '+JSON.stringify(leaks));
for(const key of ['chat.reset.month','chat.reset.persona','chat.reset.language','chat.reset.reset','investment.sources','vat.source.shop','vat.rateRowOne','spending.period.3','spending.period.12','month.previous','month.next'])
  for(const locale of ['en','fi','sv'])assert.ok(String(module.MESSAGES[locale][key]||'').trim(),locale+' '+key);
const en=module.MESSAGES.en;
assert.equal(en['money.income'],en['v3.recap.income'],'Money in has one name');
assert.equal(en['chart.cashflow.spending'],en['v3.recap.spent'],'Spent has one name');
assert.ok(/safety cushion/i.test(en['v3.safe.reserve'])&&/safety cushion/i.test(en['goal.reserve'])&&/safety cushion/i.test(en['safe.reserve']),'One name for the reserve');
assert.equal(en['investment.title'],en['v2.spending.investments'],'The accordion and its card use one title');
''')

    def test_in_app_links_use_a_chevron_not_the_external_link_arrow(self):
        for name in ('index.html', 'app.js', 'v3.js'):
            self.assertNotIn('↗', self.read(name), name)
        node_module(self, 'i18n.js', 'assert.ok(true);')  # module still loads
        self.node_app(r'''
assert.ok(!get('open-story').textContent.includes('↗'));
assert.ok(!get('home-coach-question').textContent.includes('↗'));
''')

    # ---------- page structure ----------
    def test_accordions_have_one_title_and_the_tab_bar_uses_svg_icons(self):
        source = self.read('index.html')
        doc = Document(source)
        ids = {attrs.get('id'): tag for tag, attrs in doc.elements if attrs.get('id')}
        for identifier in ('history-title', 'cashflow-title', 'investment-title', 'vat-title'):
            self.assertEqual(ids.get(identifier), 'summary', identifier + ' must be the accordion summary')
        self.assertNotIn('data-i18n="trends.monthByMonth"', source)
        self.assertNotIn('data-i18n="v3.cashflow.title"', source)
        self.assertNotIn('period-help', source, '"Recorded activity" caption is gone')
        nav = source[source.index('<nav'):source.index('</nav>')]
        self.assertEqual(nav.count('<svg'), 5)
        for glyph in '⌂▥⚑◉':
            self.assertNotIn(glyph, nav)
        self.assertEqual(ids.get('v3-dialog-title'), 'h2', 'Sheets have their title in the header')
        self.assertEqual(ids.get('coach-reset-notice'), 'p')
        css = self.read('styles.css')
        self.assertRegex(css, r'#home-view>#year-banner,#home-view>#home-tax-chip\{grid-column:1/-1\}')
        self.assertRegex(css, r'\n\.visually-hidden\{')
        self.assertIn('#v3-dialog-content .draft-card__actions{position:sticky;bottom:0', css)

    # ---------- dialogs ----------
    def test_draft_dates_use_the_customers_format_and_optional_is_said_once(self):
        node_module(self, 'draft-card.js', r'''
assert.equal(module.formatDateInput('2027-03-31','fi'),'31.3.2027');
assert.equal(module.formatDateInput('2027-03-31','sv'),'2027-03-31');
assert.equal(module.formatDateInput('2027-03-31','en'),'31/03/2027');
for(const text of ['31.3.2027','31/03/2027','2027-03-31',' 31.03.2027 '])assert.equal(module.parseDateInput(text),'2027-03-31',text);
assert.equal(module.parseDateInput('31.2.2027'),null);assert.equal(module.parseDateInput('soon'),null);
const spec={id:'g',kind:'goal',title:'Goal',mode:'edit',fields:[{name:'when',label:'Date',type:'date',value:'2027-03-31',required:true,min:'2026-10-01'},
  {name:'note',label:'A few words (optional)',type:'text',value:''}]};
const fi=module.renderDraftCard({...spec,fields:[spec.fields[0],{name:'note',label:'Muutama sana (valinnainen)',type:'text',value:''}]},'fi');
assert.match(fi,/type="text" inputmode="numeric"[^>]*placeholder="pp\.kk\.vvvv"[^>]*data-draft-input="when"[^>]*value="31\.3\.2027"/);
assert.equal((fi.match(/\(valinnainen\)/g)||[]).length,1,'"(optional)" printed twice');
const en=module.renderDraftCard(spec,'en');
assert.equal((en.match(/\(optional\)/g)||[]).length,1,'"(optional)" printed twice');
assert.match(en,/value="31\/03\/2027"/);
let result=module.validateDraft(spec,{when:'31.3.2027'},'fi');assert.equal(result.values.when,'2027-03-31');
result=module.validateDraft(spec,{when:'1/9/2026'},'en');assert.equal(result.errors.when.code,'minDate');
result=module.validateDraft(spec,{when:'30.2.2027'},'fi');assert.equal(result.errors.when.code,'date');
''')

    # ---------- charts ----------
    def test_trend_axis_uses_month_names_and_change_percent_is_printed_once(self):
        node_module(self, 'charts.js', r'''
const i18n=await import(resolveModule('i18n.js'));
const rows=Array.from({length:12},(_,i)=>{const d=new Date(Date.UTC(2025,9+i,1));return {month:d.toISOString().slice(0,7),total_cents:100000+i};});
for(const [tag,locale] of [['en-FI','en'],['fi-FI','fi'],['sv-FI','sv']]){
  const t=i18n.createI18n({storage:null,navigatorLanguages:[locale]});
  module.configureCharts({locale:tag,translate:(k,v)=>t.t(k,v)});
  const chart=module.trendChart(rows,{interactive:true,selectedIndex:11});
  const labels=[...chart.matchAll(/class="chart-note">([^<]*)</g)].map(m=>m[1]);
  assert.ok(labels.length>=4&&labels.length<=7,locale+' '+labels);
  for(const label of labels)assert.ok(!/\d{2}-\d{2}|^-\d/.test(label),locale+' ISO fragment '+label);
  assert.ok(labels.at(-1).length<=8,'newest month is labelled');
  assert.match(chart,/trend-selected-value/,'selected bar shows its value');
  const panel=module.chartDetailPanel({month:'2026-09',label:'September 2026',total_cents:12000,previous_total_cents:10000,categories:[]},{t:(k,v)=>t.t(k,v)});
  assert.ok(!/%\s*%/.test(panel),locale+' prints %% '+panel);
  assert.match(panel,/20\s?%/);
}
''')

    # ---------- app behaviour ----------
    def test_tabs_write_their_address_and_period_changes_announce_a_new_chat(self):
        self.node_app(r'''
globalThis.location={hash:''};const pushed=[];globalThis.history={pushState(_s,_t,url){pushed.push(url);location.hash=url;},replaceState(_s,_t,url){location.hash=url;}};
for(const [view,hash] of [['trends','#spending'],['goals','#goals'],['profile','#me'],['coach','#coach'],['home','#home']]){
  const button=new Element('nav-'+view);button.dataset.view=view;await documentListeners.click({target:button});
  assert.equal(location.hash,hash,view);
}
assert.deepEqual(pushed,['#spending','#goals','#me','#coach','#home']);
const again=new Element('nav-home');again.dataset.view='home';await documentListeners.click({target:again});
assert.equal(pushed.length,5,'Re-selecting the same tab adds no history entry');
// No chat yet: a month change says nothing.
get('selected-month').value='2026-08';get('selected-month').listeners.change();await settle();
assert.equal(get('coach-reset-notice').hidden,true);
// With a conversation, the customer is told why it disappeared.
app.state.conversation=[{id:'turn-1',message:'Hi',response:{}}];
get('selected-month').value='2026-07';get('selected-month').listeners.change();await settle();
assert.equal(get('coach-reset-notice').hidden,false);assert.match(get('coach-reset-notice').textContent,/new chat for July 2026/);
assert.deepEqual(app.state.conversation,[]);
// The explicit New chat button clears the notice.
const fresh=new Element('new-chat');fresh.setAttribute('data-new-conversation','');await documentListeners.click({target:fresh});
assert.equal(get('coach-reset-notice').hidden,true);
''')

    def test_vat_card_merges_rows_per_rate_and_formats_english_percent(self):
        self.node_app(r'''
app.state.vat={start:'2026-09-01',end:'2026-09-30',gross_spending_cents:10000,covered_spending_cents:10000,estimated_vat_cents:1500,coverage_basis_points:9600,transactions:[],transaction_refs:[],limitations:[],
 by_rate:[{rate_basis_points:1350,transaction_count:2,estimated_vat_cents:500},{rate_basis_points:1350,transaction_count:3,estimated_vat_cents:400},{rate_basis_points:2550,transaction_count:1,estimated_vat_cents:600}]};
get('language').value='en';get('language').listeners.change();await settle();
const html=get('vat-content').innerHTML;
assert.equal((html.match(/13\.5%/g)||[]).length,1,'One row per rate');
assert.match(html,/13\.5% · 5 purchases · ≈ €9\.00/);assert.match(html,/25\.5% · 1 purchase · ≈ €6\.00/);
assert.match(html,/96%/);assert.ok(!/MCC|mapping/.test(html));
''')

    def test_selection_box_is_hidden_until_a_category_is_chosen(self):
        self.node_app(r'''
app.state.categoryRows=[{transaction_ref:'a',category:'Groceries',amount_cents:-2000,transaction_type:'purchase',role:'flexible_essential',date:'2026-09-02'}];
app.state.categoryRowsAvailable=true;
get('language').value='en';get('language').listeners.change();await settle();
assert.equal(get('spending-selection').hidden,true);assert.equal(get('spending-selection').innerHTML,'');
const slice=new Element('slice');slice.dataset.spendingCategory='Groceries';await documentListeners.click({target:slice});
assert.equal(get('spending-selection').hidden,false);assert.equal(get('spending-center-hint').hidden,true);
''')


    def test_notices_never_throw_when_a_sheet_without_sheet_content_is_open(self):
        self.node_app(r'''
// A sheet with neither .sheet-content nor #v3-dialog-content: the notice falls back to the page status area.
const sheet=new Element('v3-dialog');sheet.open=true;sheet.querySelector=()=>null;elements.set('v3-dialog',sheet);
get('wish-title').value='A trip';get('wish-form').listeners.submit({preventDefault(){}});
assert.match(get('status-message').textContent,/wish/i);
// The review sheet (#v3-dialog-content, no .sheet-content) gets its own notice inside the sheet.
const content=new Element('v3-dialog-content');let prepended=null;content.prepend=node=>{prepended=node;};
sheet.querySelector=selector=>selector==='#v3-dialog-content'?content:null;
get('status-message').textContent='';get('wish-title').value='A bike';get('wish-form').listeners.submit({preventDefault(){}});
assert.ok(prepended,'notice is placed inside the open sheet');assert.match(prepended.textContent,/wish/i);
''')

if __name__ == '__main__':
    unittest.main()
