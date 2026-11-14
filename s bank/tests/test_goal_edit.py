"""WP-E backend: goal update/delete, audited and undoable."""
import json
import unittest
from tests.core_helper import demo_connection
from scoach.goals import create_goal, update_goal, delete_goal, link_scenario_to_goal, goal_plan
from scoach.scenarios import create_scenario
from scoach.state import undo_last

CUST = 'CUST00001'


class GoalEditTests(unittest.TestCase):
    def setUp(self):
        self.c = demo_connection()
        self.goal = create_goal(self.c, CUST, 'Trip', 100000, '2027-03-30', as_of='2026-09-30')
        self.other = next(r[0] for r in self.c.execute('SELECT customer_id FROM customers WHERE customer_id!=? ORDER BY customer_id', (CUST,)))

    def tearDown(self): self.c.close()

    def audit_count(self): return self.c.execute('select count(*) from audit_events').fetchone()[0]

    def row(self, goal_id): 
        r = self.c.execute('select * from goals where id=?', (goal_id,)).fetchone()
        return dict(r) if r else None

    def test_update_changes_fields_and_writes_audit(self):
        result = update_goal(self.c, CUST, self.goal['id'], {'name': '  Japan trip ', 'target_cents': 150000, 'current_saved_cents': 2000}, as_of='2026-09-30')
        self.assertEqual(result['name'], 'Japan trip'); self.assertEqual(result['target_cents'], 150000)
        self.assertEqual(result['remaining_cents'], 148000)
        self.assertEqual(sorted(result['changed_fields']), ['current_saved_cents', 'name', 'target_cents'])
        audit = result['audit_event']
        self.assertEqual((audit['action'], audit['scope'], audit['provenance']), ('update_goal', self.goal['id'], 'user'))
        before = json.loads(audit['before_json'])['goals']; after = json.loads(audit['after_json'])['goals']
        self.assertEqual(before[0]['name'], 'Trip'); self.assertEqual(after[0]['name'], 'Japan trip')

    def test_update_validation_writes_nothing(self):
        count = self.audit_count(); original = self.row(self.goal['id'])
        for fields in ({}, {'template': 'trip'}, {'target_cents': 0}, {'target_cents': 1.5}, {'current_saved_cents': -1},
                       {'reserve_floor_cents': -1}, {'name': ''}, {'name': 'x' * 121}, {'target_date': '2026-09-30'},
                       {'target_date': 'not a date'}, {'target_cents': True}):
            with self.assertRaises(ValueError, msg=fields):
                update_goal(self.c, CUST, self.goal['id'], fields, as_of='2026-09-30')
        with self.assertRaises(ValueError):
            update_goal(self.c, CUST, self.goal['id'], {'name': 'Ok'}, provenance='hacker')
        self.assertEqual(self.audit_count(), count); self.assertEqual(self.row(self.goal['id']), original)

    def test_update_target_date(self):
        result = update_goal(self.c, CUST, self.goal['id'], {'target_date': '2027-09-30'}, as_of='2026-09-30')
        self.assertEqual(result['target_date'], '2027-09-30'); self.assertEqual(result['months_remaining'], 12)

    def test_unknown_and_other_customer_goal_rejected(self):
        count = self.audit_count()
        for fn in (lambda: update_goal(self.c, CUST, 'goal:nope', {'name': 'X'}),
                   lambda: delete_goal(self.c, CUST, 'goal:nope'),
                   lambda: update_goal(self.c, self.other, self.goal['id'], {'name': 'X'}),
                   lambda: delete_goal(self.c, self.other, self.goal['id'])):
            with self.assertRaises(ValueError): fn()
        self.assertEqual(self.audit_count(), count); self.assertIsNotNone(self.row(self.goal['id']))

    def test_delete_unlinks_scenarios_and_audits(self):
        scenario = create_scenario(self.c, CUST, '2026-09-01', '2026-09-30')
        link_scenario_to_goal(self.c, CUST, self.goal['id'], scenario['id'])
        result = delete_goal(self.c, CUST, self.goal['id'])
        self.assertEqual(result['unlinked_scenario_ids'], [scenario['id']])
        self.assertIsNone(self.row(self.goal['id']))
        self.assertIsNone(self.c.execute('select goal_id from scenarios where id=?', (scenario['id'],)).fetchone()[0])
        audit = result['audit_event']
        self.assertEqual((audit['action'], audit['scope']), ('delete_goal', self.goal['id']))
        before = json.loads(audit['before_json'])
        self.assertEqual([g['id'] for g in before['goals']], [self.goal['id']])
        self.assertEqual([s['goal_id'] for s in before['scenarios']], [self.goal['id']])
        self.assertEqual(json.loads(audit['after_json'])['goals'], [])

    def test_undo_restores_update(self):
        update_goal(self.c, CUST, self.goal['id'], {'name': 'Changed', 'reserve_floor_cents': 7000})
        undone = undo_last(self.c, CUST)
        self.assertEqual(undone['audit_event']['reverses_event_id'], undone['undone_event_id'])
        row = self.row(self.goal['id'])
        self.assertEqual((row['name'], row['reserve_floor_cents']), ('Trip', 0))

    def test_undo_restores_delete_and_links(self):
        scenario = create_scenario(self.c, CUST, '2026-09-01', '2026-09-30')
        link_scenario_to_goal(self.c, CUST, self.goal['id'], scenario['id'])
        delete_goal(self.c, CUST, self.goal['id'])
        undo_last(self.c, CUST)
        self.assertIsNotNone(self.row(self.goal['id']))
        plan = goal_plan(self.c, CUST, self.goal['id'])
        self.assertEqual(plan['active_scenario_id'], scenario['id'])


if __name__ == '__main__':
    unittest.main()
