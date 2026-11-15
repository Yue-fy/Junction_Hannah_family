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


def _int_query(query, name, default, minimum, maximum):
    """Strict integer query parameter within [minimum, maximum]."""
    if name not in query:
        return default
    value = query[name]
    if not value.isdigit() or not minimum <= int(value) <= maximum:
        raise ValueError('%s must be an integer from %d to %d' % (name, minimum, maximum))
    return int(value)


def _validate_goal_fields(fields):
    """Shape check for /api/goals/update fields; goals.update_goal does the full validation."""
    allowed = {'name', 'target_cents', 'target_date', 'current_saved_cents', 'reserve_floor_cents'}
    if not isinstance(fields, dict) or not fields:
        raise ValueError('fields must be a non-empty object')
    if set(fields) - allowed:
        raise ValueError('Unknown goal field; allowed: ' + ', '.join(sorted(allowed)))
    for key, value in fields.items():
        if key == 'name':
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
                raise ValueError('name must be text of one to 120 characters')
        elif key == 'target_date':
            if not isinstance(value, str) or len(value) != 10:
                raise ValueError('target_date must use YYYY-MM-DD')
            date.fromisoformat(value)
        elif type(value) is not int or value < 0 or (key == 'target_cents' and value == 0):
            raise ValueError(key + (' must be positive integer cents' if key == 'target_cents' else ' must be nonnegative integer cents'))


def _year_query(query, name='year'):
    if name not in query:
        return None
    return _int_query(query, name, None, 2000, 2100)


def _locale(value):
    if value not in {'en', 'fi', 'sv'}:
        raise ValueError('locale must be en, fi, or sv')
    return value


def _tax_entry(profile, tax_year):
    """The active money-profile 'tax' entry for tax_year, or None."""
    for entry in profile.get('by_key', {}).get('tax', []):
        if entry['value'].get('tax_year') == tax_year:
            return entry
    return None


def planning_profile(conn, customer_id, as_of):
    """Money-profile planning inputs for forecast.safe_until_payday, or None when the profile is empty.

    Args: conn; customer_id; as_of (ISO date, the data reference date; drives steady mode).
    Returns money_profile.planning_inputs(...) dict or None.
    """
    from . import money_profile
    profile = money_profile.get_profile(conn, customer_id, as_of)
    if profile['empty']:
        return None
    return money_profile.planning_inputs(profile, as_of)


def offline_safe_to_spend(conn, customer_id, reference_date):
    """The spending plan (forecast.safe_to_spend) for the legacy offline coach and its narrative.

    Same numbers as /api/safe-to-spend and the agent tool: safe_to_spend_cents is
    this week's share of the comfortable spending room until payday.
    """
    from .forecast import safe_to_spend
    raw = safe_to_spend(conn, customer_id, as_of=reference_date,
                        profile=planning_profile(conn, customer_id, reference_date))
    return {**raw, 'label': 'Estimated safe-to-spend this week, until payday — not a guarantee' if raw['available'] else 'Safe-to-spend unavailable — more history needed'}


SAFE_UNTIL_PAYDAY_COPY = {
    'en': 'This is this week\'s share of a comfortable spending pace until your next payday. Bills due before payday, everyday costs like food, a surprise buffer, a small safety cushion and any saving target are already held back. Money beyond a comfortable pace is shown as money that could be saved.',
    'fi': 'Tämä on tämän viikon osuus sopivasta käyttötahdista seuraavaan palkkapäivään asti. Ennen palkkapäivää erääntyvät laskut, arjen menot kuten ruoka, yllätyspuskuri, pieni turvatyyny ja mahdollinen säästötavoite on jo jätetty sivuun. Sopivan tahdin ylittävä raha näytetään summana, jonka voisi säästää.',
    'sv': 'Det här är veckans del av en lagom utgiftstakt fram till nästa lönedag. Räkningar före lönedagen, vardagsutgifter som mat, en buffert för oväntat, en liten säkerhetsmarginal och ett eventuellt sparmål är redan avsatta. Pengar utöver en lagom takt visas som pengar som kan sparas.',
}


def _bounded_materiality(cents):
    """Map absolute change to 0–1; changes of at least EUR 100 reach the cap."""
    if type(cents) is not int:
        return 0.0
    return float(min(Decimal(1), Decimal(abs(cents)) / Decimal(10_000)))


class Application:
    def __init__(self, database='var/scoach.sqlite3', web_root=None, *, coach_transport=None, agent_transport=None):
        self.database = Path(database)
        self.web_root = Path(web_root) if web_root else Path(__file__).resolve().parent.parent / 'web'
        self.coach_transport = coach_transport
        self.agent_transport = agent_transport

    def handle(self, method, target, payload=None):
        try:
            data = self._route(method, target, payload)
            decorated = _decorate(data)
            if method == 'POST' and urlsplit(target).path == '/api/agent':
                # Action params are exact inputs to the confirmed mutation API.
                for original, action in zip(data.get('actions', []), decorated.get('actions', [])):
                    action['params'] = dict(original['params'])
            return 200, {'ok': True, 'data': decorated}
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
        get_routes = {'/api/health', '/api/personas', '/api/overview', '/api/comparison', '/api/transactions', '/api/trends', '/api/forecast', '/api/safe-to-spend', '/api/investments', '/api/financing', '/api/statistics', '/api/statistics/compare', '/api/taxes', '/api/vat', '/api/goals',
                      '/api/spender-profile', '/api/explore', '/api/cashflow', '/api/cashflow/summary', '/api/year-review/options',
                      '/api/year-review', '/api/profile', '/api/profile/suggestions', '/api/tax', '/api/vat/card', '/api/benchmarks',
                      '/api/plans', '/api/plans/mortgage/projection', '/api/plans/mortgage/preview', '/api/plans/tax', '/api/catalogue',
                      '/api/plans/tax/preview'}
        post_routes = {'/api/scenarios', '/api/scenarios/exclude', '/api/rules', '/api/goals', '/api/goals/link', '/api/goals/update', '/api/goals/delete', '/api/coach', '/api/agent', '/api/tax-plan', '/api/undo', '/api/reset',
                       '/api/year-review/captions', '/api/year-review/save', '/api/profile/entries', '/api/profile/entries/update',
                       '/api/profile/entries/delete', '/api/profile/forget', '/api/profile/suggestions/confirm',
                       '/api/profile/suggestions/dismiss', '/api/profile/migrate-local', '/api/plans/mortgage', '/api/plans/tax',
                       '/api/catalogue/answer', '/api/catalogue/match'}
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
            from .llm import agent_configured
            return {
                'status': 'ok',
                'database_ready': self.database.is_file(),
                'gemini_optional': True,
                'gemini_configured': bool(os.environ.get('GEMINI_API_KEY') or self.coach_transport),
                'agent_configured': bool(agent_configured() or self.agent_transport),
            }
        if not self.database.is_file():
            raise APIError(503, 'database_unavailable', 'Demo database missing. Run scripts/build_demo_db.py first.')
        if method == 'POST' and path not in {'/api/coach', '/api/agent', '/api/year-review/captions', '/api/catalogue/answer', '/api/catalogue/match'} and body.get('confirmed') is not True:
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
                # The spending plan uses the last recorded day for a later day of the same month (month-end callers).
                if not (path == '/api/safe-to-spend' and scope['observed_end'] < query['as_of'] <= _month_bounds(scope['observed_end'][:7])[1]):
                    raise ValueError('as_of is outside observed history')
            filters = {key: query[key] for key in ['category', 'role', 'merchant_id', 'transaction_type', 'mcc_code', 'consumption_only'] if query.get(key)} or None
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
                    # One answer: the spending plan until payday. days/horizon are accepted for
                    # older clients but no longer change the number.
                    from .forecast import safe_to_spend
                    reference_date = query.get('as_of') or min(end, scope['observed_end'])
                    reserve = int(query['reserve_floor_cents']) if 'reserve_floor_cents' in query else None
                    days = int(query['days']) if 'days' in query else None
                    if query.get('horizon') not in (None, '', 'until_payday', 'week'):
                        raise ValueError('horizon must be until_payday')
                    return safe_to_spend(conn, customer_id, as_of=reference_date, days=days, reserve_floor_cents=reserve,
                                         profile=planning_profile(conn, customer_id, reference_date))
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
                reference_date = query.get('as_of') or min(end, scope['observed_end'])
                if path == '/api/spender-profile':
                    from .spender import spender_profile, irregular_buffer
                    latest = latest_complete_month(conn, customer_id)
                    end_month = month if month <= latest else latest
                    months = _int_query(query, 'months', 6, 2, 24)
                    return {**scope, 'end_month': end_month,
                            'profile': spender_profile(conn, customer_id, end_month=end_month, months=months),
                            'buffer': irregular_buffer(conn, customer_id, end_month=end_month)}
                if path == '/api/explore':
                    from .explore import explore
                    explore_filters = self._validated_statistics_filters(
                        conn, customer_id, {key: query[key] for key in ('category', 'role', 'transaction_type', 'mcc_code', 'merchant_id') if key in query})
                    return explore(conn, customer_id, query['start'], query['end'], group_by=query['group_by'],
                                   metric=query.get('metric', 'outflow_total'), filters=explore_filters or None,
                                   top=_int_query(query, 'top', 10, 1, 31))
                if path in {'/api/cashflow', '/api/cashflow/summary'}:
                    from .cashflow import cashflow_series, cashflow_summary
                    from .ledger import shift_month
                    end_month = query.get('end_month', month)
                    start_month = query.get('start_month', max(scope['observed_start'][:7], shift_month(month, -11)))
                    function = cashflow_series if path == '/api/cashflow' else cashflow_summary
                    return function(conn, customer_id, start_month, end_month, query.get('granularity', 'month'))
                if path == '/api/year-review/options':
                    from .year_review import year_options
                    years = year_options(conn, customer_id)
                    return {**scope, 'years': years, 'options': years}
                if path == '/api/year-review':
                    from .year_story import build_review, default_year, story_cards
                    year = _year_query(query) or default_year(conn, customer_id)
                    if year is None:
                        raise ValueError('No year with enough account history')
                    review = build_review(conn, customer_id, year)
                    return {**review, 'story_cards': story_cards(review, _locale(query.get('locale', 'en')))}
                if path in {'/api/profile', '/api/profile/suggestions'}:
                    from . import money_profile
                    profile_locale = _locale(query.get('locale', 'en'))
                    try:
                        suggestions = money_profile.profile_suggestions(conn, customer_id, reference_date, profile_locale)
                    except ValueError:
                        suggestions = []
                    if path == '/api/profile/suggestions':
                        return {'suggestions': suggestions, 'as_of': reference_date}
                    return {'profile': money_profile.get_profile(conn, customer_id, reference_date),
                            'suggestions': suggestions, 'as_of': reference_date}
                if path == '/api/tax':
                    from . import money_profile
                    from .tax import tax_overview
                    tax_year = _year_query(query, 'tax_year') or int(reference_date[:4])
                    entry = _tax_entry(money_profile.get_profile(conn, customer_id, reference_date), tax_year)
                    result = tax_overview(conn, customer_id, reference_date, entry['value'] if entry else None,
                                          query.get('month', reference_date[:7]))
                    from .tax_text import localize_tax_overview
                    overview = localize_tax_overview(result['overview'], _locale(query.get('locale', 'en')))
                    # Aliases the "My taxes" card reads: cycle.label and a top-level refund_seen.
                    if isinstance(overview.get('cycle'), dict):
                        overview['cycle'] = {**overview['cycle'], 'label': overview['cycle'].get('stage_label')}
                    return {**overview, 'refund_seen': overview.get('refund'), 'tax_year': tax_year,
                            'tax_entry_id': entry['id'] if entry else None}
                if path == '/api/benchmarks':
                    from .benchmarks import compare_to_peers, benchmark_categories
                    if 'category' not in query:
                        return {'categories': benchmark_categories()}
                    return compare_to_peers(conn, customer_id, query['category'], months=int(query.get('months', 12)),
                                            end_month=query.get('month'))
                if path in {'/api/plans', '/api/plans/mortgage/projection', '/api/plans/mortgage/preview', '/api/plans/tax', '/api/plans/tax/preview'}:
                    return self._plans_get(conn, path, customer_id, reference_date, query)
                if path == '/api/vat/card':
                    from .tax import vat_learn_card
                    from .tax_text import localize_vat_card
                    card = localize_vat_card(vat_learn_card(conn, customer_id, month), _locale(query.get('locale', 'en')))
                    return {**card, 'rate_label': card.get('rate_display')}
            if path == '/api/catalogue':
                from .catalogue import catalogue
                from . import money_profile
                try:
                    steady = money_profile.coaching_mode(money_profile.get_profile(conn, customer_id, reference_date)) == 'steady'
                except Exception:
                    steady = False
                return catalogue(_locale(query.get('locale', 'en')), steady=steady)
            if path == '/api/catalogue/answer':
                from .catalogue import answer
                return {'card': answer(conn, customer_id, month, body['question_id'], body.get('params') or {},
                                       _locale(body.get('locale', 'en')))}
            if path == '/api/catalogue/match':
                from .catalogue import match_message
                from .agent_tools import ToolContext
                context = ToolContext(conn, customer_id, month)
                matched = match_message(body['message'], _locale(body.get('locale', 'en')), today=context.reference_date,
                                        observed=(scope['observed_start'], scope['observed_end']))
                return {key: matched[key] for key in ('suggestions', 'supportive', 'intent_hint')}
            if path == '/api/agent':
                from .agent import run_agent
                return run_agent(conn, customer_id, month, body.get('locale', 'en'),
                                 body.get('message'), body.get('history', []), transport=self.agent_transport)
            if path == '/api/coach':
                locale = body.get('locale', 'en')
                if locale not in {'en', 'fi', 'sv'}:
                    raise ValueError('locale must be en, fi, or sv')
                context = self._coach_context(conn, customer_id, month, locale)
                from .query_scope import validate_previous_query
                previous = validate_previous_query(body.get('previous_query'), context)
                if previous:
                    self._validated_statistics_filters(conn, customer_id, previous['filters'])
                    context['previous_query'] = previous
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
            if path == '/api/year-review/captions':
                from .agent import year_review_captions
                from .year_story import build_review, story_cards
                locale = _locale(body.get('locale', 'en'))
                review = build_review(conn, customer_id, body['year'])
                if not review.get('available'):
                    raise ValueError('Not enough account history for this year')
                return year_review_captions(review, story_cards(review, locale), locale, transport=self.agent_transport)
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
            '/api/goals/update': {'goal_id', 'fields'},
            '/api/goals/delete': {'goal_id'},
            '/api/tax-plan': {'amount_cents', 'due_date', 'reference_date', 'already_set_aside_cents', 'current_balance_cents', 'reserve_floor_cents', 'set_aside_location', 'label'},
            '/api/coach': {'message', 'locale', 'previous_query'}, '/api/undo': set(), '/api/reset': set(),
            '/api/agent': {'message', 'locale', 'history'},
            '/api/year-review/captions': {'year', 'locale'},
            '/api/year-review/save': {'year', 'captions', 'closing_message', 'locale'},
            '/api/profile/entries': {'key', 'value', 'note', 'source'},
            '/api/profile/entries/update': {'entry_id', 'value', 'note', 'active'},
            '/api/profile/entries/delete': {'entry_id'},
            '/api/profile/forget': set(),
            '/api/profile/suggestions/confirm': {'suggestion_id', 'key', 'value', 'note', 'locale'},
            '/api/profile/suggestions/dismiss': {'suggestion_id'},
            '/api/profile/migrate-local': {'local'},
            '/api/plans/mortgage': {'plan', 'source'}, '/api/plans/tax': {'plan', 'source'},
            '/api/catalogue/answer': {'question_id', 'params', 'locale'},
            '/api/catalogue/match': {'message', 'locale'},
        }
        required = {
            '/api/goals/update': {'goal_id', 'fields'}, '/api/goals/delete': {'goal_id'},
            '/api/year-review/captions': {'year'}, '/api/year-review/save': {'year'},
            '/api/profile/entries': {'key', 'value'}, '/api/profile/entries/update': {'entry_id'},
            '/api/profile/entries/delete': {'entry_id'}, '/api/profile/suggestions/confirm': {'suggestion_id'},
            '/api/profile/suggestions/dismiss': {'suggestion_id'}, '/api/profile/migrate-local': {'local'},
            '/api/plans/mortgage': {'plan'}, '/api/plans/tax': {'plan'},
            '/api/catalogue/answer': {'question_id'}, '/api/catalogue/match': {'message'},
        }
        if set(body) - common - fields.get(path, set()):
            raise ValueError('Unknown JSON body field')
        missing = sorted(required.get(path, set()) - set(body))
        if missing:
            raise ValueError('Missing JSON body field: ' + ', '.join(missing))
        if path == '/api/profile/entries/update' and not {'value', 'note', 'active'} & set(body):
            raise ValueError('Nothing to update: give value, note or active')
        if path == '/api/agent':
            from .agent import validate_request
            validate_request(body.get('message'), body.get('locale', 'en'), body.get('history', []))
        for name, value in body.items():
            if path == '/api/agent' and name == 'history':
                continue
            elif name == 'value' and path.startswith('/api/profile/'):
                continue  # Shape depends on the profile key; money_profile.validate_entry checks it strictly.
            elif name == 'params' and path == '/api/catalogue/answer':
                if value is not None and not isinstance(value, dict):
                    raise ValueError('params must be an object')
            elif name == 'message' and path == '/api/catalogue/match':
                if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                    raise ValueError('A message of one to two thousand characters is required')
            elif name == 'fields':
                _validate_goal_fields(value)
            elif name in {'local', 'plan'}:
                if not isinstance(value, dict):
                    raise ValueError(name + ' must be an object')
            elif name == 'year':
                if type(value) is not int or not 2000 <= value <= 2100:
                    raise ValueError('year must be an integer calendar year')
            elif name == 'active':
                if type(value) is not bool:
                    raise ValueError('active must be a boolean')
            elif name == 'captions':
                if value is not None and (not isinstance(value, dict) or len(value) > 12 or any(
                        not isinstance(k, str) or not isinstance(v, str) or len(k) > 60 or len(v) > 300 for k, v in value.items())):
                    raise ValueError('captions must map card ids to short texts')
            elif name in {'closing_message', 'note'}:
                if value is not None and (not isinstance(value, str) or len(value) > 500):
                    raise ValueError(name + ' must be text of at most 500 characters')
            elif name == 'previous_query':
                if value is not None and not isinstance(value, dict):
                    raise ValueError('previous_query must be a resolved scope object')
            elif name == 'confirmed':
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
            '/api/statistics': common | {'month', 'start', 'end', 'category', 'role', 'transaction_type', 'merchant_id', 'mcc_code', 'consumption_only'},
            '/api/statistics/compare': common | {'month', 'comparison_month', 'start', 'end', 'comparison_start', 'comparison_end', 'category', 'role', 'transaction_type', 'merchant_id', 'mcc_code', 'consumption_only'},
            '/api/transactions': common | {'month', 'start', 'end', 'category', 'role', 'transaction_type', 'merchant_id', 'mcc_code', 'transaction_ref', 'consumption_only'},
            '/api/taxes': common | {'month', 'start', 'end'},
            '/api/vat': common | {'month', 'start', 'end'},
            '/api/spender-profile': common | {'month', 'months'},
            '/api/explore': common | {'start', 'end', 'group_by', 'metric', 'top', 'category', 'role', 'transaction_type', 'mcc_code', 'merchant_id'},
            '/api/cashflow': common | {'month', 'start_month', 'end_month', 'granularity'},
            '/api/cashflow/summary': common | {'month', 'start_month', 'end_month', 'granularity'},
            '/api/year-review/options': common,
            '/api/year-review': common | {'year', 'locale'},
            '/api/profile': common | {'month', 'as_of', 'locale'},
            '/api/profile/suggestions': common | {'month', 'as_of', 'locale'},
            '/api/tax': common | {'month', 'as_of', 'tax_year', 'locale'},
            '/api/vat/card': common | {'month', 'locale'},
            '/api/benchmarks': common | {'category', 'months', 'month'},
            '/api/plans': common | {'month', 'as_of'},
            '/api/plans/mortgage/projection': common | {'month', 'as_of', 'extra_cents', 'rate_delta_bp'},
            '/api/plans/mortgage/preview': common | {'month', 'as_of', 'extra_cents', 'rate_delta_bp', 'principal_cents', 'loan_type',
                                                     'reference_rate', 'reference_rate_bp', 'margin_bp', 'remaining_months',
                                                     'monthly_payment_cents', 'payment_day'},
            '/api/plans/tax': common | {'month', 'as_of'},
            '/api/plans/tax/preview': common | {'month', 'as_of', 'gross_monthly_cents', 'base_rate_bp', 'additional_rate_bp',
                                                'income_limit_cents', 'expected_back_tax_cents', 'expected_refund_cents'},
            '/api/catalogue': common | {'locale', 'month'},
        }
        if path not in allowed:
            return
        if set(query) - allowed[path]:
            raise ValueError('Unknown query parameter')
        if path == '/api/explore':
            missing = sorted({'start', 'end', 'group_by'} - set(query))
            if missing:
                raise ValueError('Missing query parameter: ' + ', '.join(missing))
        if path in {'/api/explore', '/api/spender-profile', '/api/cashflow', '/api/cashflow/summary', '/api/year-review',
                    '/api/year-review/options', '/api/profile', '/api/profile/suggestions', '/api/tax', '/api/vat/card', '/api/benchmarks',
                    '/api/plans', '/api/plans/mortgage/projection', '/api/plans/mortgage/preview', '/api/plans/tax', '/api/catalogue',
                      '/api/plans/tax/preview'}:
            for field in ('category', 'role', 'transaction_type', 'merchant_id', 'mcc_code'):
                if field in query and not query[field].strip():
                    raise ValueError('Filters must be nonempty')
            return
        if set(query) - allowed[path]:
            raise ValueError('Unknown query parameter')
        for field in ('category', 'role', 'transaction_type', 'merchant_id', 'mcc_code', 'consumption_only'):
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
            if key == 'consumption_only':
                if value != 'true':
                    raise ValueError('consumption_only must be true')
                continue
            if key == 'mcc_code':
                import re
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}', value):
                    raise ValueError('mcc_code must be four digits')
                continue
            if key not in mapping:
                raise ValueError('Unknown statistics filter')
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
        # This week's share of the money free until payday (bills before payday already held back).
        safe = offline_safe_to_spend(conn, customer_id, reference_date)
        facts.append({'id': safe['fact_id'], 'value_cents': safe['safe_to_spend_cents'], 'unit': 'cents', 'label': safe['label'], 'status': 'scenario', 'available': safe['available'], 'reserve_floor_cents': safe['reserve_floor_cents'], 'reserve_floor_source': safe['reserve_floor_source'], 'next_payday': safe['next_payday'], 'per_day_cents': safe['per_day_cents']})
        safe_text = SAFE_UNTIL_PAYDAY_COPY['en'] if safe['available'] else 'There is not enough observed history yet to estimate a safe-to-spend amount.'
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
                'safe': SAFE_UNTIL_PAYDAY_COPY['en'],
                'safe_unavailable': 'There is not enough observed history yet to calculate a safe-to-spend estimate.',
                'tax': 'I found explicit observed tax records for the selected period.',
                'tax_empty': 'I found no explicit tax records for this period. Missing records do not mean no tax was paid.',
            },
            'fi': {
                'statistics': 'Tässä ovat valitun luokan ja ajanjakson tarkat havaitut tulokset.',
                'statistics_empty': 'En löytänyt tälle tarkalle luokalle ja ajanjaksolle vastaavia tapahtumia.',
                'adjustment': 'Tämä on tallentamaton suunnitteluarvio, joka perustuu valitun luokan havaittuihin menoihin.',
                'profile': 'Tämä on neutraali erittely havaituista menoista oppimiskoreittain, ei pisteytys tai arvio sinusta.',
                'safe': SAFE_UNTIL_PAYDAY_COPY['fi'],
                'safe_unavailable': 'Tilihistoriaa ei ole vielä riittävästi turvallisen käyttövaran arvioimiseen.',
                'tax': 'Löysin valitulta ajanjaksolta nimenomaisia havaittuja verotietoja.',
                'tax_empty': 'En löytänyt tältä ajanjaksolta nimenomaisia verotietoja. Puuttuvat tiedot eivät tarkoita, ettei veroa olisi maksettu.',
            },
            'sv': {
                'statistics': 'Här är de exakta observerade resultaten för den valda kategorin och perioden.',
                'statistics_empty': 'Jag hittade inga matchande transaktioner för den exakta kategorin och perioden.',
                'adjustment': 'Det här är en osparad planeringsöversikt som bygger på observerade utgifter i den valda kategorin.',
                'profile': 'Det här är en neutral uppdelning av observerade utgifter i lärandekorgarna, inte ett betyg eller omdöme.',
                'safe': SAFE_UNTIL_PAYDAY_COPY['sv'],
                'safe_unavailable': 'Det finns ännu inte tillräcklig kontohistorik för en uppskattning av tryggt att spendera.',
                'tax': 'Jag hittade uttryckliga observerade skatteuppgifter för den valda perioden.',
                'tax_empty': 'Jag hittade inga uttryckliga skatteuppgifter för perioden. Saknade uppgifter betyder inte att ingen skatt betalades.',
            },
        }
        def explanation(default_text, fact_id):
            if (response.get('source') == 'deterministic'
                    and response.get('clarification_code') == 'planned_purchase_preview'
                    and response.get('intent') == 'safe_to_spend'
                    and response.get('explanation_blocks')):
                # The local planner derived the price comparison from this
                # same snapshot's safe-to-spend fact. Retain its useful prose
                # while binding evidence to the freshly executed calculation.
                return [{'text': block['text'], 'fact_ids': [fact_id]} for block in response['explanation_blocks']]
            if response.get('source') == 'gemini' and response.get('explanation_blocks'):
                return [{'text': block['text'], 'fact_ids': [fact_id]} for block in response['explanation_blocks']]
            return [{'text': default_text, 'fact_ids': [fact_id]}]
        if intent == 'transaction_statistics':
            from .statistics import transaction_statistics, compare_transaction_statistics
            query_scope = response.get('query_scope')
            if query_scope:
                start, end = query_scope['start'], query_scope['end']
                filters = query_scope['filters']
            else:
                start, end = _month_bounds(params['period'])
                filters = {key: params[key] for key in ('category', 'role', 'transaction_type', 'merchant_id', 'mcc_code', 'consumption_only') if key in params}
                credit_filter=filters.get('role')=='income' or filters.get('transaction_type') in {'salary','other_income','investment_withdrawal'}
                query_scope = {'customer_id': customer_id, 'account_id': context['account_id'],
                               'concept': params.get('category', params.get('role', 'Selected transactions')),
                               'metric': 'inflow_total' if credit_filter else 'outflow_total', 'start': start, 'end': end,
                               'reference_date': context['reference_date'], 'filters': filters}
                response['query_scope'] = query_scope
            filters = self._validated_statistics_filters(conn, customer_id, filters)
            if 'comparison_period' in params:
                comparison_start, comparison_end = _month_bounds(params['comparison_period'])
                result = compare_transaction_statistics(conn, customer_id, start, end, comparison_start, comparison_end, filters)
                has_transactions = result['current']['has_transactions'] or result['comparison']['has_transactions']
            else:
                result = transaction_statistics(conn, customer_id, start, end, filters)
                has_transactions = result['has_transactions']
                metric = query_scope['metric']
                result['metric'] = metric
                result['metric_value_cents'] = {
                    'outflow_total': result['outflow_total_cents'],
                    'inflow_total': result['inflow_total_cents'],
                    'consumption_total': result['consumption_cents'],
                    'average_outflow': result['average_outflow_cents'],
                    'largest_outflow': (result['largest_outflow'] or {}).get('amount_cents'),
                }.get(metric)
                result['metric_value_count'] = result['outflow_count'] if metric == 'transaction_count' else None
                result['definition'] = (
                    'Consumer purchases, housing and utility payments. Saving, investment transfers and incoming amounts are separate.'
                    if metric == 'consumption_total' else
                    'Gross outgoing payments for this scope. Incoming amounts and refunds are shown separately.'
                )
                if metric == 'inflow_total':
                    result['definition'] = (
                        'All positive credits to the selected account, including investment withdrawals and other incoming transfers. This is not income or earnings.'
                        if query_scope['concept'] == 'All inflows' else
                        'Positive salary credits identified by the source transaction type. This does not establish gross pay before tax.'
                        if filters.get('transaction_type') == 'salary' else
                        'Positive payments classified as income: salary and other income. Investment withdrawals and saving transfers are separate.'
                        if filters.get('role') == 'income' else
                        'Positive credits matching the selected filter. Incoming transfers are not earnings, and credited amounts do not establish gross pay before tax.'
                    )
                    from .ledger import transactions
                    result['transaction_refs'] = [row['transaction_ref'] for row in transactions(conn, customer_id, start, end, filters) if row['amount_cents'] > 0]
                result['query_scope'] = query_scope
            response['tool_result'] = result
            response['tool_fact_id'] = result['fact_id']
            response['tool_fact_ids'] = [result['fact_id']]
            response['tool_kind'] = 'transaction_statistics_comparison' if 'comparison_period' in params else 'transaction_statistics'
            response['tool_source'] = 'deterministic_account_statistics'
            response['source_refs'] = {'transaction_refs': result['transaction_refs']}
            empty_copy = copy[locale]['statistics_empty']
            if not has_transactions and 'mcc_code' in filters:
                empty_copy = {
                    'en': 'No transactions were identified by that merchant category code in this period. This does not prove that no such spending occurred; missing or different codes may hide it.',
                    'fi': 'Tällä kauppiasluokkakoodilla ei tunnistettu tapahtumia ajanjaksolla. Tämä ei todista, ettei tällaisia menoja ollut: puuttuvat tai muut koodit voivat peittää ne.',
                    'sv': 'Inga transaktioner identifierades med den handlarkategorikoden under perioden. Det bevisar inte att inga sådana utgifter förekom; saknade eller andra koder kan dölja dem.',
                }[locale]
            response['explanation_blocks'] = explanation(copy[locale]['statistics'] if has_transactions else empty_copy, result['fact_id'])
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
            # Lead the offline answer with a described habit pattern, not only basket totals.
            from .spender import spender_profile, offline_summary
            try:
                profile = spender_profile(conn, customer_id, end_month=params['period'])
            except ValueError:
                profile = None
            if profile and profile.get('available'):
                response['spender_summary'] = offline_summary(profile, locale)
                response['spender_archetype'] = profile['archetype']
        elif intent == 'safe_to_spend':
            # Until payday: every bill before payday is held back, so this week's amount is a share of what is free.
            result = offline_safe_to_spend(conn, customer_id, context['reference_date'])
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
        elif intent == 'vat_estimate':
            from .vat import vat_lens
            start, end = (params['start'], params['end']) if 'start' in params else _month_bounds(params['period'])
            result = vat_lens(conn, customer_id, start, end)
            response['tool_result'] = result
            response['tool_fact_id'] = result['fact_id']
            response['tool_fact_ids'] = [result['fact_id']]
            response['tool_kind'] = 'vat_estimate'
            response['tool_source'] = 'deterministic_vat_estimate'
            response['source_refs'] = {'transaction_refs': result['transaction_refs']}
            vat_text = {
                'en': 'This estimates VAT already included in recorded purchase prices for the stated period. It is not an additional payment or a personal tax liability; mixed purchases and missing rate mappings limit the estimate.',
                'fi': 'Tämä arvioi ilmoitetun ajanjakson kirjattuihin ostohintoihin jo sisältyvän ALV:n. Se ei ole lisämaksu tai henkilökohtainen verovelka. Sekalaiset ostokset ja puuttuvat verokantakartoitukset rajoittavat arviota.',
                'sv': 'Detta uppskattar moms som redan ingår i registrerade inköpspriser under den angivna perioden. Det är ingen extra betalning eller personlig skatteskuld. Blandade köp och saknade momssatsmappningar begränsar uppskattningen.',
            }[locale]
            response['explanation_blocks'] = explanation(vat_text, result['fact_id'])
        elif intent == 'observed_tax_evidence':
            from .tax import observed_tax_evidence
            start, end = (params['start'], params['end']) if 'start' in params else _month_bounds(params['period'])
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
    def _plans_get(conn, path, customer_id, reference_date, query):
        """Read-only plan views: GET /api/plans, /api/plans/mortgage/projection, /api/plans/mortgage/preview, /api/plans/tax."""
        from . import plans
        if path == '/api/plans':
            return plans.plans_overview(conn, customer_id, reference_date)
        if path == '/api/plans/tax':
            return plans.tax_plan(conn, customer_id, reference_date)
        if path == '/api/plans/tax/preview':
            # Computes without saving; no inputs means the labelled example (V5 lane TX).
            inputs = {}
            for field in plans.TAX_PREVIEW_FIELDS:
                if field in query:
                    if not query[field].isdigit():
                        raise ValueError('%s must be a nonnegative integer' % field)
                    inputs[field] = int(query[field])
            return plans.tax_plan_preview(conn, customer_id, reference_date, inputs=inputs)
        def signed(name, low, high):
            text = query.get(name, '0')
            if not (text.lstrip('-').isdigit() and text.count('-') <= 1) or not low <= int(text) <= high:
                raise ValueError('%s must be an integer from %d to %d' % (name, low, high))
            return int(text)
        if path == '/api/plans/mortgage/preview':
            # Computes without saving: the customer's draft numbers, or the example loan when none are given.
            loan_fields = ('principal_cents', 'loan_type', 'reference_rate', 'reference_rate_bp', 'margin_bp',
                           'remaining_months', 'monthly_payment_cents', 'payment_day')
            inputs = None
            if any(name in query for name in loan_fields):
                if 'principal_cents' not in query:
                    raise ValueError('principal_cents is required with loan numbers; leave all out for the example')
                inputs = {'principal_cents': signed('principal_cents', 1, 10_000_000_000),
                          'loan_type': query.get('loan_type', 'annuity'), 'reference_rate': query.get('reference_rate', 'euribor_12m'),
                          'reference_rate_bp': signed('reference_rate_bp', -1000, 2000), 'margin_bp': signed('margin_bp', 0, 2000)}
                for name, low, high in (('remaining_months', 1, 600), ('monthly_payment_cents', 1, 100_000_000), ('payment_day', 1, 31)):
                    if name in query:
                        inputs[name] = signed(name, low, high)
            return plans.mortgage_preview(conn, customer_id, reference_date, inputs, extra_cents=signed('extra_cents', 0, 1_000_000),
                                          rate_delta_bp=signed('rate_delta_bp', -500, 500))
        return plans.mortgage_plan(conn, customer_id, reference_date, extra_cents=signed('extra_cents', 0, 1_000_000),
                                   rate_delta_bp=signed('rate_delta_bp', -500, 500), detail=True)

    @staticmethod
    def _mutation_result(kind, result):
        audit = result['audit_event']
        value = {key: item for key, item in result.items() if key != 'audit_event'}
        if kind == 'scenario':
            value['monthly_contribution_cents'] = value['modeled_monthly_contribution_cents']
        return {kind: value, 'audit_event': audit}

    @staticmethod
    def _mutate_profile(conn, path, customer_id, month, body, provenance):
        """Confirmed money-profile writes; entry and suggestion ids are checked against the customer."""
        from . import money_profile
        from .ledger import account_scope
        money_profile.ensure_schema(conn)
        reference_date = min(_month_bounds(month)[1], account_scope(conn, customer_id)['observed_end'])
        if 'entry_id' in body and not conn.execute(
                'SELECT 1 FROM profile_entries WHERE id=? AND customer_id=? AND key<>?',
                (body['entry_id'], customer_id, money_profile.HIDDEN_KEY)).fetchone():
            raise APIError(404, 'unknown_reference', 'Unknown entry_id in selected customer scope')
        if 'suggestion_id' in body:
            known = {item['id'] for item in money_profile.profile_suggestions(conn, customer_id, reference_date)}
            if body['suggestion_id'] not in known:
                raise APIError(404, 'unknown_reference', 'Unknown suggestion_id in selected customer scope')
        if path == '/api/profile/entries':
            source = body.get('source', 'you_told_me')
            if source not in {'you_told_me', 'from_our_chat'}:
                raise ValueError('source must be you_told_me or from_our_chat')
            if body['key'] == 'year_review':
                raise ValueError('Save a year review with /api/year-review/save')
            return money_profile.save_entry(conn, customer_id, body['key'], body['value'], source,
                                            note=body.get('note'), provenance=provenance)
        if path == '/api/profile/entries/update':
            return money_profile.update_entry(conn, customer_id, body['entry_id'], value=body.get('value'),
                                              note=body.get('note'), active=body.get('active'), provenance=provenance)
        if path == '/api/profile/entries/delete':
            return money_profile.delete_entry(conn, customer_id, body['entry_id'], provenance=provenance)
        if path == '/api/profile/forget':
            return money_profile.forget_all(conn, customer_id, provenance=provenance)
        if path == '/api/profile/suggestions/confirm':
            return money_profile.confirm_suggestion(conn, customer_id, body['suggestion_id'], key=body.get('key'),
                                                    value=body.get('value'), note=body.get('note'),
                                                    as_of=reference_date, provenance=provenance,
                                                    locale=_locale(body.get('locale', 'en')))
        if path == '/api/profile/suggestions/dismiss':
            return money_profile.dismiss_suggestion(conn, customer_id, body['suggestion_id'], as_of=reference_date,
                                                    provenance=provenance)
        if path == '/api/profile/migrate-local':
            return money_profile.migrate_local(conn, customer_id, body['local'], provenance=provenance)
        raise APIError(404, 'not_found', 'Unknown mutation')

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
        if path == '/api/goals/update':
            if not isinstance(body.get('fields'), dict):
                raise ValueError('fields must be an object')
            return self._mutation_result('goal', goals.update_goal(conn, customer_id, body['goal_id'], body['fields'], provenance=provenance))
        if path == '/api/goals/delete':
            return self._mutation_result('goal', goals.delete_goal(conn, customer_id, body['goal_id'], provenance=provenance))
        if path == '/api/year-review/save':
            from . import money_profile
            from .year_story import build_review, compact_facts
            review = build_review(conn, customer_id, body['year'])
            if not review.get('available'):
                raise ValueError('Not enough account history for this year')
            value = {'year': body['year'], 'facts': compact_facts(review, body.get('locale', 'en'))}
            if body.get('captions'):
                value['captions'] = body['captions']
            if body.get('closing_message'):
                value['closing'] = body['closing_message']
            return money_profile.save_entry(conn, customer_id, 'year_review', value, 'year_review', provenance=provenance)
        if path.startswith('/api/profile/'):
            return self._mutate_profile(conn, path, customer_id, month, body, provenance)
        if path in {'/api/plans/mortgage', '/api/plans/tax'}:
            from . import plans
            from .ledger import account_scope
            source = body.get('source', 'you_told_me')
            if source not in {'you_told_me', 'from_our_chat'}:
                raise ValueError('source must be you_told_me or from_our_chat')
            reference_date = min(end, account_scope(conn, customer_id)['observed_end'])
            return plans.save_plan(conn, customer_id, path.rsplit('/', 1)[1], body['plan'], as_of=reference_date,
                                   source=source, provenance=provenance)
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
