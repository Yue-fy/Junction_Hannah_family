import unittest
from tests.core_helper import demo_connection
from scoach.goals import create_goal, goal_plan, link_scenario_to_goal
from scoach.scenarios import create_scenario
from scoach.money import percentile_cents

class GoalTests(unittest.TestCase):
    def setUp(self): self.c=demo_connection()
    def tearDown(self): self.c.close()
    def test_upward_contribution_reserve_capacity_and_link_are_planning_only(self):
        g=create_goal(self.c,'CUST00001','My trip',10000,'2027-01-30',current_saved_cents=1,reserve_floor_cents=99999999,as_of='2026-09-30')
        self.assertEqual(g['required_monthly_cents'],2500); self.assertEqual(g['remaining_cents'],9999)
        self.assertEqual(g['upfront_available_cents'],0); self.assertEqual(len(g['cashflow_months']),6)
        self.assertEqual(g['conservative_monthly_contribution_cents'],max(percentile_cents([m['free_cashflow_cents'] for m in g['cashflow_months']],.25),0))
        s=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30')
        linked=link_scenario_to_goal(self.c,'CUST00001',g['id'],s['id'],as_of='2026-09-30')
        self.assertEqual(linked['modeled_scenario_contribution_cents'],4514); self.assertFalse(linked['observed'])
        self.assertIn('audit_event',linked); self.assertEqual(self.c.execute('select count(*) from transactions').fetchone()[0],3068)
    def test_invalid_inputs_rejected(self):
        for kw in ({'target_cents':0},{'target_date':'2026-01-01'},{'current_saved_cents':-1},{'reserve_floor_cents':-1},{'name':''}):
            args=dict(name='Goal',target_cents=10000,target_date='2027-01-30',as_of='2026-09-30'); args.update(kw)
            with self.assertRaises(ValueError): create_goal(self.c,'CUST00001',**args)

    def test_historical_reference_does_not_use_future_balance_and_short_history_is_labeled(self):
        from scoach.db import connect, initialize_schema
        c=connect(':memory:'); initialize_schema(c); c.execute("INSERT INTO customers VALUES('C','00100',30,'{}')")
        for i,(day,balance) in enumerate([('2026-08-31',10000),('2026-09-30',90000)]):
            c.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(str(i),'C','A',day,'31X26:12:00:00','Salary',10000,balance,'salary',None,None,i,'h','{}'))
        c.commit(); g=create_goal(c,'C','Buffer',20000,'2027-01-01',reserve_floor_cents=5000,as_of='2026-08-31')
        self.assertEqual(g['upfront_available_cents'],5000)
        self.assertFalse(g['capacity_available']); self.assertEqual(g['conservative_monthly_contribution_cents'],0)
        c.close()

    def test_duplicate_or_overlapping_goal_link_is_rejected_without_mutation(self):
        goal=create_goal(self.c,'CUST00001','Trip',100000,'2027-03-30',as_of='2026-09-30')
        first=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',percent=20)
        overlapping=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',percent=30)
        link_scenario_to_goal(self.c,'CUST00001',goal['id'],first['id'])
        count=self.c.execute('select count(*) from audit_events').fetchone()[0]
        for scenario_id in (first['id'],overlapping['id']):
            with self.assertRaises(ValueError): link_scenario_to_goal(self.c,'CUST00001',goal['id'],scenario_id)
        self.assertEqual(self.c.execute('select count(*) from audit_events').fetchone()[0],count)
        plan=goal_plan(self.c,'CUST00001',goal['id'])
        self.assertEqual(plan['modeled_scenario_contribution_cents'],4514)
        self.assertEqual(len(plan['linked_scenarios']),1)

    def test_goal_scenario_contribution_is_capped_by_remaining_target(self):
        goal=create_goal(self.c,'CUST00001','Small goal',5000,'2027-03-30',current_saved_cents=4000,as_of='2026-09-30')
        scenario=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',percent=100)
        plan=link_scenario_to_goal(self.c,'CUST00001',goal['id'],scenario['id'])
        self.assertEqual(plan['modeled_scenario_contribution_cents'],1000)
        self.assertEqual(plan['linked_scenarios'][0]['modeled_monthly_contribution_cents'],22570)

    def test_invalid_historical_reference_creates_no_goal_or_audit(self):
        counts=[self.c.execute(f'select count(*) from {table}').fetchone()[0] for table in ('goals','audit_events')]
        with self.assertRaises(ValueError):
            create_goal(self.c,'CUST00001','Invalid history',10000,'2027-01-01',as_of='1900-01-01')
        self.assertEqual([self.c.execute(f'select count(*) from {table}').fetchone()[0] for table in ('goals','audit_events')],counts)

    def test_legacy_multiple_links_do_not_double_count_existing_savings(self):
        goal=create_goal(self.c,'CUST00001','Trip',100000,'2027-03-30',as_of='2026-09-30')
        first=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',percent=20)
        second=create_scenario(self.c,'CUST00001','2026-09-01','2026-09-30',percent=30)
        self.c.execute('update scenarios set goal_id=? where id in (?,?)',(goal['id'],first['id'],second['id'])); self.c.commit()
        plan=goal_plan(self.c,'CUST00001',goal['id'])
        self.assertEqual(plan['modeled_scenario_contribution_cents'],6771)
        self.assertEqual(plan['inactive_linked_scenario_ids'],[first['id']])
