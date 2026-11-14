"""Strict, read-only adapters from model function calls to verified calculators."""
import ast
import math
import re
from datetime import date
from decimal import Decimal, DecimalException, localcontext

from . import analytics, forecast, goals, scenarios, spender, statistics
from .agent_numbers import allowed_numbers
from .ledger import account_scope, month_bounds, shift_month, transactions
from .money import cents_to_euros, rounded


def _field(kind='STRING', **kwargs):
    return {'type': kind, **kwargs}


_DATES = {'start': _field(), 'end': _field()}
_FILTERS = {key: _field() for key in ('category', 'role', 'transaction_type', 'mcc_code', 'merchant_id')}
_SPECS = {
    'get_overview': ('Read balance, income, saving transfers, baskets and top spending categories.', {'month': _field()}, []),
    'spending_total': ('Exact outflow statistics. Defaults to consumption; an explicit transaction_type or role can select other flows.', {**_DATES, **_FILTERS}, ['start', 'end']),
    'compare_periods': ('Compare consumption in two periods with a precomputed percentage change.', {**_DATES, 'comparison_start': _field(), 'comparison_end': _field(), 'category': _field()}, ['start', 'end', 'comparison_start', 'comparison_end']),
    'monthly_trend': ('Observed consumption trend, up to 24 months; missing history is null, never zero.', {'months': _field('INTEGER', minimum=1, maximum=24), 'category': _field(), 'end_month': _field()}, ['months']),
    'list_transactions': ('Read at most 20 consumption rows, with private identifiers removed.', {**_DATES, 'category': _field(), 'limit': _field('INTEGER', minimum=1, maximum=20), 'sort': _field(enum=['newest', 'oldest', 'largest'])}, ['start', 'end']),
    'safe_to_spend': ('What the customer can spend this week and per day until next payday, after holding back every bill due before payday, a reserve and any saving target. Default horizon until_payday; week gives the older seven-day estimate. Not a guarantee.', {'horizon': _field(enum=['until_payday', 'week']), 'days': _field('INTEGER', minimum=1, maximum=30), 'reserve_floor_cents': _field('INTEGER', minimum=0)}, []),
    'safe_to_save': ('How much could be moved to savings now while still covering bills and typical everyday spending until next payday. Not a guarantee.', {'reserve_floor_cents': _field('INTEGER', minimum=0)}, []),
    'forecast_30_days': ('Pattern-based scheduled payments and lowest/ending balances over the next 30 days.', {}, []),
    'what_if_reduce': ('Unsaved preview of reducing an eligible discretionary category, with monthly and annual amounts.', {'category': _field(), 'percent': _field('NUMBER', minimum=0, maximum=100), 'month': _field()}, ['category', 'percent']),
    'goal_plan': ('Read-only target-date arithmetic, not an affordability assessment. Use a customer-selected target.', {'name': _field(maxLength=120), 'target_cents': _field('INTEGER', minimum=1), 'target_date': _field(), 'monthly_cents': _field('INTEGER', minimum=1)}, ['name', 'target_cents', 'target_date']),
    'list_goals': ('Read saved goal progress without changing any goal.', {}, []),
    'payday_pattern': ('Read observed salary changes and low balances before salary; not a future prediction.', {}, []),
    'recurring_payments': ('Read qualified recurring outflows, including saving transfers labelled separately.', {}, []),
    'spender_profile': ('Describe what kind of spender the customer is: one archetype for the last N complete months with reasons, one strength and one thing worth a look. Percentages are precomputed. Describes habits, not character.', {'end_month': _field(), 'months': _field('INTEGER', minimum=2, maximum=24)}, []),
    'irregular_buffer': ('Surprise must-pays (necessary but unpredictable costs) over the last months: count, total, monthly average and a suggested monthly set-aside, with the largest items.', {'end_month': _field(), 'months': _field('INTEGER', minimum=1, maximum=24)}, []),
    'calculate': ('Calculate with numbers already returned by tools, using + - * / and parentheses. Constants 0–12 and 100 are allowed for unit conversions.', {'expression': _field(maxLength=256)}, ['expression']),
    'explain_concept': ('Vetted glossary: emergency fund, safe-to-spend, fixed vs variable costs, three baskets, interest, compound interest, budget, VAT, net vs gross income, MCC.', {'topic': _field()}, ['topic']),
    'propose_action': ('Record a confirmation button, never execute it. Goal/scenario params must equal a preceding preview proposal.', {'kind': _field(enum=['create_goal', 'save_scenario', 'open_view']), 'params': _field('OBJECT', properties={'view': _field(), 'name': _field(), 'target_cents': _field('INTEGER'), 'target_date': _field(), 'category': _field(), 'percent': _field(), 'month': _field()})}, ['kind', 'params']),
}
DECLARATIONS = [{'name': name, 'description': description,
                 'parameters': {'type': 'OBJECT', 'properties': properties, 'required': required}}
                for name, (description, properties, required) in _SPECS.items()]

GLOSSARY = {
    'emergency fund': 'An emergency fund is money set aside for necessary, unexpected costs. Its size depends on your essential expenses and circumstances, so an account history alone cannot determine the right target.',
    'safe-to-spend': 'Safe-to-spend is an estimate of what you can use for everyday life until your next payday, after setting aside every bill due before then, a small reserve and any saving you planned. It uses past patterns and can miss obligations that are not recorded in the account.',
    'fixed vs variable costs': 'Fixed costs recur with fairly predictable amounts, while variable costs change with use or choices. Both can be essential, so variable does not mean unnecessary.',
    'three baskets': 'The three baskets are Must-pays (bills that come every month, such as rent and electricity), Surprise must-pays (necessary but hard to predict, such as a broken washing machine) and Little leaks (small everyday choices that add up, such as coffee and takeaway). Seeing which basket money falls into helps you plan for it.',
    'interest': 'Interest is the cost of borrowing money or the payment for holding savings. The actual terms depend on the agreement, which transaction data alone does not establish.',
    'compound interest': 'Compound interest means interest can itself earn or incur interest over time. The result depends on the rate, timing and terms, so it is not a promised return.',
    'budget': 'A budget is a plan for how your income will cover spending, saving and upcoming needs. You can adjust it when your circumstances or priorities change.',
    'vat': 'VAT is a consumption tax generally included in the price of goods and services. An account transaction does not establish your personal tax liability.',
    'net vs gross income': 'Gross income is income before deductions, while net income is what remains after deductions. A salary deposit shows money received, but does not by itself reveal the full gross amount or tax position.',
    'mcc': 'An MCC is a merchant category code describing a broad type of business. It identifies neither the merchant name nor the exact items in a purchase.',
}


def redact(text):
    text = re.sub(r'\b(?:CUST|ACC)(?:[_-][A-Za-z0-9_-]+|\d[A-Za-z0-9_-]*)\b', '[private identifier]', str(text), flags=re.I)
    return re.sub(r'\btx:[A-Za-z0-9:_-]+', '[private reference]', text)


class ToolContext:
    def __init__(self, conn, customer_id, month, *, message='', history=()):
        self.scope = account_scope(conn, customer_id)
        self.month = month
        self.start, self.end = month_bounds(month)
        statistics._period(self.scope, self.start, self.end)
        self.reference_date = transactions(conn, customer_id, end=self.end)[-1]['date']
        self.message, self.history = message, history
        self.evidence, self.results, self.actions, self.proposals = {}, [], [], []
        self.private_values = (customer_id, self.scope['account_id'])

    def sanitize(self, value, *, decorate=True):
        if isinstance(value, dict):
            output = {}
            for key, item in value.items():
                if (key in {'customer_id', 'account_id', 'raw_json', 'row_hash', 'source_line', 'postal_code', 'id'} or
                        'transaction_ref' in key or key.endswith(('_fact_id', '_fact_ids')) or
                        key in {'fact_id', 'fact_ids', 'active_scenario_id', 'inactive_linked_scenario_ids', 'scheduled_item_ids'}):
                    continue
                # A monthly chart has an explicitly documented 24-point maximum.
                limit = 24 if key == 'series' else 20
                if isinstance(item, list) and len(item) > limit:
                    output[key + '_total_count'] = len(item)
                    output[key + '_truncated'] = True
                    item = item[:limit]
                output[key] = self.sanitize(item, decorate=decorate and key not in {'proposal', 'params'})
                if decorate and key.endswith('_cents') and type(item) is int:
                    display_key = key[:-6] if key[:-6] not in value else key[:-6] + '_display'
                    output[display_key] = '€' + cents_to_euros(item)
            return output
        if isinstance(value, list):
            return [self.sanitize(item, decorate=decorate) for item in value]
        if isinstance(value, str):
            for private in self.private_values:
                value = re.sub(r'(?<!\w)' + re.escape(private) + r'(?!\w)', '[private identifier]', value)
            return redact(value)
        return value


def _validate(name, args):
    if not isinstance(name, str) or name not in _SPECS or not isinstance(args, dict):
        raise ValueError('Unknown tool or invalid arguments')
    _, properties, required = _SPECS[name]
    if set(args) - set(properties) or not set(required) <= set(args):
        raise ValueError('Unknown or missing tool arguments')
    types = {'STRING': (str,), 'INTEGER': (int,), 'NUMBER': (int, float), 'OBJECT': (dict,)}
    for key, value in args.items():
        spec = properties[key]
        if type(value) not in types[spec['type']]:
            raise ValueError('Invalid argument type: ' + key)
        if isinstance(value, str) and (not value.strip() or len(value) > spec.get('maxLength', 120)):
            raise ValueError('Invalid argument length: ' + key)
        if type(value) in (int, float):
            if not math.isfinite(value) or abs(value) > 10**12 or value < spec.get('minimum', -10**12) or value > spec.get('maximum', 10**12):
                raise ValueError('Argument outside allowed range: ' + key)
        if 'enum' in spec and value not in spec['enum']:
            raise ValueError('Unsupported argument: ' + key)


def _filters(conn, customer_id, args):
    from .api import Application
    filters = {key: args[key] for key in _FILTERS if key in args}
    if not {'role', 'transaction_type'} & set(filters):
        filters['consumption_only'] = 'true'
    return Application._validated_statistics_filters(conn, customer_id, filters)


def _period(ctx, args):
    start, end = args.get('start', ctx.start), args.get('end', ctx.end)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', start) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', end):
        raise ValueError('Dates must use YYYY-MM-DD')
    statistics._period(ctx.scope, start, end)
    return start, end


def _month(ctx, month):
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Month must use YYYY-MM')
    start, end = month_bounds(month)
    statistics._period(ctx.scope, start, end)
    return start, end


def _refs(value):
    if isinstance(value, dict):
        result = []
        for key, item in value.items():
            if 'transaction_ref' in key:
                result.extend(item if isinstance(item, list) else [item])
            else:
                result.extend(_refs(item))
        return result
    if isinstance(value, list):
        return [ref for item in value for ref in _refs(item)]
    return []


def _finish(conn, customer_id, ctx, result, period, basis, query=None, label=None):
    evidence_id = 'ev' + str(len(ctx.evidence) + 1)
    record = {'id': evidence_id, 'label': label or basis, 'transaction_refs': sorted(set(_refs(result))), 'query': query}
    if query:
        rows = transactions(conn, customer_id, query['start'], query['end'],
                            {k: v for k, v in query.items() if k not in {'start', 'end'}})
        record['count'] = len(rows)
    else:
        record['count'] = 0
    ctx.evidence[evidence_id] = record
    safe = ctx.sanitize(result)
    safe.update(period={'start': period[0], 'end': period[1]}, basis=basis, evidence_id=evidence_id)
    ctx.results.append(safe)
    return safe


def _share(part, whole):
    return format((Decimal(part) * 100 / whole).quantize(Decimal('.1')), 'f') if whole else None


def _add_shares(rows, field):
    """Precompute shares so the model never needs percentage arithmetic."""
    whole = sum(row[field] for row in rows)
    for row in rows:
        row['share_percent'] = _share(row[field], whole)
    return rows


def _calculate(expression, ctx):
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, ValueError, RecursionError):
        raise ValueError('Use numeric literals, + - * / and parentheses only') from None
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError('Expression is too complex')
    sourced = allowed_numbers(ctx.results) | {Decimal(i) for i in range(13)} | {Decimal(100)}

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = Decimal(ast.get_source_segment(expression, node))
            if not value.is_finite() or value not in sourced:
                raise ValueError('Use only numbers already returned by tools')
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            if isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float):
                value = Decimal(ast.get_source_segment(expression, node.operand)) * (-1 if isinstance(node.op, ast.USub) else 1)
                if not value.is_finite() or value not in sourced:
                    raise ValueError('Use only numbers already returned by tools')
            else:
                value = evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add): value = a + b
            elif isinstance(node.op, ast.Sub): value = a - b
            elif isinstance(node.op, ast.Mult): value = a * b
            else: value = a / b
        else:
            raise ValueError('Use numeric literals, + - * / and parentheses only')
        if not value.is_finite() or abs(value) > 10**12:
            raise ValueError('Calculation outside supported range')
        return value

    try:
        with localcontext() as context:
            context.prec = 28
            value = evaluate(tree.body)
            cents = rounded(value * 100)
    except (DecimalException, OverflowError):
        raise ValueError('Invalid or unbounded arithmetic') from None
    return {'value': format(value.normalize(), 'f'), 'value_cents': cents,
            'rounding': 'Euro display rounded half up to cents; value is unrounded.'}


def dispatch(conn, customer_id, ctx, name, args):
    _validate(name, args)
    period, query = (ctx.start, ctx.end), None
    basis = _SPECS[name][0]
    if name in {'spending_total', 'compare_periods', 'list_transactions'}:
        period = _period(ctx, args)
        filters = _filters(conn, customer_id, args)
        query = {'start': period[0], 'end': period[1], **filters}
        basis = ('Observed consumption outflows; refunds and transfers are separate.' if filters.get('consumption_only') else
                 'Observed flows matching exact filters; gross outflows and inflows are separate.')
    if name == 'spending_total':
        result = statistics.transaction_statistics(conn, customer_id, *period, filters)
        result.update(total_cents=result['outflow_total_cents'], count=result['outflow_count'])
        result['highlight'] = {'label': args.get('category', 'Selected spending'), 'value': '€' + cents_to_euros(result['total_cents']), 'caption': f"{result['count']} payments · {period[0]} to {period[1]}"}
    elif name == 'compare_periods':
        comparison = _period(ctx, {'start': args['comparison_start'], 'end': args['comparison_end']})
        result = statistics.compare_transaction_statistics(conn, customer_id, *period, *comparison, filters)
        base = result['comparison']['outflow_total_cents']
        result['percent_change'] = format((Decimal(result['outflow_delta_cents']) * 100 / base).quantize(Decimal('.01')), 'f') if base else None
        result['percentage_basis'] = 'Change divided by comparison outflow; rounded to two decimals. Unavailable when comparison is zero.'
        # Each period gets an exact transaction query, including disjoint periods.
        _finish(conn, customer_id, ctx, result['comparison'], comparison, basis,
                {'start': comparison[0], 'end': comparison[1], **filters}, 'Comparison period')
        result['chart'] = {'kind': 'bar', 'title': 'Spending comparison', 'series': [
            {'label': comparison[0] + ' to ' + comparison[1], 'value_cents': base},
            {'label': period[0] + ' to ' + period[1], 'value_cents': result['current']['outflow_total_cents']}]}
    elif name == 'list_transactions':
        rows = transactions(conn, customer_id, *period, filters)
        sort = args.get('sort', 'newest')
        if sort == 'newest': rows.reverse()
        elif sort == 'largest': rows.sort(key=lambda row: (-abs(row['amount_cents']), row['date']))
        selected = rows[:args.get('limit', 20)]
        fields = ('date', 'category', 'transaction_type', 'amount_cents', 'merchant_id', 'mcc_code')
        result = {'transactions': [{**{k: row[k] for k in fields}, 'weekday': date.fromisoformat(row['date']).strftime('%A')} for row in selected],
                  'count': len(rows), 'returned_count': len(selected), 'truncated': len(rows) > len(selected),
                  'transaction_refs': [row['transaction_ref'] for row in selected]}
    elif name == 'get_overview':
        month = args.get('month', ctx.month)
        period = _month(ctx, month)
        overview = analytics.money_map(conn, customer_id, month)
        rows = transactions(conn, customer_id, end=min(period[1], ctx.scope['observed_end']))
        categories = sorted({r['category'] for r in transactions(conn, customer_id, *period) if r['amount_cents'] < 0 and r['transaction_type'] in {'purchase', 'housing_payment', 'utilities_payment'}})
        tops = [{'category': category, **analytics.summarize(transactions(conn, customer_id, *period, {'category': category, 'consumption_only': 'true'}))} for category in categories]
        result = {k: overview[k] for k in ('salary_cents', 'other_income_cents', 'consumption_cents', 'committed_saving_transfers_cents', 'free_cashflow_cents', 'transaction_refs')}
        result.update(balance_cents=rows[-1]['balance_after_cents'], balance_date=rows[-1]['date'],
                      observed_start=ctx.scope['observed_start'], observed_end=ctx.scope['observed_end'],
                      baskets=analytics.three_basket_profile(conn, customer_id, month)['baskets'],
                      top_categories=sorted(tops, key=lambda r: -r['total_cents']))
        _add_shares(result['baskets'], 'amount_cents')
        _add_shares(result['top_categories'], 'total_cents')
        result['chart'] = {'kind': 'baskets', 'title': 'Three spending baskets', 'series': [{'label': r['role'], 'value_cents': r['amount_cents']} for r in result['baskets']]}
        query = {'start': period[0], 'end': period[1]}
    elif name == 'monthly_trend':
        end_month = args.get('end_month', ctx.month)
        _month(ctx, end_month)
        filters = _filters(conn, customer_id, args)
        result = analytics.trend_series(conn, customer_id, end_month, args['months'], filters)
        result['chart'] = {'kind': 'line', 'title': args.get('category', 'Consumption') + ' by month', 'series': [{'label': row['month'], 'value_cents': row['total_cents']} for row in result['months']]}
        period = (shift_month(end_month, 1 - args['months']) + '-01', month_bounds(end_month)[1])
        query = {'start': period[0], 'end': period[1], **filters}
        basis = 'Monthly consumption; missing history is unavailable. Charts retain up to 24 exact monthly points.'
    elif name in {'safe_to_spend', 'safe_to_save'} and args.get('horizon', 'week' if 'days' in args else 'until_payday') == 'until_payday':
        from .api import planning_profile
        if 'days' in args:
            raise ValueError('days applies only to horizon week')
        raw = forecast.safe_until_payday(conn, customer_id, as_of=ctx.reference_date,
                                         reserve_floor_cents=args.get('reserve_floor_cents'),
                                         profile=planning_profile(conn, customer_id, ctx.reference_date))
        result = {key: value for key, value in raw.items() if key not in {'comparison_transaction_refs'}}
        if name == 'safe_to_save':
            result['highlight'] = {'label': 'Safe to save now', 'value': '€' + cents_to_euros(raw['safe_to_save_cents']), 'caption': 'Until payday ' + raw['next_payday']}
        else:
            result['highlight'] = {'label': 'Safe to spend this week', 'value': '€' + cents_to_euros(raw['this_week_cents']), 'caption': '€' + cents_to_euros(raw['per_day_cents']) + ' a day until ' + raw['next_payday']}
        period = (ctx.reference_date, raw['next_payday'])
        query = {'start': ctx.scope['observed_start'], 'end': ctx.reference_date}
    elif name == 'safe_to_spend':
        args = {key: value for key, value in args.items() if key != 'horizon'}
        result = forecast.safe_to_spend(conn, customer_id, as_of=ctx.reference_date, **args)
        period = (ctx.reference_date, result['horizon_end'])
        query = {'start': ctx.scope['observed_start'], 'end': ctx.reference_date}
    elif name == 'forecast_30_days':
        raw = forecast.preview_30_days(conn, customer_id, ctx.reference_date)
        result = {key: raw[key] for key in ('starting_balance_cents', 'scheduled_items', 'assumptions', 'transaction_refs')}
        result.update(ending_balance_cents=raw['projected'][-1]['balance_cents'], lowest_balance_cents=min(r['balance_cents'] for r in raw['projected']), observed=False)
        period = (ctx.reference_date, raw['projected'][-1]['date'])
        query = {'start': ctx.scope['observed_start'], 'end': ctx.reference_date}
    elif name == 'what_if_reduce':
        month = args.get('month', ctx.month)
        period = _month(ctx, month)
        _filters(conn, customer_id, args)
        result = scenarios.preview_spending_adjustment(conn, customer_id, *period, args['category'], args['percent'])
        result.update(monthly_freed_cents=result['modeled_monthly_contribution_cents'], yearly_freed_cents=result['modeled_monthly_contribution_cents'] * 12)
        result['proposal'] = {'category': args['category'], 'percent': result['percent'], 'month': month, 'name': 'Spending adjustment'}
        ctx.proposals.append(('save_scenario', result['proposal']))
        query = {'start': period[0], 'end': period[1], 'category': args['category'], 'consumption_only': 'true'}
    elif name == 'goal_plan':
        sourced = allowed_numbers(ctx.results, ctx.message, ctx.history)
        for field in ('target_cents', 'monthly_cents'):
            if field in args and Decimal(args[field]) / 100 not in sourced:
                raise ValueError('Goal amounts must come from customer inputs or previous calculations')
        reference = goals._reference(conn, customer_id, ctx.reference_date)
        target = date.fromisoformat(args['target_date'])
        months = goals._months_remaining(reference, target)
        if target <= reference or months < 1:
            raise ValueError('Goal target must be at least one calendar month ahead')
        target_cents = args['target_cents']
        monthly = args.get('monthly_cents')
        result = {'name': args['name'].strip(), 'target_cents': target_cents, 'target_date': target.isoformat(),
                  'months_remaining': months, 'required_monthly_cents': (target_cents + months - 1) // months,
                  'months_needed': (target_cents + monthly - 1) // monthly if monthly else None,
                  'monthly_cents': monthly, 'current_saved_cents': 0, 'observed': False,
                  'assumptions': ['New goal starts with no assigned savings; no interest or investment return assumed.', 'Calendar-month ceiling arithmetic; capacity and affordability are not assessed.']}
        result['proposal'] = {k: result[k] for k in ('name', 'target_cents', 'target_date')}
        ctx.proposals.append(('create_goal', result['proposal']))
        period = (ctx.reference_date, target.isoformat())
    elif name == 'list_goals':
        ids = [row[0] for row in conn.execute('SELECT id FROM goals WHERE customer_id=? ORDER BY created_at,id', (customer_id,))]
        result = {'goals': [goals.goal_plan(conn, customer_id, key, ctx.reference_date) for key in ids[:20]], 'count': len(ids), 'truncated': len(ids) > 20}
    elif name == 'payday_pattern':
        result = {'payday': analytics.payday_timing_signal(conn, customer_id, ctx.month), 'salary': analytics.salary_change_signal(conn, customer_id, ctx.month)}
        period = (max(ctx.scope['observed_start'], shift_month(ctx.month, -8) + '-01'), ctx.reference_date)
        query = {'start': period[0], 'end': period[1]}
    elif name == 'recurring_payments':
        rows = [r for r in forecast.detect_recurring(conn, customer_id, ctx.reference_date) if r['amount_cents'] < 0]
        result = {'items': rows, 'count': len(rows)}
        period = (min((r['history_start'] for r in rows), default=ctx.start), max((r['history_end'] for r in rows), default=ctx.reference_date))
        query = {'start': period[0], 'end': period[1]}
    elif name in {'spender_profile', 'irregular_buffer'}:
        end_month = args.get('end_month')
        if end_month is not None:
            _month(ctx, end_month)
        elif analytics.latest_complete_month(conn, customer_id) > ctx.month:
            end_month = ctx.month
        function = spender.spender_profile if name == 'spender_profile' else spender.irregular_buffer
        result = function(conn, customer_id, end_month=end_month, **({'months': args['months']} if 'months' in args else {}))
        if name == 'spender_profile':
            result = {key: value for key, value in result.items() if key not in {'archetype_labels', 'thresholds', 'rule'}}
        if result.get('period'):
            period = (result['period']['start'], result['period']['end'])
            query = {'start': period[0], 'end': period[1]}
    elif name == 'calculate':
        result = _calculate(args['expression'], ctx)
    elif name == 'explain_concept':
        definition = GLOSSARY.get(args['topic'].strip().casefold())
        result = {'known': definition is not None, 'definition': definition}
    elif name == 'propose_action':
        kind, params = args['kind'], args['params']
        if kind == 'open_view':
            if set(params) != {'view'} or params['view'] not in ('home', 'trends', 'goals', 'coach'):
                raise ValueError('Unknown view')
        elif (kind, params) not in ctx.proposals:
            raise ValueError('First create a matching read-only preview')
        label = {'create_goal': 'Review goal', 'save_scenario': 'Review spending scenario', 'open_view': 'Open view'}[kind]
        action = {'kind': kind, 'label': label, 'params': ctx.sanitize(params, decorate=False)}
        if action not in ctx.actions:
            if len(ctx.actions) >= 3:
                raise ValueError('At most three proposals per answer')
            ctx.actions.append(action)
        result = {'proposed': True, 'requires_confirmation': kind != 'open_view', 'action': action}
    return _finish(conn, customer_id, ctx, result, period, basis, query,
                   f"{args.get('category', 'Account history')} · {period[0]} to {period[1]}")
