"""Local question definitions, data-clock dates and safe follow-up state.

This resolver is deliberately bounded. Unresolved meaning is a question to the
customer, never permission to substitute a broader category or a model guess.
"""
import calendar
import re
from datetime import date

from .ledger import month_bounds, shift_month


CATEGORY_TERMS = (
    ('Restaurants', ('restaurant', 'dining', 'eating out', 'ravintol', 'restaurang')),
    ('Groceries', ('grocer', 'food shopping', 'ruokaostos', 'ruokaost', 'elintarvik', 'matvar', 'matinköp', 'livsmedel')),
    ('Transportation', ('transportation', 'transport', 'kuljetus', 'liikenne')),
    ('Entertainment', ('entertainment', 'cinema', 'movie', 'games', 'viih', 'elokuv', 'pelit', 'underhållning', 'nöje', 'bio', 'spel')),
    ('Health', ('health', 'medical', 'tervey', 'häls')),
    ('Home & Tech', ('home & tech', 'home appliance', 'appliance', 'electronics', 'washing machine', 'koti ja tekniikka', 'kodinkone', 'elektroniikka', 'pesukone', 'hem och teknik', 'hemelektronik', 'vitvar', 'tvättmaskin')),
    ('Housing', ('housing', 'rent', 'asumismen', 'vuokra', 'boende', 'hyra')),
    ('Lifestyle', ('lifestyle', 'shopping', 'ostokset', 'ostoksiin', 'clothes', 'clothing', 'fashion', 'elämäntyyli', 'vaatte', 'muoti', 'livsstil', 'kläder')),
    ('Travel', ('travel', 'flight', 'hotel', 'matkail', 'matkamen', 'lento', 'hotelli', 'resor', 'resa', 'flyg', 'hotell')),
    ('Utilities', ('utilities', 'electricity', 'water bill', 'phone bill', 'sähkö', 'vesilask', 'puhelinlask', 'käyttölask', 'elräkning', 'vattenräkning', 'telefonräkning')),
)
MCC_TERMS = (
    ('Taxi', '4121', ('taxi', 'taks')),
    ('Pharmacy', '5912', ('pharmac', 'apteek', 'apotek')),
    ('Doctor', '8011', ('doctor', 'lääkäri', 'läkare')),
    ('Dentist', '8021', ('dentist', 'hammaslääkäri', 'tandläkare')),
)
MONTHS = (
    ('january', 'jan', 'tammik', 'januari'), ('february', 'feb', 'helmik', 'februari'),
    ('march', 'mar', 'maalisk', 'mars'), ('april', 'apr', 'huhtik'),
    ('may', 'toukok', 'maj'), ('june', 'jun', 'kesäk', 'juni'),
    ('july', 'jul', 'heinäk', 'juli'), ('august', 'aug', 'elok', 'augusti'),
    ('september', 'sep', 'syysk'), ('october', 'oct', 'lokak', 'oktober'),
    ('november', 'nov', 'marrask'), ('december', 'dec', 'jouluk'),
)
METRICS = {'outflow_total', 'inflow_total', 'consumption_total', 'average_outflow', 'transaction_count', 'largest_outflow'}
SCOPE_FIELDS = {'customer_id', 'account_id', 'concept', 'metric', 'start', 'end', 'reference_date', 'filters'}
FILTER_FIELDS = {'category', 'role', 'transaction_type', 'merchant_id', 'mcc_code', 'consumption_only'}


def _locale(context):
    return context.get('interface_locale', context.get('locale', 'en'))


def _copy(context, en, fi, sv):
    return {'en': en, 'fi': fi, 'sv': sv}.get(_locale(context), en)


def clarify(context, code, en, fi, sv, options=()):
    return {'needs_clarification': True, 'clarification_question': _copy(context, en, fi, sv),
            'clarification_code': code, 'clarification_options': list(options), 'query_scope': None}


def is_vat_question(text):
    return bool(re.search(r'(?<!\w)(?:vat|alv|moms|arvonlisävero\w*|mervärdesskatt\w*)(?!\w)|\btax\s+inside\b', text.casefold()))


def has_reduction_verb(text):
    """Keep scenario and statistics routing aligned for bounded verb forms."""
    return bool(re.search(
        r'(?<!\w)(?:reduc(?:e[sd]?|ing)|cut(?:s|ting)?|lower(?:s|ed|ing)?|'
        r'vähent\w*|vähenn\w*|pienent\w*|minska(?:r|de|t|nde)?)(?!\w)',
        text.casefold(),
    ))


def is_exploratory_goal(text):
    """Recognize a small set of wishes without interpreting unrelated questions."""
    normalized = ' '.join(text.casefold().replace('’', "'").split()).rstrip('.?!')
    patterns = (
        r'(?:help me )?plan (?:an? )?(?:emergency )?buffer',
        r'i want (?:to save|(?:an? )?(?:emergency )?buffer)'
        r'(?:,? but i (?:do not|don\'t) know (?:how much|the amount)(?: yet)?)?',
        r'(?:suunnittele|auta suunnittelemaan) (?:vararahasto|puskuri)',
        r'haluan (?:säästää|puskurin|vararahaston)'
        r'(?:,? mutta en tiedä (?:vielä )?(?:summaa|kuinka paljon)(?: vielä)?)?',
        r'(?:hjälp mig )?planera en (?:buffert|nödbuffert)',
        r'jag vill (?:spara|ha en (?:buffert|nödbuffert))'
        r'(?:,? men jag vet inte (?:hur mycket|beloppet)(?: ännu)?)?',
    )
    return any(re.fullmatch(pattern, normalized) for pattern in patterns)


def planning_request(message):
    """Recognize a prospective decision before an item can become a ledger filter.

    This is deliberately about the speech act, not just the category noun. An
    explicit request to inspect earlier spending remains a history question.
    """
    text = ' '.join(message.casefold().replace('’', "'").split())
    historical = re.search(r'\b(?:spent|did i spend|have i spent|paid|history|statistics|transactions|spending|'
                           r'average|käytin|maksoin|kulutustilasto|spenderade|betalade|historik)\b', text)
    if is_exploratory_goal(text) or re.search(r'\b(?:save|saving|savings|sääst\w*|spara|sparmål)\b', text):
        return None
    prospective = re.search(
        r"\b(?:i (?:want|need|hope|plan|intend|would like)|i'd like|"
        r"i(?: am|'m) (?:planning|thinking|going)|(?:can|could|should) i (?:spend|afford|buy|get|go|book|pay)|"
        r'haluan|haluaisin|aion|suunnittelen|tarvitsen|voinko (?:ostaa|mennä|käyttää)|onko minulla varaa|'
        r'jag vill|jag skulle vilja|jag tänker|jag planerar|jag behöver|kan jag (?:köpa|gå|spendera)|har jag råd)\b',
        text,
    )
    if not prospective:
        return None
    if re.search(r'\b(?:want|would like|need) to (?:know|understand|check|see how|review)\b', text):
        return None
    if historical:
        if re.search(r'\b(?:buy|go|watch|have dinner|travel|see (?:a |the )?movie)\b', text):
            return 'mixed'
        return None
    if re.search(r'\b(?:car|home|house|mortgage|loan|credit|rent|holiday|vacation|trip|flight|laptop|'
                 r'subscription|monthly|annually|every (?:week|month|year)|per (?:week|month|year)|'
                 r'auto\w*|asunto\w*|laina\w*|luotto\w*|vuokra\w*|loma\w*|tilaus|kuukausittain|'
                 r'bil|bostad\w*|bolån\w*|lån|kredit|hyra\w*|semester|prenumeration|varje månad)\b', text):
        return 'commitment'
    topics = (
        ('movie', r'\b(?:movie\w*|cinema|film\w*|elokuv\w*|bio)\b'),
        ('meal', r'\b(?:dinner|lunch|meal\w*|restaurant\w*|dining|takeaway|takeout|ravintol\w*|illalli\w*|lounas|restaurang\w*|middag)\b'),
        ('coffee', r'\b(?:coffee\w*|cafe|café|kahvi\w*|kaffe)\b'),
        ('groceries', r'\b(?:grocer\w*|food shopping|ruokaostos\w*|ruokaost\w*|matvar\w*|matinköp)\b'),
        ('clothes', r'\b(?:clothes|clothing|shoes|vaatte\w*|keng\w*|kläder|skor)\b'),
        ('outing', r'\b(?:concert|taxi|entertainment|outing|konsertti\w*|taks\w*|konsert|nöje\w*)\b'),
    )
    for topic, pattern in topics:
        if re.search(pattern, text):
            return topic
    if re.search(r'\b(?:travel|matka\w*|resa|resor)\b', text):
        return 'commitment'
    # Without an object, an affordability question still needs its original
    # contextual clarification; a general wish must not pick a random insight.
    if re.search(r'\b(?:afford(?: it)?|onko minulla varaa|har jag råd)\b', text):
        return None
    if re.search(r'\b(?:buy|purchase|book|replace|go|watch|visit|get|ostaa|mennä|köpa|gå)\b', text):
        return 'wish'
    return None


def _category_shorthand(text):
    """Allow an explicit category/date fragment, not any sentence naming it."""
    remainder = text
    for _, terms in CATEGORY_TERMS:
        for term in sorted(terms, key=len, reverse=True):
            remainder = re.sub(r'(?<!\w)' + re.escape(term) + r'\w*', ' ', remainder)
    for _, _, terms in MCC_TERMS:
        for term in terms:
            remainder = re.sub(r'(?<!\w)' + re.escape(term) + r'\w*', ' ', remainder)
    for terms in MONTHS:
        for term in terms:
            remainder = re.sub(r'(?<!\w)' + re.escape(term) + (r'uu\w*' if term.endswith('k') else r'(?!\w)'), ' ', remainder)
    remainder = re.sub(r'\d{4}-\d{2}(?:-\d{2})?|\b\d{4}\b', ' ', remainder)
    remainder = re.sub(r'\b(?:my|in|during|for|on|from|to|between|and|this|last|next|previous|current|'
                       r'month|week|yesterday|today|tomorrow|before|after|since|past|over|the|'
                       r'kuussa|viime|tässä|i|den|här|månaden|förra)\b', ' ', remainder)
    return re.search(r'\w', remainder) is None


def _matches(text, term):
    if term in {'rent', 'shopping', 'ostokset', 'ostoksiin'}:
        return re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text) is not None
    return term in text


def concept_filters(text):
    # A known MCC concept takes priority over its broader source category.
    for concept, code, terms in reversed(MCC_TERMS):
        if any(_matches(text, term) for term in terms):
            return concept, {'mcc_code': code}
    for category, terms in CATEGORY_TERMS:
        if any(_matches(text, term) for term in terms):
            return category, {'category': category}
    return None, {}


def _check_dates(start, end, context):
    if not all(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) for value in (start, end)):
        raise ValueError('Scope dates must be ISO dates')
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError('Reversed period')
    if context.get('observed_start') and start[:7] < context['observed_start'][:7]:
        raise ValueError('Period before observed history')
    if context.get('observed_end') and end[:7] > context['observed_end'][:7]:
        raise ValueError('Period after observed history')


def validate_previous_query(value, context):
    """Validate client-carried scope; it grants no access outside current account."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != SCOPE_FIELDS:
        raise ValueError('previous_query must be a resolved scope object')
    if value['customer_id'] != context.get('customer_id') or value['account_id'] != context.get('account_id'):
        raise ValueError('Previous query belongs to another customer or account')
    if not isinstance(value['metric'], str) or value['metric'] not in METRICS or not isinstance(value['concept'], str) or not 0 < len(value['concept']) <= 80:
        raise ValueError('Unsupported previous query definition')
    _check_dates(value['start'], value['end'], context)
    if not isinstance(value['reference_date'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value['reference_date']):
        raise ValueError('Invalid previous query reference date')
    date.fromisoformat(value['reference_date'])
    filters = value['filters']
    aggregate = (value['concept'], value['metric']) in {('All spending', 'consumption_total'), ('All outflows', 'outflow_total'), ('All inflows', 'inflow_total')}
    if not isinstance(filters, dict) or (not filters and not aggregate) or set(filters) - FILTER_FIELDS:
        raise ValueError('Unsupported previous query filters')
    for name, item in filters.items():
        if not isinstance(item, str) or not item.strip() or len(item) > 100:
            raise ValueError('Invalid previous query filter')
        if name == 'mcc_code' and not re.fullmatch(r'\d{4}', item):
            raise ValueError('mcc_code must be four digits')
        if name == 'consumption_only' and item != 'true':
            raise ValueError('consumption_only must be true')
    return {**value, 'filters': dict(filters)}


def _period(text, context, previous, followup):
    selected = context.get('period')
    if not selected:
        raise ValueError('A selected period is required')
    # A month default must never erase a requested week, rolling window, or
    # open-ended date predicate. These need an explicit supported date range.
    if re.search(r'\b(?:this|last|next|previous|current) week\b|\b(?:today|tomorrow|yesterday)\b|'
                 r'\b(?:past|last|next|previous)\s+(?:(?:\d+|one|two|three|four|six|twelve)\s+)?(?:days|weeks|months|years)\b|'
                 r'\b(?:before|after|since|through|earlier than|later than)\s+(?:\d{4}|january|february|march|april|may|june|july|august|september|october|november|december)\b|'
                 r'tällä viikolla|viime viikolla|ensi viikolla|den här veckan|förra veckan|nästa vecka', text):
        raise ValueError('Choose an explicit date range for that window')
    relative_month = re.search(r'\b(?:last|previous|this|current|next) month\b|viime kuussa|tässä kuussa|förra månaden|den här månaden', text)
    iso_days = re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', text)
    if iso_days:
        if relative_month:
            raise ValueError('Choose one date expression')
        if len(iso_days) not in {1, 2}:
            raise ValueError('Choose one date or one date range')
        if len(iso_days) == 1 and re.search(r'\b(?:from|between|to|until)\b', text):
            raise ValueError('Both dates are required for a range')
        return iso_days[0], iso_days[-1]
    iso_months = re.findall(r'(?<!\d)\d{4}-\d{2}(?!-\d|\d)', text)
    if iso_months:
        if relative_month:
            raise ValueError('Choose one date expression')
        if len(set(iso_months)) != 1:
            raise ValueError('Choose one month or an explicit date range')
        return month_bounds(iso_months[0])
    named = []
    for number, terms in enumerate(MONTHS, 1):
        if any(re.search(r'(?<!\w)' + re.escape(term) + (r'uu\w*' if term.endswith('k') else r'(?!\w)'), text) for term in terms):
            named.append(number)
    if len(named) > 1:
        raise ValueError('Choose one month or an explicit date range')
    years = re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', text)
    if named:
        if relative_month:
            raise ValueError('Choose one date expression')
        if any(re.search(r'(?<!\w)' + re.escape(term) + r'\w*\s+\d{1,2}(?=\s|,|$)', text)
               for number in named for term in MONTHS[number - 1]):
            raise ValueError('Use ISO dates for a specific day or date range')
        inherited_year = previous['start'][:4] if followup and previous else selected[:4]
        year = int(years[0]) if len(set(years)) == 1 else int(inherited_year)
        if len(set(years)) > 1:
            raise ValueError('Choose one year')
        return month_bounds(f'{year:04d}-{named[0]:02d}')
    if years:
        # The UI is a complete-month explorer; year-only scope is ambiguous here.
        raise ValueError('Choose a month or explicit dates for that year')
    if any(term in text for term in ('last month', 'previous month', 'viime kuussa', 'edellisessä kuussa', 'förra månaden', 'föregående månad')):
        return month_bounds(shift_month(selected, -1))
    if any(term in text for term in ('this month', 'current month', 'tässä kuussa', 'tänä kuukautena', 'den här månaden', 'denna månad')):
        return month_bounds(selected)
    if any(term in text for term in ('yesterday', 'today', 'last week', 'this year', 'last year', 'next month', 'annual', 'yearly', 'per year', 'vuositulo', 'vuodessa', 'vuotuinen', 'årsinkomst', 'per år', 'årliga', 'eilen', 'tänään', 'i går', 'idag')):
        raise ValueError('Choose explicit dates for that expression')
    if followup and previous:
        return previous['start'], previous['end']
    return month_bounds(selected)


def resolve_period(message, context):
    """Resolve other deterministic tools' dates with the same data-clock rules."""
    text = message.casefold()
    previous = validate_previous_query(context.get('previous_query'), context)
    followup = bool(re.match(r'(?:and\b|what about\b|how about\b|entä\b|och\b|hur är det med\b)', text))
    start, end = _period(text, context, previous, followup)
    _check_dates(start, end, context)
    return start, end


def _tool_request_tail(message, phrases):
    text = ' '.join(message.casefold().split()).rstrip('.?!')
    for phrase in phrases:
        match = re.fullmatch(r'(?:' + phrase + r')(?P<tail>(?: .*)?)', text)
        if match:
            return match['tail'].strip()
    raise ValueError('Choose a supported tool question and period')


def resolve_cashflow_parameters(message, context):
    """A forecast starts on an exact reference date; it is not a month total."""
    tail = _tool_request_tail(message, (
        r'(?:(?:show(?: me)?|preview|explain) )?(?:my )?(?:cash ?flow|runway)(?: forecast)?',
        r'how does (?:my )?cash ?flow look',
        r'(?:what might next month look like|how does next month look)',
        r'(?:näytä(?: minulle)? )?kassavirta(?:ni)?',
        r'(?:visa(?: mig)? )?(?:mitt )?kassaflöde',
    ))
    if tail:
        match = re.fullmatch(r'(?:as of|from|starting(?: on)?|alkaen|från) (\d{4}-\d{2}-\d{2})', tail)
        if not match:
            raise ValueError('A forecast needs one ISO reference date')
        reference_date = match[1]
    else:
        reference_date = context.get('reference_date') or month_bounds(context['period'])[1]
    _check_dates(reference_date, reference_date, context)
    if context.get('observed_start') and reference_date < context['observed_start']:
        raise ValueError('Reference date is before observed history')
    if context.get('observed_end') and reference_date > context['observed_end']:
        raise ValueError('Reference date is after observed history')
    return {'reference_date': reference_date, 'days': 30}


def has_current_safe_to_spend_scope(message):
    """The current API executes this estimate only at the selected data clock."""
    try:
        tail = _tool_request_tail(message, (
            r'(?:what is |how much is |show )?safe (?:for me )?to spend',
            r'(?:how much(?: money)? (?:can|could) i (?:safely )?spend|what can i spend)(?: safely)?',
            r'(?:paljonko|kuinka paljon) (?:voin käyttää(?: turvallisesti)?|on turvallista käyttää)',
            r'hur mycket (?:kan jag spendera|är säkert att spendera|är tryggt för mig att spendera)',
        ))
    except ValueError:
        return False
    return tail in {'', 'this week', 'tällä viikolla', 'den här veckan'}


def resolve_investment_parameters(message, context):
    """Only a recognized single month may replace the default investment window."""
    tail = _tool_request_tail(message, (
        r'(?:(?:show(?: me)?|review|explain|what are|what were) )?(?:my )?'
        r'investment(?:s| transfers| cash ?flow| contributions| deposits| withdrawals)?',
        r'(?:näytä(?: minulle)? )?(?:sijoitussiirtoni|sijoitussiirrot|sijoitukset|sijoitukseni)',
        r'(?:visa(?: mig)? )?(?:mina )?(?:investeringsöverföringar|investeringar|placeringar)',
    ))
    if not tail:
        return {'period': context['period'], 'months': context.get('months', 12)}
    names = '|'.join(re.escape(term) + (r'uu\w*' if term.endswith('k') else '')
                     for terms in MONTHS for term in terms)
    month = r'(?:(?:' + names + r')(?: (?:19|20)\d{2})?|\d{4}-\d{2})'
    relative = r'(?:last|previous|this|current) month|viime kuussa|edellisessä kuussa|tässä kuussa|tänä kuukautena|förra månaden|föregående månad|den här månaden|denna månad'
    if not re.fullmatch(r'(?:(?:in|during|for|i|under) )?(?:' + month + '|' + relative + ')', tail):
        raise ValueError('Choose one complete month for investment transfers')
    start, end = resolve_period(tail, context)
    if (start, end) != month_bounds(start[:7]):
        raise ValueError('Investment transfers need a complete month')
    return {'period': start[:7], 'months': 1}


def _total_spending_question(text):
    match = re.match(r'^(?:how much(?: money)? did i spend|what (?:was|is) my total spending|total spending|paljonko käytin|hur mycket spenderade jag)\b', text)
    if not match:
        return False
    remainder = text[match.end():]
    remainder = re.sub(r'\d{4}-\d{2}(?:-\d{2})?|\b\d{4}\b', ' ', remainder)
    for terms in MONTHS:
        for term in terms:
            remainder = re.sub(r'(?<!\w)' + re.escape(term) + (r'uu\w*' if term.endswith('k') else r'(?!\w)'), ' ', remainder)
    remainder = re.sub(r'\b(?:in|during|from|to|between|this|last|the|current|previous|month|for|my|account|all|tähän|tässä|viime|kuussa|i|den|här|månaden|förra)\b', ' ', remainder)
    return re.search(r'\w', remainder) is None


def _personal_inference_request(text):
    """Payment categories are not evidence of feelings, diagnoses or life events."""
    emotion = any(term in text for term in (
        'stress', 'depress', 'anxio', 'anxiety', 'lonely', 'loneliness', 'sadness', 'angry',
        'addict', 'mental health', 'emotional', 'masennu', 'ahdist', 'yksinäi', 'tuntei',
        'nedstämd', 'ångest', 'ensamhet', 'beroende', 'känsl',
    ))
    biography = any(term in text for term in (
        'lost my job', 'lose my job', 'was fired', 'got fired', 'got promoted', 'promotion',
        'got divorced', 'divorce', 'got married', 'pregnan', 'my life story', 'my personality',
        'my motivation', 'irtisan', 'työttöm', 'raskaana', 'avioero', 'persoonallisu',
        'arbetslös', 'uppsagd', 'gravid', 'skilsmäss', 'personlighet',
    ))
    medical = any(term in text for term in (
        'doctor', 'pharmac', 'medication', 'medicine', 'health', 'diagnos', 'cancer', 'disease',
        'apteek', 'lääkär', 'lääkke', 'tervey', 'sairau', 'läkar', 'apotek', 'medicin', 'häls', 'sjuk',
    ))
    inference = any(term in text for term in (
        'because', 'why did i', 'why do i', 'am i', 'was i', 'do my', 'when i was', 'while i was',
        'does my', 'mean i', 'mean that', 'based on', 'say about', 'reveal', 'diagnos',
        'koska', 'olenko', 'oliko', 'ovatko', 'tarkoitta', 'merkki', 'päätellä',
        'för att', 'betyder', 'är jag', 'var jag', 'säger om', 'tyder på',
    ))
    inference = inference or bool(re.match(r'^(?:did|do) i\b', text))
    motive = bool(re.search(r'\bwhy (?:did|do) i (?:buy|purchase|book|choose|pay|shop|travel)\b', text))
    motive = motive or any(term in text for term in ('miksi ostin', 'miksi ostinko', 'varför köpte jag', 'varför valde jag', 'what kind of person', 'what sort of person'))
    motive = motive or (
        any(term in text for term in ('because', 'in order to', 'so that', 'koska', 'för att'))
        and any(term in text for term in ('buy', 'bought', 'purchase', 'ostin', 'ostinko', 'köpte', 'handlade', 'valde'))
    )
    return motive or (inference and (emotion or biography or medical))


def _income_options(context):
    return (
        _copy(context, 'How much salary was credited to my account this month?', 'Paljonko palkkaa sain tässä kuussa?', 'Hur mycket lön fick jag den här månaden?'),
        _copy(context, 'How much income did I receive this month?', 'Paljonko tuloja sain tässä kuussa?', 'Hur mycket inkomst fick jag den här månaden?'),
    )


def _incoming_definition(text):
    """Source income is not the same thing as all credits to the account."""
    if any(term in text for term in ('all incoming', 'money came into', 'money into my account', 'all money received', 'total inflows', 'kaikki saapuvat', 'alla inkommande')):
        return 'All inflows', {}
    if re.search(r'\b(?:salary|paycheck|paycheque|net pay|palkka\w*|palkan\w*|lön\w*|nettopalk\w*|nettolön\w*)\b', text):
        return 'Salary credits', {'transaction_type': 'salary'}
    if re.search(r'\b(?:income|earnings|tulot|tuloja|tulojen|inkomst\w*)\b', text):
        return 'Income received', {'role': 'income'}
    return None, {}


def _broader_spending_options(context):
    return (
        _copy(context, 'How much did I spend this month?', 'Paljonko käytin tässä kuussa?', 'Hur mycket spenderade jag den här månaden?'),
        _copy(context, 'How much did I spend on restaurants this month?', 'Paljonko käytin ravintoloihin tässä kuussa?', 'Hur mycket spenderade jag på restaurang den här månaden?'),
    )


def _unsupported_merchant_name(message):
    """The CSV has merchant IDs, not a map from real store names to those IDs."""
    text = message.casefold()
    generic = {'restaurant', 'restaurants', 'pharmacy', 'pharmacies', 'doctor', 'doctors', 'dentist', 'dentists',
               'groceries', 'shopping', 'transportation', 'health', 'housing', 'utilities', 'entertainment', 'travel',
               'restaurang', 'restauranger', 'matvaror', 'matinköp', 'apotek', 'läkare', 'tandläkare', 'boende', 'resor',
               'taxi', 'hälsa', 'nöjen', 'kläder', 'hyra', 'bio', 'spel'}
    for match in re.finditer(r'\b(?:at|from|hos|från|på)\s+([\w-]+)', text):
        word = match.group(1)
        tail = text[match.start(1):]
        if word[0].isdigit() or word in generic or _incoming_definition(tail)[0]:
            continue
        if re.match(r'(?:this|my|the|selected|that)\s+(?:selected\s+)?(?:bank\s+)?account\b', tail) or re.match(r'(?:mitt|min|det här|det valda)\s+(?:bank)?konto\b', tail):
            continue
        if any(word == term or term.endswith('k') and word.startswith(term) for terms in MONTHS for term in terms):
            continue
        return True
    # Finnish commonly attaches the location ending to a proper store name.
    for word in re.findall(r'\b[A-ZÅÄÖ][a-zåäö]+(?:ssa|ssä|sta|stä)\b', message):
        lowered = word.casefold()
        if concept_filters(lowered)[0] or any(term.endswith('k') and lowered.startswith(term) for terms in MONTHS for term in terms):
            continue
        return True
    return False


def resolve_statistics(message, context):
    """Return a scoped local statistics plan, a clarification, or None for other intents."""
    text = message.casefold().strip()
    previous = validate_previous_query(context.get('previous_query'), context)
    if _personal_inference_request(text):
        return clarify(context, 'inference_unavailable',
                       'Payments cannot tell me your feelings, motives, diagnoses, or life events. I cannot infer why you bought something or what a healthcare payment means. Would you like to review the transactions or add your own reflection to your notebook?',
                       'Maksuista ei voi päätellä tunteitasi, motiivejasi, diagnooseja tai elämäntapahtumia. En voi päätellä ostoksen syytä tai terveysmaksun merkitystä. Haluatko tarkastella tapahtumia tai lisätä oman pohdintasi muistikirjaan?',
                       'Betalningar visar inte känslor, motiv, diagnoser eller livshändelser. Jag kan inte avgöra varför du köpte något eller vad en vårdbetalning betyder. Vill du granska transaktionerna eller lägga till en egen reflektion i anteckningsboken?',
                       ('What kind of spender am I?',))
    account_ids = re.findall(r'\b(?:cust|acc)\d+\b', text)
    own_ids = {str(context.get('customer_id', '')).casefold(), str(context.get('account_id', '')).casefold()}
    if any(value not in own_ids for value in account_ids) or any(term in text for term in (
        'all my accounts', 'all my bank accounts', 'across accounts', 'across all', 'other bank',
        'other accounts', 'joint account', 'family account', 'kaikilta tile', 'alla mina konton',
    )):
        return clarify(context, 'account_scope',
                       'This demo contains one account for the selected profile. Should I use that account only? Other people and banks are outside this data.',
                       'Demo sisältää yhden tilin valitulle profiilille. Käytänkö vain sitä? Muiden ihmisten ja pankkien tiedot puuttuvat.',
                       'Demon innehåller ett konto för vald profil. Ska jag använda bara det? Andra personers och bankers uppgifter saknas.')
    if planning_request(message):
        return None
    if (re.search(r"\bi(?: am|'m| feel) (?:really |very )?(?:worried|stressed|anxious|overwhelmed)\b", text.replace('’', "'"))
            and not re.search(r'\b(?:how much|how many|total|average|did i|have i)\b', text)):
        return clarify(context, 'coaching_support',
                       'We can take this one step at a time. What feels most urgent: upcoming bills, day-to-day spending, or building a small buffer?',
                       'Voimme edetä yksi askel kerrallaan. Mikä tuntuu tärkeimmältä: tulevat laskut, arjen menot vai pieni vararahasto?',
                       'Vi kan ta ett steg i taget. Vad känns mest angeläget: kommande räkningar, vardagsutgifter eller en liten buffert?')
    threshold = re.search(r'\b(?:over|under|above|below|more than|less than|at least|at most|yli|alle|vähintään|enintään|enemmän kuin|vähemmän kuin|över|mer än|mindre än|minst|högst)\s*(?:[€$£]|eur\s*)?\d', text)
    if threshold or any(term in text for term in (
        'after refunds', 'net of refunds', 'excluding', 'except ', 'without ', 'not including',
        'weekdays', 'weekends', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'palautusten jälkeen', 'ilman ', 'arkipäiv', 'viikonloppu', 'återbetalningar', 'exklusive', 'vardagar', 'helger',
    )):
        return clarify(context, 'unsupported_filter',
                       'That condition is not supported yet. The choices below deliberately show a broader default view, without applying the condition you asked for.',
                       'Tätä ehtoa ei vielä tueta. Alla olevat valinnat näyttävät tarkoituksella laajemman oletusnäkymän ilman pyytämääsi ehtoa.',
                       'Det villkoret stöds inte ännu. Valen nedan visar avsiktligt en bredare standardvy utan det villkor du bad om.',
                       _broader_spending_options(context))
    if _unsupported_merchant_name(message):
        return clarify(context, 'unsupported_detail',
                       'Merchant names are not provided in this dataset, so I cannot match that store reliably. The choices below deliberately use broader category totals instead.',
                       'Aineisto ei sisällä kauppiaiden nimiä, joten en voi tunnistaa tätä kauppaa luotettavasti. Alla olevat valinnat käyttävät tarkoituksella laajempia luokkasummia.',
                       'Datan innehåller inte handlarnamn, så jag kan inte matcha den butiken säkert. Valen nedan använder avsiktligt bredare kategorisummor.',
                       _broader_spending_options(context))
    if any(term in text for term in ('gross salary', 'gross pay', 'before tax', 'pre-tax', 'tax withheld', 'withheld from', 'bruttopalk', 'bruttolön', 'tax rate', 'tax percentage', 'veroprosent', 'veroaste', 'skattesats', 'skatteprocent')):
        return clarify(context, 'income_gross_unavailable',
                       'The source shows salary credited to the account. It cannot establish gross pay or a personal tax rate. The choices below use observed credited amounts instead.',
                       'Lähde näyttää tilille maksetun palkan. Siitä ei voi päätellä bruttopalkkaa tai henkilökohtaista veroprosenttia. Alla olevat valinnat käyttävät havaittuja tilille maksettuja summia.',
                       'Källan visar lön som satts in på kontot. Den kan inte fastställa bruttolön eller personlig skattesats. Valen nedan använder i stället observerade insättningar.',
                       _income_options(context))
    if re.search(r'\b(?:investment|interest|dividend|rental|passive|business)\s+income\b', text):
        return clarify(context, 'income_source_unavailable',
                       'The source does not identify that income subtype. The choices below show broader observed salary credits or classified income, not an estimate of the subtype you asked about.',
                       'Lähde ei tunnista tätä tulolajia. Alla näkyvät vaihtoehdot näyttävät laajemmat havaitut palkka- tai tulomaksut, eivät arviota pyytämästäsi tulolajista.',
                       'Källan identifierar inte den inkomsttypen. Valen nedan visar bredare observerade löneinsättningar eller klassificerade inkomster, inte en uppskattning av typen du frågade om.',
                       _income_options(context))
    # Taxes are a different evidence tool, even when the previous query was a
    # restaurant statistic. Never carry that old category into a new topic.
    if is_vat_question(text):
        return None
    credited_salary = _incoming_definition(text)[0] == 'Salary credits' and any(term in text for term in ('after tax', 'efter skatt', 'verojen jälkeen'))
    if re.search(r'\b(?:tax|taxes|vero|verot|veroja|veroa|skatt|skatter)\b', text) and not credited_salary:
        return None
    if any(term in text for term in ('portfolio return', 'investment return', 'investment performance', 'portfolio value', 'best fund', 'best stock', 'sijoitustuotto', 'salkun arvo', 'portföljvärde', 'avkastning')):
        return clarify(context, 'investment_data_limit',
                       'This dataset contains investment transfers, not holdings, market values, or returns. Would you like to see the money moved into and out of investments?',
                       'Aineistossa on sijoitussiirtoja, ei omistuksia, markkina-arvoja tai tuottoja. Haluatko nähdä sijoituksiin ja niistä siirretyt rahat?',
                       'Datan innehåller investeringsöverföringar, inte innehav, marknadsvärden eller avkastning. Vill du se pengar som förts till och från investeringar?',
                       ('Show my investment transfers',))
    if any(term in text for term in ('can i afford', 'afford it', 'is it affordable', 'onko minulla varaa', 'har jag råd')):
        return clarify(context, 'affordability_context',
                       'What would you like to buy, how much will it cost, and when? I can compare a planning scenario with this account history.',
                       'Mitä haluaisit ostaa, paljonko se maksaa ja milloin? Voin verrata suunnitelmaa tämän tilin historiaan.',
                       'Vad vill du köpa, vad kostar det och när? Jag kan jämföra en plan med historiken på detta konto.')
    # More specific item/brand data is absent; do not silently widen it to a category.
    if any(term in text for term in ('coffee', 'coffees', 'beer', 'alcohol', 'starbucks', 'uber', 'kahvi', 'olut', 'kaffe', 'öl ')):
        return clarify(context, 'unsupported_detail',
                       'The data identifies categories and merchant codes, not individual items or these brands. Would you like a supported category such as restaurants instead?',
                       'Aineisto tunnistaa luokkia ja kauppiaskoodeja, ei yksittäisiä tuotteita tai näitä brändejä. Haluatko tarkistaa esimerkiksi ravintolamenot?',
                       'Datan visar kategorier och handlarkoder, inte enskilda varor eller dessa varumärken. Vill du se en kategori som restauranger?',
                       ('How much did I spend on restaurants?', 'How much did I spend on groceries?'))
    categories = {category for category, terms in CATEGORY_TERMS if any(_matches(text, term) for term in terms)}
    narrow = {name for name, code, terms in MCC_TERMS if any(_matches(text, term) for term in terms)}
    if len(categories) > 1 or len(narrow) > 1:
        return clarify(context, 'category_selection',
                       'I can calculate one category at a time. Which category should I start with?',
                       'Voin laskea yhden luokan kerrallaan. Mistä luokasta aloitetaan?',
                       'Jag kan räkna en kategori i taget. Vilken kategori vill du börja med?',
                       tuple(f'How much did I spend on {category.lower()}?' for category in sorted(categories)))
    if has_reduction_verb(text) or any(term in text for term in ('reduzier', 'spare ich')):
        return None
    financial_change = any(term in text for term in ('what changed', 'explain', 'selitä', 'muuttui', 'förändr')) or (
        any(term in text for term in ('why', 'miksi', 'varför'))
        and any(term in text for term in ('increas', 'decreas', 'change', 'rose', 'fell', 'kasvo', 'vähen', 'ökad', 'minskad'))
    )
    if financial_change:
        # The existing primary explanation compares visits and average payments
        # for restaurants. Other causal stories need a supported comparison.
        if concept_filters(text)[0] in {None, 'Restaurants'}:
            return None
        return {**clarify(context, 'comparison_definition',
                       'I can compare observed payment totals, counts and averages, but cannot infer a personal cause. Which category and two periods would you like to compare?',
                       'Voin verrata havaittuja maksusummia, määriä ja keskiarvoja, mutta en päätellä henkilökohtaista syytä. Mitä luokkaa ja kahta ajanjaksoa haluat verrata?',
                       'Jag kan jämföra observerade betalningar, antal och genomsnitt, men inte avgöra en personlig orsak. Vilken kategori och vilka två perioder vill du jämföra?'), 'parameters': {}}
    if is_exploratory_goal(text) or any(term in text for term in ('want to save', 'saving goal', 'plan a goal', 'plan my', 'help me save', 'savings goal', 'säästää', 'säästötavoit', 'sparmål', 'vill spara')):
        return None
    concept, filters = concept_filters(text)
    aggregate_metric = None
    incoming_concept, incoming_filters = _incoming_definition(text)
    if incoming_concept:
        concept, filters, aggregate_metric = incoming_concept, incoming_filters, 'inflow_total'
    elif not concept and _total_spending_question(text):
        concept, filters, aggregate_metric = 'All spending', {'consumption_only': 'true'}, 'consumption_total'
    elif not concept and any(term in text for term in ('money left this account', 'money left my account', 'money out of this account', 'total outflows')):
        concept, filters, aggregate_metric = 'All outflows', {}, 'outflow_total'
    followup = bool(re.match(r'(?:and\b|what about\b|how about\b|entä\b|och\b|hur är det med\b)', text))
    if followup and not previous:
        return clarify(context, 'missing_context',
                       'Which spending category and period should I start from?',
                       'Mistä kululuokasta ja ajanjaksosta aloitetaan?',
                       'Vilken utgiftskategori och period ska jag utgå från?',
                       ('How much did I spend on restaurants?', 'How much did I spend on groceries?'))
    if followup and not concept and previous:
        remainder = re.sub(r'\d{4}-\d{2}(?:-\d{2})?|\b\d{4}\b', ' ', text)
        for terms in MONTHS:
            for term in terms:
                remainder = re.sub(r'(?<!\w)' + re.escape(term) + (r'uu\w*' if term.endswith('k') else r'(?!\w)'), ' ', remainder)
        remainder = re.sub(r'\b(?:and|what|about|how|entä|och|hur|är|det|med|in|for|on|from|to|between|my|the|last|this|previous|current|month|månaden|månad|kuussa|viime|tässä|per|purchase|transaction|average|largest|biggest|count|many|purchases)\b', ' ', remainder)
        if re.search(r'\w', remainder) or text in {'and?', 'what about?', 'and', 'entä?', 'och?'}:
            return clarify(context, 'followup_scope',
                           'That sounds like a new topic. Which supported spending category, metric, or date range would you like me to use?',
                           'Tämä vaikuttaa uudelta aiheelta. Mitä tuettua kululuokkaa, mittaria tai päiväväliä käytän?',
                           'Det låter som ett nytt ämne. Vilken stödd utgiftskategori, mätning eller vilket datumintervall vill du använda?')
        concept, filters = previous['concept'], dict(previous['filters'])
    statistics_question = any(term in text for term in ('how much', 'spent', 'spend', 'total', 'average', 'how many', 'largest', 'biggest', 'paljonko', 'kuinka paljon', 'käytin', 'hur mycket', 'spenderade', 'summa', 'keski', 'genomsnitt'))
    statistics_question = statistics_question or bool(re.search(r'\b(?:count|montako|kuinka monta|hur många)\b', text))
    if not concept:
        if statistics_question and not any(term in text for term in ('save', 'safe', 'week', 'invest', 'tax', 'spender am', 'spenderare', 'rahankäyttäjä', 'sääst', 'verot', 'veroa', 'skatt', 'voin käyttää', 'kan jag spendera', 'tryggt för mig att spendera')):
            return clarify(context, 'missing_category',
                           'Which category or exact filter and month should I use?',
                           'Mitä luokkaa tai tarkkaa suodatinta ja kuukautta käytän?',
                           'Vilken kategori eller exakt filtrering och månad ska jag använda?',
                           ('How much did I spend on restaurants?', 'How much did I spend on groceries?'))
        return None
    if not (statistics_question or followup or incoming_concept or _category_shorthand(text)):
        return None
    try:
        start, end = _period(text, context, previous, followup)
        _check_dates(start, end, context)
    except (ValueError, TypeError):
        return clarify(context, 'period_scope',
                       'Which month or ISO date range within the available history should I use? Relative dates use the selected data month, not today.',
                       'Mitä kuukautta tai ISO-päiväväliä käytettävissä olevasta historiasta käytän? Suhteelliset päivät perustuvat valittuun datakuukauteen.',
                       'Vilken månad eller vilket ISO-datumintervall i historiken ska jag använda? Relativa datum utgår från vald datamånad.')
    inherited_metric = previous['metric'] if followup and previous else 'outflow_total'
    if concept in {category for category, terms in CATEGORY_TERMS} and inherited_metric == 'inflow_total':
        inherited_metric = 'outflow_total'
    metric = aggregate_metric or inherited_metric
    if metric == 'inflow_total' and (any(term in text for term in ('average', 'keski', 'genomsnitt', 'largest', 'biggest', 'suurin', 'största')) or re.search(r'\b(?:how many|count|montako|kuinka monta|hur många)\b', text)):
        return clarify(context, 'income_metric_definition',
                       'This view totals incoming credits. For a count or average, please first choose whether to count salary payments or all income payments. You can open either observed total below.',
                       'Tämä näkymä laskee saapuvien maksujen summan. Määrää tai keskiarvoa varten valitse ensin palkkamaksut tai kaikki tulomaksut. Alla voit avata havaitut summat.',
                       'Den här vyn summerar inkommande betalningar. För antal eller genomsnitt behöver du först välja lönebetalningar eller alla inkomstbetalningar. Du kan öppna observerade summor nedan.',
                       _income_options(context))
    if any(term in text for term in ('average', 'keski', 'genomsnitt')):
        if concept in {'All spending', 'All outflows'}:
            return clarify(context, 'average_definition',
                           'Which category should I average? A purchase average and an average of bills and transfers have different denominators.',
                           'Minkä luokan keskiarvon lasken? Ostosten, laskujen ja siirtojen keskiarvoilla on eri jakajat.',
                           'Vilken kategori ska jag räkna genomsnittet för? Köp, räkningar och överföringar har olika nämnare.',
                           ('What was my average restaurant purchase?', 'What was my average grocery purchase?'))
        if not any(term in text for term in ('purchase', 'transaction', 'per visit', 'per payment', 'ostos', 'tapahtuma', 'per köp', 'transaktion')):
            return clarify(context, 'average_definition',
                           'Do you mean the average per purchase, or the average per calendar month? Please choose a definition before I calculate it.',
                           'Tarkoitatko keskiarvoa ostosta vai kalenterikuukautta kohti? Valitse määritelmä ennen laskentaa.',
                           'Menar du genomsnitt per köp eller per kalendermånad? Välj en definition innan jag räknar.',
                           (f'What was my average {concept.lower()} purchase in {start[:7]}?',))
        metric = 'average_outflow'
    elif re.search(r'\b(?:how many|count|montako|kuinka monta|hur många)\b', text):
        metric = 'transaction_count'
    elif any(term in text for term in ('largest', 'biggest', 'suurin', 'största')):
        metric = 'largest_outflow'
    scope = {key: context.get(key) for key in ('customer_id', 'account_id')}
    scope.update(concept=concept, metric=metric, start=start, end=end,
                 reference_date=context.get('reference_date', month_bounds(context['period'])[1]), filters=filters)
    params = dict(filters)
    if start == month_bounds(start[:7])[0] and end == month_bounds(start[:7])[1]:
        params['period'] = start[:7]
    else:
        params.update(start=start, end=end)
    return {'intent': 'transaction_statistics', 'parameters': params, 'query_scope': scope,
            'needs_clarification': False, 'clarification_question': None,
            'clarification_code': None, 'clarification_options': []}
