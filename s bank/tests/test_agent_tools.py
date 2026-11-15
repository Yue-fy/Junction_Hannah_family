from decimal import Decimal
import json

from agent_helper import AgentFixture
from scoach import analytics, forecast, goals, scenarios, statistics
from scoach.ledger import transactions


class AgentToolsTests(AgentFixture):
    def setUp(self):
        super().setUp()
        from scoach.agent_tools import ToolContext
        self.ctx = ToolContext(self.conn, self.customer, '2026-09', message='Plan a €600 goal with €150 per month by March 2027.')

    def tool(self, tool_name, **args):
        from scoach.agent_tools import dispatch
        result = dispatch(self.conn, self.customer, self.ctx, tool_name, args)
        self.assertIn('evidence_id', result)
        self.assertTrue(result['basis'])
        self.assertEqual(set(result['period']), {'start', 'end'})
        sent = json.dumps(result)
        for forbidden in ('CUST', 'ACC', 'tx:', 'raw_json', 'row_hash', 'transaction_ref'):
            self.assertNotIn(forbidden, sent)
        return result

    def test_spending_and_comparison_reuse_verified_statistics(self):
        args = {'start': '2026-09-01', 'end': '2026-09-30', 'category': 'Restaurants'}
        total = self.tool('spending_total', **args)
        raw = statistics.transaction_statistics(self.conn, self.customer, args['start'], args['end'], {'category': 'Restaurants', 'consumption_only': 'true'})
        self.assertEqual(total['total_cents'], 22570)
        self.assertEqual(total['total'], '€225.70')
        self.assertEqual(total['average_outflow_cents'], raw['average_outflow_cents'])
        self.assertEqual(total['count'], 2)
        result = self.tool('compare_periods', **args, comparison_start='2026-08-01', comparison_end='2026-08-31')
        self.assertEqual(result['outflow_delta_cents'], 0)
        self.assertEqual(result['percent_change'], '0.00')
        self.assertEqual(result['current']['outflow_total_cents'], raw['outflow_total_cents'])
        self.assertEqual(self.ctx.evidence[total['evidence_id']]['count'], 2)

    def test_overview_has_selected_period_balance_not_future_balance(self):
        result = self.tool('get_overview', month='2026-08')
        raw = analytics.money_map(self.conn, self.customer, '2026-08')
        self.assertEqual(result['consumption_cents'], raw['consumption_cents'])
        baskets = [{k: v for k, v in row.items() if k != 'share_percent'} for row in result['baskets']]
        self.assertEqual(baskets, self.ctx.sanitize(analytics.three_basket_profile(self.conn, self.customer, '2026-08')['baskets']))
        # Shares are precomputed so the model never derives percentages itself.
        total = sum(row['amount_cents'] for row in result['baskets'])
        for row in result['baskets']:
            self.assertEqual(row['share_percent'], format((Decimal(row['amount_cents']) * 100 / total).quantize(Decimal('.1')), 'f'))
        self.assertEqual(result['balance_cents'], transactions(self.conn, self.customer, end='2026-08-31')[-1]['balance_after_cents'])
        self.assertLess(result['balance_date'], '2026-09-01')

    def test_trend_returns_exact_points_and_announces_capped_lists(self):
        result = self.tool('monthly_trend', months=24, category='Restaurants')
        raw = analytics.trend_series(self.conn, self.customer, '2026-09', 24, {'category': 'Restaurants', 'consumption_only': 'true'})
        # Time series are the explicit 24-point exception to the 20-item list cap.
        self.assertEqual([p['value_cents'] for p in result['chart']['series']], [m['total_cents'] for m in raw['months']])
        self.assertEqual(len(result['chart']['series']), 24)

    def test_transactions_are_capped_sorted_and_allowlisted(self):
        result = self.tool('list_transactions', start='2026-01-01', end='2026-09-30', limit=20, sort='largest')
        self.assertEqual(len(result['transactions']), 20)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['transactions'][0]['amount_cents'], -60000)
        self.assertEqual(set(result['transactions'][0]), {'date', 'weekday', 'category', 'transaction_type', 'amount_cents', 'amount', 'merchant_id', 'mcc_code'})

    def test_forecast_safe_recurring_and_payday_match_existing_engines(self):
        # V4: one spending plan until payday. A legacy seven-day request gets the same numbers.
        safe = self.tool('safe_to_spend', horizon='week', days=7, reserve_floor_cents=50000)
        raw = forecast.spending_plan(self.conn, self.customer, '2026-09-28', reserve_floor_cents=50000)
        self.assertEqual(safe['this_week_cents'], raw['this_week_cents'])
        payday = self.tool('safe_to_spend')
        raw_payday = forecast.safe_until_payday(self.conn, self.customer, '2026-09-28')
        self.assertEqual(payday['this_week_cents'], raw_payday['this_week_cents'])
        self.assertEqual(payday['per_day_cents'], raw_payday['per_day_cents'])
        self.assertEqual(safe['this_week_cents'], payday['this_week_cents'])
        save = self.tool('safe_to_save')
        self.assertEqual(save['safe_to_save_cents'], raw_payday['extra_cents'])
        # Daily life until payday and what could be saved never overlap; the model sees only these figures
        # (the free-choice part and free money are hidden so they cannot be quoted as the total).
        raw_save = forecast.spending_plan(self.conn, self.customer, '2026-09-28')
        self.assertEqual(save['daily_life_cents'], raw_save['daily_life_cents'])
        self.assertEqual(save['daily_life_cents'] - save['everyday_cents'] + save['extra_cents'], raw_save['free_cents'])
        self.assertNotIn('spendable_until_payday_cents', save)
        self.assertNotIn('free_cents', save)
        preview = self.tool('forecast_30_days')
        raw_preview = forecast.preview_30_days(self.conn, self.customer, '2026-09-28')
        self.assertEqual(preview['ending_balance_cents'], raw_preview['projected'][-1]['balance_cents'])
        self.assertEqual(preview['lowest_balance_cents'], min(x['balance_cents'] for x in raw_preview['projected']))
        recurring = self.tool('recurring_payments')
        self.assertEqual([x['amount_cents'] for x in recurring['items']], [x['amount_cents'] for x in forecast.detect_recurring(self.conn, self.customer, '2026-09-28') if x['amount_cents'] < 0])
        payday = self.tool('payday_pattern')
        self.assertEqual(payday['payday']['qualified'], analytics.payday_timing_signal(self.conn, self.customer, '2026-09')['qualified'])
        self.assertEqual(payday['salary']['qualified'], analytics.salary_change_signal(self.conn, self.customer, '2026-09')['qualified'])

    def test_scenarios_goals_and_actions_never_persist(self):
        before = self.conn.total_changes
        preview = self.tool('what_if_reduce', category='Restaurants', percent=20)
        raw = scenarios.preview_spending_adjustment(self.conn, self.customer, '2026-09-01', '2026-09-30', 'Restaurants', 20)
        self.assertEqual(preview['monthly_freed_cents'], raw['modeled_monthly_contribution_cents'])
        self.assertEqual(preview['yearly_freed_cents'], 54168)
        plan = self.tool('goal_plan', name='Buffer', target_cents=60000, target_date='2027-03-28', monthly_cents=15000)
        self.assertEqual(plan['required_monthly_cents'], 10000)
        self.assertEqual(plan['months_needed'], 4)
        self.tool('propose_action', kind='create_goal', params=plan['proposal'])
        self.tool('propose_action', kind='save_scenario', params=preview['proposal'])
        self.tool('propose_action', kind='open_view', params={'view': 'trends'})
        self.assertEqual(len(self.ctx.actions), 3)
        self.assertEqual(self.tool('list_goals')['goals'], [])
        self.assertEqual(self.conn.total_changes, before)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM audit_events').fetchone()[0], 0)

    def test_list_goals_reuses_existing_progress_without_writing(self):
        saved = goals.create_goal(self.conn, self.customer, 'Buffer', 60000, '2027-03-28', current_saved_cents=12000, as_of='2026-09-28')
        before = self.conn.total_changes
        result = self.tool('list_goals')
        self.assertEqual(result['goals'][0]['remaining_cents'], saved['remaining_cents'])
        self.assertEqual(result['goals'][0]['required_monthly_cents'], saved['required_monthly_cents'])
        self.assertEqual(self.conn.total_changes, before)

    def test_calculate_uses_sourced_literals_and_rejects_code(self):
        self.tool('spending_total', start='2026-09-01', end='2026-09-30', category='Restaurants')
        result = self.tool('calculate', expression='225.70 * (12 / 100)')
        self.assertEqual(result['value'], '27.084')
        self.assertEqual(result['value_cents'], 2708)
        self.assertEqual(result['rounding'], 'Euro display rounded half up to cents; value is unrounded.')
        for expression in ('amount', 'sum([1])', '(1).__class__', '2 ** 3', '"45"', '1 / 0', '9999 + 1', 'True + 1', '1 // 2', '2 % 1', '1e99999'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.tool('calculate', expression=expression)

    def test_calculate_accepts_a_negative_sourced_literal(self):
        self.ctx.results.append({'delta_cents': -4514})
        result = self.tool('calculate', expression='-45.14 * 12')
        self.assertEqual(result['value_cents'], -54168)

    def test_goal_target_must_be_sourced_and_model_labels_do_not_authorize_it(self):
        with self.assertRaises(ValueError):
            self.tool('goal_plan', name='Ideal buffer', target_cents=9999900, target_date='2027-03-28')
        with self.assertRaises(ValueError):
            self.tool('goal_plan', name='Buffer €99999', target_cents=9999900, target_date='2027-03-28')

    def test_selected_historical_month_uses_its_last_recorded_day(self):
        from scoach.agent_tools import ToolContext
        self.ctx = ToolContext(self.conn, self.customer, '2026-08')
        self.assertEqual(self.ctx.reference_date, '2026-08-28')
        # A legacy seven-day request gets the same until-payday plan (V4: one answer).
        result = self.tool('safe_to_spend', days=7)
        self.assertEqual(result['as_of'], '2026-08-28')
        self.assertGreater(result['next_payday'], '2026-08-28')
        again = self.tool('safe_to_spend')
        self.assertEqual({k: v for k, v in result.items() if k != 'evidence_id'}, {k: v for k, v in again.items() if k != 'evidence_id'})

    def test_redaction_preserves_ordinary_words_and_short_id_substrings(self):
        from scoach.agent_tools import redact
        self.assertEqual(redact('The customer account is accurate.'), 'The customer account is accurate.')
        self.assertNotIn('CUST', redact('CUST_TEST ACC123 tx:12:secret'))
        self.ctx.private_values = ('C', 'A')
        self.assertEqual(self.ctx.sanitize('Category ABC; ids C and A.'), 'Category ABC; ids [private identifier] and [private identifier].')

    def test_glossary_is_bounded_and_unknown_topics_are_honest(self):
        self.assertTrue(self.tool('explain_concept', topic='emergency fund')['known'])
        self.assertFalse(self.tool('explain_concept', topic='best shares')['known'])

    def test_invalid_arguments_cannot_expand_scope_or_write(self):
        cases = [
            ('get_overview', {'month': '2027-01'}),
            ('get_overview', {'customer_id': 'OTHER'}),
            ('spending_total', {'start': '2026-09-30', 'end': '2026-09-01'}),
            ('spending_total', {'start': '2026-09-01', 'end': '2026-09-30', 'category': 'Fake'}),
            ('spending_total', {'start': '2026-09-01', 'end': '2026-09-30', 'mcc_code': 'x'}),
            ('list_transactions', {'start': '2026-09-01', 'end': '2026-09-30', 'limit': 21}),
            ('monthly_trend', {'months': True}),
            ('monthly_trend', {'months': 25}),
            ('safe_to_spend', {'reserve_floor_cents': -1}),
            ('what_if_reduce', {'category': 'Restaurants', 'percent': float('nan')}),
            ('goal_plan', {'name': 'Goal', 'target_cents': 500, 'target_date': '2026-09-29'}),
            ('propose_action', {'kind': 'create_goal', 'params': {'confirmed': True}}),
            ('propose_action', {'kind': 'open_view', 'params': {'view': 'javascript:bad'}}),
            ('reset', {}),
        ]
        for name, args in cases:
            with self.subTest(tool=name, args=args), self.assertRaises(ValueError):
                self.tool(name, **args)
