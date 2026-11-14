"""Local JSON/static boundary; service code owns every financial calculation."""
import calendar
import json
import mimetypes
import os
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .coach import interpret, rank_candidates
from .db import connect
from .money import cents_to_euros


class APIError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def _decorate(value):
    if isinstance(value, list):
        return [_decorate(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _decorate(item) for key, item in value.items()}
    for key, item in value.items():
        if key.endswith('_cents') and type(item) is int:
            result[key[:-6] + '_display'] = cents_to_euros(item)
    if value.get('observed') is True:
        result['status'] = 'observed'
    elif value.get('scenario') is True or value.get('observed') is False:
        result['status'] = 'scenario'
    return result


def _month_bounds(month):
    if not isinstance(month, str) or len(month) != 7:
        raise ValueError('month must use YYYY-MM')
    first = date.fromisoformat(month + '-01')
    return first.isoformat(), first.replace(day=calendar.monthrange(first.year, first.month)[1]).isoformat()


def _previous_month(month):
    value = date.fromisoformat(month + '-01')
    return f'{value.year - (value.month == 1):04d}-{12 if value.month == 1 else value.month - 1:02d}'


def _bounded_materiality(cents):
    """Map absolute change to 0–1; changes of at least EUR 100 reach the cap."""
    if type(cents) is not int:
        return 0.0
    return float(min(Decimal(1), Decimal(abs(cents)) / Decimal(10_000)))


class Application:
    def __init__(self, database='var/scoach.sqlite3', web_root=None, *, coach_transport=None):
        self.database = Path(database)
        self.web_root = Path(web_root) if web_root else Path(__file__).resolve().parent.parent / 'web'
        self.coach_transport = coach_transport

    def handle(self, method, target, payload=None):
        try:
            data = self._route(method, target, payload)
            return 200, {'ok': True, 'data': _decorate(data)}
        except APIError as error:
            return error.status, {'ok': False, 'error': {'code': error.code, 'message': str(error)}}
        except (ValueError, TypeError, KeyError) as error:
            return 400, {'ok': False, 'error': {'code': 'validation_error', 'message': str(error)}}
        except sqlite3.Error:
            return 503, {'ok': False, 'error': {'code': 'database_unavailable', 'message': 'Demo database unavailable. Build the demo database first.'}}

    def _route(self, method, target, payload):
        parsed = urlsplit(target)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        if any(len(values) != 1 for values in query.values()):
            raise ValueError('Repeated query parameters are not supported')
        query = {key: values[0] for key, values in query.items()}
        get_routes = {'/api/health', '/api/personas', '/api/overview', '/api/comparison', '/api/transactions', '/api/trends', '/api/forecast', '/api/safe-to-spend', '/api/investments', '/api/financing', '/api/statistics', '/api/statistics/compare', '/api/taxes', '/api/vat', '/api/goals'}
        post_routes = {'/api/scenarios', '/api/scenarios/exclude', '/api/rules', '/api/goals', '/api/goals/link', '/api/coach', '/api/tax-plan', '/api/undo', '/api/reset'}
        if path not in get_routes | post_routes:
            raise APIError(404, 'not_found', 'Unknown API endpoint')
        if (method == 'GET' and path not in get_routes) or (method == 'POST' and path not in post_routes) or method not in {'GET', 'POST'}:
            raise APIError(405, 'method_not_allowed', 'Method not allowed')
        self._validate_tool_query(path, query)
        if method == 'POST' and not isinstance(payload, dict):
            raise ValueError('JSON body must be an object')
        body = payload or {}
        if method == 'POST':
            self._validate_body(path, body)
        if path == '/api/health':
            return {
                'status': 'ok',
                'database_ready': self.database.is_file(),
                'gemini_optional': True,
                'gemini_configured': bool(os.environ.get('GEMINI_API_KEY') or self.coach_transport),
            }
        if not self.database.is_file():
            raise APIError(503, 'database_unavailable', 'Demo database missing. Run scripts/build_demo_db.py first.')
        if method == 'POST' and path != '/api/coach' and body.get('confirmed') is not True:
            raise ValueError('This action requires explicit customer confirmation (confirmed: true)')
        if body.get('provenance', 'user') not in {'user', 'gemini_proposed_user_confirmed'}:
            raise ValueError('Invalid mutation provenance')
        conn = connect(self.database)
        try:
            from .ledger import account_scope, transactions
            from .analytics import latest_complete_month, money_map, compare_periods, trend_series
            if path == '/api/personas':
                aliases = {'CUST00001': ('Alex', 'Everyday spending'), 'CUST00676': ('Robin', 'Payday timing'), 'CUST05097': ('Sam', 'Unusual travel purchase'), 'CUST00756': ('Jules', 'Income growth'), 'CUST00296': ('Taylor', 'Optional home goal'), 'CUST01331': ('Kai', 'Young-adult payday timing')}
                return {'personas': [{'customer_id': row[0], 'name': aliases.get(row[0], ('Demo customer', 'Personal money coach'))[0], 'story': aliases.get(row[0], ('Demo customer', 'Personal money coach'))[1]} for row in conn.execute('SELECT customer_id FROM customers ORDER BY customer_id')]}
            customer_id = body.get('customer_id', query.get('customer_id', 'CUST00001'))
            if not isinstance(customer_id, str) or not conn.execute('SELECT 1 FROM customers WHERE customer_id=?', (customer_id,)).fetchone():
                raise APIError(404, 'unknown_customer', 'Unknown demo persona')
            scope = account_scope(conn, customer_id)
            account_id = body.get('account_id', query.get('account_id'))
            if account_id is not None and account_id != scope['account_id']:
                raise ValueError('Account does not belong to the selected customer')
            month = body.get('month', query.get('month', latest_complete_month(conn, customer_id)))
            start, end = _month_bounds(month)
            if month < scope['observed_start'][:7] or month > scope['observed_end'][:7]:
                raise ValueError('month is outside observed history')
            if query.get('as_of') and not scope['observed_start'] <= query['as_of'] <= scope['observed_end']:
                raise ValueError('as_of is outside observed history')
            filters = {key: query[key] for key in ['category', 'role', 'merchant_id', 'transaction_type'] if query.get(key)} or None
            if method == 'GET':
                if path == '/api/overview':
                    overview = money_map(conn, customer_id, month)
                    context = self._coach_context(conn, customer_id, month)
                    from .scenarios import scenario_result
                    persisted = [scenario_result(conn, customer_id, row[0]) for row in conn.execute('SELECT id FROM scenarios WHERE customer_id=? ORDER BY created_at,id', (customer_id,))]
                    for item in persisted:
                        item['monthly_contribution_cents'] = item['modeled_monthly_contribution_cents']
                    personalized = [item for item in context['candidates'] if not item.get('utility', False)]
                    priority = rank_candidates(personalized)[0] if personalized else None
                    return {**overview, 'scenarios': persisted, 'priority': priority, **context, 'transaction_refs': overview['transaction_refs'], 'forecast': self._forecast(conn, customer_id)}
                if path == '/api/comparison':
                    comparison = query.get('comparison_month', _previous_month(month))
                    pstart, pend = _month_bounds(comparison)
                    return compare_periods(conn, customer_id, start, end, pstart, pend, filters or {'category': 'Restaurants'})
                if path == '/api/transactions':
                    rows = transactions(conn, customer_id, query.get('start', start), query.get('end', end), filters)
                    ref = query.get('transaction_ref')
                    if ref:
                        rows = [row for row in rows if row['transaction_ref'] == ref]
                        if not rows:
                            raise APIError(404, 'unknown_reference', 'Unknown transaction reference in selected scope')
                    return {**scope, 'transactions': rows, 'transaction_refs': [row['transaction_ref'] for row in rows], 'status': 'observed', 'month': month}
                if path == '/api/trends':
                    return trend_series(conn, customer_id, month, int(query.get('months', 12)), filters)
                if path == '/api/forecast':
                    return self._forecast(conn, customer_id, query)
                if path == '/api/safe-to-spend':
                    from .forecast import safe_to_spend
                    reference_date = query.get('as_of') or min(end, scope['observed_end'])
                    reserve = int(query['reserve_floor_cents']) if 'reserve_floor_cents' in query else None
                    return safe_to_spend(
                        conn,
                        customer_id,
                        as_of=reference_date,
                        days=int(query.get('days', 7)),
                        reserve_floor_cents=reserve,
                    )
                if path == '/api/investments':
                    from .analytics import investment_cashflows
                    return investment_cashflows(conn, customer_id, month, int(query.get('months', 12)))
                if path == '/api/financing':
                    from .financing import financing_context
                    return financing_context(conn, customer_id, query.get('goal_type', 'home'))
                if path == '/api/statistics':
                    from .statistics import transaction_statistics
                    statistic_filters = self._validated_statistics_filters(conn, customer_id, filters)
                    if 'start' in query:
                        statistic_start, statistic_end = query['start'], query['end']
                    else:
                        statistic_start, statistic_end = start, end
                    return transaction_statistics(conn, customer_id, statistic_start, statistic_end, statistic_filters)
                if path == '/api/statistics/compare':
                    from .statistics import compare_transaction_statistics
                    statistic_filters = self._validated_statistics_filters(conn, customer_id, filters)
                    if 'start' in query:
                        current_start, current_end = query['start'], query['end']
                        comparison_start, comparison_end = query['comparison_start'], query['comparison_end']
                    else:
                        current_start, current_end = start, end
                        comparison_start, comparison_end = _month_bounds(query['comparison_month'])
                    return compare_transaction_statistics(conn, customer_id, current_start, current_end, comparison_start, comparison_end, statistic_filters)
                if path == '/api/taxes':
                    from .tax import observed_tax_evidence
                    if 'start' in query:
                        tax_start, tax_end = query['start'], query['end']
                    elif 'month' in query:
                        tax_start, tax_end = start, end
                    else:
                        tax_start = tax_end = None
                    return observed_tax_evidence(conn, customer_id, tax_start, tax_end)
                if path == '/api/vat':
                    from .vat import vat_lens
                    if 'start' in query:
                        vat_start, vat_end = query['start'], query['end']
                    else:
                        vat_start, vat_end = start, end
                    return vat_lens(conn, customer_id, vat_start, vat_end)
                if path == '/api/goals':
                    from .goals import goal_plan
                    return {**scope, 'goals': [goal_plan(conn, customer_id, row[0]) for row in conn.execute('SELECT id FROM goals WHERE customer_id=? ORDER BY created_at,id', (customer_id,))]}
            if path == '/api/coach':
                locale = body.get('locale', 'en')
                if locale not in {'en', 'fi', 'sv'}:
                    raise ValueError('locale must be en, fi, or sv')
                context = self._coach_context(conn, customer_id, month, locale)
                response = interpret(body.get('message'), context, transport=self.coach_transport)
                return self._execute_coach_tool(conn, customer_id, response, context)
            if path == '/api/tax-plan':
                from .tax import tax_planning_scenario
                for required in ('amount_cents', 'due_date', 'reference_date'):
                    if required not in body:
                        raise ValueError('Missing ' + required)
                return tax_planning_scenario(
                    body['amount_cents'], body['due_date'], body['reference_date'],
                    already_set_aside_cents=body.get('already_set_aside_cents', 0),
                    current_balance_cents=body.get('current_balance_cents'),
                    reserve_floor_cents=body.get('reserve_floor_cents', 0),
                    set_aside_location=body.get('set_aside_location', 'inside_current_balance'),
                    label=body.get('label', 'Tax planning amount'),
                )
            return self._mutate(conn, path, customer_id, month, body)
        finally:
            conn.close()

    @staticmethod
    def _validate_body(path, body):
        common = {'customer_id', 'account_id', 'month', 'confirmed', 'provenance'}
        fields = {
            '/api/scenarios': {'category', 'percent', 'name'},
            '/api/scenarios/exclude': {'scenario_id', 'transaction_ref'},
            '/api/rules': {'type', 'transaction_ref', 'role', 'category', 'merchant_id', 'label'},
            '/api/goals': {'name', 'target_cents', 'target_date', 'current_saved_cents', 'reserve_floor_cents', 'template'},
            '/api/goals/link': {'goal_id', 'scenario_id'},
            '/api/tax-plan': {'amount_cents', 'due_date', 'reference_date', 'already_set_aside_cents', 'current_balance_cents', 'reserve_floor_cents', 'set_aside_location', 'label'},
            '/api/coach': {'message', 'locale'}, '/api/undo': set(), '/api/reset': set(),
        }
        if set(body) - common - fields.get(path, set()):
            raise ValueError('Unknown JSON body field')
        for name, value in body.items():
            if name == 'confirmed':
                if type(value) is not bool:
                    raise ValueError('confirmed must be a boolean')
            elif name == 'current_balance_cents':
                if type(value) is not int:
                    raise ValueError('current_balance_cents must be signed integer cents')
            elif name == 'amount_cents':
                if type(value) is not int or value <= 0:
                    raise ValueError('amount_cents must be positive integer cents')
            elif name.endswith('_cents'):
                if type(value) is not int or value < 0:
                    raise ValueError(name + ' must be nonnegative integer cents')
            elif name == 'percent':
                if type(value) not in {str, int, float}:
                    raise ValueError('percent must be a decimal percentage')
                try:
                    percentage = Decimal(str(value))
                except InvalidOperation:
                    raise ValueError('percent must be a decimal percentage') from None
                if not percentage.is_finite() or not 0 <= percentage <= 100:
                    raise ValueError('percent must be between zero and one hundred')
            elif value is None and name in {'merchant_id', 'label'}:
                pass
            elif not isinstance(value, str):
                raise ValueError(name + ' must be a string')

    @staticmethod
    def _validate_tool_query(path, query):
        common = {'customer_id', 'account_id'}
        allowed = {
            '/api/statistics': common | {'month', 'start', 'end', 'category', 'role', 'transaction_type', 'merchant_id'},
            '/api/statistics/compare': common | {'month', 'comparison_month', 'start', 'end', 'comparison_start', 'comparison_end', 'category', 'role', 'transaction_type', 'merchant_id'},
            '/api/taxes': common | {'month', 'start', 'end'},
            '/api/vat': common | {'month', 'start', 'end'},
        }
        if path not in allowed:
            return
        if set(query) - allowed[path]:
            raise ValueError('Unknown query parameter')
        for field in ('category', 'role', 'transaction_type', 'merchant_id'):
            if field in query and not query[field].strip():
                raise ValueError('Statistics filters must be nonempty')
        has_dates = any(key in query for key in ('start', 'end'))
        if path == '/api/statistics':
            if has_dates and not all(key in query for key in ('start', 'end')):
                raise ValueError('start and end must be provided together')
            if not has_dates and 'month' not in query:
                raise ValueError('month or explicit start and end are required')
            if has_dates and 'month' in query:
                raise ValueError('Use month or explicit dates, not both')
        elif path == '/api/statistics/compare':
            date_fields = ('start', 'end', 'comparison_start', 'comparison_end')
            if any(key in query for key in date_fields):
                if not all(key in query for key in date_fields) or 'month' in query or 'comparison_month' in query:
                    raise ValueError('Provide all four comparison dates or two months')
            elif not all(key in query for key in ('month', 'comparison_month')):
                raise ValueError('month and comparison_month are required')
        elif path in {'/api/taxes', '/api/vat'}:
            if has_dates and not all(key in query for key in ('start', 'end')):
                raise ValueError('start and end must be provided together')
            if has_dates and 'month' in query:
                raise ValueError('Use month or explicit dates, not both')
            if not has_dates and 'month' not in query:
                raise ValueError('month or explicit start and end are required')

    @staticmethod
    def _filter_catalog(conn, customer_id, *, bounded=False):
        from .ledger import transactions
        rows = transactions(conn, customer_id)
        values = {
            'categories': sorted({row['category'] for row in rows if row['category']}),
            'roles': sorted({row['role'] for row in rows if row['role']}),
            'transaction_types': sorted({row['transaction_type'] for row in rows if row['transaction_type']}),
            'merchant_ids': sorted({row['merchant_id'] for row in rows if row['merchant_id']}),
        }
        if bounded:
            limits = {'categories': 64, 'roles': 8, 'transaction_types': 32, 'merchant_ids': 100}
            values = {key: items[:limits[key]] for key, items in values.items()}
        return values

    @classmethod
    def _validated_statistics_filters(cls, conn, customer_id, filters):
        filters = filters or {}
        catalog = cls._filter_catalog(conn, customer_id)
        mapping = {'category': 'categories', 'role': 'roles', 'transaction_type': 'transaction_types', 'merchant_id': 'merchant_ids'}
        for key, value in filters.items():
            if value not in catalog[mapping[key]]:
                raise ValueError('Unknown statistics ' + key)
        return filters

    def _forecast(self, conn, customer_id, query=None):
        from .forecast import preview_30_days
        query = query or {}
        assumptions = json.loads(query.get('assumptions', '{}'))
        if not isinstance(assumptions, dict):
            raise ValueError('assumptions must be an object keyed by recurring item ID')
        for edits in assumptions.values():
            if not isinstance(edits, dict) or set(edits) - {'enabled', 'amount_cents', 'median_day'}:
                raise ValueError('Unknown recurring assumption fields')
            if 'enabled' in edits and type(edits['enabled']) is not bool:
                raise ValueError('enabled must be a boolean')
            for key in ['amount_cents', 'median_day']:
                if key in edits and type(edits[key]) is not int:
                    raise ValueError(key + ' must be an integer')
        return preview_30_days(conn, customer_id, as_of=query.get('as_of'), assumptions=assumptions)


    def _coach_context(self, conn, customer_id, month, locale='en'):
        from .ledger import month_bounds, account_scope
        from .analytics import compare_periods, unusual_candidates, investment_cashflows, salary_change_signal, payday_timing_signal
        from .forecast import safe_to_spend
        from .financing import financing_context
        start, end = month_bounds(month)
        comparison_month = _previous_month(month)
        pstart, pend = month_bounds(comparison_month)
        facts, candidates = [], []
        try:
            comparison = compare_periods(conn, customer_id, start, end, pstart, pend, {'category': 'Restaurants'})
            facts.append({'id': comparison['fact_id'], 'value_cents': comparison['delta_cents'], 'unit': 'cents', 'label': 'Restaurant spending change', 'status': 'observed', 'transaction_refs': comparison['transaction_refs']})
            if comparison['current']['count']:
                text = 'Restaurant visits stayed level; average purchase size changed.' if comparison['count_delta'] == 0 else 'Restaurant spending changed. Compare visits and average purchase size.'
                candidates.append({'id': 'restaurant_change', 'kind': 'explain_change', 'text': text, 'fact_ids': [comparison['fact_id']], 'materiality': _bounded_materiality(comparison['delta_cents']), 'urgency': 0, 'explainability': 1, 'addressability': 1, 'transaction_refs': comparison['current']['transaction_refs'], 'status': 'observed'})
        except ValueError:
            pass
        for item in unusual_candidates(conn, customer_id, month):
            facts.append({'id': item['fact_id'], 'value_cents': item['amount_cents'], 'unit': 'cents', 'label': item['label'], 'status': 'observed', 'transaction_refs': item['transaction_refs']})
            candidates.append({'id': item['candidate_id'], 'kind': 'explain_change', 'text': 'A purchase is unusual for your earlier pattern. Would you like to review it?', 'fact_ids': [item['fact_id']], 'materiality': _bounded_materiality(item['amount_cents']), 'urgency': 1, 'explainability': 1, 'addressability': 1, 'transaction_refs': item['transaction_refs'], 'status': 'observed'})
        salary_change = salary_change_signal(conn, customer_id, month)
        if salary_change['qualified']:
            direction = salary_change['direction']
            facts.append({'id': salary_change['fact_id'], 'value_cents': salary_change['delta_cents'], 'unit': 'cents', 'label': salary_change['label'], 'status': 'observed', 'direction': direction, 'change_basis_points': salary_change['change_basis_points'], 'threshold_basis_points': salary_change['threshold_basis_points'], 'recent_period': salary_change['recent_period'], 'baseline_period': salary_change['baseline_period'], 'transaction_refs': salary_change['transaction_refs'], 'other_income_excluded': True})
            candidates.append({'id': 'salary_change', 'kind': 'salary_change', 'text': f"Your recent salary-only level {direction}d compared with the earlier baseline. Other income is kept separate.", 'fact_ids': [salary_change['fact_id']], 'materiality': min(1.0, abs(salary_change['change_basis_points']) / salary_change['threshold_basis_points']), 'urgency': .25, 'explainability': 1, 'addressability': 1, 'transaction_refs': salary_change['transaction_refs'], 'status': 'observed'})
        payday = payday_timing_signal(conn, customer_id, month)
        if payday['qualified']:
            threshold = max(payday['low_balance_threshold_cents'], 1)
            gap = max(0, threshold - payday['lowest_pre_salary_balance_cents'])
            facts.append({'id': payday['fact_id'], 'value_cents': payday['lowest_pre_salary_balance_cents'], 'unit': 'cents', 'label': payday['label'], 'status': 'observed', 'period': payday['period'], 'lookback_days': payday['lookback_days'], 'low_balance_threshold_cents': payday['low_balance_threshold_cents'], 'observed_window_count': payday['observed_window_count'], 'low_balance_event_count': payday['low_balance_event_count'], 'transaction_refs': payday['transaction_refs']})
            candidates.append({'id': 'payday_timing', 'kind': 'payday_timing', 'text': 'Across several observed pay cycles, your balance reached a low point before salary arrived. This is a timing pattern, not a prediction.', 'fact_ids': [payday['fact_id']], 'materiality': min(1.0, gap / threshold), 'urgency': .5, 'explainability': 1, 'addressability': 1, 'transaction_refs': payday['transaction_refs'], 'status': 'observed'})
        scope = account_scope(conn, customer_id)
        reference_date = min(end, scope['observed_end'])
        safe = safe_to_spend(conn, customer_id, reference_date, days=7)
        facts.append({'id': safe['fact_id'], 'value_cents': safe['safe_to_spend_cents'], 'unit': 'cents', 'label': safe['label'], 'status': 'scenario', 'available': safe['available'], 'reserve_floor_cents': safe['reserve_floor_cents'], 'reserve_floor_source': safe['reserve_floor_source']})
        safe_text = 'This estimate protects the sourced reserve, upcoming outflows, and a buffer based on earlier flexible spending.' if safe['available'] else 'There is not enough observed history yet to estimate a safe-to-spend amount.'
        candidates.append({'id': 'safe_to_spend', 'kind': 'safe_to_spend', 'copy_key': 'safe_to_spend' if safe['available'] else 'safe_unavailable', 'text': safe_text, 'fact_ids': [safe['fact_id']], 'materiality': _bounded_materiality(safe['safe_to_spend_cents']), 'urgency': 1, 'explainability': 1, 'addressability': 1, 'transaction_refs': safe['transaction_refs'], 'status': 'scenario', 'available': safe['available'], 'utility': True})
        investing = investment_cashflows(conn, customer_id, month, 12)
        facts.append({'id': investing['fact_id'], 'value_cents': investing['net_contributions_cents'], 'unit': 'cents', 'label': investing['label'], 'status': 'observed'})
        candidates.append({'id': 'investment_cashflow', 'kind': 'investment_cashflow', 'text': 'These are observed contributions and withdrawals, not portfolio value or performance.', 'fact_ids': [investing['fact_id']], 'materiality': _bounded_materiality(investing['total_contributions_cents']), 'urgency': 0, 'explainability': 1, 'addressability': 1, 'transaction_refs': investing['transaction_refs'], 'status': 'observed', 'utility': True})
        financing = financing_context(conn, customer_id, 'home')
        if financing['available']:
            facts.append({'id': financing['fact_id'], 'value_cents': financing['requested_loan_cents'], 'unit': 'cents', 'label': 'Linked historical home-financing context', 'status': 'observed', 'historical_context_only': True, 'event_refs': financing['event_refs'], 'recorded_fees_total_cents': financing['recorded_fees_total_cents']})
            candidates.append({'id': 'home_financing_history', 'kind': 'home_financing_history', 'copy_key': 'home_financing_history', 'text': 'Linked past mortgage data is historical context only. It is not a current approval or affordability assessment.', 'fact_ids': [financing['fact_id']], 'materiality': 1, 'urgency': 0, 'explainability': 1, 'addressability': 1, 'transaction_refs': [], 'event_refs': financing['event_refs'], 'status': 'observed', 'historical_context_only': True})
        return {**scope, 'period': month, 'comparison_period': comparison_month, 'reference_date': reference_date, 'days': 7, 'months': 12, 'interface_locale': locale, 'filter_catalog': self._filter_catalog(conn, customer_id, bounded=True), 'facts': facts, 'candidates': candidates, 'transaction_refs': sorted({ref for item in candidates for ref in item.get('transaction_refs', [])}), 'scenario_ids': [row[0] for row in conn.execute('SELECT id FROM scenarios WHERE customer_id=?', (customer_id,))], 'goal_ids': [row[0] for row in conn.execute('SELECT id FROM goals WHERE customer_id=?', (customer_id,))]}

    def _execute_coach_tool(self, conn, customer_id, response, context):
        if response.get('needs_clarification'):
            return response
        intent = response.get('intent')
        params = response.get('parameters', {})
        locale = context['interface_locale']
        copy = {
            'en': {
                'statistics': 'Here are the exact observed results for the selected category and period.',
                'statistics_empty': 'I found no matching transactions for that exact category and period.',
                'adjustment': 'This is an unsaved planning preview based on observed spending in the selected category.',
                'profile': 'This is a neutral breakdown of observed spending across the learning baskets, not a score or judgment.',
                'safe': 'This estimate protects the reserve, qualified recurring outflows, and a buffer based on earlier unscheduled spending.',
                'safe_unavailable': 'There is not enough observed history yet to calculate a safe-to-spend estimate.',
                'tax': 'I found explicit observed tax records for the selected period.',
                'tax_empty': 'I found no explicit tax records for this period. Missing records do not mean no tax was paid.',
            },
            'fi': {
                'statistics': 'Tässä ovat valitun luokan ja ajanjakson tarkat havaitut tulokset.',
                'statistics_empty': 'En löytänyt tälle tarkalle luokalle ja ajanjaksolle vastaavia tapahtumia.',
                'adjustment': 'Tämä on tallentamaton suunnitteluarvio, joka perustuu valitun luokan havaittuihin menoihin.',
                'profile': 'Tämä on neutraali erittely havaituista menoista oppimiskoreittain, ei pisteytys tai arvio sinusta.',
                'safe': 'Arvio suojaa vararahasi, tunnistetut toistuvat menot ja aiempaan aikatauluttamattomaan kulutukseen perustuvan varan.',
                'safe_unavailable': 'Tilihistoriaa ei ole vielä riittävästi turvallisen käyttövaran arvioimiseen.',
                'tax': 'Löysin valitulta ajanjaksolta nimenomaisia havaittuja verotietoja.',
                'tax_empty': 'En löytänyt tältä ajanjaksolta nimenomaisia verotietoja. Puuttuvat tiedot eivät tarkoita, ettei veroa olisi maksettu.',
            },
            'sv': {
                'statistics': 'Här är de exakta observerade resultaten för den valda kategorin och perioden.',
                'statistics_empty': 'Jag hittade inga matchande transaktioner för den exakta kategorin och perioden.',
                'adjustment': 'Det här är en osparad planeringsöversikt som bygger på observerade utgifter i den valda kategorin.',
                'profile': 'Det här är en neutral uppdelning av observerade utgifter i lärandekorgarna, inte ett betyg eller omdöme.',
                'safe': 'Uppskattningen skyddar bufferten, kvalificerade återkommande utflöden och ett utrymme baserat på tidigare ej schemalagda utgifter.',
                'safe_unavailable': 'Det finns ännu inte tillräcklig kontohistorik för en uppskattning av tryggt att spendera.',
                'tax': 'Jag hittade uttryckliga observerade skatteuppgifter för den valda perioden.',
                'tax_empty': 'Jag hittade inga uttryckliga skatteuppgifter för perioden. Saknade uppgifter betyder inte att ingen skatt betalades.',
            },
        }
        def explanation(default_text, fact_id):
            if response.get('source') == 'gemini' and response.get('explanation_blocks'):
                return [{'text': block['text'], 'fact_ids': [fact_id]} for block in response['explanation_blocks']]
            return [{'text': default_text, 'fact_ids': [fact_id]}]
        if intent == 'transaction_statistics':
            from .statistics import transaction_statistics, compare_transaction_statistics
            period = params['period']
            start, end = _month_bounds(period)
            filters = {key: params[key] for key in ('category', 'role', 'transaction_type', 'merchant_id') if key in params}
            filters = self._validated_statistics_filters(conn, customer_id, filters)
            if 'comparison_period' in params:
                comparison_start, comparison_end = _month_bounds(params['comparison_period'])
                result = compare_transaction_statistics(conn, customer_id, start, end, comparison_start, comparison_end, filters)
                has_transactions = result['current']['has_transactions'] or result['comparison']['has_transactions']
            else:
                result = transaction_statistics(conn, customer_id, start, end, filters)
                has_transactions = result['has_transactions']
            response['tool_result'] = result
            response['tool_fact_id'] = result['fact_id']
            response['tool_fact_ids'] = [result['fact_id']]
            response['tool_kind'] = 'transaction_statistics_comparison' if 'comparison_period' in params else 'transaction_statistics'
            response['tool_source'] = 'deterministic_account_statistics'
            response['source_refs'] = {'transaction_refs': result['transaction_refs']}
            response['explanation_blocks'] = explanation(copy[locale]['statistics' if has_transactions else 'statistics_empty'], result['fact_id'])
        elif intent == 'spending_adjustment':
            from .scenarios import preview_spending_adjustment
            start, end = _month_bounds(params['period'])
            result = preview_spending_adjustment(conn, customer_id, start, end, params['category'], params['percent'])
            response['tool_result'] = result
            response['tool_fact_id'] = result['fact_id']
            response['tool_fact_ids'] = [result['fact_id']]
            response['tool_kind'] = 'spending_adjustment_preview'
            response['tool_source'] = 'deterministic_unsaved_scenario'
            response['source_refs'] = {'transaction_refs': result['transaction_refs']}
            response['explanation_blocks'] = explanation(copy[locale]['adjustment'], result['fact_id'])
        elif intent == 'spending_profile':
            from .analytics import three_basket_profile
            result = three_basket_profile(conn, customer_id, params['period'])
            basket_fact_ids = [row['fact_id'] for row in result['baskets']]
            response['tool_result'] = result
            response['tool_fact_id'] = result['fact_id']
            response['tool_fact_ids'] = [result['fact_id'], *basket_fact_ids]
            response['tool_kind'] = 'three_basket_profile'
            response['tool_source'] = 'deterministic_money_map'
            response['source_refs'] = {'transaction_refs': result['transaction_refs']}
            response['explanation_blocks'] = explanation(copy[locale]['profile'], result['fact_id'])
        elif intent == 'safe_to_spend':
            from .forecast import safe_to_spend
            result = safe_to_spend(
                conn,
                customer_id,
                context['reference_date'],
                days=context.get('days', 7),
            )
            refs = sorted(set(result['transaction_refs'] + result['comparison_transaction_refs']))
            response['tool_result'] = result
            response['tool_fact_id'] = result['fact_id']
            response['tool_fact_ids'] = [result['fact_id']]
            response['tool_kind'] = 'safe_to_spend'
            response['tool_source'] = 'deterministic_safe_to_spend'
            response['source_refs'] = {'transaction_refs': refs}
            response['explanation_blocks'] = explanation(
                copy[locale]['safe' if result['available'] else 'safe_unavailable'],
                result['fact_id'],
            )
        elif intent == 'observed_tax_evidence':
            from .tax import observed_tax_evidence
            start, end = _month_bounds(params['period'])
            result = observed_tax_evidence(conn, customer_id, start, end)
            response['tool_result'] = result
            response['tool_fact_id'] = result['fact_id']
            response['tool_fact_ids'] = [result['fact_id']]
            response['tool_kind'] = 'observed_tax_evidence'
            response['tool_source'] = 'deterministic_observed_tax_evidence'
            response['source_refs'] = {'transaction_refs': result['transaction_refs'], 'mortgage_event_refs': result['mortgage_event_refs']}
            response['explanation_blocks'] = explanation(copy[locale]['tax' if result['available'] else 'tax_empty'], result['fact_id'])
        return response

    @staticmethod
    def _mutation_result(kind, result):
        audit = result['audit_event']
        value = {key: item for key, item in result.items() if key != 'audit_event'}
        if kind == 'scenario':
            value['monthly_contribution_cents'] = value['modeled_monthly_contribution_cents']
        return {kind: value, 'audit_event': audit}

    def _mutate(self, conn, path, customer_id, month, body):
        from . import state, scenarios, goals
        provenance = body.get('provenance', 'user')
        start, end = _month_bounds(month)
        # All references are checked against the authenticated demo scope before services run.
        for field, table, column in [('transaction_ref', 'transactions', 'transaction_ref'), ('scenario_id', 'scenarios', 'id'), ('goal_id', 'goals', 'id')]:
            if field in body and not conn.execute(f'SELECT 1 FROM {table} WHERE {column}=? AND customer_id=?', (body[field], customer_id)).fetchone():
                raise APIError(404, 'unknown_reference', 'Unknown ' + field + ' in selected customer scope')
        if path == '/api/scenarios':
            return self._mutation_result('scenario', scenarios.create_scenario(conn, customer_id, start, end, body.get('category', 'Restaurants'), body.get('percent', 20), name=body.get('name', 'Spending adjustment'), provenance=provenance))
        if path == '/api/scenarios/exclude':
            return self._mutation_result('scenario', scenarios.exclude_from_scenario(conn, customer_id, body['scenario_id'], body['transaction_ref'], provenance=provenance))
        if path == '/api/rules':
            if body.get('type') == 'classify_row' or 'transaction_ref' in body:
                return state.classify_row(conn, customer_id, body['transaction_ref'], body['role'], label=body.get('label'), provenance=provenance)
            return state.create_matching_rule(conn, customer_id, body['category'], body['role'], merchant_id=body.get('merchant_id'), label=body.get('label'), provenance=provenance)
        if path == '/api/goals':
            for key in ['target_cents', 'current_saved_cents', 'reserve_floor_cents']:
                if key in body and (type(body[key]) is not int or body[key] < 0):
                    raise ValueError(key + ' must be nonnegative integer cents')
            return self._mutation_result('goal', goals.create_goal(conn, customer_id, body['name'], body['target_cents'], body['target_date'], current_saved_cents=body.get('current_saved_cents', 0), reserve_floor_cents=body.get('reserve_floor_cents', 0), template=body.get('template', 'custom'), provenance=provenance))
        if path == '/api/goals/link':
            result = self._mutation_result('goal', goals.link_scenario_to_goal(conn, customer_id, body['goal_id'], body['scenario_id'], provenance=provenance))
            result['host_action'] = {'type': 'attach_modeled_contribution', 'goal_ref': body['goal_id'], 'cents': result['goal']['modeled_scenario_contribution_cents'], 'scenario_ref': body['scenario_id'], 'requires_host_confirmation': True, 'creates_transfer': False}
            return result
        if path == '/api/undo':
            return state.undo_last(conn, customer_id)
        if path == '/api/reset':
            return state.reset_demo(conn, customer_id)
        raise APIError(404, 'not_found', 'Unknown mutation')


def create_server(application=None, *, host='127.0.0.1', port=8080):
    application = application or Application()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send_error(self, code, message=None, explain=None):
            if code == 501 and urlsplit(getattr(self, 'path', '')).path.startswith('/api/'):
                self._json(405, {'ok': False, 'error': {'code': 'method_not_allowed', 'message': 'Method not allowed'}})
                return
            super().send_error(code, message, explain)

        def _json(self, status, result):
            content = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(content)

        def do_GET(self):
            if urlsplit(self.path).path.startswith('/api/'):
                self._json(*application.handle('GET', self.path))
                return
            path = unquote(urlsplit(self.path).path)
            if '%' in path or '\\' in path or '\x00' in path or '..' in Path(path).parts:
                self._json(403, {'ok': False, 'error': {'code': 'forbidden', 'message': 'Invalid static path'}})
                return
            root = application.web_root.resolve()
            file = (root / path.lstrip('/')).resolve()
            if path == '/':
                file = (root / 'index.html').resolve()
            if not file.is_relative_to(root) or not file.is_file():
                self._json(404, {'ok': False, 'error': {'code': 'not_found', 'message': 'Static file not found'}})
                return
            content = file.read_bytes()
            self.send_response(200)
            mime = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
            if file.suffix == '.js':
                mime = 'text/javascript'
            self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers(); self.wfile.write(content)

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('JSON body must be between one byte and sixty-four kilobytes')
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Content-Type must be application/json')
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self._json(400, {'ok': False, 'error': {'code': 'invalid_json', 'message': 'A valid JSON object is required'}})
                return
            self._json(*application.handle('POST', self.path, body))
    return ThreadingHTTPServer((host, port), Handler)
