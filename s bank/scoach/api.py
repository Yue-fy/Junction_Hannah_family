"""Local JSON/static boundary; service code owns every financial calculation."""
import calendar
import json
import mimetypes
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
        get_routes = {'/api/health', '/api/personas', '/api/overview', '/api/comparison', '/api/transactions', '/api/trends', '/api/forecast', '/api/safe-to-spend', '/api/investments', '/api/goals'}
        post_routes = {'/api/scenarios', '/api/scenarios/exclude', '/api/rules', '/api/goals', '/api/goals/link', '/api/coach', '/api/undo', '/api/reset'}
        if path not in get_routes | post_routes:
            raise APIError(404, 'not_found', 'Unknown API endpoint')
        if (method == 'GET' and path not in get_routes) or (method == 'POST' and path not in post_routes) or method not in {'GET', 'POST'}:
            raise APIError(405, 'method_not_allowed', 'Method not allowed')
        if method == 'POST' and not isinstance(payload, dict):
            raise ValueError('JSON body must be an object')
        body = payload or {}
        if method == 'POST':
            self._validate_body(path, body)
        if path == '/api/health':
            return {'status': 'ok', 'database_ready': self.database.is_file(), 'gemini_optional': True}
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
                aliases = {'CUST00001': ('Alex', 'Everyday spending'), 'CUST00676': ('Robin', 'Payday timing'), 'CUST05097': ('Sam', 'Unusual travel purchase'), 'CUST00756': ('Jules', 'Income growth'), 'CUST00296': ('Taylor', 'Optional home goal')}
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
                if path == '/api/goals':
                    from .goals import goal_plan
                    return {**scope, 'goals': [goal_plan(conn, customer_id, row[0]) for row in conn.execute('SELECT id FROM goals WHERE customer_id=? ORDER BY created_at,id', (customer_id,))]}
            if path == '/api/coach':
                locale = body.get('locale', 'en')
                if locale not in {'en', 'fi', 'sv'}:
                    raise ValueError('locale must be en, fi, or sv')
                return interpret(body.get('message'), self._coach_context(conn, customer_id, month, locale), transport=self.coach_transport)
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
            '/api/coach': {'message', 'locale'}, '/api/undo': set(), '/api/reset': set(),
        }
        if set(body) - common - fields.get(path, set()):
            raise ValueError('Unknown JSON body field')
        for name, value in body.items():
            if name == 'confirmed':
                if type(value) is not bool:
                    raise ValueError('confirmed must be a boolean')
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
        from .analytics import compare_periods, unusual_candidates, investment_cashflows
        from .forecast import safe_to_spend
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
        scope = account_scope(conn, customer_id)
        reference_date = min(end, scope['observed_end'])
        safe = safe_to_spend(conn, customer_id, reference_date, days=7)
        facts.append({'id': safe['fact_id'], 'value_cents': safe['safe_to_spend_cents'], 'unit': 'cents', 'label': safe['label'], 'status': 'scenario', 'available': safe['available'], 'reserve_floor_cents': safe['reserve_floor_cents'], 'reserve_floor_source': safe['reserve_floor_source']})
        safe_text = 'This estimate protects the sourced reserve, upcoming outflows, and a buffer based on earlier flexible spending.' if safe['available'] else 'There is not enough observed history yet to estimate a safe-to-spend amount.'
        candidates.append({'id': 'safe_to_spend', 'kind': 'safe_to_spend', 'copy_key': 'safe_to_spend' if safe['available'] else 'safe_unavailable', 'text': safe_text, 'fact_ids': [safe['fact_id']], 'materiality': _bounded_materiality(safe['safe_to_spend_cents']), 'urgency': 1, 'explainability': 1, 'addressability': 1, 'transaction_refs': safe['transaction_refs'], 'status': 'scenario', 'available': safe['available'], 'utility': True})
        investing = investment_cashflows(conn, customer_id, month, 12)
        facts.append({'id': investing['fact_id'], 'value_cents': investing['net_contributions_cents'], 'unit': 'cents', 'label': investing['label'], 'status': 'observed'})
        candidates.append({'id': 'investment_cashflow', 'kind': 'investment_cashflow', 'text': 'These are observed contributions and withdrawals, not portfolio value or performance.', 'fact_ids': [investing['fact_id']], 'materiality': _bounded_materiality(investing['total_contributions_cents']), 'urgency': 0, 'explainability': 1, 'addressability': 1, 'transaction_refs': investing['transaction_refs'], 'status': 'observed', 'utility': True})
        return {**scope, 'period': month, 'comparison_period': comparison_month, 'reference_date': reference_date, 'days': 7, 'months': 12, 'interface_locale': locale, 'facts': facts, 'candidates': candidates, 'transaction_refs': sorted({ref for item in candidates for ref in item.get('transaction_refs', [])}), 'scenario_ids': [row[0] for row in conn.execute('SELECT id FROM scenarios WHERE customer_id=?', (customer_id,))], 'goal_ids': [row[0] for row in conn.execute('SELECT id FROM goals WHERE customer_id=?', (customer_id,))]}

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
