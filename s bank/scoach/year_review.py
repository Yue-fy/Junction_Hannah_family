"""Deterministic year-in-review facts (WP-L, data half).

Everything here is computed from the account-scoped ledger (`ledger.transactions`).
Amounts are integer cents; percentages are precomputed strings with one decimal
("12.3"); formatted euro strings ("€1,234.56") are provided as display extras.
Definitions follow `analytics.money_map`:

- money in   = salary + other_income amounts;
- money out  = consumption: amount < 0 and transaction_type in
               purchase / utilities_payment / housing_payment (as a positive number);
- saved      = investment_deposit + salary_sweep outflows minus
               investment_withdrawal inflows (money_map's committed saving transfers,
               net of withdrawals);
- baskets    = consumption rows by classified role (fixed_obligation,
               flexible_essential, discretionary), user rules applied.
"""
import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .ledger import account_scope, transactions, fact_id

CONSUMPTION_TYPES = ('purchase', 'utilities_payment', 'housing_payment')
SAVING_OUT_TYPES = ('investment_deposit', 'salary_sweep')
BASKET_ROLES = ('fixed_obligation', 'flexible_essential', 'discretionary')
MIN_MONTHS = 3
MAX_CARDS = 10
WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
# Friendly English MCC labels. 4121 and 5912 match query_scope.MCC_TERMS (Taxi, Pharmacy);
# 8011 / 8021 are taken from MCC_TERMS as well.
MCC_LABELS = {
    '5411': 'Groceries', '5812': 'Restaurants', '5814': 'Fast food & cafés',
    '4121': 'Taxis', '4111': 'Public transport', '5541': 'Fuel', '5912': 'Pharmacy',
    '7832': 'Cinema', '5311': 'Department stores', '5732': 'Electronics',
    '4511': 'Flights', '7011': 'Hotels', '8011': 'Doctor', '8021': 'Dentist',
}


# Finnish and Swedish versions of MCC_LABELS (same keys), for the year cards.
MCC_LABELS_FI = {
    '5411': 'Ruokaostokset', '5812': 'Ravintolat', '5814': 'Pikaruoka ja kahvilat',
    '4121': 'Taksit', '4111': 'Joukkoliikenne', '5541': 'Polttoaine', '5912': 'Apteekki',
    '7832': 'Elokuvat', '5311': 'Tavaratalot', '5732': 'Elektroniikka',
    '4511': 'Lennot', '7011': 'Hotellit', '8011': 'Lääkäri', '8021': 'Hammaslääkäri',
}
MCC_LABELS_SV = {
    '5411': 'Matinköp', '5812': 'Restaurang', '5814': 'Snabbmat och kaféer',
    '4121': 'Taxi', '4111': 'Kollektivtrafik', '5541': 'Bränsle', '5912': 'Apotek',
    '7832': 'Bio', '5311': 'Varuhus', '5732': 'Elektronik',
    '4511': 'Flyg', '7011': 'Hotell', '8011': 'Läkare', '8021': 'Tandläkare',
}
_MCC_UNKNOWN = {'en': 'Code {code}', 'fi': 'Koodi {code}', 'sv': 'Kod {code}'}


def mcc_label(code, locale='en'):
    """Return a friendly label for a four-digit MCC string ('en' | 'fi' | 'sv'), else 'Code NNNN'."""
    table = {'fi': MCC_LABELS_FI, 'sv': MCC_LABELS_SV}.get(locale, MCC_LABELS)
    return table.get(code) or _MCC_UNKNOWN.get(locale, _MCC_UNKNOWN['en']).format(code=code)


def _pct(part, whole):
    """part/whole*100 as a one-decimal string, or None when whole is not positive."""
    if not whole or whole <= 0:
        return None
    return str((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _ratio(part, whole):
    if not whole or whole <= 0:
        return None
    return str((Decimal(part) / Decimal(whole)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _eur(cents):
    """Format integer cents as '€1,234.56' (negative as '-€1,234.56')."""
    sign = '-' if cents < 0 else ''
    whole, rest = divmod(abs(int(cents)), 100)
    return '{}€{:,}.{:02d}'.format(sign, whole, rest)


def _month_index(month):
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def _observed_months(scope, year):
    """Calendar months of `year` inside the customer's observed span (YYYY-MM list)."""
    low, high = scope['observed_start'][:7], scope['observed_end'][:7]
    months = ['{:04d}-{:02d}'.format(year, m) for m in range(1, 13)]
    return [m for m in months if low <= m <= high]


def _complete(scope, year, months):
    """A year is complete when all 12 months are observed and the span covers Jan 1..Dec 31."""
    return (len(months) == 12 and scope['observed_start'] <= '{:04d}-01-01'.format(year)
            and scope['observed_end'] >= '{:04d}-12-31'.format(year))


def year_options(conn, customer_id):
    """List calendar years that contain observed data for the customer.

    Args: conn (sqlite3 connection with row_factory=Row), customer_id (str).
    Returns: list (newest year first) of
      {'year': int, 'observed_months': int, 'complete': bool, 'available': bool}
    where available means at least 3 observed months (enough for a review).
    Raises ValueError for an unknown customer.
    """
    scope = account_scope(conn, customer_id)
    result = []
    for year in range(int(scope['observed_end'][:4]), int(scope['observed_start'][:4]) - 1, -1):
        months = _observed_months(scope, year)
        if months:
            result.append({'year': year, 'observed_months': len(months),
                           'complete': _complete(scope, year, months),
                           'available': len(months) >= MIN_MONTHS})
    return result


def _is_consumption(row):
    return row['amount_cents'] < 0 and row['transaction_type'] in CONSUMPTION_TYPES


def _base_metrics(rows):
    money_in = sum(r['amount_cents'] for r in rows if r['transaction_type'] in ('salary', 'other_income'))
    money_out = -sum(r['amount_cents'] for r in rows if _is_consumption(r))
    saved = (-sum(min(r['amount_cents'], 0) for r in rows if r['transaction_type'] in SAVING_OUT_TYPES)
             - sum(max(r['amount_cents'], 0) for r in rows if r['transaction_type'] == 'investment_withdrawal'))
    return {'money_in_cents': money_in, 'money_out_cents': money_out, 'saved_cents': saved,
            'saving_rate_percent': _pct(saved, money_in),
            'money_in': _eur(money_in), 'money_out': _eur(money_out), 'saved': _eur(saved)}


def _year_rows(conn, customer_id, year):
    return transactions(conn, customer_id, '{:04d}-01-01'.format(year), '{:04d}-12-31'.format(year))


def _avg(cents, count):
    return int((Decimal(cents) / count).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _change(current, previous):
    delta = current - previous
    return {'delta_cents': delta, 'change_percent': _pct(delta, previous) if previous > 0 else None}


def _caption(kind):
    return {
        'intro': 'Your {year} in money: {observed_months} months of your account, in a few cards.',
        'money_in_out': '{money_in} came in and {money_out} went out on spending.',
        'saved': 'You moved {saved} to saving and investing, {saving_rate_percent} % of what came in. It is part of the {left_over} left over.',
        'top_category': '{category} was your biggest spending category: {amount}, {share_percent} % of spending.',
        'baskets': 'Regular essentials {fixed_obligation}, irregular essentials {flexible_essential}, little leaks {discretionary}.',
        'little_leaks': 'Little leaks added up to {amount}, {share_percent} % of your spending.',
        'peak_month': 'Your busiest month was {biggest_month_label} ({biggest_month_amount}); the calmest was {calmest_month_label} ({calmest_month_amount}).',
        'busiest_day': 'Your busiest day was {date}: {count} payments, {amount} in total.',
        'favourite_weekday_or_mcc': '{weekday} was your favourite shopping day, and {mcc_label} your most frequent kind of purchase ({mcc_count} times).',
        'archetype': 'This year you looked like a {archetype_label}.',
        'closing': 'That was your {year}: {purchase_count} purchases, {saved} saved. Here is to the next one.',
    }[kind]


def _month_label(month):
    return calendar.month_name[int(month[5:7])] + ' ' + month[:4]


def _archetype_label(result):
    if not isinstance(result, dict):
        return None
    for key in ('archetype_label', 'label', 'name', 'archetype'):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            for inner in ('label', 'name', 'id'):
                if isinstance(value.get(inner), str):
                    return value[inner]
    return None


def year_review(conn, customer_id, year, *, archetype_fn=None, goals_fn=None):
    """Deterministic year-in-review facts for one calendar year.

    Args:
      conn: sqlite3 connection (row_factory=Row) holding the ledger.
      customer_id: str. year: int calendar year.
      archetype_fn: optional callable (conn, customer_id, end_month 'YYYY-MM', months int) -> dict|None,
        e.g. spender.spender_profile; called with the year's last observed month and the observed
        month count. Its result is returned under 'archetype' (and for the previous year, when that
        year is available, under 'archetype_previous').
      goals_fn: optional callable (conn, customer_id, year) -> list|None; result under 'goals'.

    Returns dict. When fewer than 3 months of the year are observed:
      {'available': False, 'year', 'complete', 'observed_months', 'reason', 'cards': [], ...}.
    Otherwise 'available': True and:
      year, complete (bool, whole year observed), observed_months (int), start, end (ISO dates),
      money_in_cents, money_out_cents, saved_cents, saving_rate_percent ('12.3' or None),
        plus formatted money_in / money_out / saved strings;
      previous_year: None or {year, complete, observed_months, money_in_cents, money_out_cents,
        saved_cents, saving_rate_percent, changes: {money_in|money_out|saved: {delta_cents,
        change_percent}}, saving_rate_delta_points (string, percentage points), comparable (both
        years complete), monthly_average_changes (same shape as changes, per observed month)};
      top_category: None or {category, cents, share_percent};
      baskets: [{role, cents, share_percent}] for the three roles (shares of money_out);
      little_leaks: {cents, share_percent, months_of_rent_equivalent ('2.4' or None),
        average_monthly_housing_cents (or None)} - the rent equivalent divides the discretionary
        total by the average monthly housing_payment total over months that had one;
      biggest_month / calmest_month: {month, cents} by consumption over observed months;
      busiest_day: {date, cents, count, transaction_refs}; largest_purchase: {category, date, cents,
        mcc_code, transaction_ref} (transaction_type purchase only); purchase_count (int);
      favourite_weekday: {weekday, weekday_index (Mon=0), count}; most_frequent_mcc:
        {mcc_code, count, label};
      archetype, archetype_previous, goals (see args);
      cards: ordered list of 8-10 {id, kind, facts, caption_template}; every {placeholder} in the
        caption_template is a key of facts (caption_template.format(**facts) works). When the
        optional archetype card would push the list past 10, busiest_day facts merge into peak_month;
      transaction_refs: refs of all the year's rows; fact_id: stable evidence id.
    Shares and rates are percentages with one decimal, ROUND_HALF_UP. Raises ValueError for an
    unknown customer.
    """
    year = int(year)
    scope = account_scope(conn, customer_id)
    months = _observed_months(scope, year)
    complete = _complete(scope, year, months)
    base = {'customer_id': customer_id, 'account_id': scope['account_id'], 'year': year,
            'complete': complete, 'observed_months': len(months),
            'start': '{:04d}-01-01'.format(year), 'end': '{:04d}-12-31'.format(year), 'observed': True}
    if len(months) < MIN_MONTHS:
        return {**base, 'available': False, 'reason': 'Fewer than {} observed months in {}'.format(MIN_MONTHS, year),
                'cards': [], 'transaction_refs': [], 'archetype': None, 'goals': None}

    rows = _year_rows(conn, customer_id, year)
    metrics = _base_metrics(rows)
    consumption = [r for r in rows if _is_consumption(r)]
    purchases = [r for r in consumption if r['transaction_type'] == 'purchase']
    money_out = metrics['money_out_cents']

    # Previous year comparison.
    previous = None
    prev_months = _observed_months(scope, year - 1)
    if prev_months:
        prev_metrics = _base_metrics(_year_rows(conn, customer_id, year - 1))
        previous = {'year': year - 1, 'observed_months': len(prev_months),
                    'complete': _complete(scope, year - 1, prev_months), **prev_metrics,
                    'changes': {k: _change(metrics[k + '_cents'], prev_metrics[k + '_cents'])
                                for k in ('money_in', 'money_out', 'saved')},
                    'saving_rate_delta_points': None}
        # Partial years distort totals: 'comparable' is True only when both years are complete;
        # monthly averages (per observed month) give a fairer view otherwise.
        previous['comparable'] = complete and previous['complete']
        previous['monthly_average_changes'] = {
            k: _change(_avg(metrics[k + '_cents'], len(months)), _avg(prev_metrics[k + '_cents'], len(prev_months)))
            for k in ('money_in', 'money_out', 'saved')}
        if metrics['saving_rate_percent'] is not None and prev_metrics['saving_rate_percent'] is not None:
            previous['saving_rate_delta_points'] = str(Decimal(metrics['saving_rate_percent']) - Decimal(prev_metrics['saving_rate_percent']))

    # Categories and baskets.
    by_category = {}
    for r in consumption:
        by_category[r['category']] = by_category.get(r['category'], 0) - r['amount_cents']
    top_category = None
    if by_category:
        name = sorted(by_category, key=lambda c: (-by_category[c], c))[0]
        top_category = {'category': name, 'cents': by_category[name], 'share_percent': _pct(by_category[name], money_out)}
    baskets = []
    for role in BASKET_ROLES:
        cents = -sum(r['amount_cents'] for r in consumption if r['role'] == role)
        baskets.append({'role': role, 'cents': cents, 'share_percent': _pct(cents, money_out)})
    discretionary = baskets[2]['cents']

    housing_by_month = {}
    for r in consumption:
        if r['transaction_type'] == 'housing_payment':
            housing_by_month[r['date'][:7]] = housing_by_month.get(r['date'][:7], 0) - r['amount_cents']
    avg_housing = None
    if housing_by_month:
        avg_housing = int((Decimal(sum(housing_by_month.values())) / len(housing_by_month)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    little_leaks = {'cents': discretionary, 'share_percent': _pct(discretionary, money_out),
                    'average_monthly_housing_cents': avg_housing,
                    'months_of_rent_equivalent': _ratio(discretionary, avg_housing) if avg_housing else None}

    # Months and days.
    by_month = {m: 0 for m in months}
    for r in consumption:
        by_month[r['date'][:7]] = by_month.get(r['date'][:7], 0) - r['amount_cents']
    biggest = sorted(by_month, key=lambda m: (-by_month[m], m))[0]
    calmest = sorted(by_month, key=lambda m: (by_month[m], m))[0]
    by_day = {}
    for r in consumption:
        by_day.setdefault(r['date'], []).append(r)
    busiest_day = None
    if by_day:
        day = sorted(by_day, key=lambda d: (sum(r['amount_cents'] for r in by_day[d]), d))[0]
        busiest_day = {'date': day, 'cents': -sum(r['amount_cents'] for r in by_day[day]), 'count': len(by_day[day]),
                       'transaction_refs': [r['transaction_ref'] for r in by_day[day]]}
    largest = None
    if purchases:
        top = sorted(purchases, key=lambda r: (r['amount_cents'], r['date']))[0]
        largest = {'category': top['category'], 'date': top['date'], 'cents': -top['amount_cents'],
                   'mcc_code': top['mcc_code'] or None, 'transaction_ref': top['transaction_ref']}
    favourite = None
    if purchases:
        counts = [0] * 7
        for r in purchases:
            counts[date.fromisoformat(r['date']).weekday()] += 1
        index = sorted(range(7), key=lambda i: (-counts[i], i))[0]
        favourite = {'weekday': WEEKDAYS[index], 'weekday_index': index, 'count': counts[index]}
    mcc_counts = {}
    for r in purchases:
        if r['mcc_code']:
            mcc_counts[r['mcc_code']] = mcc_counts.get(r['mcc_code'], 0) + 1
    frequent_mcc = None
    if mcc_counts:
        code = sorted(mcc_counts, key=lambda c: (-mcc_counts[c], c))[0]
        frequent_mcc = {'mcc_code': code, 'count': mcc_counts[code], 'label': mcc_label(code)}

    archetype = archetype_fn(conn, customer_id, months[-1], len(months)) if archetype_fn else None
    archetype_previous = None
    if archetype_fn and len(prev_months) >= MIN_MONTHS:
        archetype_previous = archetype_fn(conn, customer_id, prev_months[-1], len(prev_months))
    goals = goals_fn(conn, customer_id, year) if goals_fn else None

    result = {**base, 'available': True, **metrics, 'previous_year': previous, 'top_category': top_category,
              'baskets': baskets, 'little_leaks': little_leaks,
              'biggest_month': {'month': biggest, 'cents': by_month[biggest]},
              'calmest_month': {'month': calmest, 'cents': by_month[calmest]},
              'busiest_day': busiest_day, 'largest_purchase': largest, 'purchase_count': len(purchases),
              'favourite_weekday': favourite, 'most_frequent_mcc': frequent_mcc,
              'archetype': archetype, 'archetype_previous': archetype_previous, 'goals': goals,
              'transaction_refs': [r['transaction_ref'] for r in rows]}
    result['cards'] = _cards(result)
    result['fact_id'] = fact_id('year-review', customer_id, year, result['transaction_refs'])
    return result


def _cards(r):
    cards = []

    def add(kind, facts):
        cards.append({'id': '{}-{}'.format(r['year'], kind), 'kind': kind, 'facts': facts, 'caption_template': _caption(kind)})

    add('intro', {'year': r['year'], 'observed_months': r['observed_months'], 'complete': r['complete']})
    prev = r['previous_year']
    add('money_in_out', {'money_in_cents': r['money_in_cents'], 'money_out_cents': r['money_out_cents'],
                         'money_in': r['money_in'], 'money_out': r['money_out'],
                         'previous_year': prev['year'] if prev else None,
                         'previous_complete': prev['complete'] if prev else None,
                         'previous_comparable': prev['comparable'] if prev else None,
                         'money_in_change_percent': prev['changes']['money_in']['change_percent'] if prev and prev['comparable'] else None,
                         'money_out_change_percent': prev['changes']['money_out']['change_percent'] if prev and prev['comparable'] else None})
    add('saved', {'saved_cents': r['saved_cents'], 'saved': r['saved'], 'saving_rate_percent': r['saving_rate_percent'],
                  'left_over_cents': r['money_in_cents'] - r['money_out_cents'], 'left_over': _eur(r['money_in_cents'] - r['money_out_cents']),
                  'previous_saving_rate_percent': prev['saving_rate_percent'] if prev and prev['comparable'] else None,
                  'saving_rate_delta_points': prev['saving_rate_delta_points'] if prev and prev['comparable'] else None})
    if r['saving_rate_percent'] is None:
        cards[-1]['caption_template'] = 'You moved {saved} to saving and investing. It is part of the {left_over} left over.'
    if r['top_category']:
        t = r['top_category']
        add('top_category', {'category': t['category'], 'cents': t['cents'], 'amount': _eur(t['cents']), 'share_percent': t['share_percent']})
    facts = {}
    for b in r['baskets']:
        facts[b['role'] + '_cents'] = b['cents']; facts[b['role']] = _eur(b['cents'])
        facts[b['role'] + '_share_percent'] = b['share_percent']
    add('baskets', facts)
    leaks = r['little_leaks']
    add('little_leaks', {'cents': leaks['cents'], 'amount': _eur(leaks['cents']), 'share_percent': leaks['share_percent'],
                         'months_of_rent_equivalent': leaks['months_of_rent_equivalent']})
    if leaks['months_of_rent_equivalent'] is not None:
        cards[-1]['caption_template'] += ' That is about {months_of_rent_equivalent} months of your rent.'
    big, calm = r['biggest_month'], r['calmest_month']
    add('peak_month', {'biggest_month': big['month'], 'biggest_month_label': _month_label(big['month']),
                       'biggest_month_cents': big['cents'], 'biggest_month_amount': _eur(big['cents']),
                       'calmest_month': calm['month'], 'calmest_month_label': _month_label(calm['month']),
                       'calmest_month_cents': calm['cents'], 'calmest_month_amount': _eur(calm['cents'])})
    busiest = None
    if r['busiest_day']:
        d, lp = r['busiest_day'], r['largest_purchase']
        busiest = {'date': d['date'], 'cents': d['cents'], 'amount': _eur(d['cents']), 'count': d['count']}
        if lp:
            busiest.update({'largest_purchase_category': lp['category'], 'largest_purchase_date': lp['date'],
                            'largest_purchase_cents': lp['cents'], 'largest_purchase_amount': _eur(lp['cents'])})
        add('busiest_day', busiest)
        if d['count'] < 2:
            # One payment is not a "busy day"; it is the largest purchase, shown once.
            cards.pop(); busiest = None
        elif lp:
            cards[-1]['caption_template'] += ' Your largest single purchase: {largest_purchase_amount} on {largest_purchase_category}, {largest_purchase_date}.'
    fav, mcc = r['favourite_weekday'], r['most_frequent_mcc']
    if fav and mcc:
        add('favourite_weekday_or_mcc', {'weekday': fav['weekday'], 'weekday_index': fav['weekday_index'], 'weekday_count': fav['count'],
                                         'mcc_code': mcc['mcc_code'], 'mcc_label': mcc['label'], 'mcc_count': mcc['count']})
    elif fav:
        add('favourite_weekday_or_mcc', {'weekday': fav['weekday'], 'weekday_index': fav['weekday_index'], 'weekday_count': fav['count']})
        cards[-1]['caption_template'] = '{weekday} was your favourite shopping day ({weekday_count} purchases).'
    label = _archetype_label(r['archetype'])
    if label:
        prev_label = _archetype_label(r['archetype_previous'])
        add('archetype', {'archetype_label': label, 'previous_archetype_label': prev_label,
                          'changed': (prev_label != label) if prev_label else None})
    add('closing', {'year': r['year'], 'purchase_count': r['purchase_count'], 'saved': r['saved'], 'saved_cents': r['saved_cents']})
    if len(cards) > MAX_CARDS and busiest:
        # Keep the story within 10 cards: fold busiest-day facts into the peak-month card.
        index = next(i for i, c in enumerate(cards) if c['kind'] == 'busiest_day')
        card = cards.pop(index)
        peak = next(c for c in cards if c['kind'] == 'peak_month')
        peak['facts'].update({'busiest_day_' + k if not k.startswith('largest') else k: v for k, v in card['facts'].items()})
        peak['caption_template'] += ' Your busiest day was {busiest_day_date} ({busiest_day_amount}).'
    return cards
