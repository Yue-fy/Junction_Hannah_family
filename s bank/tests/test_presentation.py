"""Presentation math must reconcile with source rows and preserve answer scope."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[1] / 'web'

@unittest.skipUnless(shutil.which('node'), 'Node is required for presentation checks')
class PresentationTests(unittest.TestCase):
    def test_category_totals_scope_forecast_and_milestones(self):
        source = (WEB/'presentation.js').read_text()
        script = 'import assert from "node:assert/strict";\nconst p=await import("data:text/javascript;base64,"+Buffer.from('+json.dumps(source)+').toString("base64"));\n'+r'''
const rows=[
 {category:'Restaurants',amount_cents:-1001,transaction_type:'purchase'},
 {category:'Groceries',amount_cents:-2000,transaction_type:'purchase'},
 {category:'Housing',amount_cents:-50000,transaction_type:'housing_payment'},
 {category:'Investment',amount_cents:-20000,transaction_type:'investment_deposit'},
 {category:'Restaurants',amount_cents:100,transaction_type:'refund'},
 {category:'Salary',amount_cents:100000,transaction_type:'salary'}
];
const all=p.spendingCategories(rows);
assert.equal(all.reduce((sum,row)=>sum+row.total_cents,0),53001);
assert.equal(p.spendingCategories(rows,'everyday').reduce((sum,row)=>sum+row.total_cents,0),3001);
assert.deepEqual(p.spendingCategories(rows,'home').map(row=>row.category),['Housing']);
assert.deepEqual(p.spendingCategories([]),[]);
assert.deepEqual(p.toolScope({query_scope:{start:'2026-08-01',end:'2026-08-31',filters:{mcc_code:'4121'}},tool_result:{filters:{category:'Transportation'}}},'2026-09'),{month:'2026-08',start:'2026-08-01',end:'2026-08-31',mcc_code:'4121'});
assert.equal(p.forecastSummary(null),null);
assert.deepEqual(p.forecastSummary({projected:[{date:'2026-10-01',balance_cents:20000},{date:'2026-10-02',balance_cents:10000},{date:'2026-10-03',balance_cents:30000}]}),{end_cents:30000,end_date:'2026-10-03',low_cents:10000,low_date:'2026-10-02'});
assert.equal(p.milestoneFor([]),null);
assert.deepEqual(p.milestoneFor([{name:'A trip',target_cents:100000,current_saved_cents:30000}]),{name:'A trip',percent:30,next:50,remaining_cents:20000});
'''
        result = subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
