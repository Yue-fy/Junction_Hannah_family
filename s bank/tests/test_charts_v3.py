"""V3 chart components: selectable bars, detail panel, cash-flow chart and month-range control."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[1] / 'web'

# Output of the pre-V3 charts.js for the sample below (fresh module, so ids start at chart-1).
# V4: month axis labels are readable month names ("Jul 26", "Aug", "Sept"), not ISO fragments.
ORIGINAL_TREND = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 330 151\" role=\"img\" aria-labelledby=\"chart-1-title chart-1-desc\"><title id=\"chart-1-title\">Complete-month spending trend</title><desc id=\"chart-1-desc\">July 2026: €123.45. August 2026: €234.56. September 2026: €34.56</desc><rect x=\"3\" y=\"57.369542974079124\" width=\"104\" height=\"52.630457025920876\" rx=\"3\" fill=\"#b9cba3\"/><text x=\"2\" y=\"127\" text-anchor=\"start\" class=\"chart-note\">Jul 26</text><rect x=\"113\" y=\"10\" width=\"104\" height=\"100\" rx=\"3\" fill=\"#b9cba3\"/><text x=\"165\" y=\"127\" text-anchor=\"middle\" class=\"chart-note\">Aug</text><rect x=\"223\" y=\"95.26603001364256\" width=\"104\" height=\"14.733969986357435\" rx=\"3\" fill=\"#466d48\"/><text x=\"328\" y=\"127\" text-anchor=\"end\" class=\"chart-note\">Sept</text></svg>"
ORIGINAL_BAR = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 330 130\" role=\"img\" aria-labelledby=\"chart-2-title chart-2-desc\"><title id=\"chart-2-title\">Recorded amounts</title><desc id=\"chart-2-desc\">Groceries: \u20ac45.00. Refund &lt;b&gt;: -\u20ac12.00</desc><text x=\"0\" y=\"12\" class=\"chart-label\"><title>Groceries</title>Groceries</text><text x=\"330\" y=\"30\" text-anchor=\"end\" class=\"chart-value\">\u20ac45.00</text><rect x=\"0\" y=\"39\" width=\"330\" height=\"16\" rx=\"4\" fill=\"#e8ecdf\"/><rect x=\"69.47368421052632\" y=\"39\" width=\"260.5263157894737\" height=\"16\" rx=\"4\" fill=\"#466d48\"/><text x=\"0\" y=\"77\" class=\"chart-label\"><title>Refund &lt;b&gt;</title>Refund &lt;b&gt;</text><text x=\"330\" y=\"95\" text-anchor=\"end\" class=\"chart-value\">-\u20ac12.00</text><rect x=\"0\" y=\"104\" width=\"330\" height=\"16\" rx=\"4\" fill=\"#e8ecdf\"/><rect x=\"0\" y=\"104\" width=\"69.47368421052632\" height=\"16\" rx=\"4\" fill=\"#466d48\"/></svg>"


@unittest.skipUnless(shutil.which('node'), 'Node is required for chart checks')
class ChartsV3Tests(unittest.TestCase):
    def run_node(self, filename, body):
        source = (WEB / filename).read_text()
        script = ('import assert from "node:assert/strict";\n'
                  'const module = await import("data:text/javascript;base64," + Buffer.from(' + json.dumps(source) + ').toString("base64"));\n' + body)
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_output_is_unchanged_when_options_are_omitted(self):
        self.run_node('charts.js', 'const trend=module.trendChart([{month:"2026-07",total_cents:12345},{month:"2026-08",total_cents:23456},{month:"2026-09",total_cents:3456}]);\n'
                      'const bar=module.barChart([{label:"Groceries",value_cents:4500},{label:"Refund <b>",value_cents:-1200}]);\n'
                      'assert.equal(trend,' + json.dumps(ORIGINAL_TREND) + ');\nassert.equal(bar,' + json.dumps(ORIGINAL_BAR) + ');\n'
                      'assert.ok(!module.trendChart([{month:"2026-01",total_cents:1}],{}).includes("data-index"));')

    def test_selection_markup_only_when_interactive(self):
        self.run_node('charts.js', r"""
const rows=[{month:'2026-07',total_cents:100},{month:'2026-08',total_cents:200},{month:'2026-09',total_cents:300}];
const plain=module.trendChart(rows);
assert.ok(!plain.includes('data-index')); assert.ok(!plain.includes('role="button"')); assert.ok(plain.includes('role="img"'));
const chart=module.trendChart(rows,{interactive:true,selectedIndex:1});
assert.equal((chart.match(/role="button"/g)||[]).length,3);
assert.equal((chart.match(/tabindex="0"/g)||[]).length,3);
assert.ok(chart.includes('role="group"'));
assert.match(chart,/data-index="1" aria-label="August 2026: €2.00" aria-pressed="true"/);
assert.match(chart,/data-index="0" aria-label="July 2026: €1.00" aria-pressed="false"/);
assert.equal((chart.match(/aria-pressed="true"/g)||[]).length,1);
assert.ok(chart.includes('is-selected')&&chart.includes('is-dimmed'));
assert.ok(chart.includes('<desc')&&chart.includes('July 2026: €1.00. August 2026: €2.00. September 2026: €3.00'));
assert.match(chart,/class="chart-hit" x="0" y="0" width="110" height="131"/);
assert.ok(chart.includes('--chart-columns:3'));
const none=module.trendChart(rows,{interactive:true});
assert.ok(!none.includes('aria-pressed="true"')); assert.ok(!none.includes('is-dimmed'));
const outOfRange=module.trendChart(rows,{interactive:true,selectedIndex:9});
assert.ok(!outOfRange.includes('aria-pressed="true"'));
const bars=module.barChart([{label:'A <x>',value_cents:100},{label:'B',value_cents:-50}],{interactive:true,selectedIndex:0});
assert.match(bars,/data-index="0" aria-label="A &lt;x&gt;: €1.00" aria-pressed="true"/);
assert.match(bars,/data-index="1" aria-label="B: -€0.50" aria-pressed="false"/);
assert.ok(!bars.includes('<x>'));
assert.ok(!module.barChart([{label:'A',value_cents:100}]).includes('data-index'));
assert.ok(!module.barChart([{label:'A',value_cents:100}],{selectedIndex:0}).includes('aria-pressed'),'selectedIndex alone does not make a chart interactive');
""")

    def test_selection_wiring_calls_back_with_index_and_is_idempotent(self):
        self.run_node('charts.js', r"""
const listeners={};
const container={addEventListener:(type,fn)=>{(listeners[type]??=[]).push(fn);},removeEventListener:(type,fn)=>{listeners[type]=listeners[type].filter(x=>x!==fn);},contains:()=>true};
const bar=index=>({getAttribute:name=>name==='data-index'?String(index):null});
const target=index=>({closest:selector=>selector==='[data-index]'?bar(index):null});
const calls=[];
const detach=module.attachChartSelection(container,index=>calls.push(['first',index]));
const again=module.attachChartSelection(container,index=>calls.push(['second',index]));
assert.equal(detach,again);
assert.equal(listeners.click.length,1); assert.equal(listeners.keydown.length,1);
let prevented=0;
listeners.click[0]({type:'click',target:target(2)});
listeners.keydown[0]({type:'keydown',key:'Enter',target:target(0),preventDefault:()=>prevented++});
listeners.keydown[0]({type:'keydown',key:' ',target:target(1),preventDefault:()=>prevented++});
listeners.keydown[0]({type:'keydown',key:'a',target:target(1),preventDefault:()=>prevented++});
listeners.click[0]({type:'click',target:{closest:()=>null}});
assert.deepEqual(calls,[['second',2],['second',0],['second',1]]);
assert.equal(prevented,2);
assert.equal(module.chartSelectionIndex({type:'click',target:target(3)},{contains:()=>false}),null);
detach();
assert.equal(listeners.click.length,0); assert.equal(listeners.keydown.length,0);
module.attachChartSelection(container,()=>{});
assert.equal(listeners.click.length,1,'re-attaching after detach binds again');
assert.equal(typeof module.attachChartSelection(null,()=>{}),'function');
""")

    def test_detail_panel_escapes_and_reports_change_in_text(self):
        self.run_node('charts.js', r"""
const html=module.chartDetailPanel({month:'2026-09"><x',label:'<script>alert(1)</script>',total_cents:12000,previous_total_cents:10000,
  categories:[{label:'<img src=x>',total_cents:5000},{label:'B',total_cents:4000},{label:'C',total_cents:2000},{label:'D',total_cents:1000}]});
assert.ok(!html.includes('<script>')); assert.ok(!html.includes('<img')); assert.ok(html.includes('&lt;script&gt;'));
assert.ok(html.includes('data-chart-transactions="2026-09&quot;&gt;&lt;x"'));
assert.ok(html.includes('data-chart-ask="2026-09&quot;&gt;&lt;x"'));
assert.match(html,/is-up/); assert.match(html,/↑/); assert.match(html,/Up €20.00 \(\+20%\) vs previous month/);
assert.equal((html.match(/<li>/g)||[]).length,3); assert.ok(!html.includes('>D<'));
assert.match(html,/See transactions/); assert.match(html,/Ask coach about this month/);
const down=module.chartDetailPanel({month:'2026-09',total_cents:5000,previous_total_cents:10000},{money:v=>'EUR'+v,t:(key,values,fallback)=>key==='chart.detail.total'?'Yhteensä':key});
assert.match(down,/Down EUR5000 \(-50%\)/); assert.match(down,/Yhteensä/); assert.match(down,/No category breakdown/);
assert.match(module.chartDetailPanel({month:'m',total_cents:100}),/No previous month/);
assert.match(module.chartDetailPanel({month:'m',total_cents:100,previous_total_cents:0}),/Up €1.00 vs previous month/);
assert.match(module.chartDetailPanel({month:'m',total_cents:100,previous_total_cents:100}),/Same as previous month/);
assert.equal(module.chartDetailPanel({month:'m'}),'');
""")

    def test_cashflow_chart_handles_negative_net_and_partial_periods(self):
        # V5 fix (lane SP2): drawn at the real width with an HTML legend, y gridlines and a left-over strip.
        self.run_node('charts.js', r"""
const rows=[{label:'2026-07',period:'2026-07',income_cents:300000,consumption_cents:250000,savings_transfers_cents:20000,net_cents:30000,complete:true},
 {label:'2026-08',period:'2026-08',income_cents:300000,consumption_cents:350000,savings_transfers_cents:20000,net_cents:-70000,complete:true},
 {label:'<b>2026-09',income_cents:100000,consumption_cents:50000,savings_transfers_cents:0,net_cents:50000,complete:false}];
const chart=module.cashflowChart(rows,{width:360});
assert.match(chart,/^<div class="cf5"><ul class="cf5-legend"/,'the legend is HTML above the chart, so it wraps');
assert.match(chart,/width="360" height="\d+" viewBox="0 0 360 \d+"/,'drawn in real pixels'); assert.match(chart,/role="img"/);
assert.ok((chart.match(/class="cf5-ylabel"/g)||[]).length>=3,'y gridline labels');
assert.match(chart,/>€2k</); assert.match(chart,/>€4k</);
assert.match(chart,/class="cashflow-zero/,'negative left-over needs a zero line');
assert.match(chart,/<pattern id="cashflow-\d+-hatch"/); assert.match(chart,/fill="url\(#cashflow-\d+-hatch\)"/);
assert.match(chart,/Partial period/); assert.match(chart,/>Partial</);
assert.match(chart,/Money in/); assert.match(chart,/Money out/);
assert.equal((chart.match(/class="cashflow-net cf5-left/g)||[]).length,3); assert.match(chart,/cf5-left is-negative/);
assert.match(chart,/>Jul 26</); assert.match(chart,/>Aug</);
assert.match(chart,/\(partial period\)/);
assert.ok(!chart.includes('<b>')); assert.ok(!chart.includes('NaN'));
assert.ok(!chart.includes('data-index'));
const positive=module.cashflowChart([rows[0]]);
assert.ok(!positive.includes('cashflow-zero')); assert.ok(!positive.includes('Partial'));
const live=module.cashflowChart(rows,{interactive:true,selectedIndex:2});
assert.equal((live.match(/role="button"/g)||[]).length,3);
assert.match(live,/data-index="2" aria-label="&lt;b&gt;2026-09: money in €1,000.00, money out €500.00, net €500.00 \(partial period\)" aria-pressed="true"/);
assert.match(live,/class="cf5-left-value"[^>]*>€500</,'the selected column names its left-over amount');
// The highlight band stays inside the plot: it never reaches the legend (HTML) or the month labels.
const band=/class="cf5-band" x="[\d.]+" y="([\d.]+)" width="[\d.]+" height="([\d.]+)"/.exec(live);
const labelY=Number(/class="cf5-xlabel[^"]*" x="[\d.]+" y="([\d.]+)"/.exec(live)[1]);
assert.ok(Number(band[1])>=0 && Number(band[1])+Number(band[2])<labelY-10);
// Narrow phones: every label stays inside the width; month names never crowd.
const twelve=Array.from({length:12},(_,i)=>({period:`2026-${String(i+1).padStart(2,'0')}`,income_cents:250000,consumption_cents:200000,left_over_cents:50000,complete:true}));
const narrow=module.cashflowChart(twelve,{width:280});
assert.ok((narrow.match(/class="cf5-xlabel/g)||[]).length<=5);
for(const m of narrow.matchAll(/class="cf5-xlabel[^"]*" x="([\d.]+)"/g))assert.ok(Number(m[1])>=0&&Number(m[1])<=280);
const gap=module.cashflowChart([{label:'a',income_cents:1,consumption_cents:2},{label:'b',income_cents:'x',consumption_cents:2}]);
assert.ok(!gap.includes('cf5-left')); assert.ok(!gap.includes('NaN'));
assert.match(module.cashflowChart([]),/empty-state/);
// Axis money: "€1k" in English, "1 000 €" in Finnish and Swedish (never "t." or "tn").
assert.equal(module.axisEuro(150000),'€1.5k'); assert.equal(module.axisEuro(80000),'€800');
module.configureCharts({locale:'fi-FI'}); assert.equal(module.axisEuro(100000).replace(/\s/g,' '),'1 000 €');
module.configureCharts({locale:'sv-FI'}); assert.ok(!/tn|t\./.test(module.axisEuro(18000000)));
""")

    def test_clamp_and_step_range_edges(self):
        self.run_node('month-range.js', r"""
const {clampRange,stepRange,lastMonthsRange,monthSpan}=module;
const pick=r=>[r.start,r.end,r.months];
const bounds={min:'2024-11',max:'2026-10',maxSpan:24};
assert.deepEqual(pick(clampRange({...bounds,start:'2020-01',end:'2030-01'})),['2024-11','2026-10',24]);
assert.deepEqual(pick(clampRange({...bounds,start:'2026-05',end:'2025-02'})),['2025-02','2026-05',16],'reversed ends swap');
assert.deepEqual(pick(clampRange({...bounds,start:'2026-05',end:'2025-02',anchor:'start'})),['2026-05','2026-05',1]);
assert.deepEqual(pick(clampRange({...bounds,start:'2026-05',end:'2025-02',anchor:'end'})),['2025-02','2025-02',1]);
assert.deepEqual(pick(clampRange({min:'2020-01',max:'2026-10',maxSpan:12,start:'2024-01',end:'2026-01'})),['2025-02','2026-01',12],'span trims start by default');
assert.deepEqual(pick(clampRange({min:'2020-01',max:'2026-10',maxSpan:12,start:'2024-01',end:'2026-01',anchor:'start'})),['2024-01','2024-12',12]);
assert.deepEqual(pick(clampRange({...bounds,start:'bad',end:null})),['2025-11','2026-10',12],'malformed values fall back to 12 months ending at max');
assert.deepEqual(pick(clampRange({min:'2026-10',max:'2024-11',start:'2025-01',end:'2025-03'})),['2025-01','2025-03',3],'min/max reversed');
assert.throws(()=>clampRange({start:'2025-01',end:'2025-02'}));
assert.deepEqual(pick(stepRange({...bounds,start:'2025-11',end:'2026-10'},'start',-1)),['2025-10','2026-10',13]);
assert.deepEqual(pick(stepRange({...bounds,start:'2025-11',end:'2026-10'},'start',1)),['2025-12','2026-10',11]);
assert.deepEqual(pick(stepRange({...bounds,start:'2024-11',end:'2026-10'},'start',-1)),['2024-11','2026-10',24],'cannot pass min');
assert.deepEqual(pick(stepRange({min:'2020-01',max:'2026-10',maxSpan:24,start:'2024-11',end:'2026-10'},'start',-1)),['2024-10','2026-09',24],'max span moves the end');
assert.deepEqual(pick(stepRange({...bounds,start:'2026-03',end:'2026-03'},'start',1)),['2026-04','2026-04',1],'shrinking past end pushes end');
assert.deepEqual(pick(stepRange({...bounds,start:'2026-10',end:'2026-10'},'start',1)),['2026-10','2026-10',1]);
assert.deepEqual(pick(stepRange({...bounds,start:'2025-12',end:'2026-01'},'end',-3)),['2025-10','2025-10',1]);
assert.deepEqual(pick(stepRange({...bounds,start:'2025-12',end:'2026-01'},'start',-1)),['2025-11','2026-01',3],'year boundary');
assert.deepEqual(pick(lastMonthsRange({...bounds,end:'2026-03'})),['2025-04','2026-03',12]);
assert.deepEqual(pick(lastMonthsRange({min:'2026-01',max:'2026-10'})),['2026-01','2026-10',10],'short history');
assert.equal(monthSpan('2025-12','2026-01'),2); assert.equal(monthSpan('2026-02','2026-01'),0);
""")

    def test_month_range_markup_and_event_wiring(self):
        self.run_node('month-range.js', r"""
const html=module.renderMonthRange({start:'2025-11',end:'2026-10',min:'2025-06',max:'2026-10',monthLabel:m=>'<'+m+'>',defaultEnd:'2026-09'});
assert.equal((html.match(/<select/g)||[]).length,2);
assert.equal((html.match(/<option/g)||[]).length,34);
assert.match(html,/<option value="2025-11" selected>&lt;2025-11&gt;<\/option>/);
assert.match(html,/data-month-range-step="-1">−1 month/); assert.match(html,/data-month-range-step="1">\+1 month/);
assert.match(html,/data-month-range-reset>Last 12 months/); assert.match(html,/data-default-end="2026-09"/);
assert.ok(!html.includes('<2025'));
const atMin=module.renderMonthRange({start:'2025-06',end:'2025-06',min:'2025-06',max:'2025-06'});
assert.match(atMin,/data-month-range-step="-1" disabled/); assert.match(atMin,/data-month-range-step="1" disabled/);
// Fake DOM for event wiring
const attrs={'data-min':'2025-06','data-max':'2026-10','data-max-span':'24','data-default-end':'2026-09'};
const from={value:'2025-11'}, to={value:'2026-10'};
const root={getAttribute:n=>attrs[n]??null,querySelector:s=>s==='[data-month-range-from]'?from:s==='[data-month-range-to]'?to:null};
const el=(own,extra={})=>({closest:s=>s==='[data-month-range]'?root:(own.some(a=>s.includes(a))?button:null),hasAttribute:n=>own.includes(n),getAttribute:n=>extra[n]??null,...extra});
let button;
const listeners={};
const container={addEventListener:(t,f)=>{(listeners[t]??=[]).push(f);},removeEventListener:(t,f)=>{listeners[t]=listeners[t].filter(x=>x!==f);}};
const seen=[];
const detach=module.attachMonthRange(container,r=>seen.push([r.start,r.end,r.months]));
assert.equal(module.attachMonthRange(container,r=>seen.push([r.start,r.end,r.months])),detach);
assert.equal(listeners.change.length,1); assert.equal(listeners.click.length,1);
from.value='2026-12'; // out of bounds then clamped; start anchored -> end follows
listeners.change[0]({type:'change',target:el(['data-month-range-from'])});
from.value='2025-11'; to.value='2025-01';
listeners.change[0]({type:'change',target:el(['data-month-range-to'])});
to.value='2026-10';
button=el(['data-month-range-step'],{getAttribute:n=>n==='data-month-range-step'?'-1':null,disabled:false});
listeners.click[0]({type:'click',target:button});
button=el(['data-month-range-reset'],{disabled:false});
listeners.click[0]({type:'click',target:button});
button={...el(['data-month-range-step'],{getAttribute:()=>'1'}),disabled:true};
listeners.click[0]({type:'click',target:button});
listeners.click[0]({type:'click',target:{closest:()=>null}});
assert.deepEqual(seen,[['2026-10','2026-10',1],['2025-06','2025-06',1],['2025-10','2026-10',13],['2025-10','2026-09',12]]);
detach(); assert.equal(listeners.click.length,0); assert.equal(listeners.change.length,0);
""")

    def test_stylesheet_covers_components_with_touch_targets(self):
        css = (WEB / 'charts-v3.css').read_text()
        for selector in ('.chart-bar.is-selected', '.chart-bar.is-dimmed', '.chart-bar:focus-visible', '.chart-detail', '.chart-detail-actions button', '.month-range', '.month-range-field select', '.month-range-actions button'):
            self.assertIn(selector, css)
        self.assertGreaterEqual(css.count('min-height: 44px'), 3)
        for variable in ('--green', '--ink', '--muted', '--line', '--wash', '--radius'):
            self.assertIn('var(' + variable, css)


if __name__ == '__main__':
    unittest.main()
