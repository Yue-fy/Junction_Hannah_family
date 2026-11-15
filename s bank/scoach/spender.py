"""Spender profile ("What kind of spender am I?") and the Surprise must-pays buffer.

Everything here is deterministic arithmetic over the account-scoped ledger
(`ledger.transactions`).  Amounts are integer cents.  Percentages are
precomputed decimal strings with one decimal (for example ``"42.5"``) so a
language model can quote them but never has to derive them.

Basket names used in customer-facing text:
``fixed_obligation`` -> "Must-pays", ``flexible_essential`` -> "Surprise
must-pays", ``discretionary`` -> "Free choices", which splits into "Little
leaks" (purchases under LITTLE_LEAK_MAX_CENTS, default €40) and "Bigger
choices" (everything else, e.g. travel or a car rental).
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import sqrt

from .analytics import latest_complete_month, payday_timing_signal
from .labels import category_label
from .ledger import account_scope, fact_id, month_bounds, shift_month, transactions
from .money import median_cents, rounded


# --------------------------------------------------------------------------
# Definitions and thresholds (named so the integrator and tests can cite them)
# --------------------------------------------------------------------------
CONSUMPTION_TYPES = ('purchase', 'utilities_payment', 'housing_payment')
SAVING_TYPES = ('investment_deposit', 'salary_sweep')
BASKET_ROLES = ('fixed_obligation', 'flexible_essential', 'discretionary')
BASKET_LABELS = {
    'fixed_obligation': 'Must-pays',
    'flexible_essential': 'Surprise must-pays',
    'discretionary': 'Free choices',
}
LITTLE_LEAK_MAX_CENTS = 4000    # a Little leak is a free-choice purchase under €40

MIN_PROFILE_MONTHS = 2          # fewer complete months -> available False
MAX_PROFILE_MONTHS = 24
PAYDAY_WINDOW_DAYS = 7          # salary day plus the following six days

# Archetype rules, evaluated in ARCHETYPE_PRIORITY order; the first match wins.
# "Free choices" = discretionary spending; Little leaks = free-choice purchases
# under LITTLE_LEAK_MAX_CENTS; Bigger choices = the rest.
# 1. payday_sprinter: free-choice share in the payday window >= PAYDAY_SHARE_MIN,
#    or >= PAYDAY_SHARE_WITH_LOW_BALANCE_MIN when payday_timing_signal qualified.
# 2. weekend_spender: weekend share of free-choice spending >= WEEKEND_SHARE_MIN.
#    Rules 1-2 need at least MIN_RHYTHM_PURCHASES free-choice purchases.
# 3. small_and_often: Little leaks per week >= SMALL_OFTEN_PER_WEEK_MIN and
#    median Little leak <= SMALL_OFTEN_MEDIAN_MAX_CENTS.
# 4. big_ticket_occasional: Bigger choices make >= BIG_TICKET_SHARE_MIN of
#    free-choice spending (at least MIN_BIGGER_PURCHASES of them) and Little
#    leaks per week <= BIG_TICKET_PER_WEEK_MAX.
# 5. steady_planner: saving share of salary >= STEADY_SAVING_SHARE_MIN,
#    free-choice month-to-month variability <= STEADY_VARIABILITY_MAX and no
#    qualified low-balance-before-payday pattern.
# 6. balanced: everything else.
MIN_RHYTHM_PURCHASES = 8
PAYDAY_SHARE_MIN = Decimal('45')
PAYDAY_SHARE_WITH_LOW_BALANCE_MIN = Decimal('35')
WEEKEND_SHARE_MIN = Decimal('50')
SMALL_OFTEN_PER_WEEK_MIN = Decimal('4')
SMALL_OFTEN_MEDIAN_MAX_CENTS = 1500
BIG_TICKET_CENTS = LITTLE_LEAK_MAX_CENTS   # kept for older callers: Bigger choices start at €40
BIG_TICKET_SHARE_MIN = Decimal('60')
MIN_BIGGER_PURCHASES = 3
BIG_TICKET_PER_WEEK_MAX = Decimal('1.5')
STEADY_SAVING_SHARE_MIN = Decimal('10')
STEADY_VARIABILITY_MAX = Decimal('25')

ARCHETYPE_PRIORITY = ('payday_sprinter', 'weekend_spender', 'small_and_often',
                      'big_ticket_occasional', 'steady_planner', 'balanced')
ARCHETYPE_LABELS = {
    'steady_planner': {'en': 'Steady Planner', 'fi': 'Tasainen suunnittelija', 'sv': 'Stadig planerare'},
    'payday_sprinter': {'en': 'Payday Sprinter', 'fi': 'Palkkapäivän pikajuoksija', 'sv': 'Lönedagssprinter'},
    'weekend_spender': {'en': 'Weekend Spender', 'fi': 'Viikonloppukuluttaja', 'sv': 'Helgkonsument'},
    'small_and_often': {'en': 'Small-and-Often', 'fi': 'Pienesti mutta usein', 'sv': 'Smått och ofta'},
    'big_ticket_occasional': {'en': 'Big-Ticket Occasional', 'fi': 'Harvoin mutta isosti', 'sv': 'Sällan men stort'},
    'balanced': {'en': 'Balanced', 'fi': 'Tasapainoinen', 'sv': 'Balanserad'},
}

# Surprise must-pays buffer
BUFFER_LARGE_MULTIPLIER = 3     # essential purchase > 3 x own category median
BUFFER_MIN_CATEGORY_PURCHASES = 5
BUFFER_MAX_ITEMS = 20

_LOCALES = ('en', 'fi', 'sv')


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _pct(numerator, denominator):
    """Percentage string with one decimal (ROUND_HALF_UP), or None when denominator is 0."""
    if not denominator:
        return None
    value = Decimal(numerator) * 100 / Decimal(denominator)
    return str(value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _one_decimal(value):
    return str(Decimal(value).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _euro(cents, locale='en'):
    """Format integer cents as euros: '€1,234.50' (en) or '1 234,50 €' (fi/sv)."""
    sign = '-' if cents < 0 else ''
    whole, part = divmod(abs(cents), 100)
    if locale == 'en':
        return sign + '€' + format(whole, ',') + '.' + format(part, '02d')
    return sign + format(whole, ',').replace(',', ' ') + ',' + format(part, '02d') + ' €'


def _euro_whole(cents, locale='en'):
    """Whole-euro thresholds: '€40' (en) or '40 €' (fi/sv); falls back to cents when not whole."""
    if cents % 100:
        return _euro(cents, locale)
    whole = format(abs(cents) // 100, ',')
    return '€' + whole if locale == 'en' else whole.replace(',', ' ') + ' €'


def _percent_text(value, locale='en'):
    if locale == 'en':
        return value + '%'
    return value.replace('.', ',') + ' %'


def _number_text(value, locale='en'):
    return value if locale == 'en' else value.replace('.', ',')


def _variability(values):
    """Coefficient of variation (population stdev / mean) in percent, one decimal string."""
    if len(values) < 2:
        return None
    mean = Decimal(sum(values)) / len(values)
    if mean <= 0:
        return None
    variance = sum((Decimal(v) - mean) ** 2 for v in values) / len(values)
    return _one_decimal(Decimal(str(sqrt(float(variance)))) * 100 / mean)


def _is_consumption(row):
    return row['amount_cents'] < 0 and row['transaction_type'] in CONSUMPTION_TYPES


def _window(conn, customer_id, end_month, months, maximum):
    """Resolve the complete-month window. Returns (scope, month list) or raises ValueError."""
    if type(months) is not int or not 1 <= months <= maximum:
        raise ValueError('months must be 1-' + str(maximum))
    scope = account_scope(conn, customer_id)
    end_month = end_month or latest_complete_month(conn, customer_id)
    month_bounds(end_month)
    if not scope['observed_start'][:7] <= end_month <= scope['observed_end'][:7]:
        raise ValueError('Month outside observed dataset coverage')
    start_month = max(shift_month(end_month, -months + 1), scope['observed_start'][:7])
    month_list = []
    month = start_month
    while month <= end_month:
        month_list.append(month)
        month = shift_month(month, 1)
    return scope, month_list


# --------------------------------------------------------------------------
# Fact sentences (EN text in the profile, FI/SV for offline_summary)
# --------------------------------------------------------------------------
_TEMPLATES = {
    'payday_share': {
        'en': '{percent} of your free-choice spending happened in the 7 days after payday.',
        'fi': '{percent} vapaavalintaisista menoistasi kertyi 7 päivän sisällä palkkapäivästä.',
        'sv': '{percent} av dina valfria utgifter skedde inom 7 dagar efter lönedagen.',
    },
    'low_balance_before_payday': {
        'en': 'Your balance dipped below {threshold} in the week before payday {count} times out of {windows}.',
        'fi': 'Saldosi laski alle {threshold} palkkapäivää edeltävällä viikolla {count} kertaa {windows} kuukaudesta.',
        'sv': 'Ditt saldo sjönk under {threshold} veckan före lönedagen {count} gånger av {windows}.',
    },
    'no_low_balance_before_payday': {
        'en': 'Your balance did not run low in the week before payday.',
        'fi': 'Saldosi ei käynyt matalalla palkkapäivää edeltävällä viikolla.',
        'sv': 'Ditt saldo blev inte lågt veckan före lönedagen.',
    },
    'weekend_share': {
        'en': '{percent} of your free-choice spending happened on Saturdays and Sundays.',
        'fi': '{percent} vapaavalintaisista menoistasi osui lauantaille ja sunnuntaille.',
        'sv': '{percent} av dina valfria utgifter skedde på lördagar och söndagar.',
    },
    'purchases_per_week': {
        'en': 'You made about {value} small purchases (under {threshold}) a week.',
        'fi': 'Teit noin {value} pientä, alle {threshold} ostosta viikossa.',
        'sv': 'Du gjorde ungefär {value} små köp (under {threshold}) i veckan.',
    },
    'median_purchase': {
        'en': 'A typical small purchase was {amount}.',
        'fi': 'Tyypillinen pieni ostos oli {amount}.',
        'sv': 'Ett typiskt litet köp var {amount}.',
    },
    'bigger_choices_share': {
        'en': '{percent} of your free-choice spending went on bigger purchases of {threshold} or more.',
        'fi': '{percent} vapaavalintaisista menoistasi meni vähintään {threshold} suuruisiin ostoksiin.',
        'sv': '{percent} av dina valfria utgifter gick till större köp på {threshold} eller mer.',
    },
    'largest_bigger_choice': {
        'en': 'Your largest bigger purchase was {amount} ({category}).',
        'fi': 'Suurin isompi ostoksesi oli {amount} ({category}).',
        'sv': 'Ditt största större köp var {amount} ({category}).',
    },
    'saving_share': {
        'en': 'You moved {percent} of your salary into saving or investing.',
        'fi': 'Siirsit {percent} palkastasi säästöön tai sijoituksiin.',
        'sv': 'Du flyttade {percent} av din lön till sparande eller investeringar.',
    },
    'free_choice_variability': {
        'en': 'Your free-choice spending varied by {percent} from month to month.',
        'fi': 'Vapaavalintaiset menosi vaihtelivat {percent} kuukaudesta toiseen.',
        'sv': 'Dina valfria utgifter varierade med {percent} från månad till månad.',
    },
    'must_pays_share': {
        'en': 'Must-pays were {percent} of your spending.',
        'fi': 'Pakolliset menot olivat {percent} kulutuksestasi.',
        'sv': 'Nödvändiga utgifter var {percent} av dina utgifter.',
    },
    'free_choice_share': {
        'en': 'Free choices were {percent} of your spending.',
        'fi': 'Vapaavalintaiset menot olivat {percent} kulutuksestasi.',
        'sv': 'Valfria utgifter var {percent} av dina utgifter.',
    },
    'little_leaks_monthly': {
        'en': 'Small purchases under {threshold} came to about {amount} a month.',
        'fi': 'Alle {threshold} pikkuostoksia kertyi noin {amount} kuukaudessa.',
        'sv': 'Små köp under {threshold} blev ungefär {amount} i månaden.',
    },
    'free_choice_monthly': {
        'en': 'Free choices came to about {amount} a month.',
        'fi': 'Vapaavalintaisia menoja kertyi noin {amount} kuukaudessa.',
        'sv': 'Valfria utgifter blev ungefär {amount} i månaden.',
    },
    'top_category_annual': {
        'en': '{category} spending adds up to about {amount} a year.',
        'fi': 'Luokassa {category} menoja kertyy noin {amount} vuodessa.',
        'sv': '{category} blir ungefär {amount} per år.',
    },
}

# One plain sentence per archetype, with at most one number, using the same figures as the baskets.
_EXPLANATIONS = {
    'payday_sprinter': ('A large part of your free-choice spending comes soon after payday: {percent} in the first week.',
                        'Suuri osa vapaavalintaisista menoistasi osuu heti palkkapäivän jälkeen: {percent} ensimmäisellä viikolla.',
                        'En stor del av dina valfria utgifter kommer strax efter lönedagen: {percent} första veckan.'),
    'weekend_spender': ('Your free-choice spending happens mostly at weekends: {percent} on Saturdays and Sundays.',
                        'Vapaavalintaiset menosi osuvat enimmäkseen viikonloppuihin: {percent} lauantaille ja sunnuntaille.',
                        'Dina valfria utgifter sker mest på helger: {percent} på lördagar och söndagar.'),
    'small_and_often': ('You buy small things often: about {value} purchases under {threshold} a week.',
                        'Ostat pieniä asioita usein: noin {value} alle {threshold} ostosta viikossa.',
                        'Du köper små saker ofta: ungefär {value} köp under {threshold} i veckan.'),
    'big_ticket_occasional': ('You buy less often but bigger: {percent} of your free-choice spending went on purchases of {threshold} or more.',
                              'Ostat harvemmin mutta isommin: {percent} vapaavalintaisista menoistasi meni vähintään {threshold} ostoksiin.',
                              'Du köper mer sällan men större: {percent} av dina valfria utgifter gick till köp på {threshold} eller mer.'),
    'steady_planner': ('You move money to saving every month and your free-choice spending stays steady.',
                       'Siirrät rahaa säästöön joka kuukausi, ja vapaavalintaiset menosi pysyvät tasaisina.',
                       'Du för över pengar till sparande varje månad och dina valfria utgifter håller sig jämna.'),
    'balanced': ('No single habit stands out: free choices were {percent} of your spending.',
                 'Mikään yksittäinen tapa ei erotu: vapaavalintaiset menot olivat {percent} kulutuksestasi.',
                 'Ingen enskild vana sticker ut: valfria utgifter var {percent} av dina utgifter.'),
}


def _fact(fact_key, **values):
    """Build a fact dict: {'fact': id, 'text': English sentence, ...values}."""
    item = {'fact': fact_key}
    item.update(values)
    item['text'] = _render(item, 'en')
    return item


def _render(item, locale):
    template = _TEMPLATES[item['fact']].get(locale) or _TEMPLATES[item['fact']]['en']
    fields = {}
    if 'percent' in item:
        fields['percent'] = _percent_text(item['percent'], locale)
    if 'amount_cents' in item:
        fields['amount'] = _euro(item['amount_cents'], locale)
    if 'threshold_cents' in item:
        fields['threshold'] = _euro_whole(item['threshold_cents'], locale)
    if 'value' in item:
        fields['value'] = _number_text(item['value'], locale)
    for key in ('count', 'windows'):
        if key in item:
            fields[key] = item[key]
    if 'category' in item:
        fields['category'] = category_label(item['category'], locale) if locale != 'en' else item['category']
    return template.format(**fields)


# --------------------------------------------------------------------------
# Spender profile
# --------------------------------------------------------------------------
def spender_profile(conn, customer_id, end_month=None, months=6):
    """Describe the customer's spending habits and pick one archetype.

    Args:
        conn: sqlite3 connection with the S-Coach schema.
        customer_id: customer id (account scope is enforced by the ledger).
        end_month: 'YYYY-MM', last complete month to include. Default: the
            latest complete month in the data (analytics.latest_complete_month).
        months: number of complete calendar months to look back (1-24, default 6).
            The window is clipped to the customer's observed history.

    Returns dict. If fewer than MIN_PROFILE_MONTHS complete months exist:
        {'available': False, 'reason': str, 'months_used': int, 'period': {...}}.
    Otherwise:
        available: True
        archetype: one of ARCHETYPE_PRIORITY ids
        archetype_label: English display name, e.g. 'Payday Sprinter'
        archetype_labels: {'en','fi','sv'} display names
        why: 2-3 fact dicts {'fact': id, 'text': English sentence, plus value
             fields such as 'percent' (one-decimal string), 'amount_cents' (int),
             'threshold_cents', 'value', 'count', 'windows', 'category'}
        strength: one fact dict (a positive habit)
        watch: one fact dict (one thing worth a look)
        figures: every computed number (cents ints, percentages one-decimal strings):
            consumption_cents, monthly_consumption_cents,
            baskets {role: {label, amount_cents, share_percent, monthly_cents[],
                            monthly_average_cents, variability_percent}},
            little_leaks {purchase_count, weekend_cents, weekend_share_percent,
                          payday_window_cents, payday_share_percent,
                          median_purchase_cents, purchases_per_week,
                          big_ticket_cents, big_ticket_share_percent,
                          largest {category, date, amount_cents} | None},
            top_little_leaks_categories [{category, total_cents, annualised_cents,
                                          share_of_little_leaks_percent}] (max 3),
            saving {salary_cents, saved_cents, investment_deposit_cents,
                    salary_sweep_cents, share_of_salary_percent},
            payday_pattern {available, qualified, low_balance_event_count,
                            observed_window_count, low_balance_threshold_cents,
                            lowest_pre_salary_balance_cents}
        thresholds: the named constants used for the rules
        rule: short English sentence of the rule that matched
        period: {'start': ISO date, 'end': ISO date}
        months_used: int
        label_note: 'A description of your last N months. It changes as your habits do.'
        basis: what was counted
        transaction_refs: list of evidence transaction refs
        fact_id, observed: True
    Raises ValueError for an unknown customer or a month outside coverage.
    """
    scope, month_list = _window(conn, customer_id, end_month, months, MAX_PROFILE_MONTHS)
    start = month_bounds(month_list[0])[0]
    end = month_bounds(month_list[-1])[1]
    period = {'start': start, 'end': end}
    n = len(month_list)
    if n < MIN_PROFILE_MONTHS:
        return {
            **scope, 'available': False, 'months_used': n, 'period': period,
            'reason': 'At least ' + str(MIN_PROFILE_MONTHS) + ' complete months of history are needed for a spender profile',
            'transaction_refs': [], 'observed': True,
        }

    history_start = (date.fromisoformat(start) - timedelta(days=PAYDAY_WINDOW_DAYS)).isoformat()
    all_rows = transactions(conn, customer_id, history_start, end)
    rows = [r for r in all_rows if r['date'] >= start]
    consumption = [r for r in rows if _is_consumption(r)]
    total = -sum(r['amount_cents'] for r in consumption)

    # Baskets and month-to-month variability
    baskets = {}
    for role in BASKET_ROLES:
        group = [r for r in consumption if r['role'] == role]
        amount = -sum(r['amount_cents'] for r in group)
        monthly = [-sum(r['amount_cents'] for r in group if r['date'][:7] == m) for m in month_list]
        baskets[role] = {
            'label': BASKET_LABELS[role],
            'amount_cents': amount,
            'share_percent': _pct(amount, total),
            'monthly_cents': monthly,
            'monthly_average_cents': rounded(Decimal(amount) / n),
            'variability_percent': _variability(monthly),
        }
    other_consumption = total - sum(b['amount_cents'] for b in baskets.values())

    # Free choices (discretionary), split into Little leaks (< LITTLE_LEAK_MAX_CENTS) and Bigger choices.
    free = [r for r in consumption if r['role'] == 'discretionary']
    free_total = baskets['discretionary']['amount_cents']
    small = [r for r in free if r['transaction_type'] == 'purchase' and -r['amount_cents'] < LITTLE_LEAK_MAX_CENTS]
    small_refs = {r['transaction_ref'] for r in small}
    bigger = [r for r in free if r['transaction_ref'] not in small_refs]
    salary_rows = [r for r in all_rows if r['transaction_type'] == 'salary' and r['amount_cents'] > 0]
    payday_days = set()
    for row in salary_rows:
        day = date.fromisoformat(row['date'])
        for offset in range(PAYDAY_WINDOW_DAYS):
            payday_days.add((day + timedelta(days=offset)).isoformat())
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1

    def spent(group):
        return -sum(r['amount_cents'] for r in group)

    def weekend(group):
        return spent([r for r in group if date.fromisoformat(r['date']).weekday() >= 5])

    def payday(group):
        return spent([r for r in group if r['date'] in payday_days])

    def per_week(count):
        return _one_decimal(Decimal(count) * 7 / days)

    def largest_of(group):
        row = min(group, key=lambda r: (r['amount_cents'], r['date'])) if group else None
        return {'category': row['category'], 'date': row['date'], 'amount_cents': -row['amount_cents']} if row else None

    def top_categories(group):
        totals = {}
        for r in group:
            totals[r['category']] = totals.get(r['category'], 0) - r['amount_cents']
        whole = spent(group)
        return [{'category': category, 'total_cents': amount, 'annualised_cents': rounded(Decimal(amount) * 12 / n),
                 'share_percent': _pct(amount, whole), 'share_of_little_leaks_percent': _pct(amount, whole)}
                for category, amount in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:3]]

    free_purchases = [r for r in free if r['transaction_type'] == 'purchase']
    free_choices = {
        'label': BASKET_LABELS['discretionary'],
        'total_cents': free_total,
        'purchase_count': len(free_purchases),
        'purchases_per_week': per_week(len(free_purchases)),
        'weekend_cents': weekend(free),
        'weekend_share_percent': _pct(weekend(free), free_total),
        'payday_window_cents': payday(free),
        'payday_share_percent': _pct(payday(free), free_total) if salary_rows else None,
        'monthly_average_cents': baskets['discretionary']['monthly_average_cents'],
    }
    small_total = spent(small)
    little = {
        'label': 'Little leaks',
        'threshold_cents': LITTLE_LEAK_MAX_CENTS,
        'purchase_count': len(small),
        'total_cents': small_total,
        'monthly_average_cents': rounded(Decimal(small_total) / n),
        'share_of_free_choices_percent': _pct(small_total, free_total),
        'weekend_cents': weekend(small),
        'weekend_share_percent': _pct(weekend(small), small_total),
        'payday_window_days': PAYDAY_WINDOW_DAYS,
        'payday_window_cents': payday(small),
        'payday_share_percent': _pct(payday(small), small_total) if salary_rows else None,
        'median_purchase_cents': median_cents([-r['amount_cents'] for r in small]) if small else None,
        'purchases_per_week': per_week(len(small)),
        'largest': largest_of(small),
    }
    bigger_total = spent(bigger)
    bigger_choices = {
        'label': 'Bigger choices',
        'threshold_cents': LITTLE_LEAK_MAX_CENTS,
        'purchase_count': len(bigger),
        'total_cents': bigger_total,
        'monthly_average_cents': rounded(Decimal(bigger_total) / n),
        'share_of_free_choices_percent': _pct(bigger_total, free_total),
        'largest': largest_of(bigger),
    }
    top_small = top_categories(small)
    top_bigger = top_categories(bigger)

    # Saving behaviour
    salary_in_period = [r for r in salary_rows if r['date'] >= start]
    salary_total = sum(r['amount_cents'] for r in salary_in_period)
    saving_rows = [r for r in rows if r['transaction_type'] in SAVING_TYPES and r['amount_cents'] < 0]
    deposits = -sum(r['amount_cents'] for r in saving_rows if r['transaction_type'] == 'investment_deposit')
    sweeps = -sum(r['amount_cents'] for r in saving_rows if r['transaction_type'] == 'salary_sweep')
    saving_share = _pct(deposits + sweeps, salary_total)

    # Low balance before payday (reuses the analytics signal)
    try:
        signal = payday_timing_signal(conn, customer_id, month_list[-1])
    except ValueError:
        signal = None
    payday_pattern = {
        'available': bool(signal and signal['available']),
        'qualified': bool(signal and signal['qualified']),
        'low_balance_event_count': signal['low_balance_event_count'] if signal else 0,
        'observed_window_count': signal['observed_window_count'] if signal else 0,
        'low_balance_threshold_cents': signal['low_balance_threshold_cents'] if signal else None,
        'lowest_pre_salary_balance_cents': signal['lowest_pre_salary_balance_cents'] if signal else None,
        'period': signal['period'] if signal else None,
    }

    figures = {
        'consumption_cents': total,
        'monthly_consumption_cents': rounded(Decimal(total) / n),
        'other_consumption_cents': other_consumption,
        'baskets': baskets,
        'free_choices': free_choices,
        'little_leaks': little,
        'bigger_choices': bigger_choices,
        'top_little_leaks_categories': top_small,
        'top_bigger_choices_categories': top_bigger,
        'top_free_choice_categories': top_categories(free),
        'saving': {
            'salary_cents': salary_total,
            'saved_cents': deposits + sweeps,
            'investment_deposit_cents': deposits,
            'salary_sweep_cents': sweeps,
            'share_of_salary_percent': saving_share,
        },
        'payday_pattern': payday_pattern,
    }

    archetype, rule = _choose_archetype(figures)
    why = _why(archetype, figures)
    strength = _strength(figures, archetype)
    watch = _watch(figures, archetype)
    explanation = _explanation(archetype, figures)

    refs = [r['transaction_ref'] for r in consumption]
    refs += [r['transaction_ref'] for r in salary_in_period]
    refs += [r['transaction_ref'] for r in saving_rows]
    if signal:
        refs += signal['transaction_refs']
    refs = list(dict.fromkeys(refs))
    result = {
        **scope,
        'available': True,
        'archetype': archetype,
        'archetype_label': ARCHETYPE_LABELS[archetype]['en'],
        'archetype_labels': dict(ARCHETYPE_LABELS[archetype]),
        'rule': rule,
        'explanation': explanation,
        'why': why,
        'strength': strength,
        'watch': watch,
        'figures': figures,
        'thresholds': _thresholds(),
        'period': period,
        'months_used': n,
        'label_note': 'A description of your last ' + str(n) + ' months. It changes as your habits do.',
        'basis': 'Spending = purchases, utility and housing payments (outflows). Free choices = discretionary spending; Little leaks are free-choice purchases under ' + _euro_whole(LITTLE_LEAK_MAX_CENTS) + ', Bigger choices are the rest. Saving = investment deposits and salary sweeps, compared with salary income.',
        'transaction_refs': refs,
        'observed': True,
    }
    result['fact_id'] = fact_id('spender-profile', customer_id, start, end, archetype, refs)
    return result


def _thresholds():
    return {
        'little_leak_max_cents': LITTLE_LEAK_MAX_CENTS,
        'min_rhythm_purchases': MIN_RHYTHM_PURCHASES,
        'payday_window_days': PAYDAY_WINDOW_DAYS,
        'payday_share_min_percent': str(PAYDAY_SHARE_MIN),
        'payday_share_with_low_balance_min_percent': str(PAYDAY_SHARE_WITH_LOW_BALANCE_MIN),
        'weekend_share_min_percent': str(WEEKEND_SHARE_MIN),
        'small_often_per_week_min': str(SMALL_OFTEN_PER_WEEK_MIN),
        'small_often_median_max_cents': SMALL_OFTEN_MEDIAN_MAX_CENTS,
        'bigger_choices_share_min_percent': str(BIG_TICKET_SHARE_MIN),
        'min_bigger_purchases': MIN_BIGGER_PURCHASES,
        'big_ticket_little_leaks_per_week_max': str(BIG_TICKET_PER_WEEK_MAX),
        'steady_saving_share_min_percent': str(STEADY_SAVING_SHARE_MIN),
        'steady_variability_max_percent': str(STEADY_VARIABILITY_MAX),
        'priority': list(ARCHETYPE_PRIORITY),
    }


def _dec(value):
    return Decimal(value) if value is not None else None


def _choose_archetype(f):
    """Apply the rules in ARCHETYPE_PRIORITY order. Returns (id, English rule sentence)."""
    free, little, bigger = f['free_choices'], f['little_leaks'], f['bigger_choices']
    rhythm = free['purchase_count'] >= MIN_RHYTHM_PURCHASES
    payday = _dec(free['payday_share_percent'])
    weekend = _dec(free['weekend_share_percent'])
    small_per_week = Decimal(little['purchases_per_week'])
    bigger_share = _dec(bigger['share_of_free_choices_percent'])
    saving = _dec(f['saving']['share_of_salary_percent'])
    variability = _dec(f['baskets']['discretionary']['variability_percent'])
    low_balance = f['payday_pattern']['qualified']
    if rhythm and payday is not None and (payday >= PAYDAY_SHARE_MIN or (low_balance and payday >= PAYDAY_SHARE_WITH_LOW_BALANCE_MIN)):
        return 'payday_sprinter', 'Free-choice spending is concentrated in the 7 days after payday'
    if rhythm and weekend is not None and weekend >= WEEKEND_SHARE_MIN:
        return 'weekend_spender', 'At least half of free-choice spending happens on weekends'
    if small_per_week >= SMALL_OFTEN_PER_WEEK_MIN and little['median_purchase_cents'] is not None and little['median_purchase_cents'] <= SMALL_OFTEN_MEDIAN_MAX_CENTS:
        return 'small_and_often', 'Many small purchases every week'
    if bigger['purchase_count'] >= MIN_BIGGER_PURCHASES and bigger_share is not None and bigger_share >= BIG_TICKET_SHARE_MIN and small_per_week <= BIG_TICKET_PER_WEEK_MAX:
        return 'big_ticket_occasional', 'Few small purchases; most free-choice spending is in bigger purchases'
    if saving is not None and saving >= STEADY_SAVING_SHARE_MIN and variability is not None and variability <= STEADY_VARIABILITY_MAX and not low_balance:
        return 'steady_planner', 'Regular saving and steady free-choice spending'
    return 'balanced', 'No single pattern stands out'


def _explanation(archetype, f):
    """One plain sentence per locale with at most one number, from the same figures as the baskets."""
    values = {'percent': None, 'value': None, 'threshold_cents': LITTLE_LEAK_MAX_CENTS}
    if archetype == 'payday_sprinter':
        values['percent'] = f['free_choices']['payday_share_percent']
    elif archetype == 'weekend_spender':
        values['percent'] = f['free_choices']['weekend_share_percent']
    elif archetype == 'small_and_often':
        values['value'] = f['little_leaks']['purchases_per_week']
    elif archetype == 'big_ticket_occasional':
        values['percent'] = f['bigger_choices']['share_of_free_choices_percent']
    elif archetype == 'balanced':
        values['percent'] = f['baskets']['discretionary']['share_percent'] or '0.0'
    out = {}
    for index, locale in enumerate(_LOCALES):
        fields = {'threshold': _euro_whole(LITTLE_LEAK_MAX_CENTS, locale)}
        if values['percent'] is not None:
            fields['percent'] = _percent_text(values['percent'], locale)
        if values['value'] is not None:
            fields['value'] = _number_text(values['value'], locale)
        out[locale] = _EXPLANATIONS[archetype][index].format(**fields)
    return out


def _share_fact(f, role, fact_key):
    return _fact(fact_key, percent=f['baskets'][role]['share_percent'])


def _low_balance_fact(f):
    p = f['payday_pattern']
    return _fact('low_balance_before_payday', count=p['low_balance_event_count'], windows=p['observed_window_count'], threshold_cents=p['low_balance_threshold_cents'])


def _top_fact(top):
    if not top:
        return None
    return _fact('top_category_annual', category=top[0]['category'], amount_cents=top[0]['annualised_cents'])


def _why(archetype, f):
    free, little, bigger = f['free_choices'], f['little_leaks'], f['bigger_choices']
    facts = []
    if archetype == 'payday_sprinter':
        facts.append(_fact('payday_share', percent=free['payday_share_percent']))
        if f['payday_pattern']['qualified']:
            facts.append(_low_balance_fact(f))
        facts.append(_fact('free_choice_monthly', amount_cents=free['monthly_average_cents']))
    elif archetype == 'weekend_spender':
        facts.append(_fact('weekend_share', percent=free['weekend_share_percent']))
        facts.append(_top_fact(f['top_free_choice_categories']))
        facts.append(_share_fact(f, 'discretionary', 'free_choice_share'))
    elif archetype == 'small_and_often':
        facts.append(_fact('purchases_per_week', value=little['purchases_per_week'], threshold_cents=LITTLE_LEAK_MAX_CENTS))
        facts.append(_fact('median_purchase', amount_cents=little['median_purchase_cents']))
        facts.append(_fact('little_leaks_monthly', amount_cents=little['monthly_average_cents'], threshold_cents=LITTLE_LEAK_MAX_CENTS))
    elif archetype == 'big_ticket_occasional':
        facts.append(_fact('bigger_choices_share', percent=bigger['share_of_free_choices_percent'], threshold_cents=LITTLE_LEAK_MAX_CENTS))
        facts.append(_fact('purchases_per_week', value=little['purchases_per_week'], threshold_cents=LITTLE_LEAK_MAX_CENTS))
        if bigger['largest']:
            facts.append(_fact('largest_bigger_choice', amount_cents=bigger['largest']['amount_cents'], category=bigger['largest']['category']))
    elif archetype == 'steady_planner':
        facts.append(_fact('saving_share', percent=f['saving']['share_of_salary_percent']))
        facts.append(_fact('free_choice_variability', percent=f['baskets']['discretionary']['variability_percent']))
        facts.append(_fact('free_choice_monthly', amount_cents=free['monthly_average_cents']))
    else:
        if f['baskets']['fixed_obligation']['share_percent'] is not None:
            facts.append(_share_fact(f, 'fixed_obligation', 'must_pays_share'))
            facts.append(_share_fact(f, 'discretionary', 'free_choice_share'))
        if free['weekend_share_percent'] is not None:
            facts.append(_fact('weekend_share', percent=free['weekend_share_percent']))
        elif little['median_purchase_cents'] is not None:
            facts.append(_fact('median_purchase', amount_cents=little['median_purchase_cents']))
    return [item for item in facts if item is not None][:3]


def _strength(f, archetype):
    """One positive habit, chosen from candidates in a fixed order, or None.

    A large Must-pays share is never offered as a strength (it is a pressure, not a habit).
    """
    saving = _dec(f['saving']['share_of_salary_percent'])
    if saving is not None and saving >= STEADY_SAVING_SHARE_MIN and archetype != 'steady_planner':
        return _fact('saving_share', percent=f['saving']['share_of_salary_percent'])
    pattern = f['payday_pattern']
    if pattern['available'] and not pattern['qualified']:
        return _fact('no_low_balance_before_payday')
    variability = _dec(f['baskets']['discretionary']['variability_percent'])
    if variability is not None and variability <= STEADY_VARIABILITY_MAX and archetype != 'steady_planner':
        return _fact('free_choice_variability', percent=f['baskets']['discretionary']['variability_percent'])
    if saving is not None and saving > 0:
        return _fact('saving_share', percent=f['saving']['share_of_salary_percent'])
    return None


def _watch(f, archetype):
    """One thing worth a look, chosen from candidates in a fixed order."""
    if f['payday_pattern']['qualified'] and archetype != 'payday_sprinter':
        return _low_balance_fact(f)
    if archetype == 'big_ticket_occasional' and f['top_bigger_choices_categories']:
        return _top_fact(f['top_bigger_choices_categories'])
    top = f['top_free_choice_categories']
    if archetype == 'weekend_spender' and len(top) > 1:
        return _fact('top_category_annual', category=top[1]['category'], amount_cents=top[1]['annualised_cents'])
    if top:
        return _top_fact(top)
    return _share_fact(f, 'discretionary', 'free_choice_share')


# --------------------------------------------------------------------------
# Surprise must-pays buffer
# --------------------------------------------------------------------------
def irregular_buffer(conn, customer_id, end_month=None, months=12):
    """Estimate a monthly set-aside for Surprise must-pays.

    Surprise must-pays are: every consumption outflow with role
    'flexible_essential', plus essential purchases (role 'fixed_obligation' or
    'flexible_essential', transaction_type 'purchase') larger than
    BUFFER_LARGE_MULTIPLIER x the customer's own median purchase for that
    category in the same window (category needs at least
    BUFFER_MIN_CATEGORY_PURCHASES purchases).

    Args:
        conn, customer_id: as for spender_profile.
        end_month: 'YYYY-MM' last complete month; default latest complete month.
        months: complete months to look back (1-24, default 12), clipped to history.

    Returns dict:
        available: True
        count: int, total_cents: int, monthly_average_cents: int (total / months_used, half-up)
        total, monthly_average: formatted euro strings
        largest: {category, date, amount_cents} | None
        suggested_monthly_set_aside_cents: int (= monthly_average_cents)
        items: up to 20 {date, category, amount_cents, reason ('surprise_basket'|'large_essential')},
               largest first; items_truncated: bool
        by_category: [{category, count, total_cents}] largest first
        period: {start, end}, months_used: int, basis: str,
        transaction_refs: list, fact_id, observed: True
    Raises ValueError for an unknown customer or a month outside coverage.
    """
    scope, month_list = _window(conn, customer_id, end_month, months, MAX_PROFILE_MONTHS)
    start = month_bounds(month_list[0])[0]
    end = month_bounds(month_list[-1])[1]
    n = len(month_list)
    rows = [r for r in transactions(conn, customer_id, start, end) if _is_consumption(r)]
    essential_purchases = [r for r in rows if r['transaction_type'] == 'purchase' and r['role'] in ('fixed_obligation', 'flexible_essential')]
    medians = {}
    for category in {r['category'] for r in essential_purchases}:
        values = [-r['amount_cents'] for r in essential_purchases if r['category'] == category]
        if len(values) >= BUFFER_MIN_CATEGORY_PURCHASES:
            medians[category] = median_cents(values)
    selected = []
    for r in rows:
        if r['role'] == 'flexible_essential':
            selected.append((r, 'surprise_basket'))
        elif r in essential_purchases and r['category'] in medians and -r['amount_cents'] > BUFFER_LARGE_MULTIPLIER * medians[r['category']]:
            selected.append((r, 'large_essential'))
    total = -sum(r['amount_cents'] for r, _ in selected)
    average = rounded(Decimal(total) / n)
    ordered = sorted(selected, key=lambda item: (item[0]['amount_cents'], item[0]['date']))
    items = [{'date': r['date'], 'category': r['category'], 'amount_cents': -r['amount_cents'], 'reason': reason} for r, reason in ordered[:BUFFER_MAX_ITEMS]]
    largest = {'category': ordered[0][0]['category'], 'date': ordered[0][0]['date'], 'amount_cents': -ordered[0][0]['amount_cents']} if ordered else None
    by_category = {}
    for r, _ in selected:
        entry = by_category.setdefault(r['category'], {'category': r['category'], 'count': 0, 'total_cents': 0})
        entry['count'] += 1
        entry['total_cents'] -= r['amount_cents']
    refs = [r['transaction_ref'] for r, _ in selected]
    result = {
        **scope,
        'available': True,
        'count': len(selected),
        'total_cents': total,
        'total': _euro(total),
        'monthly_average_cents': average,
        'monthly_average': _euro(average),
        'largest': largest,
        'suggested_monthly_set_aside_cents': average,
        'suggested_monthly_set_aside': _euro(average),
        'items': items,
        'items_truncated': len(selected) > BUFFER_MAX_ITEMS,
        'by_category': sorted(by_category.values(), key=lambda e: (-e['total_cents'], e['category'])),
        'category_medians_cents': dict(sorted(medians.items())),
        'large_multiplier': BUFFER_LARGE_MULTIPLIER,
        'period': {'start': start, 'end': end},
        'months_used': n,
        'basis': 'Surprise must-pays (for example health and home repairs) plus essential purchases more than '
                 + str(BUFFER_LARGE_MULTIPLIER) + 'x your usual amount for that category, over ' + str(n) + ' complete months.',
        'transaction_refs': refs,
        'observed': True,
    }
    result['fact_id'] = fact_id('irregular-buffer', customer_id, start, end, refs)
    return result


# --------------------------------------------------------------------------
# Offline summary
# --------------------------------------------------------------------------
_SUMMARY = {
    'en': {'intro': 'Your spending style: {label}.',
           'note': 'This describes your last {months} months, not who you are.',
           'unavailable': 'I need at least two complete months of history before I can describe your spending style.'},
    'fi': {'intro': 'Kulutustyylisi: {label}.',
           'note': 'Tämä kuvaa viimeisiä {months} kuukauttasi, ei sinua ihmisenä.',
           'unavailable': 'Tarvitsen vähintään kaksi täyttä kuukautta tapahtumia, jotta voin kuvata kulutustyyliäsi.'},
    'sv': {'intro': 'Din utgiftsstil: {label}.',
           'note': 'Det här beskriver dina senaste {months} månader, inte vem du är.',
           'unavailable': 'Jag behöver minst två hela månader med historik innan jag kan beskriva din utgiftsstil.'},
}


def offline_summary(profile, locale='en'):
    """One or two plain sentences naming the archetype and its main reason.

    Args:
        profile: dict returned by spender_profile.
        locale: 'en', 'fi' or 'sv' (anything else falls back to 'en').
    Returns: str, e.g. 'Your spending style: Payday Sprinter. 52.3% of your
        Little leaks spending happened in the 7 days after payday. This describes
        your last 6 months, not who you are.' Uses only figures already present
        in profile['why'] (no new arithmetic).
    """
    locale = locale if locale in _LOCALES else 'en'
    texts = _SUMMARY[locale]
    if not profile.get('available'):
        return texts['unavailable']
    parts = [texts['intro'].format(label=ARCHETYPE_LABELS[profile['archetype']][locale])]
    if profile.get('explanation'):
        parts.append(profile['explanation'][locale])
    elif profile.get('why'):
        parts.append(_render(profile['why'][0], locale))
    parts.append(texts['note'].format(months=profile['months_used']))
    return ' '.join(parts)
