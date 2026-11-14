"""Goal planning must use the selected account and preserve existing assignments."""
import tempfile
import unittest
from pathlib import Path

from scoach.api import Application
from scoach.db import connect, initialize_schema
from scoach.goals import create_goal, goal_plan, link_scenario_to_goal
from scoach.scenarios import create_scenario


class GoalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(':memory:')
        initialize_schema(self.conn)
        self.addCleanup(self.conn.close)
        for customer in ('LONG', 'SHORT'):
            self.conn.execute('INSERT INTO customers VALUES(?,?,?,?)', (customer, '00100', 30, '{}'))
        for month in range(4, 10):
            self.add_row('LONG', f'2026-{month:02d}-30', 100000, 'Salary', 'salary')
        for month in (8, 9):
            self.add_row('SHORT', f'2026-{month:02d}-30', 100000, 'Salary', 'salary')
        self.add_row('SHORT', '2026-09-15', -10000, 'Restaurants', 'purchase')
        self.conn.commit()

    def add_row(self, customer, day, amount, category, kind):
        ref = f'{customer}-{day}-{kind}'
        self.conn.execute(
            'INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (ref, customer, customer + '-account', day, day + 'T12:00:00', category,
             amount, 200000, kind, None, None, 1, ref, '{}'),
        )

    def test_another_customers_history_cannot_supply_missing_goal_capacity_months(self):
        short = create_goal(self.conn, 'SHORT', 'New account plan', 300000, '2027-03-30')
        self.assertFalse(short['capacity_available'], 'Two observed months cannot establish six-month capacity')
        self.assertEqual([row['month'] for row in short['cashflow_months']], ['2026-08', '2026-09'])
        self.assertEqual(short['conservative_monthly_contribution_cents'], 0)
        self.assertTrue(all(row['customer_id'] == 'SHORT' for row in short['cashflow_months']))

        long = create_goal(self.conn, 'LONG', 'Established account plan', 300000, '2027-03-30')
        self.assertTrue(long['capacity_available'])
        self.assertEqual(long['conservative_monthly_contribution_cents'], 100000)

    def test_a_scenario_cannot_be_silently_moved_between_goals(self):
        first = create_goal(self.conn, 'SHORT', 'First goal', 10000, '2027-03-30')
        second = create_goal(self.conn, 'SHORT', 'Second goal', 10000, '2027-03-30')
        scenario = create_scenario(self.conn, 'SHORT', '2026-09-01', '2026-09-30', percent=20)
        link_scenario_to_goal(self.conn, 'SHORT', first['id'], scenario['id'])
        audits = self.conn.execute('SELECT count(*) FROM audit_events').fetchone()[0]

        with self.assertRaisesRegex(ValueError, 'already.*linked'):
            link_scenario_to_goal(self.conn, 'SHORT', second['id'], scenario['id'])

        self.assertEqual(goal_plan(self.conn, 'SHORT', first['id'])['modeled_scenario_contribution_cents'], 2000)
        self.assertEqual(goal_plan(self.conn, 'SHORT', second['id'])['modeled_scenario_contribution_cents'], 0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM audit_events').fetchone()[0], audits)

    def test_api_rejects_a_second_goal_link_without_changing_the_original(self):
        first = create_goal(self.conn, 'SHORT', 'First goal', 10000, '2027-03-30')
        second = create_goal(self.conn, 'SHORT', 'Second goal', 10000, '2027-03-30')
        scenario = create_scenario(self.conn, 'SHORT', '2026-09-01', '2026-09-30', percent=20)
        link_scenario_to_goal(self.conn, 'SHORT', first['id'], scenario['id'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'goals.sqlite3'
            target = connect(path)
            self.conn.backup(target)
            target.close()
            app = Application(path)
            status, response = app.handle('POST', '/api/goals/link', {
                'customer_id': 'SHORT', 'goal_id': second['id'],
                'scenario_id': scenario['id'], 'confirmed': True,
            })
            self.assertEqual(status, 400)
            self.assertEqual(response['error']['code'], 'validation_error')
            status, response = app.handle('GET', '/api/goals?customer_id=SHORT')
            self.assertEqual(status, 200)
            amounts = {goal['id']: goal['modeled_scenario_contribution_cents'] for goal in response['data']['goals']}
            self.assertEqual(amounts, {first['id']: 2000, second['id']: 0})
