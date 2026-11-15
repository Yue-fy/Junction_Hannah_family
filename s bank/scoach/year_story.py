"""Adapter from ``year_review.year_review`` output to the story viewer contract (web/year-review.js).

The viewer was written before the data module and reads its own fact names per card kind
(see the header comment of web/year-review.js). This module maps the deterministic review
into exactly those names. It does no new arithmetic except ``net_cents`` (money in minus
money out, the same subtraction the viewer would do itself).
"""

_SUPPORTED = ('intro', 'money_in_out', 'saved', 'top_category', 'baskets', 'little_leaks',
              'peak_month', 'busiest_day', 'favourite_weekday_or_mcc', 'archetype', 'closing')


def _archetype_label(result, locale):
    """Localized archetype display name from a spender_profile result, or None."""
    if not isinstance(result, dict) or result.get('available') is False:
        return None
    labels = result.get('archetype_labels')
    if isinstance(labels, dict) and isinstance(labels.get(locale), str) and labels[locale]:
        return labels[locale]
    label = result.get('archetype_label')
    return label if isinstance(label, str) and label else None


def _compact(facts):
    return {key: value for key, value in facts.items() if value is not None}


def card_facts(kind, review, card_facts_in, locale='en'):
    """Facts for one card kind, using the viewer's names.

    Args:
        kind: card kind from year_review cards.
        review: the whole year_review dict (available True).
        card_facts_in: that card's own ``facts`` from year_review (used for merged fields).
        locale: 'en' | 'fi' | 'sv', for the archetype display name only.
    Returns: dict of facts (None values omitted). Amounts are integer cents,
        shares/rates one-decimal percentage strings.
    """
    r = review
    if kind == 'intro':
        return _compact({'year': r['year'], 'purchase_count': r.get('purchase_count')})
    if kind == 'money_in_out':
        return _compact({'money_in_cents': r['money_in_cents'], 'money_out_cents': r['money_out_cents'],
                         'net_cents': r['money_in_cents'] - r['money_out_cents']})
    if kind == 'saved':
        previous = r.get('previous_year') or {}
        return _compact({'saved_cents': r['saved_cents'], 'saving_rate_percent': r.get('saving_rate_percent'),
                         'previous_saved_cents': previous.get('saved_cents')})
    if kind == 'top_category':
        top = r.get('top_category') or {}
        return _compact({'category': top.get('category'), 'category_label': top.get('category'),
                         'amount_cents': top.get('cents'), 'share_percent': top.get('share_percent')})
    if kind == 'baskets':
        names = {'fixed_obligation': 'must_pays', 'flexible_essential': 'surprise_must_pays', 'discretionary': 'little_leaks'}
        facts = {}
        for row in r.get('baskets') or []:
            name = names.get(row.get('role'))
            if name:
                facts[name + '_cents'] = row.get('cents')
                facts[name + '_percent'] = row.get('share_percent')
        return _compact(facts)
    if kind == 'little_leaks':
        leaks = r.get('little_leaks') or {}
        return _compact({'little_leaks_cents': leaks.get('cents'), 'amount_cents': leaks.get('cents'),
                         'share_percent': leaks.get('share_percent'),
                         'rent_months': leaks.get('months_of_rent_equivalent')})
    if kind == 'peak_month':
        big, calm = r.get('biggest_month') or {}, r.get('calmest_month') or {}
        facts = {'month': big.get('month'), 'amount_cents': big.get('cents'),
                 'calmest_month': calm.get('month'), 'calmest_amount_cents': calm.get('cents')}
        if 'busiest_day_date' in card_facts_in:
            facts.update(busiest_day_date=card_facts_in.get('busiest_day_date'),
                         busiest_day_cents=card_facts_in.get('busiest_day_cents'))
        return _compact(facts)
    if kind == 'busiest_day':
        day = r.get('busiest_day') or {}
        return _compact({'date': day.get('date'), 'amount_cents': day.get('cents'), 'purchase_count': day.get('count')})
    if kind == 'favourite_weekday_or_mcc':
        weekday, mcc = r.get('favourite_weekday') or {}, r.get('most_frequent_mcc') or {}
        # weekday is the Monday=0 index so the viewer localizes it; no English weekday_label is sent.
        return _compact({'weekday': weekday.get('weekday_index'), 'weekday_count': weekday.get('count'),
                         'mcc_label': mcc.get('label'), 'mcc_count': mcc.get('count')})
    if kind == 'archetype':
        return _compact({'archetype_label': _archetype_label(r.get('archetype'), locale),
                         'previous_archetype_label': _archetype_label(r.get('archetype_previous'), locale)})
    if kind == 'closing':
        return _compact({'year': r['year']})
    return {}


def story_cards(review, locale='en'):
    """Map a year_review result to the viewer input.

    Args:
        review: dict returned by year_review.year_review (available or not).
        locale: 'en' | 'fi' | 'sv' (archetype display name only; other text is localized by the viewer).
    Returns: {'year': int, 'complete': bool, 'available': bool,
              'cards': [{'id': str (same id as year_review cards, e.g. '2025-saved'),
                         'kind': str, 'facts': {...viewer fact names...}}]}.
        Cards whose essential facts are missing (e.g. no archetype label) are dropped.
    """
    story = {'year': review.get('year'), 'complete': bool(review.get('complete')),
             'available': bool(review.get('available')), 'cards': []}
    if not story['available']:
        return story
    for card in review.get('cards') or []:
        kind = card.get('kind')
        if kind not in _SUPPORTED:
            continue
        facts = card_facts(kind, review, card.get('facts') or {}, locale)
        if kind == 'archetype' and 'archetype_label' not in facts:
            continue
        story['cards'].append({'id': card['id'], 'kind': kind, 'facts': facts})
    return story


def compact_facts(review, locale='en'):
    """Small summary of a year review for the money profile and the agent.

    Returns {year, complete, observed_months, money_in_cents, money_out_cents, saved_cents,
    saving_rate_percent, top_category, top_category_share_percent, purchase_count,
    archetype_label} (None values omitted).
    """
    top = review.get('top_category') or {}
    return _compact({'year': review.get('year'), 'complete': review.get('complete'),
                     'observed_months': review.get('observed_months'),
                     'money_in_cents': review.get('money_in_cents'), 'money_out_cents': review.get('money_out_cents'),
                     'saved_cents': review.get('saved_cents'), 'saving_rate_percent': review.get('saving_rate_percent'),
                     'top_category': top.get('category'), 'top_category_share_percent': top.get('share_percent'),
                     'purchase_count': review.get('purchase_count'),
                     'archetype_label': _archetype_label(review.get('archetype'), locale)})


def _archetype(conn, customer_id, end_month, months):
    from .spender import spender_profile
    try:
        return spender_profile(conn, customer_id, end_month=end_month, months=max(2, min(months, 12)))
    except ValueError:
        return None


def build_review(conn, customer_id, year):
    """year_review.year_review with the spender archetype wired in (goals_fn=None).

    Args: conn, customer_id, year (int). Returns the year_review dict. Raises ValueError for an
    unknown customer.
    """
    from .year_review import year_review
    return year_review(conn, customer_id, year, archetype_fn=_archetype, goals_fn=None)


def default_year(conn, customer_id):
    """Newest complete available year, else newest available year, else None."""
    from .year_review import year_options
    options = [item for item in year_options(conn, customer_id) if item['available']]
    complete = [item for item in options if item['complete']]
    return (complete or options or [{'year': None}])[0]['year']


def compact_year(review, locale='en'):
    """Compact year facts for the AI tool: no story cards, no transaction refs.

    Returns {available, year, complete, observed_months, reason?} plus when available:
    money_in_cents, money_out_cents, saved_cents, saving_rate_percent, previous_year
    {year, complete, money_in_cents, money_out_cents, saved_cents, saving_rate_percent,
    saving_rate_delta_points, comparable, changes}, top_category {category, cents, share_percent},
    baskets [{basket, role, cents, share_percent}], little_leaks {cents, share_percent,
    months_of_rent_equivalent}, biggest_month, calmest_month {month, cents}, busiest_day
    {date, cents, count}, largest_purchase {category, date, cents}, purchase_count,
    favourite_weekday {weekday, count}, most_frequent_mcc {label, count},
    archetype_label, previous_archetype_label.
    """
    base = {'available': bool(review.get('available')), 'year': review.get('year'),
            'complete': review.get('complete'), 'observed_months': review.get('observed_months')}
    if not base['available']:
        base['reason'] = review.get('reason')
        return base
    names = {'fixed_obligation': 'Must-pays', 'flexible_essential': 'Surprise must-pays', 'discretionary': 'Little leaks'}
    previous = review.get('previous_year')
    if previous:
        previous = {key: previous.get(key) for key in ('year', 'complete', 'money_in_cents', 'money_out_cents', 'saved_cents',
                                                      'saving_rate_percent', 'saving_rate_delta_points', 'comparable', 'changes')}
    day, purchase = review.get('busiest_day'), review.get('largest_purchase')
    weekday, mcc = review.get('favourite_weekday'), review.get('most_frequent_mcc')
    base.update({
        'money_in_cents': review['money_in_cents'], 'money_out_cents': review['money_out_cents'],
        'saved_cents': review['saved_cents'], 'saving_rate_percent': review.get('saving_rate_percent'),
        'previous_year': previous, 'top_category': review.get('top_category'),
        'baskets': [{'basket': names.get(row['role'], row['role']), **row} for row in review.get('baskets') or []],
        'little_leaks': {key: (review.get('little_leaks') or {}).get(key) for key in ('cents', 'share_percent', 'months_of_rent_equivalent')},
        'biggest_month': review.get('biggest_month'), 'calmest_month': review.get('calmest_month'),
        'busiest_day': {key: day[key] for key in ('date', 'cents', 'count')} if day else None,
        'largest_purchase': {key: purchase[key] for key in ('category', 'date', 'cents')} if purchase else None,
        'purchase_count': review.get('purchase_count'),
        'favourite_weekday': {'weekday': weekday['weekday'], 'count': weekday['count']} if weekday else None,
        'most_frequent_mcc': {'label': mcc['label'], 'count': mcc['count']} if mcc else None,
        'archetype_label': _archetype_label(review.get('archetype'), locale),
        'previous_archetype_label': _archetype_label(review.get('archetype_previous'), locale),
    })
    return base
