import unittest
from tests.core_helper import demo_connection
from scoach.ledger import transactions
from scoach.analytics import month_summary
from scoach.scenarios import create_scenario, exclude_from_scenario, scenario_result
from scoach.state import undo_last

class ScenarioTests(unittest.TestCase):
    def setUp(self): self.c=demo_connection()
    def tearDown(self): self.c.close()
    def test_gold_exclusion_is_scenario_only_and_undoable(self):
        s=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30')
        self.assertEqual(s['modeled_monthly_contribution_cents'],4514)
        rows=transactions(self.c,'CUST00001','2026-09-01','2026-09-30',{'category':'Restaurants'})
        ref=next(r['transaction_ref'] for r in rows if r['amount_cents']==-3647)
        changed=exclude_from_scenario(self.c,'CUST00001',s['id'],ref)
        self.assertEqual(changed['adjustable_base_cents'],18923)
        self.assertEqual(changed['modeled_monthly_contribution_cents'],3785)
        self.assertEqual(month_summary(self.c,'CUST00001','2026-09',{'category':'Restaurants'})['total_cents'],22570)
        self.assertEqual(changed['excluded_transaction_refs'],[ref]); self.assertFalse(changed['observed'])
        undo_last(self.c,'CUST00001'); self.assertEqual(scenario_result(self.c,'CUST00001',s['id'])['modeled_monthly_contribution_cents'],4514)
        with self.assertRaises(ValueError): create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',percent=101)
    def test_transfer_and_essential_cannot_be_default_adjustment(self):
        with self.assertRaises(ValueError): create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',category='Invest Deposit')
        with self.assertRaises(ValueError): create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',category='Housing')

    def test_monthly_scenario_requires_one_complete_month(self):
        for start,end in [('2026-09-02','2026-09-30'),('2026-08-01','2026-09-30')]:
            with self.assertRaises(ValueError): create_scenario(self.c,'CUST00001',start,end)

    def test_invalid_scenario_percentage_is_validation_error(self):
        for value in ('not-money',True,'NaN','Infinity'):
            with self.assertRaises(ValueError): create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',percent=value)

    def test_corrections_revalidate_existing_scenario_without_rewriting_actuals(self):
        from scoach.state import classify_row, create_matching_rule
        scenario=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30')
        rows=transactions(self.c,'CUST00001','2026-09-01','2026-09-30',{'category':'Restaurants'})
        ref=next(r['transaction_ref'] for r in rows if r['amount_cents']==-3647)
        classify_row(self.c,'CUST00001',ref,'flexible_essential')
        changed=scenario_result(self.c,'CUST00001',scenario['id'])
        self.assertEqual(changed['actual_total_cents'],22570)
        self.assertEqual(changed['adjustable_base_cents'],18923)
        self.assertEqual(changed['modeled_monthly_contribution_cents'],3785)
        self.assertEqual(changed['eligibility_status'],'stale')
        self.assertIn(ref,changed['ineligible_transaction_refs'])
        self.assertNotIn(ref,changed['transaction_refs'])
        create_matching_rule(self.c,'CUST00001','Restaurants','fixed_obligation')
        changed=scenario_result(self.c,'CUST00001',scenario['id'])
        self.assertEqual(changed['adjustable_base_cents'],0)
        self.assertEqual(changed['modeled_monthly_contribution_cents'],0)
        self.assertEqual(changed['eligibility_status'],'invalid')
        self.assertEqual(changed['actual_total_cents'],22570)
