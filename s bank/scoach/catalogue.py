"""Question catalogue and answer cards (V4 lane C).

The catalogue is the offline answer contract: every question has a stable id,
EN/FI/SV wording, read-only tool calls through ``agent_tools.dispatch`` and a
card builder. Free text is only *ranked* against the catalogue
(``match_message``); it is never answered by guessing. The AI path reuses the
same builders (``cards_for_tool_calls``), so AI and offline answers look alike.

Card shape (all text localized here, money formatted per locale)::

    {question_id, title, headline:{label, value_text, value_cents|None},
     lines:[str] (at most 4), chart:{kind, data}|None, caveat:str|None,
     evidence:[{label, query}], followups:[{id, text, params?}] (2-3),
     pickers:[{name, kind, value, options?}], params_used:{}, actions:[...]}

Chart data: ``bars``/``trend``/``ring`` -> list of {label, value_cents,
value_text}; ``progress`` -> {value_cents, target_cents, percent, value_text,
target_text}. Picker options are lists of {value, label}.
"""
import math
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import money_profile
from .agent_tools import ToolContext, dispatch
from .labels import category_labels
from .ledger import month_bounds, shift_month

LOCALES = ('en', 'fi', 'sv')


def _t(en, fi, sv):
    return {'en': en, 'fi': fi, 'sv': sv}


# --------------------------------------------------------------------------- formatting

def money(cents, locale):
    """Integer cents as text: EN '€1,138.27', FI/SV '1 138,27 €' (minus sign U+2212)."""
    sign = '−' if cents < 0 else ''
    whole, part = divmod(abs(int(cents)), 100)
    if locale == 'en':
        return sign + '€' + format(whole, ',') + '.' + format(part, '02d')
    return sign + format(whole, ',').replace(',', ' ') + ',' + format(part, '02d') + ' €'


def percent(value, locale, signed=False):
    """'9.6' -> EN '9.6%', FI/SV '9,6 %'."""
    number = Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    text = format(abs(number), 'f')
    if text.endswith('.0'):
        text = text[:-2]
    sign = ('+' if number > 0 else '−' if number < 0 else '') if signed else ('−' if number < 0 else '')
    if locale == 'en':
        return sign + text + '%'
    return sign + text.replace('.', ',') + ' %'


def _share(part, whole):
    return Decimal(part) * 100 / Decimal(whole) if whole else Decimal(0)


_MONTHS = {
    'en': ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'),
    'fi': ('tammikuu', 'helmikuu', 'maaliskuu', 'huhtikuu', 'toukokuu', 'kesäkuu', 'heinäkuu', 'elokuu', 'syyskuu', 'lokakuu', 'marraskuu', 'joulukuu'),
    'sv': ('januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober', 'november', 'december'),
}
_SHORT = {
    'en': ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'),
    'sv': ('jan.', 'feb.', 'mars', 'apr.', 'maj', 'juni', 'juli', 'aug.', 'sep.', 'okt.', 'nov.', 'dec.'),
}


def month_label(month, locale, case='nom'):
    """'2026-09' -> EN 'September 2026'; FI 'syyskuu 2026' / 'syyskuussa 2026' (case='in') /
    'syyskuuhun 2026' (case='ill'); SV 'september 2026'."""
    year, number = int(month[:4]), int(month[5:7])
    name = _MONTHS[locale][number - 1]
    if locale == 'fi':
        name += {'nom': '', 'in': 'ssa', 'ill': 'hun', 'gen': 'n'}[case]
    return '%s %d' % (name, year)


def date_label(iso, locale, year=True):
    """'2026-10-22' -> EN '22 Oct 2026', FI '22.10.2026', SV '22 okt. 2026'."""
    day = date.fromisoformat(iso)
    if locale == 'fi':
        return '%d.%d.%s' % (day.day, day.month, day.year if year else '')
    text = '%d %s' % (day.day, _SHORT[locale][day.month - 1])
    return text + (' %d' % day.year if year else '')


def period_label(start, end, locale):
    if (start, end) == month_bounds(start[:7]):
        return month_label(start[:7], locale)
    return date_label(start, locale) + ' – ' + date_label(end, locale)


def join(items, locale):
    items = [item for item in items if item]
    if len(items) < 2:
        return ''.join(items)
    word = {'en': ' and ', 'fi': ' ja ', 'sv': ' och '}[locale]
    return ', '.join(items[:-1]) + word + items[-1]


_WEEKDAYS = {
    'en': ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'),
    'fi': ('maanantai', 'tiistai', 'keskiviikko', 'torstai', 'perjantai', 'lauantai', 'sunnuntai'),
    'sv': ('måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag', 'söndag'),
}
_WEEKDAYS_PLURAL = {
    'en': ('Mondays', 'Tuesdays', 'Wednesdays', 'Thursdays', 'Fridays', 'Saturdays', 'Sundays'),
    'fi': ('maanantaisin', 'tiistaisin', 'keskiviikkoisin', 'torstaisin', 'perjantaisin', 'lauantaisin', 'sunnuntaisin'),
    'sv': ('måndagar', 'tisdagar', 'onsdagar', 'torsdagar', 'fredagar', 'lördagar', 'söndagar'),
}

# One category table for the whole server (scoach/labels.py), so coach cards, the payday
# plan and Spending use the same names.
CATEGORY_LABELS = {name: category_labels(name) for name in
                   ('Housing', 'Utilities', 'Groceries', 'Transportation', 'Restaurants', 'Health',
                    'Home & Tech', 'Lifestyle', 'Entertainment', 'Travel')}
SPENDING_CATEGORIES = ('Housing', 'Utilities', 'Groceries', 'Transportation', 'Restaurants', 'Health',
                       'Home & Tech', 'Lifestyle', 'Entertainment', 'Travel')
CUTTABLE = ('Restaurants', 'Entertainment', 'Lifestyle', 'Travel')
PEER_CATEGORIES = ('Groceries', 'Restaurants', 'Lifestyle', 'Health', 'Transportation', 'Entertainment')
BASKETS = {
    'fixed_obligation': _t('Must-pays', 'Pakolliset kuukausimenot', 'Fasta måsten'),
    'flexible_essential': _t('Surprise must-pays', 'Yllättävät pakolliset menot', 'Oväntade måsten'),
    'discretionary': _t('Little leaks', 'Arjen pikkumenot', 'Vardagens småutgifter'),
}
BASKET_HELP = {
    'fixed_obligation': _t('bills that come every month, like rent and electricity',
                           'joka kuukausi tulevat laskut, kuten vuokra ja sähkö',
                           'räkningar som kommer varje månad, som hyra och el'),
    'flexible_essential': _t('necessary but hard to predict, like the dentist',
                             'välttämättömät mutta vaikeasti ennakoitavat, kuten hammaslääkäri',
                             'nödvändigt men svårt att förutse, som tandläkaren'),
    'discretionary': _t('small everyday choices that add up, like coffee and takeaway',
                        'pienet arjen valinnat, jotka kertyvät, kuten kahvit ja noutoruoka',
                        'små vardagsval som blir mycket, som kaffe och hämtmat'),
}


def category_label(category, locale):
    return CATEGORY_LABELS.get(category, {}).get(locale, category)


# --------------------------------------------------------------------------- spending plan adapter

def _plan(conn, customer_id, as_of, profile=None):
    """The one spending plan for safe-to-spend/save cards.

    Uses ``forecast.spending_plan`` when lane N's version is present; until then
    ``safe_until_payday`` is reshaped to the same contract (adapter below).
    Returns the spending_plan dict plus ``can_save_cents`` when known.
    """
    from . import forecast
    if hasattr(forecast, 'spending_plan'):
        plan = forecast.spending_plan(conn, customer_id, as_of=as_of, profile=profile)
        plan.setdefault('can_save_cents', plan.get('extra_cents', 0))
        return plan
    return _plan_from_safe_until_payday(forecast.safe_until_payday(conn, customer_id, as_of=as_of, profile=profile))


def _plan_from_safe_until_payday(raw):
    held = []
    for item in raw['committed_items']:
        kind = 'bill' if item['source'] == 'recurring' else 'loan' if item['transaction_type'] == 'debt' else 'goal'
        held.append({'kind': kind, 'label': item['label'], 'amount_cents': item['amount_cents'], 'date': item['date']})
    if raw['planned_saving_cents']:
        held.append({'kind': 'goal', 'label': 'Saving target', 'amount_cents': raw['planned_saving_cents'], 'date': None})
    held.append({'kind': 'reserve', 'label': 'Reserve', 'amount_cents': raw['reserve_floor_cents'], 'date': None})
    return {
        'as_of': raw['reference_date'], 'balance_cents': raw['starting_balance_cents'],
        'next_payday': raw['next_payday'], 'days_to_payday': raw['days_until_payday'],
        'held_back': held, 'everyday_cents': 0, 'buffer_cents': 0,
        'reserve_floor_cents': raw['reserve_floor_cents'], 'free_cents': raw['spendable_cents'],
        'per_day_cents': raw['per_day_cents'], 'extra_cents': 0,
        'shortfall_cents': raw['shortfall_cents'],
        'can_save_cents': raw['safe_to_save_cents'] if raw['safe_to_save_available'] else 0,
        'steady_mode': raw['steady_mode'],
        'basis': {'source': 'safe_until_payday', 'payday_source': raw['payday_source']},
        'evidence': {'transaction_refs': raw['transaction_refs']},
    }


# --------------------------------------------------------------------------- personal context

_LIFE_STAGES = {
    'student': _t('studying', 'opiskelen', 'studerar'),
    'working': _t('working', 'olen töissä', 'arbetar'),
    'self_employed': _t('self-employed', 'yrittäjä', 'egenföretagare'),
    'between_jobs': _t('between jobs', 'töiden välissä', 'mellan jobb'),
    'parental_leave': _t('on parental leave', 'vanhempainvapaalla', 'föräldraledig'),
    'retired': _t('retired', 'eläkkeellä', 'pensionär'),
}
_EVENTS = {
    'job_loss': _t('lost your job', 'työn menetys', 'förlorat jobbet'),
    'income_drop': _t('lower income', 'tulot pienenivät', 'lägre inkomst'),
    'large_loss': _t('a large unexpected cost', 'iso yllättävä meno', 'en stor oväntad kostnad'),
    'new_child': _t('a new baby', 'vauva perheeseen', 'nytt barn'),
    'moving': _t('moving home', 'muutto', 'flytt'),
    'other': _t('a life change', 'elämänmuutos', 'en livsförändring'),
}
_DEBTS = {
    'mortgage': _t('mortgage', 'asuntolaina', 'bolån'), 'student_loan': _t('student loan', 'opintolaina', 'studielån'),
    'car_loan': _t('car loan', 'autolaina', 'billån'), 'consumer_credit': _t('consumer credit', 'kulutusluotto', 'konsumtionskredit'),
    'other': _t('loan', 'laina', 'lån'),
}


class Personal:
    """What the customer told the coach, read once per card from the money profile."""

    def __init__(self, conn, customer_id, as_of, locale):
        self.locale = locale
        try:
            self.profile = money_profile.get_profile(conn, customer_id, as_of)
        except ValueError:
            self.profile = {'empty': True, 'by_key': {}, 'mode': 'normal', 'entries': []}
        by_key = self.profile.get('by_key', {})

        def single(key):
            entry = by_key.get(key)
            return entry['value'] if isinstance(entry, dict) else None

        def many(key):
            found = by_key.get(key) or []
            return [entry['value'] for entry in (found if isinstance(found, list) else [found])]
        self.empty = self.profile.get('empty', True)
        self.steady = self.profile.get('mode') == 'steady'
        self.steady_type = (self.profile.get('mode_reason') or {}).get('type')
        self.life_stage = single('life_stage')
        self.saving_target = single('saving_rate_target_pct')
        self.buffer_months = single('emergency_fund_target_months')
        self.protected = [item for item in (single('protected_categories') or [])]
        self.style = single('coaching_style')
        self.household = single('household')
        self.upcoming = sorted(many('upcoming'), key=lambda value: value['month'])
        self.events = [value for value in many('life_event') if not value.get('ended')]
        self.debts = many('debts')
        self.tax = many('tax')
        self.used = []

    @property
    def gentle(self):
        return self.steady or self.style == 'gentle'

    def is_protected(self, category):
        labels = {category.casefold()} | {label.casefold() for label in CATEGORY_LABELS.get(category, {}).values()}
        return any(item.casefold() in labels for item in self.protected)

    def use(self, *keys):
        """Mark profile facts as used by this card (rendered by ``line``)."""
        for key in keys:
            if key not in self.used:
                self.used.append(key)

    def _fact(self, key):
        locale = self.locale
        if key == 'life_stage' and self.life_stage:
            return _LIFE_STAGES[self.life_stage][locale]
        if key == 'steady' and self.steady:
            event = _EVENTS.get(self.steady_type or 'other', _EVENTS['other'])[locale]
            return _t('steady mode (%s)', 'rauhallinen tahti (%s)', 'lugnt tempo (%s)')[locale] % event
        if key == 'events':
            events = [value for value in self.events if not (self.steady and value['type'] == self.steady_type)]
            return ', '.join(_EVENTS[value['type']][locale] for value in events[:2]) or None
        if key == 'saving_target' and self.saving_target:
            return _t('saving target %s of income', 'säästötavoite %s tuloista', 'sparmål %s av inkomsten')[locale] % percent(self.saving_target, locale)
        if key == 'buffer_months' and self.buffer_months:
            return _t('buffer goal %s months', 'hätävaratavoite %s kk', 'mål för sparkudden %s månader')[locale] % _number(self.buffer_months, locale)
        if key == 'protected' and self.protected:
            names = join([category_label(item, locale) for item in self.protected], locale)
            return _t('no cuts to %s', 'ei leikkauksia: %s', 'inga nedskärningar i %s')[locale] % names
        if key == 'upcoming' and self.upcoming:
            first = self.upcoming[0]
            return _t('coming up: %s (%s)', 'tulossa: %s (%s)', 'på gång: %s (%s)')[locale] % (first['what'], month_label(first['month'], locale))
        if key == 'debts' and self.debts:
            total = sum(item['monthly_payment_cents'] for item in self.debts)
            kinds = join([_DEBTS[item['type']][locale] for item in self.debts[:2]], locale)
            return _t('%s %s a month', '%s %s kuussa', '%s %s i månaden')[locale] % (kinds, money(total, locale))
        if key == 'household' and self.household:
            adults, children = self.household['adults'], self.household['children']
            if locale == 'en':
                return 'household of %d adult%s and %d child%s' % (adults, '' if adults == 1 else 's', children, '' if children == 1 else 'ren')
            if locale == 'fi':
                return 'kotitalous: %d %s, %d %s' % (adults, 'aikuinen' if adults == 1 else 'aikuista', children, 'lapsi' if children == 1 else 'lasta')
            return 'hushåll: %d %s, %d %s' % (adults, 'vuxen' if adults == 1 else 'vuxna', children, 'barn')
        if key == 'style' and self.style:
            return _t('%s coaching', 'valmennustyyli: %s', '%s coachning')[locale] % (
                {'gentle': _t('gentle', 'lempeä', 'varsam'), 'direct': _t('direct', 'suora', 'rak')}[self.style][locale])
        return None

    def facts(self, keys=None):
        return [fact for fact in (self._fact(key) for key in (keys or self.used)) if fact]

    def line(self):
        facts = self.facts()
        if not facts:
            return None
        prefix = _t('Using what you told me: ', 'Käytin kertomaasi: ', 'Jag utgick från det du berättat: ')[self.locale]
        return prefix + '; '.join(facts) + '.'


def _number(value, locale):
    text = format(Decimal(str(value)).normalize(), 'f')
    return text if locale == 'en' else text.replace('.', ',')


# --------------------------------------------------------------------------- environment

class CardEnv:
    """Everything a builder needs: dispatch wrapper, locale helpers and profile."""

    def __init__(self, conn, customer_id, month, locale, *, message=''):
        if locale not in LOCALES:
            raise ValueError('locale must be en, fi, or sv')
        self.conn, self.customer_id, self.month, self.locale = conn, customer_id, month, locale
        self.ctx = ToolContext(conn, customer_id, month, message=message)
        self.reference_date = self.ctx.reference_date
        self.scope = self.ctx.scope
        self.personal = Personal(conn, customer_id, self.reference_date, locale)
        self.evidence = []

    def tr(self, texts, *args, **kwargs):
        text = texts[self.locale]
        return text.format(*args, **kwargs) if args or kwargs else text

    def money(self, cents):
        return money(cents, self.locale)

    def pct(self, value, signed=False):
        return percent(value, self.locale, signed)

    def month_label(self, month, case='nom'):
        return month_label(month, self.locale, case)

    def date(self, iso, year=True):
        return date_label(iso, self.locale, year)

    def cat(self, category):
        return category_label(category, self.locale)

    def call(self, name, args=None, label=None):
        result = dispatch(self.conn, self.customer_id, self.ctx, name, dict(args or {}))
        if label:
            record = self.ctx.evidence.get(result.get('evidence_id'))
            if record and record.get('query'):
                self.add_evidence(label, record['query'])
        return result

    def add_evidence(self, label, query):
        query = {key: value for key, value in query.items() if value is not None}
        if not any(item['query'] == query for item in self.evidence) and len(self.evidence) < 4:
            self.evidence.append({'label': label, 'query': query})

    def complete_month(self):
        """Selected month, or the latest complete month when the selected one is still running."""
        from .analytics import latest_complete_month
        latest = latest_complete_month(self.conn, self.customer_id)
        return self.month if self.month <= latest else latest

    def months_back(self, end_month, count):
        first = max(shift_month(end_month, 1 - count), self.scope['observed_start'][:7])
        months, month = [], first
        while month <= end_month:
            months.append(month)
            month = shift_month(month, 1)
        return months

    def month_period(self, month):
        start, end = month_bounds(month)
        return max(start, self.scope['observed_start']), min(end, self.scope['observed_end'])

    def plan(self):
        from .api import planning_profile
        return _plan(self.conn, self.customer_id, self.reference_date,
                     planning_profile(self.conn, self.customer_id, self.reference_date))

    def spending_categories(self, *, cuttable=False):
        rows = self.conn.execute(
            "SELECT DISTINCT category FROM transactions WHERE customer_id=? AND amount_cents<0", (self.customer_id,)).fetchall()
        present = {row[0] for row in rows}
        allowed = CUTTABLE if cuttable else SPENDING_CATEGORIES
        return [category for category in allowed if category in present]

    def category_options(self, categories):
        return [{'value': category, 'label': self.cat(category)} for category in categories]

    def month_options(self):
        end = self.scope['observed_end'][:7]
        return [{'value': month, 'label': self.month_label(month)} for month in reversed(self.months_back(end, 12))]


# --------------------------------------------------------------------------- question definitions

GROUPS = (
    ('overview', _t('Money overview', 'Rahojen yleiskuva', 'Översikt över pengarna')),
    ('spending', _t('Spending', 'Kulutus', 'Utgifter')),
    ('room', _t('Safe to spend & save', 'Käyttövara ja säästäminen', 'Att spendera och spara')),
    ('goals', _t('Goals', 'Tavoitteet', 'Mål')),
    ('bills', _t('Bills & coming up', 'Laskut ja tulevat menot', 'Räkningar och det som väntar')),
    ('me', _t('My profile & life events', 'Profiilini ja elämäntilanne', 'Min profil och livshändelser')),
    ('extras', _t('Compare, taxes & year', 'Vertailu, verot ja vuosi', 'Jämförelse, skatter och året')),
)


class Question:
    def __init__(self, qid, group, text, builder, *, pickers=(), required=(), followups=(), keywords=(), tools=()):
        self.id, self.group, self.text, self.builder = qid, group, text, builder
        self.pickers, self.required, self.followups = tuple(pickers), tuple(required), tuple(followups)
        self.keywords, self.tools = tuple(keywords), tuple(tools)


QUESTIONS = {}


def _question(qid, group, text, **options):
    def register(builder):
        QUESTIONS[qid] = Question(qid, group, text, builder, **options)
        return builder
    return register


STARTERS = ('money.where', 'spend.spender', 'room.week', 'room.save_more', 'me.peers', 'extra.baskets')
BRIEF_QUESTIONS = ('money.where', 'spend.spender', 'room.week', 'room.save_more')

_ESTIMATE = _t('An estimate from your past patterns, not a guarantee. Income counts only once it arrives.',
               'Arvio aiempien tapahtumiesi perusteella, ei lupaus. Tulot huomioidaan vasta, kun ne ovat tilillä.',
               'En uppskattning utifrån dina tidigare mönster, ingen garanti. Inkomster räknas först när de kommit in.')


def _card(env, qid, title, label, value_text, value_cents=None, *, lines=(), chart=None, caveat=None,
          pickers=(), params=None, actions=(), personal=True):
    question = QUESTIONS[qid]
    lines = [_tidy(line) for line in lines if line]
    title = _tidy(title)
    profile_note = env.personal.line() if personal else None
    # The "Using what you told me" sentence lives only in profile_note (the card shows it once, separately).
    followups = []
    items = list(question.followups)
    if env.personal.steady:
        # V5 fix (lane CO): steady mode never offers a saving suggestion; calmer questions take their place.
        items = [item for item in items if (item if isinstance(item, str) else item[0]) not in _STEADY_HIDDEN]
        taken = {qid} | {item if isinstance(item, str) else item[0] for item in items}
        items += [fid for fid in _STEADY_FOLLOWUPS if fid not in taken][:max(0, 3 - len(items))]
    for item in items:
        fid, fparams = (item, None) if isinstance(item, str) else item
        entry = {'id': fid, 'text': QUESTIONS[fid].text[env.locale]}
        if fparams:
            entry['params'] = dict(fparams)
        followups.append(entry)
    return {
        'question_id': qid, 'title': title,
        'headline': {'label': label, 'value_text': value_text, 'value_cents': value_cents},
        'lines': lines[:4], 'chart': chart, 'caveat': caveat, 'evidence': list(env.evidence),
        'followups': followups[:3], 'pickers': list(pickers), 'params_used': dict(params or {}),
        'actions': list(actions), 'profile_note': profile_note,
    }


# Saving suggestions that steady mode never offers as a next question, and the calm questions offered instead.
_STEADY_HIDDEN = frozenset({'room.save_now', 'room.save_more', 'room.cut', 'goals.new'})
_STEADY_FOLLOWUPS = ('bills.upcoming', 'room.payday', 'goals.buffer', 'money.where')


def _tidy(text):
    text = text[:1].upper() + text[1:]
    while text.endswith('..'):
        text = text[:-1]
    return text


def count_text(count, locale, kind='payment'):
    forms = {'payment': (('payment', 'payments'), ('maksu', 'maksua'), ('betalning', 'betalningar')),
             'purchase': (('purchase', 'purchases'), ('ostos', 'ostosta'), ('köp', 'köp'))}[kind]
    one, many = forms[LOCALES.index(locale)]
    return '%d %s' % (count, one if count == 1 else many)


def _bars(env, rows):
    return [{'label': label, 'value_cents': cents, 'value_text': env.money(cents)} for label, cents in rows]


def _month_picker(env, value):
    return {'name': 'month', 'kind': 'month', 'value': value, 'options': env.month_options()}


def _category_picker(env, value, categories):
    return {'name': 'category', 'kind': 'category', 'value': value, 'options': env.category_options(categories)}


def _percent_picker(value):
    return {'name': 'percent', 'kind': 'percent', 'value': value,
            'options': [{'value': option, 'label': str(option) + ' %'} for option in (10, 20, 30)]}


def _param_month(env, params):
    month = params.get('month') or env.month
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise ValueError('month must use YYYY-MM')
    if not env.scope['observed_start'][:7] <= month <= env.scope['observed_end'][:7]:
        raise ValueError('month is outside observed history')
    return month


def _param_category(params, allowed, default):
    category = params.get('category') or default
    if category not in allowed:
        raise ValueError('Unknown or unsupported category')
    return category


def _param_percent(params, default):
    value = params.get('percent', default)
    try:
        number = Decimal(str(value))
    except Exception:
        raise ValueError('percent must be a number') from None
    if not number.is_finite() or not 0 < number <= 100:
        raise ValueError('percent must be between 0 and 100')
    return int(number) if number == number.to_integral() else float(number)


# ---- Money overview -------------------------------------------------------------------

@_question('money.where', 'overview', _t('Where did my money go this month?', 'Mihin rahani menivät tässä kuussa?',
                                         'Vart tog mina pengar vägen den här månaden?'),
           pickers=('month',), followups=('money.category', 'spend.leaks', 'money.compare'),
           keywords=('where go went spend money', 'mihin menivät meni raha kulut', 'vart pengar tog vägen gick'),
           tools=('get_overview',))
def _money_where(env, params):
    month = _param_month(env, params)
    start, end = env.month_period(month)
    overview = env.call('get_overview', {'month': month}, env.tr(_t('Spending in {0}', 'Kulutus: {0}', 'Utgifter i {0}'), env.month_label(month)))
    spent = overview['consumption_cents']
    lines = []
    previous = shift_month(month, -1)
    if previous >= env.scope['observed_start'][:7]:
        try:
            before = env.call('get_overview', {'month': previous})['consumption_cents']
            delta = spent - before
            if delta:
                lines.append(env.tr(_t('{0} {1} than in {2} ({3}).', '{0} {1} kuin {2} ({3}).', '{0} {1} än i {2} ({3}).'),
                                    env.money(abs(delta)), env.tr(_t('more', 'enemmän', 'mer') if delta > 0 else _t('less', 'vähemmän', 'mindre')),
                                    env.month_label(previous, 'in'), env.money(before)))
        except ValueError:
            pass
    tops = [row for row in overview['top_categories'] if row['total_cents'] > 0]
    if tops:
        lines.append(env.tr(_t('Biggest: {0}.', 'Suurimmat: {0}.', 'Störst: {0}.'),
                            join(['%s %s' % (env.cat(row['category']), env.money(row['total_cents'])) for row in tops[:3]], env.locale)))
    baskets = {row['role']: row['amount_cents'] for row in overview['baskets']}
    lines.append(' · '.join('%s %s' % (env.tr(BASKETS[role]), env.money(baskets.get(role, 0))) for role in BASKETS))
    if overview['committed_saving_transfers_cents']:
        lines.append(env.tr(_t('You also moved {0} to savings; that is not counted as spending.',
                               'Lisäksi siirsit säästöön {0}; sitä ei lasketa kulutukseksi.',
                               'Du flyttade dessutom {0} till sparande; det räknas inte som utgifter.'),
                            env.money(overview['committed_saving_transfers_cents'])))
    if not spent:
        lines = [env.tr(_t('No spending is recorded for {0}.', 'Kulutusta ei ole kirjattu: {0}.', 'Inga utgifter har registrerats för {0}.'), env.month_label(month))]
    chart = {'kind': 'bars', 'data': _bars(env, [(env.cat(row['category']), row['total_cents']) for row in tops[:5]])} if tops else None
    return _card(env, 'money.where',
                 env.tr(_t('Where your money went in {0}', 'Mihin rahasi menivät {0}', 'Vart pengarna tog vägen i {0}'),
                        env.month_label(month, 'in')),
                 env.tr(_t('Spent in {0}', 'Menot {0}', 'Utgifter i {0}'), env.month_label(month, 'in')),
                 env.money(spent), spent, lines=lines, chart=chart,
                 caveat=env.tr(_t('Savings transfers and income are kept separate from spending.',
                                  'Säästösiirrot ja tulot on erotettu kulutuksesta.',
                                  'Sparöverföringar och inkomster hålls isär från utgifterna.')) if end < month_bounds(month)[1] else None,
                 pickers=[_month_picker(env, month)], params={'month': month})


@_question('money.category', 'overview', _t('How much did I spend on one category?', 'Paljonko käytin yhteen menoluokkaan?',
                                            'Hur mycket spenderade jag på en kategori?'),
           pickers=('category', 'month'), required=('category',), followups=('room.cut', 'me.peers', 'money.trend'),
           keywords=('how much spend spent on category', 'paljonko käytin kulutin', 'hur mycket spenderade lade'),
           tools=('spending_total',))
def _money_category(env, params):
    month = _param_month(env, params)
    categories = env.spending_categories()
    start, end = env.month_period(month)
    default = categories[0] if categories else 'Groceries'
    if not params.get('category'):
        try:
            tops = env.call('get_overview', {'month': month})['top_categories']
            default = tops[0]['category'] if tops else default
        except ValueError:
            pass
    category = _param_category(params, categories, default)
    label = env.tr(_t('{0} in {1}', '{0}: {1}', '{0} i {1}'), env.cat(category), env.month_label(month))
    result = env.call('spending_total', {'start': start, 'end': end, 'category': category}, label)
    total, count = result['total_cents'], result['count']
    lines = []
    if count:
        lines.append(env.tr(_t('{0}, on average {1}.', '{0}, keskimäärin {1}.', '{0}, i snitt {1}.'),
                            count_text(count, env.locale), env.money(result['average_outflow_cents'])))
        largest = result.get('largest_outflow')
        if largest:
            lines.append(env.tr(_t('Largest: {0} on {1}.', 'Suurin: {0} ({1}).', 'Störst: {0} den {1}.'),
                                env.money(largest['amount_cents']), env.date(largest['date'])))
    else:
        lines.append(env.tr(_t('No payments in this category in {0}.', 'Tässä luokassa ei ollut maksuja {0}.', 'Inga betalningar i den här kategorin i {0}.'),
                            env.month_label(month, 'in')))
    chart = None
    try:
        trend = env.call('monthly_trend', {'months': 6, 'category': category, 'end_month': month})
        points = [row for row in trend['months'] if row.get('total_cents') is not None]
        if len(points) >= 2:
            chart = {'kind': 'trend', 'data': [{'label': month_label(row['month'], env.locale),
                                                'value_cents': row['total_cents'], 'value_text': env.money(row['total_cents'])} for row in points]}
            average = sum(row['total_cents'] for row in points) // len(points)
            lines.append(env.tr(_t('Your monthly average over {0} months: {1}.', 'Kuukausikeskiarvosi {0} kuukauden ajalta: {1}.',
                                   'Ditt månadssnitt för {0} månader: {1}.'), len(points), env.money(average)))
    except ValueError:
        pass
    if env.personal.is_protected(category):
        env.personal.use('protected')
    return _card(env, 'money.category', label, env.tr(_t('Spent', 'Käytetty', 'Spenderat')), env.money(total), total,
                 lines=lines, chart=chart, pickers=[_category_picker(env, category, categories), _month_picker(env, month)],
                 params={'category': category, 'month': month})


@_question('money.compare', 'overview', _t('Compare this month with last month', 'Vertaa tätä kuuta edelliseen', 'Jämför den här månaden med förra'),
           pickers=('month',), followups=('money.where', 'money.trend', 'spend.leaks'),
           keywords=('compare last month previous change', 'vertaa edellinen viime kuu', 'jämför förra månaden'),
           tools=('compare_periods',))
def _money_compare(env, params):
    month = _param_month(env, params)
    previous = shift_month(month, -1)
    if previous < env.scope['observed_start'][:7]:
        raise ValueError('No earlier month to compare with')
    start, end = env.month_period(month)
    pstart, pend = env.month_period(previous)
    result = env.call('compare_periods', {'start': start, 'end': end, 'comparison_start': pstart, 'comparison_end': pend},
                      env.tr(_t('Spending in {0}', 'Kulutus: {0}', 'Utgifter i {0}'), env.month_label(month)))
    env.add_evidence(env.tr(_t('Spending in {0}', 'Kulutus: {0}', 'Utgifter i {0}'), env.month_label(previous)),
                     {'start': pstart, 'end': pend, 'consumption_only': 'true'})
    now, before = result['current']['outflow_total_cents'], result['comparison']['outflow_total_cents']
    delta = now - before
    value = env.money(delta) if delta < 0 else '+' + env.money(delta)
    if result.get('percent_change') is not None:
        value += ' (%s)' % env.pct(result['percent_change'], signed=True)
    lines = [env.tr(_t('{0}: {1} in {2}.', '{0}: {1}, {2}.', '{0}: {1} på {2}.'),
                    env.month_label(month), env.money(now), count_text(result['current']['outflow_count'], env.locale)),
             env.tr(_t('{0}: {1} in {2}.', '{0}: {1}, {2}.', '{0}: {1} på {2}.'),
                    env.month_label(previous), env.money(before), count_text(result['comparison']['outflow_count'], env.locale))]
    try:
        now_rows = env.call('explore', {'start': start, 'end': end, 'group_by': 'category', 'top': 31})['rows']
        before_rows = env.call('explore', {'start': pstart, 'end': pend, 'group_by': 'category', 'top': 31})['rows']
        a = {row['label']: row['value_cents'] for row in now_rows}
        b = {row['label']: row['value_cents'] for row in before_rows}
        changes = sorted(((a.get(key, 0) - b.get(key, 0), key) for key in set(a) | set(b)), key=lambda item: item[0])
        if changes and changes[-1][0] > 0:
            lines.append(env.tr(_t('Biggest rise: {0} +{1}.', 'Eniten kasvoi: {0} +{1}.', 'Störst ökning: {0} +{1}.'),
                                env.cat(changes[-1][1]), env.money(changes[-1][0])))
        if changes and changes[0][0] < 0:
            lines.append(env.tr(_t('Biggest drop: {0} {1}.', 'Eniten laski: {0} {1}.', 'Störst minskning: {0} {1}.'),
                                env.cat(changes[0][1]), env.money(changes[0][0])))
    except ValueError:
        pass
    chart = {'kind': 'bars', 'data': _bars(env, [(env.month_label(previous), before), (env.month_label(month), now)])}
    return _card(env, 'money.compare',
                 env.tr(_t('{0} compared with {1}', '{0} verrattuna {1}', '{0} jämfört med {1}'),
                        env.month_label(month), env.month_label(previous, 'ill')),
                 env.tr(_t('Change in spending', 'Muutos kulutuksessa', 'Förändring i utgifter')), value, delta,
                 lines=lines, chart=chart, pickers=[_month_picker(env, month)], params={'month': month})


@_question('money.trend', 'overview', _t('How has my spending changed lately?', 'Miten kulutukseni on muuttunut viime aikoina?',
                                         'Hur har mina utgifter förändrats på sistone?'),
           pickers=('category', 'month'), followups=('money.compare', 'spend.leaks', 'money.inout'),
           keywords=('trend changed lately months over time history', 'muuttunut kehitys kuukausien', 'förändrats utveckling månader'),
           tools=('monthly_trend',))
def _money_trend(env, params):
    month = _param_month(env, params)
    categories = env.spending_categories()
    category = params.get('category') or None
    if category is not None:
        _param_category(params, categories, None)
    args = {'months': 6, 'end_month': month, **({'category': category} if category else {})}
    label = env.tr(_t('Spending, last 6 months', 'Kulutus, 6 kk', 'Utgifter, 6 månader'))
    trend = env.call('monthly_trend', args, label)
    points = [row for row in trend['months'] if row.get('total_cents') is not None]
    if not points:
        raise ValueError('No spending history')
    average = sum(row['total_cents'] for row in points) // len(points)
    high = max(points, key=lambda row: row['total_cents'])
    low = min(points, key=lambda row: row['total_cents'])
    latest = points[-1]
    diff = latest['total_cents'] - average
    lines = [env.tr(_t('Highest: {0} ({1}). Lowest: {2} ({3}).', 'Suurin: {0} ({1}). Pienin: {2} ({3}).', 'Högst: {0} ({1}). Lägst: {2} ({3}).'),
                    env.month_label(high['month']), env.money(high['total_cents']), env.month_label(low['month']), env.money(low['total_cents'])),
             env.tr(_t('{0} was {1} {2} than your average.', '{0}: {1} {2} kuin keskimäärin.', '{0} var {1} {2} än ditt snitt.'),
                    env.month_label(latest['month']), env.money(abs(diff)),
                    env.tr(_t('more', 'enemmän', 'mer') if diff > 0 else _t('less', 'vähemmän', 'mindre')))]
    title = env.tr(_t('Your spending over {0} months', 'Kulutuksesi {0} kuukauden ajalta', 'Dina utgifter under {0} månader'), len(points))
    if category:
        title += ' · ' + env.cat(category)
    chart = {'kind': 'trend', 'data': [{'label': month_label(row['month'], env.locale), 'value_cents': row['total_cents'],
                                        'value_text': env.money(row['total_cents'])} for row in points]}
    return _card(env, 'money.trend', title, env.tr(_t('Average a month', 'Keskimäärin kuukaudessa', 'I snitt per månad')),
                 env.money(average), average, lines=lines, chart=chart,
                 pickers=[_category_picker(env, category, categories), _month_picker(env, month)],
                 params={'category': category, 'month': month})


@_question('money.inout', 'overview', _t('Money in vs money out this year', 'Tulot ja menot tänä vuonna', 'Pengar in och ut i år'),
           pickers=('month',), followups=('extra.year', 'room.save_more', 'money.trend'),
           keywords=('money in out income salary earned year', 'tulot menot palkka vuosi', 'inkomster lön in ut år'),
           tools=('cashflow_summary',))
def _money_inout(env, params):
    month = _param_month(env, params)
    start_month = max(month[:4] + '-01', env.scope['observed_start'][:7])
    result = env.call('cashflow_summary', {'start_month': start_month, 'end_month': month, 'granularity': 'month'},
                      env.tr(_t('Money in and out', 'Tulot ja menot', 'Pengar in och ut')))
    periods = result['periods']
    income = sum(row['income_cents'] for row in periods)
    spent = sum(row['consumption_cents'] for row in periods)
    saved = sum(row['savings_transfers_cents'] for row in periods)
    left = income - spent
    lines = [env.tr(_t('Money in: {0}. Spending: {1}.', 'Tulot: {0}. Kulutus: {1}.', 'In: {0}. Utgifter: {1}.'), env.money(income), env.money(spent)),
             env.tr(_t('Of what was left, you moved {0} to savings or investments.', 'Jäljelle jääneestä siirsit {0} säästöön tai sijoituksiin.',
                       'Av det som blev över flyttade du {0} till sparande eller investeringar.'), env.money(saved)),
             env.tr(_t('Months counted: {0} – {1}.', 'Mukana kuukaudet: {0} – {1}.', 'Månader som räknats: {0} – {1}.'),
                    env.month_label(start_month), env.month_label(month))]
    if any(not row.get('complete', True) for row in periods):
        lines.append(env.tr(_t('The latest month is still incomplete.', 'Viimeisin kuukausi on vielä kesken.', 'Den senaste månaden är inte klar än.')))
    env.personal.use('saving_target')
    chart = {'kind': 'bars', 'data': _bars(env, [(month_label(row['period'], env.locale), row['income_cents'] - row['consumption_cents']) for row in periods][-12:])}
    return _card(env, 'money.inout', env.tr(_t('Money in and out in {0}', 'Tulot ja menot vuonna {0}', 'Pengar in och ut {0}'), month[:4]),
                 env.tr(_t('Left after spending', 'Jäi kulutuksen jälkeen', 'Kvar efter utgifter')), env.money(left), left,
                 lines=lines, chart=chart, pickers=[_month_picker(env, month)], params={'month': month})


# ---- Spending -------------------------------------------------------------------------

def _render_fact(fact, locale):
    from . import spender
    item = dict(fact)
    if 'category' in item:
        item['category'] = category_label(item['category'], locale)
    try:
        return spender._render(item, locale)
    except (KeyError, AttributeError, ValueError):
        return fact.get('text')


@_question('spend.spender', 'spending', _t('What kind of spender am I?', 'Millainen rahankäyttäjä olen?', 'Hurdan är jag med pengar?'),
           followups=('spend.leaks', 'room.save_more', 'spend.weekday'),
           keywords=('what kind spender am i type style careful habits', 'millainen kuluttaja rahankäyttäjä olen tyyli', 'vilken typ spenderare är jag stil hurdan med pengar'),
           tools=('spender_profile',))
def _spend_spender(env, params):
    from .spender import ARCHETYPE_LABELS
    result = env.call('spender_profile', {}, env.tr(_t('Spending, last 6 months', 'Kulutus, 6 kk', 'Utgifter, 6 månader')))
    if not result.get('available'):
        return _card(env, 'spend.spender', env.tr(_t('Your spending style', 'Rahankäyttötyylisi', 'Din utgiftsstil')),
                     env.tr(_t('Not enough history yet', 'Historiaa ei vielä ole tarpeeksi', 'Inte tillräckligt med historik än')), '—',
                     lines=[env.tr(_t('I need at least a few complete months of spending to describe your style.',
                                      'Tarvitsen muutaman täyden kuukauden kulutustiedot, jotta voin kuvata tyyliäsi.',
                                      'Jag behöver några hela månader med utgifter för att beskriva din stil.'))])
    months = result.get('months_used', 6)
    label = ARCHETYPE_LABELS.get(result['archetype'], {}).get(env.locale, result.get('archetype_label', ''))
    reasons = [_render_fact(fact, env.locale) for fact in result.get('why', [])]
    lines = reasons[:2]
    if result.get('strength'):
        lines.append(env.tr(_t('Strength: {0}', 'Vahvuus: {0}', 'Styrka: {0}'), _render_fact(result['strength'], env.locale)))
    if env.personal.steady:
        env.personal.use('steady')
        lines.append(env.tr(_t('For now the focus is on Must-pays and your buffer, not on cutting back.',
                               'Nyt painopiste on pakollisissa menoissa ja turvatyynyssä, ei menojen karsimisessa.',
                               'Just nu ligger fokus på fasta måsten och säkerhetsmarginalen, inte på att dra ner.')))
    elif result.get('watch'):
        watch = result['watch']
        if watch.get('category') and env.personal.is_protected(watch['category']):
            env.personal.use('protected')
        else:
            lines.append(env.tr(_t('Worth a look: {0}', 'Kannattaa katsoa: {0}', 'Värt att titta på: {0}'), _render_fact(watch, env.locale)))
    baskets = (result.get('figures') or {}).get('baskets') or {}
    chart = None
    if baskets:
        chart = {'kind': 'ring', 'data': [{'label': env.tr(BASKETS[role]), 'value_cents': baskets[role]['amount_cents'],
                                           'value_text': env.money(baskets[role]['amount_cents'])} for role in BASKETS if role in baskets]}
    return _card(env, 'spend.spender', env.tr(_t('Your spending style', 'Rahankäyttötyylisi', 'Din utgiftsstil')),
                 env.tr(_t('Last {0} months', 'Viimeiset {0} kuukautta', 'Senaste {0} månaderna'), months), label,
                 lines=lines, chart=chart,
                 caveat=env.tr(_t('Describes your last {0} months, not who you are.', 'Kuvaa viimeisiä {0} kuukauttasi, ei sitä, kuka olet.',
                                  'Beskriver dina senaste {0} månader, inte vem du är.'), months),
                 params={'months': months})


def _leak_rows(env, months):
    """Little leaks (discretionary) spending per category over complete months, biggest first."""
    end_month = env.complete_month()
    window = env.months_back(end_month, months)
    start, end = month_bounds(window[0])[0], month_bounds(window[-1])[1]
    start, end = max(start, env.scope['observed_start']), min(end, env.scope['observed_end'])
    result = env.call('explore', {'start': start, 'end': end, 'group_by': 'category', 'role': 'discretionary', 'top': 31},
                      env.tr(_t('Little leaks, {0}', 'Arjen pikkumenot, {0}', 'Vardagens småutgifter, {0}'), period_label(start, end, env.locale)))
    rows = [row for row in result['rows'] if row['value_cents'] > 0]
    return rows, len(window), result


@_question('spend.leaks', 'spending', _t('What are my Little leaks?', 'Mitkä ovat arjen pikkumenoni?', 'Vilka är mina vardagliga småutgifter?'),
           followups=('room.save_more', 'room.cut', 'spend.weekday'),
           keywords=('little leaks small leak coffee takeaway', 'pikkumenot pienet kahvi', 'småutgifter småköp kaffe läcka'),
           tools=('explore',))
def _spend_leaks(env, params):
    rows, months, result = _leak_rows(env, 3)
    total = sum(row['value_cents'] for row in rows)
    count = sum(row['count'] for row in rows)
    lines = []
    if rows:
        lines.append(env.tr(_t('About {0} a month, {1} in total.', 'Noin {0} kuukaudessa, yhteensä {1}.', 'Ungefär {0} i månaden, {1} totalt.'),
                            env.money(total // months), count_text(count, env.locale, 'purchase')))
        lines.append(env.tr(_t('Biggest: {0}.', 'Suurimmat: {0}.', 'Störst: {0}.'),
                            join(['%s %s' % (env.cat(row['label']), env.money(row['value_cents'])) for row in rows[:3]], env.locale)))
        lines.append(env.tr(_t('Little leaks are small everyday choices that add up: easy to miss, easy to change.',
                               'Arjen pikkumenot ovat pieniä valintoja, jotka kertyvät: helppo ohittaa, helppo muuttaa.',
                               'Vardagens småutgifter är små val som blir mycket tillsammans: lätta att missa, lätta att ändra.')))
    else:
        lines.append(env.tr(_t('No Little leaks were recorded in these months.', 'Arjen pikkumenoja ei kirjattu näinä kuukausina.',
                               'Inga vardagliga småutgifter registrerades de här månaderna.')))
    if any(env.personal.is_protected(row['label']) for row in rows):
        env.personal.use('protected')
    chart = {'kind': 'bars', 'data': _bars(env, [(env.cat(row['label']), row['value_cents']) for row in rows[:5]])} if rows else None
    return _card(env, 'spend.leaks', env.tr(_t('Your Little leaks', 'Arjen pikkumenosi', 'Dina vardagliga småutgifter')),
                 env.tr(_t('Last {0} months', 'Viimeiset {0} kuukautta', 'Senaste {0} månaderna'), months), env.money(total), total,
                 lines=lines, chart=chart, params={'months': months})


@_question('spend.weekday', 'spending', _t('Which weekday do I spend the most?', 'Minä viikonpäivänä kulutan eniten?', 'Vilken veckodag spenderar jag mest?'),
           followups=('spend.leaks', 'spend.spender', 'money.where'),
           keywords=('weekday day week weekend most', 'viikonpäivä päivä viikonloppu eniten', 'veckodag dag helg mest'),
           tools=('explore',))
def _spend_weekday(env, params):
    end_month = env.complete_month()
    window = env.months_back(end_month, 6)
    start, end = max(month_bounds(window[0])[0], env.scope['observed_start']), min(month_bounds(window[-1])[1], env.scope['observed_end'])
    result = env.call('explore', {'start': start, 'end': end, 'group_by': 'weekday'},
                      env.tr(_t('Spending, {0}', 'Kulutus, {0}', 'Utgifter, {0}'), period_label(start, end, env.locale)))
    rows = sorted(result['rows'], key=lambda row: row['key'])
    if not rows:
        raise ValueError('No spending in this period')
    top = max(rows, key=lambda row: row['value_cents'])
    low = min(rows, key=lambda row: row['value_cents'])
    total = sum(row['value_cents'] for row in rows)
    weekend = sum(row['value_cents'] for row in rows if row['key'] in (6, 7))
    day = lambda row: _WEEKDAYS[env.locale][row['key'] - 1]
    lines = [env.tr(_t('{0}: {1} in {2} payments, {3} of your spending.', '{0}: {1}, {2} maksua, {3} kulutuksestasi.',
                       '{0}: {1} på {2} betalningar, {3} av dina utgifter.'),
                    day(top).capitalize(), env.money(top['value_cents']), top['count'], env.pct(_share(top['value_cents'], total))),
             env.tr(_t('Quietest day: {0} ({1}).', 'Hiljaisin päivä: {0} ({1}).', 'Lugnaste dagen: {0} ({1}).'), day(low), env.money(low['value_cents'])),
             env.tr(_t('Weekends: {0} of your spending.', 'Viikonloput: {0} kulutuksestasi.', 'Helger: {0} av dina utgifter.'), env.pct(_share(weekend, total)))]
    chart = {'kind': 'bars', 'data': _bars(env, [(day(row)[:3 if env.locale != 'fi' else 2].capitalize(), row['value_cents']) for row in rows])}
    return _card(env, 'spend.weekday', env.tr(_t('Your spending by weekday', 'Kulutuksesi viikonpäivittäin', 'Dina utgifter per veckodag')),
                 env.tr(_t('You spend the most on', 'Kulutat eniten', 'Du spenderar mest på')),
                 _WEEKDAYS_PLURAL[env.locale][top['key'] - 1], top['value_cents'], lines=lines, chart=chart,
                 caveat=env.tr(_t('Based on {0}.', 'Perusteena {0}.', 'Baserat på {0}.'), period_label(start, end, env.locale)),
                 params={'months': len(window)})


def _transaction_line(env, row):
    return '%s · %s · %s' % (env.money(abs(row['amount_cents'])), env.cat(row['category']), env.date(row['date'], False).strip())


@_question('spend.biggest', 'spending', _t('What were my biggest purchases this month?', 'Mitkä olivat tämän kuun suurimmat ostokseni?',
                                           'Vilka var mina största köp den här månaden?'),
           pickers=('month',), followups=('money.where', 'spend.recent', 'spend.leaks'),
           keywords=('biggest largest purchases expensive', 'suurimmat isoimmat ostokset kallein', 'största köp dyraste'),
           tools=('list_transactions',))
def _spend_biggest(env, params):
    month = _param_month(env, params)
    start, end = env.month_period(month)
    result = env.call('list_transactions', {'start': start, 'end': end, 'sort': 'largest', 'limit': 5},
                      env.tr(_t('Spending in {0}', 'Kulutus: {0}', 'Utgifter i {0}'), env.month_label(month)))
    rows = result['transactions']
    if not rows:
        lines = [env.tr(_t('No purchases in {0}.', 'Ei ostoksia {0}.', 'Inga köp i {0}.'), env.month_label(month, 'in'))]
    else:
        lines = [_transaction_line(env, row) for row in rows[:4]]
    value = abs(rows[0]['amount_cents']) if rows else 0
    return _card(env, 'spend.biggest', env.tr(_t('Your biggest purchases in {0}', 'Suurimmat ostoksesi {0}', 'Dina största köp i {0}'), env.month_label(month, 'in')),
                 env.tr(_t('Largest', 'Suurin', 'Störst')), env.money(value), value, lines=lines, personal=False,
                 pickers=[_month_picker(env, month)], params={'month': month})


@_question('spend.recent', 'spending', _t('Show my latest transactions', 'Näytä viimeisimmät tapahtumani', 'Visa mina senaste transaktioner'),
           pickers=('month',), followups=('spend.biggest', 'money.where', 'money.category'),
           keywords=('show latest recent transactions payments list last week', 'näytä viimeisimmät tapahtumat maksut', 'visa senaste transaktioner betalningar'),
           tools=('list_transactions',))
def _spend_recent(env, params):
    month = _param_month(env, params)
    start, end = env.month_period(month)
    result = env.call('list_transactions', {'start': start, 'end': end, 'sort': 'newest', 'limit': 5},
                      env.tr(_t('Spending in {0}', 'Kulutus: {0}', 'Utgifter i {0}'), env.month_label(month)))
    rows = result['transactions']
    lines = [_transaction_line(env, row) for row in rows[:4]] or [
        env.tr(_t('No purchases in {0}.', 'Ei ostoksia {0}.', 'Inga köp i {0}.'), env.month_label(month, 'in'))]
    return _card(env, 'spend.recent', env.tr(_t('Your latest payments', 'Viimeisimmät maksusi', 'Dina senaste betalningar')),
                 env.tr(_t('Payments in {0}', 'Maksuja {0}', 'Betalningar i {0}'), env.month_label(month, 'in')), str(result['count']),
                 lines=lines, personal=False,
                 caveat=env.tr(_t('Open the list to see every payment.', 'Avaa luettelo nähdäksesi kaikki maksut.', 'Öppna listan för att se alla betalningar.')),
                 pickers=[_month_picker(env, month)], params={'month': month})


# ---- Safe to spend & save -------------------------------------------------------------

def _held(plan, kinds):
    return [item for item in plan['held_back'] if item['kind'] in kinds]


def _held_label(env, item):
    """A held-back item's name in the card's language.

    The spending plan gives every item ``labels`` {en, fi, sv} (e.g. Rent / Vuokra /
    Hyra, Mortgage payment / Asuntolainan erä); those are used first so no English
    label leaks into a Finnish or Swedish answer. Older plan shapes fall back to
    the kind or the category name.
    """
    labels = item.get('labels')
    if isinstance(labels, dict) and labels.get(env.locale):
        return labels[env.locale]
    if item['kind'] == 'reserve':
        return env.tr(_t('safety cushion', 'turvatyyny', 'säkerhetsmarginal'))
    if item['kind'] == 'goal':
        return env.tr(_t('saving target', 'säästötavoite', 'sparmål'))
    if item['kind'] == 'loan':
        return env.tr(_t('loan payment', 'lainanlyhennys', 'lånebetalning'))
    if item['kind'] == 'tax':
        return env.tr(_t('tax set-aside', 'verovaraus', 'skatteavsättning'))
    if item['kind'] == 'buffer':
        return env.tr(_t('surprise buffer', 'yllätyspuskuri', 'buffert för oväntat'))
    return _bill_label(env, item['label'])


_BILL_LABELS = {'Utilities': _t('Home bills', 'Kodin laskut', 'Hemräkningar'), 'utilities_payment': _t('Home bills', 'Kodin laskut', 'Hemräkningar'),
                'housing_payment': _t('Rent', 'Vuokra', 'Hyra'), 'Rent': _t('Rent', 'Vuokra', 'Hyra'),
                'Mortgage payment': _t('Mortgage payment', 'Asuntolainan erä', 'Bolånebetalning')}


def _bill_label(env, label):
    return env.tr(_BILL_LABELS[label]) if label in _BILL_LABELS else env.cat(label)


def _plan_evidence(env, plan):
    reference = plan['as_of']
    start = max(env.scope['observed_start'], shift_month(reference[:7], -5) + '-01')
    env.add_evidence(env.tr(_t('Bills and must-pays used', 'Laskut ja pakolliset menot', 'Räkningar och fasta måsten')),
                     {'start': start, 'end': reference, 'role': 'fixed_obligation'})
    env.add_evidence(env.tr(_t('Recent spending', 'Viimeaikaiset menot', 'Senaste utgifter')),
                     {'start': max(env.scope['observed_start'], (date.fromisoformat(reference) - timedelta(days=89)).isoformat()),
                      'end': reference, 'consumption_only': 'true'})


def _plan_personal(env, plan):
    personal = env.personal
    personal.use('steady', 'life_stage', 'debts', 'saving_target')
    if personal.upcoming:
        payday = plan['next_payday'][:7]
        if any(item['month'] <= shift_month(payday, 1) for item in personal.upcoming):
            personal.use('upcoming')


def _spendable(plan):
    return max(plan['free_cents'] - plan.get('extra_cents', 0), 0)


@_question('room.week', 'room', _t('What can I safely spend this week?', 'Paljonko voin turvallisesti käyttää tällä viikolla?',
                                   'Hur mycket kan jag tryggt spendera den här veckan?'),
           followups=('room.payday', 'bills.upcoming', 'room.save_now'),
           keywords=('safe safely spend this week afford until payday can i spend left', 'paljonko voin käyttää viikolla turvallisesti käyttövara',
                     'hur mycket kan spendera veckan tryggt'),
           tools=('safe_to_spend',))
def _room_week(env, params):
    plan = env.plan()
    _plan_evidence(env, plan)
    days, per_day = plan['days_to_payday'], plan['per_day_cents']
    spendable = plan.get('daily_life_cents', _spendable(plan))
    week_days = min(7, days)
    bills = _held(plan, ('bill', 'loan', 'tax'))
    reserve = sum(item['amount_cents'] for item in _held(plan, ('reserve',))) or plan.get('reserve_floor_cents', 0)
    goals_held = sum(item['amount_cents'] for item in _held(plan, ('goal',)))
    lines = []
    if env.personal.steady:
        lines.append(env.tr(_t('Your safety cushion comes first: {0} stays untouched.', 'Turvatyynysi on etusijalla: {0} jätetään koskematta.',
                               'Din säkerhetsmarginal kommer först: {0} lämnas orörd.'), env.money(reserve)))
    lines.append(env.tr(_t('This week ({0} days): about {1}. Until payday ({2} days): {3}.',
                           'Tällä viikolla ({0} päivää) noin {1}. Palkkapäivään ({2} päivää) yhteensä {3}.',
                           'Den här veckan ({0} dagar): ungefär {1}. Fram till lönedagen ({2} dagar): {3}.'),
                        week_days, env.money(per_day * week_days), days, env.money(spendable)))
    held = env.money(sum(item['amount_cents'] for item in bills))
    names = join(['%s %s' % (_held_label(env, item), env.date(item['date'], False).strip()) if item.get('date') else _held_label(env, item)
                  for item in bills[:3]], env.locale)
    if bills:
        text = env.tr(_t('Already held back: bills before payday {0} ({1})', 'Jo sivussa: laskut ennen palkkapäivää {0} ({1})',
                         'Redan avsatt: räkningar före lönedagen {0} ({1})'), held, names)
    else:
        text = env.tr(_t('No bills are expected before payday', 'Ennen palkkapäivää ei odoteta laskuja', 'Inga räkningar väntas före lönedagen'))
    surprise = sum(item['amount_cents'] for item in _held(plan, ('buffer',)))
    if not env.personal.steady:
        text += env.tr(_t(', plus a {0} safety cushion', ', lisäksi turvatyyny {0}', ', plus en säkerhetsmarginal på {0}'), env.money(reserve))
    if surprise:
        text += env.tr(_t(' and a {0} surprise buffer', ' ja yllätyspuskuri {0}', ' och en buffert för oväntat på {0}'), env.money(surprise))
    if goals_held:
        text += env.tr(_t(' and your saving target {0}', ' ja säästötavoitteesi {0}', ' och ditt sparmål {0}'), env.money(goals_held))
    lines.append(text + '.')
    if plan.get('extra_cents') and not env.personal.steady:
        lines.append(env.tr(_t('{0} is more than you usually need before payday; it could go to savings.',
                               '{0} on enemmän kuin yleensä tarvitset ennen palkkapäivää; sen voisi siirtää säästöön.',
                               '{0} är mer än du brukar behöva före lönedagen; det kan gå till sparande.'), env.money(plan['extra_cents'])))
    if plan.get('shortfall_cents'):
        texts = (plan.get('shortfall_breakdown') or {}).get('texts')
        lines.append(texts[env.locale] if texts else env.tr(_t('Bills and the safety cushion are {0} more than your balance right now.',
                                                               'Laskut ja turvatyyny ovat yhteensä {0} enemmän kuin saldosi nyt.',
                                                               'Räkningar och säkerhetsmarginal är {0} mer än ditt saldo just nu.'), env.money(plan['shortfall_cents'])))
    _plan_personal(env, plan)
    held_total = sum(item['amount_cents'] for item in plan['held_back'])
    # V5 fix (lane CO): the same three parts and names as the Home payday bar; the app draws them as one labelled bar
    # and shows no chart when only one part is above €0. Steady mode shows no "could be saved" part.
    extra = plan.get('extra_cents') if not env.personal.steady else 0
    chart = {'kind': 'ring', 'data': _bars(env, [(env.tr(_t('Held back', 'Varattu', 'Avsatt')), held_total),
                                                 (env.tr(_t('For daily life until payday', 'Arkeen palkkapäivään asti', 'Till vardagen fram till lönedagen')), spendable)]
                                             + ([(env.tr(_t('Could be saved', 'Voisi säästää', 'Kan sparas')), extra)] if extra else []))}
    return _card(env, 'room.week', env.tr(_t('What you can spend until payday', 'Käyttövarasi', 'Att använda fram till lönedagen')),
                 env.tr(_t('a day until payday on {0}', 'päivässä palkkapäivään {0} asti', 'om dagen fram till lönedagen {0}'), env.date(plan['next_payday'])),
                 env.money(per_day), per_day, lines=lines, chart=chart, caveat=env.tr(_ESTIMATE),
                 params={'as_of': plan['as_of'], 'next_payday': plan['next_payday']})


@_question('room.payday', 'room', _t('Will my money last until payday?', 'Riittävätkö rahani palkkapäivään asti?', 'Räcker pengarna till lönedagen?'),
           followups=('room.week', 'bills.upcoming', 'goals.buffer'),
           keywords=('last until payday enough make it run out', 'riittävätkö rahat palkkapäivään riittää', 'räcker pengarna lönedagen'),
           tools=('forecast_30_days',))
def _room_payday(env, params):
    from .forecast import preview_30_days
    plan = env.plan()
    _plan_evidence(env, plan)
    preview = preview_30_days(env.conn, env.customer_id, plan['as_of'])
    path = [point for point in preview['projected'] if point['date'] < plan['next_payday']] or preview['projected'][:1]
    lowest = min(path, key=lambda point: point['balance_cents'])
    bills = sum(item['amount_cents'] for item in _held(plan, ('bill', 'loan', 'tax')))
    if lowest['balance_cents'] >= plan.get('reserve_floor_cents', 0):
        verdict = env.tr(_t('Yes, it looks like it will last.', 'Kyllä, rahojen pitäisi riittää.', 'Ja, det ser ut att räcka.'))
    elif lowest['balance_cents'] >= 0:
        verdict = env.tr(_t('Probably, but it gets tight before payday.', 'Todennäköisesti, mutta loppu on tiukka.', 'Troligen, men det blir knappt före lönedagen.'))
    else:
        verdict = env.tr(_t('It could run short before payday.', 'Rahat voivat loppua ennen palkkapäivää.', 'Det kan ta slut före lönedagen.'))
    lines = [verdict,
             env.tr(_t('After bills ({0}) and usual everyday spending, your balance should stay around {1} or more; lowest around {2}.',
                       'Laskujen ({0}) ja tavallisen arjen kulutuksen jälkeen saldosi pysyy noin {1} tai enemmän; matalimmillaan noin {2}.',
                       'Efter räkningar ({0}) och vanliga vardagsutgifter bör saldot ligga kring {1} eller mer; som lägst runt {2}.'),
                    env.money(bills), env.money(lowest['balance_cents']), env.date(lowest['date'], False).strip()),
             env.tr(_t('Next payday: {0}, in {1} days.', 'Seuraava palkkapäivä: {0}, {1} päivän päästä.', 'Nästa lönedag: {0}, om {1} dagar.'),
                    env.date(plan['next_payday']), plan['days_to_payday'])]
    if env.personal.steady:
        lines.insert(0, env.tr(_t('Your safety cushion of {0} is kept aside first, so this is a careful picture.',
                                  'Turvatyynysi {0} on ensin sivussa, joten arvio on maltillinen.',
                                  'Din säkerhetsmarginal på {0} hålls undan först, så det här är en återhållsam bild.'), env.money(plan.get('reserve_floor_cents', 0))))
        lines = lines[:1] + lines[1:3]
    _plan_personal(env, plan)
    chart = {'kind': 'trend', 'data': [{'label': env.date(point['date'], False).strip(), 'value_cents': point['balance_cents'],
                                        'value_text': env.money(point['balance_cents'])} for point in path]}
    return _card(env, 'room.payday', env.tr(_t('Will your money last until payday?', 'Riittävätkö rahasi palkkapäivään?', 'Räcker pengarna till lönedagen?')),
                 env.tr(_t('Lowest expected balance before payday', 'Matalin odotettu saldo ennen palkkapäivää', 'Lägsta väntade saldo före lönedagen')),
                 env.money(lowest['balance_cents']), lowest['balance_cents'], lines=lines, chart=chart, caveat=env.tr(_ESTIMATE),
                 params={'as_of': plan['as_of'], 'next_payday': plan['next_payday']})


@_question('room.save_now', 'room', _t('How much can I save this month?', 'Paljonko voin säästää tässä kuussa?', 'Hur mycket kan jag spara den här månaden?'),
           followups=('goals.new', 'room.save_more', 'goals.progress'),
           keywords=('how much can i save this month put aside move savings', 'paljonko voin säästää siirtää säästöön', 'hur mycket kan jag spara sätta undan'),
           tools=('safe_to_save',))
def _room_save_now(env, params):
    plan = env.plan()
    _plan_evidence(env, plan)
    can_save = max(plan.get('can_save_cents') or 0, 0)
    bills = sum(item['amount_cents'] for item in _held(plan, ('bill', 'loan', 'tax')))
    reserve = sum(item['amount_cents'] for item in _held(plan, ('reserve',)))
    lines = [env.tr(_t('That still leaves bills before payday ({0}), your safety cushion ({1}) and usual spending until {2} covered.',
                       'Silloinkin laskut ennen palkkapäivää ({0}), turvatyynysi ({1}) ja tavalliset menot {2} asti on katettu.',
                       'Då är räkningar före lönedagen ({0}), din säkerhetsmarginal ({1}) och vanliga utgifter fram till {2} fortfarande täckta.'),
                    env.money(bills), env.money(reserve), env.date(plan['next_payday']))]
    goal = sum(item['amount_cents'] for item in _held(plan, ('goal',)))
    if goal:
        lines.append(env.tr(_t('Your saving target ({0}) is already set aside on top of this.', 'Säästötavoitteesi ({0}) on jo varattu tämän lisäksi.',
                               'Ditt sparmål ({0}) är redan avsatt utöver detta.'), env.money(goal)))
    if env.personal.steady:
        lines.insert(0, env.tr(_t('No pressure right now: keeping this as a buffer in your account is a fine choice too.',
                                  'Ei paineita: rahan voi hyvin myös jättää tilillesi.',
                                  'Ingen press just nu: att låta pengarna ligga kvar på kontot är också ett bra val.')))
    elif not can_save:
        lines.append(env.tr(_t('There is no clear room to save before payday this time. Even a small amount after payday helps.',
                               'Tällä kertaa ennen palkkapäivää ei jää selvää säästövaraa. Pienikin summa palkkapäivän jälkeen auttaa.',
                               'Den här gången finns inget tydligt utrymme att spara före lönedagen. Även en liten summa efter lönedagen hjälper.')))
    else:
        lines.append(env.tr(_t('Moving it right after payday makes it a habit.', 'Kun siirrät sen heti palkkapäivänä, siitä tulee tapa.',
                               'Om du flyttar det direkt på lönedagen blir det en vana.')))
    _plan_personal(env, plan)
    env.personal.use('buffer_months')
    return _card(env, 'room.save_now', env.tr(_t('What you could save now', 'Paljonko voisit säästää nyt', 'Vad du kan spara nu')),
                 env.tr(_t('Could move to savings now', 'Voisit siirtää säästöön nyt', 'Kan flyttas till sparande nu')),
                 env.money(can_save), can_save, lines=lines, caveat=env.tr(_ESTIMATE),
                 params={'as_of': plan['as_of'], 'next_payday': plan['next_payday']})


def _eligible_leaks(env, rows):
    return [row for row in rows if row['label'] in CUTTABLE and not env.personal.is_protected(row['label'])]


@_question('room.save_more', 'room', _t('How could I save more?', 'Miten voisin säästää enemmän?', 'Hur skulle jag kunna spara mer?'),
           pickers=('category', 'percent'), followups=('room.cut', 'spend.leaks', 'goals.new'),
           keywords=('how could save more saving tips cut back reduce spending less', 'miten säästää enemmän säästövinkit vähentää',
                     'hur spara mer spartips minska dra ner'),
           tools=('spender_profile', 'safe_to_save'))
def _room_save_more(env, params):
    rows, months, _ = _leak_rows(env, 6)
    eligible = _eligible_leaks(env, rows)
    protected_hit = [row for row in rows if row['label'] in CUTTABLE and env.personal.is_protected(row['label'])]
    if protected_hit:
        env.personal.use('protected')
    default_percent = 10 if env.personal.gentle else 20
    pct = _param_percent(params, default_percent)
    choices = [row['label'] for row in eligible]
    category = params.get('category') or (choices[0] if choices else None)
    if category is not None and category not in CUTTABLE:
        raise ValueError('Unknown or unsupported category')
    if category is not None and env.personal.is_protected(category):
        category = choices[0] if choices else None
    lines = []
    monthly = 0
    if env.personal.steady:
        env.personal.use('steady')
        lines.append(env.tr(_t('Your safety cushion comes first, so start small: one easy change is enough.',
                               'Turvatyyny on nyt tärkein, joten aloita pienestä: yksi helppo muutos riittää.',
                               'Säkerhetsmarginalen kommer först, så börja smått: en enkel ändring räcker.')))
    if category:
        row = next((item for item in rows if item['label'] == category), None)
        base = row['value_cents'] // months if row else 0
        monthly = int((Decimal(base) * Decimal(str(pct)) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        lines.append(env.tr(_t('{0} has averaged {1} a month. Spending {2} less frees about {3} a month, {4} a year.',
                               '{0}: keskimäärin {1} kuukaudessa. {2} vähemmän vapauttaa noin {3} kuukaudessa, {4} vuodessa.',
                               '{0} har legat på i snitt {1} i månaden. {2} mindre frigör ungefär {3} i månaden, {4} per år.'),
                            env.cat(category), env.money(base), env.pct(pct), env.money(monthly), env.money(monthly * 12)))
    else:
        lines.append(env.tr(_t('Your Little leaks are already small or protected, so there is no obvious cut to suggest.',
                               'Arjen pikkumenosi ovat jo pienet tai suojattuja, joten selvää leikattavaa ei ole.',
                               'Dina vardagliga småutgifter är redan små eller skyddade, så det finns ingen självklar nedskärning.')))
    others = [row for row in eligible if row['label'] != category][:2]
    if others:
        lines.append(env.tr(_t('Other Little leaks to look at: {0}.', 'Muita katsottavia pikkumenoja: {0}.', 'Andra småutgifter att titta på: {0}.'),
                            join(['%s %s' % (env.cat(row['label']), env.money(row['value_cents'] // months)) for row in others], env.locale)))
    try:
        plan = env.plan()
        can_save = max(plan.get('can_save_cents') or 0, 0)
        if can_save and not env.personal.steady:
            lines.append(env.tr(_t('Right now you could also move about {0} to savings and still cover bills until payday.',
                                   'Juuri nyt voisit myös siirtää noin {0} säästöön, ja laskut ennen palkkapäivää olisivat silti katettuina.',
                                   'Just nu kan du också flytta ungefär {0} till sparande och ändå klara räkningarna till lönedagen.'),
                                env.money(can_save)))
    except ValueError:
        pass
    env.personal.use('saving_target', 'upcoming')
    visible = [row for row in rows if not env.personal.is_protected(row['label'])]
    chart = {'kind': 'bars', 'data': _bars(env, [(env.cat(row['label']), row['value_cents'] // months) for row in visible[:5]])} if visible else None
    actions = []
    if category and monthly:
        actions.append({'kind': 'open_question', 'label': env.tr(_t('Try a different cut', 'Kokeile muuta vähennystä', 'Prova en annan nedskärning')),
                        'params': {'question_id': 'room.cut', 'category': category, 'percent': pct}})
    return _card(env, 'room.save_more', env.tr(_t('How you could save more', 'Miten voisit säästää enemmän', 'Så kan du spara mer')),
                 env.tr(_t('Could free up a month', 'Voisi vapauttaa kuukaudessa', 'Kan frigöra per månad')), env.money(monthly), monthly,
                 lines=lines, chart=chart,
                 caveat=env.tr(_t('Based on your Little leaks over the last {0} months. Nothing changes until you decide.',
                                  'Perusteena arjen pikkumenosi viimeisen {0} kuukauden ajalta. Mikään ei muutu ennen kuin päätät.',
                                  'Baserat på dina vardagliga småutgifter de senaste {0} månaderna. Inget ändras förrän du bestämmer dig.'), months),
                 pickers=[_category_picker(env, category, [c for c in CUTTABLE if c in {row['label'] for row in eligible}]), _percent_picker(pct)],
                 params={'category': category, 'percent': pct, 'months': months}, actions=actions)


@_question('room.cut', 'room', _t('What if I cut back on a category?', 'Entä jos vähentäisin yhtä menoa?', 'Vad händer om jag drar ner på en kategori?'),
           pickers=('category', 'percent', 'month'), required=('category',), followups=('room.save_more', 'goals.new', 'money.category'),
           keywords=('what if cut back less reduce percent', 'entä jos vähentäisin vähemmän prosenttia', 'vad händer om drar ner mindre procent'),
           tools=('what_if_reduce',))
def _room_cut(env, params):
    month = _param_month(env, params)
    present = env.spending_categories(cuttable=True)
    start, end = env.month_period(month)
    rows = [row for row in env.call('explore', {'start': start, 'end': end, 'group_by': 'category', 'role': 'discretionary', 'top': 31})['rows']
            if row['value_cents'] > 0]
    eligible = [row['label'] for row in _eligible_leaks(env, rows)]
    category = _param_category(params, present, eligible[0] if eligible else (present[0] if present else 'Restaurants'))
    pct = _param_percent(params, 10 if env.personal.gentle else 20)
    if env.personal.is_protected(category):
        env.personal.use('protected')
        others = [item for item in eligible if item != category]
        return _card(env, 'room.cut', env.tr(_t('Spending you want to keep', 'Menot, jotka haluat pitää', 'Utgifter du vill behålla')),
                     env.tr(_t('No cut suggested', 'Ei leikkausehdotusta', 'Ingen nedskärning föreslås')), '—', None,
                     lines=[env.tr(_t('You asked me to keep this spending as it is, so I will not suggest cutting it.',
                                      'Pyysit pitämään nämä menot ennallaan, joten en ehdota niiden leikkaamista.',
                                      'Du bad mig att låta de här utgifterna vara, så jag föreslår ingen nedskärning.')),
                            env.tr(_t('You can change this under Me.', 'Voit muuttaa tätä kohdassa Minä.', 'Du kan ändra det under Jag.'))],
                     pickers=[_category_picker(env, others[0] if others else None, [c for c in present if not env.personal.is_protected(c)]),
                              _percent_picker(pct), _month_picker(env, month)],
                     params={'percent': pct, 'month': month})
    start, end = env.month_period(month)
    label = env.tr(_t('{0} in {1}', '{0}: {1}', '{0} i {1}'), env.cat(category), env.month_label(month))
    try:
        result = env.call('what_if_reduce', {'category': category, 'percent': pct, 'month': month}, label)
    except ValueError:
        result = None
    title = env.tr(_t('If you cut {0} by {1}', 'Jos vähennät: {0} −{1}', 'Om du drar ner på {0} med {1}'), env.cat(category), env.pct(pct))
    if result is None:
        return _card(env, 'room.cut', title, env.tr(_t('Freed up a month', 'Vapautuu kuukaudessa', 'Frigörs per månad')), env.money(0), 0,
                     lines=[env.tr(_t('There was no {0} spending in {1} to adjust.', 'Luokassa {0} ei ollut kulutusta {1}.', 'Det fanns inga utgifter för {0} i {1} att justera.'),
                                   env.cat(category), env.month_label(month, 'in'))],
                     pickers=[_category_picker(env, category, [c for c in present if not env.personal.is_protected(c)]), _percent_picker(pct), _month_picker(env, month)],
                     params={'category': category, 'percent': pct, 'month': month})
    monthly = result['monthly_freed_cents']
    base = result['adjustable_base_cents']
    lines = [env.tr(_t('Based on {0} spent in {1}.', 'Perusteena {1} kulutus {0}.', 'Baserat på {0} i {1}.'), env.money(base),
                    env.month_label(month, 'gen') if env.locale == 'fi' else env.month_label(month)),
             env.tr(_t('Over a year that is about {0}.', 'Vuodessa se tekee noin {0}.', 'Under ett år blir det ungefär {0}.'), env.money(result['yearly_freed_cents'])),
             env.tr(_t('It is only a plan: nothing changes unless you save it.', 'Tämä on vain suunnitelma: mikään ei muutu, ellet tallenna sitä.',
                       'Det är bara en plan: inget ändras om du inte sparar den.'))]
    env.personal.use('saving_target')
    chart = {'kind': 'bars', 'data': _bars(env, [(env.tr(_t('Now', 'Nyt', 'Nu')), base), (env.tr(_t('With the cut', 'Vähennyksen jälkeen', 'Med nedskärningen')), base - monthly)])}
    actions = [{'kind': 'save_scenario', 'label': env.tr(_t('Review spending plan', 'Tarkista suunnitelma', 'Granska planen')),
                'params': dict(result['proposal'])}]
    return _card(env, 'room.cut', title, env.tr(_t('Freed up a month', 'Vapautuu kuukaudessa', 'Frigörs per månad')), env.money(monthly), monthly,
                 lines=lines, chart=chart, actions=actions,
                 pickers=[_category_picker(env, category, [c for c in present if not env.personal.is_protected(c)]), _percent_picker(pct), _month_picker(env, month)],
                 params={'category': category, 'percent': pct, 'month': month})


# ---- Goals ----------------------------------------------------------------------------

@_question('goals.progress', 'goals', _t('How are my goals doing?', 'Miten tavoitteeni etenevät?', 'Hur går det med mina mål?'),
           followups=('goals.new', 'room.save_now', 'room.save_more'),
           keywords=('goals progress how doing on track', 'tavoitteet etenevät tavoite', 'mål går det framsteg'),
           tools=('list_goals',))
def _goals_progress(env, params):
    result = env.call('list_goals')
    goals = result['goals']
    env.personal.use('saving_target', 'upcoming')
    if not goals:
        return _card(env, 'goals.progress', env.tr(_t('Your goals', 'Tavoitteesi', 'Dina mål')),
                     env.tr(_t('Saved goals', 'Tallennetut tavoitteet', 'Sparade mål')), '0', None,
                     lines=[env.tr(_t('You have no saving goals yet. Tell me what you would like to save for.',
                                      'Sinulla ei ole vielä säästötavoitteita. Kerro, mihin haluaisit säästää.',
                                      'Du har inga sparmål än. Berätta vad du vill spara till.'))])
    lines = []
    for goal in goals[:3]:
        lines.append(env.tr(_t('{0}: {1} of {2} · {3} a month until {4}.', '{0}: {1} / {2} · {3} kuukaudessa {4} asti.',
                               '{0}: {1} av {2} · {3} i månaden fram till {4}.'),
                            goal['name'], env.money(goal['current_saved_cents']), env.money(goal['target_cents']),
                            env.money(goal['required_monthly_cents']), env.date(goal['target_date'])))
    try:
        can_save = max(env.plan().get('can_save_cents') or 0, 0)
        lines.append(env.tr(_t('Right now about {0} could go to savings before payday.', 'Juuri nyt noin {0} voisi mennä säästöön ennen palkkapäivää.',
                               'Just nu kan ungefär {0} gå till sparande före lönedagen.'), env.money(can_save)))
    except ValueError:
        pass
    first = goals[0]
    share = _share(first['current_saved_cents'], first['target_cents'])
    chart = {'kind': 'progress', 'data': {'current_cents': first['current_saved_cents'], 'target_cents': first['target_cents'],
                                          'percent': format(share.quantize(Decimal('0.1')), 'f'),
                                          'value_text': env.money(first['current_saved_cents']), 'target_text': env.money(first['target_cents'])}}
    saved = sum(goal['current_saved_cents'] for goal in goals)
    return _card(env, 'goals.progress', env.tr(_t('Your goals', 'Tavoitteesi', 'Dina mål')),
                 env.tr(_t('Saved towards {0} goals', 'Säästetty {0} tavoitteeseen', 'Sparat till {0} mål'), len(goals)) if len(goals) > 1 else
                 env.tr(_t('Saved towards your goal', 'Säästetty tavoitteeseen', 'Sparat till ditt mål')),
                 env.money(saved), saved, lines=lines, chart=chart,
                 caveat=env.tr(_t('Saved amounts are what you entered; nothing moves money automatically.',
                                  'Säästetyt summat ovat itse kirjaamiasi; rahaa ei siirretä automaattisesti.',
                                  'Sparade belopp är de du själv angett; inga pengar flyttas automatiskt.')))


def _goal_params(env, params):
    amount = params.get('amount_cents', params.get('target_cents'))
    target = params.get('target_date')
    name = params.get('name')
    if amount is not None and (type(amount) is not int or not 0 < amount <= 10_000_000_000):
        raise ValueError('amount_cents must be positive integer cents')
    if target is not None:
        if not isinstance(target, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', target):
            raise ValueError('target_date must use YYYY-MM-DD')
        date.fromisoformat(target)
    if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 120):
        raise ValueError('name must be text of one to 120 characters')
    return amount, target, (name or '').strip() or None


@_question('goals.new', 'goals', _t('Help me save for something', 'Auta minua säästämään johonkin', 'Hjälp mig att spara till något'),
           pickers=('amount', 'date'), required=('amount_cents', 'target_date'), followups=('goals.progress', 'room.save_now', 'room.save_more'),
           keywords=('save for goal trip want to buy saving for target by', 'säästää johonkin tavoite matka haluan ostaa', 'spara till mål resa vill köpa'),
           tools=('goal_plan',))
def _goals_new(env, params):
    amount, target, name = _goal_params(env, params)
    name = name or env.tr(_t('My goal', 'Oma tavoite', 'Mitt mål'))
    env.personal.use('steady', 'buffer_months', 'upcoming')
    reference = date.fromisoformat(env.reference_date)
    default_date = date(reference.year + 1, reference.month, 1) - timedelta(days=1)
    pickers = [{'name': 'amount_cents', 'kind': 'amount', 'value': amount},
               {'name': 'target_date', 'kind': 'date', 'value': target or default_date.isoformat()}]
    can_save = None
    try:
        can_save = max(env.plan().get('can_save_cents') or 0, 0)
    except ValueError:
        pass
    if amount is None or target is None:
        lines = [env.tr(_t('Choose how much and by when, and I will work out the monthly amount.',
                           'Valitse summa ja päivämäärä, niin lasken kuukausittaisen säästösumman.',
                           'Välj belopp och datum, så räknar jag ut hur mycket det blir i månaden.'))]
        if can_save is not None:
            lines.append(env.tr(_t('For reference: about {0} could go to savings before your next payday.',
                                   'Vertailuksi: noin {0} voisi mennä säästöön ennen seuraavaa palkkapäivää.',
                                   'Som jämförelse: ungefär {0} kan gå till sparande före nästa lönedag.'), env.money(can_save)))
        return _card(env, 'goals.new', env.tr(_t('Plan a saving goal', 'Suunnittele säästötavoite', 'Planera ett sparmål')),
                     env.tr(_t('Choose an amount and a date', 'Valitse summa ja päivämäärä', 'Välj belopp och datum')), '—', None,
                     lines=lines, pickers=pickers, params={'name': name, 'amount_cents': amount, 'target_date': target})
    env.ctx.message = '€' + format(Decimal(amount) / 100, 'f')
    result = env.call('goal_plan', {'name': name, 'target_cents': amount, 'target_date': target})
    monthly, months = result['required_monthly_cents'], result['months_remaining']
    lines = [env.tr(_t('{0} by {1}: {2} months to go.', '{0} {1} mennessä: {2} kuukautta aikaa.', '{0} till {1}: {2} månader kvar.'),
                    env.money(amount), env.date(target), months)]
    if can_save is not None:
        if monthly <= can_save:
            lines.append(env.tr(_t('Right now about {0} could go to savings before payday, so this looks reachable.',
                                   'Juuri nyt noin {0} voisi mennä säästöön ennen palkkapäivää, joten tämä näyttää mahdolliselta.',
                                   'Just nu kan ungefär {0} gå till sparande före lönedagen, så det här ser möjligt ut.'), env.money(can_save)))
        else:
            lines.append(env.tr(_t('That is more than the {0} free to save right now; a later date makes the monthly amount smaller.',
                                   'Se on enemmän kuin nyt säästettävissä oleva {0}; myöhempi päivämäärä pienentää kuukausisummaa.',
                                   'Det är mer än de {0} som går att spara nu; ett senare datum gör månadsbeloppet mindre.'), env.money(can_save)))
    if env.personal.steady:
        lines.append(env.tr(_t('While things are uncertain, a small buffer first is a good idea.', 'Kun tilanne on epävarma, kannattaa ensin koota pieni turvatyyny.',
                               'När läget är osäkert är det klokt att först bygga upp en liten säkerhetsmarginal.')))
    actions = [{'kind': 'create_goal', 'label': env.tr(_t('Review goal', 'Tarkista tavoite', 'Granska målet')), 'params': dict(result['proposal'])}]
    return _card(env, 'goals.new', env.tr(_t('Saving for {0}', 'Säästötavoite: {0}', 'Sparmål: {0}'), name),
                 env.tr(_t('a month until {0}', 'kuukaudessa {0} asti', 'i månaden fram till {0}'), env.date(target)), env.money(monthly), monthly,
                 lines=lines, pickers=pickers, actions=actions,
                 caveat=env.tr(_t('Not saved yet: review the goal to keep it. No interest is assumed.',
                                  'Ei vielä tallennettu: tarkista tavoite, jos haluat pitää sen. Korkoa ei ole oletettu.',
                                  'Inte sparat än: granska målet för att behålla det. Ingen ränta har antagits.')),
                 params={'name': name, 'amount_cents': amount, 'target_date': target})


@_question('goals.buffer', 'goals', _t('How big should my emergency buffer be?', 'Kuinka suuri hätävaran pitäisi olla?', 'Hur stor borde min sparkudde vara?'),
           followups=('room.save_now', 'goals.new', 'bills.recurring'),
           keywords=('emergency fund buffer cushion rainy day how big', 'hätävara puskuri kuinka suuri', 'buffert nödbuffert sparkudde hur stor'),
           tools=('irregular_buffer', 'spender_profile'))
def _goals_buffer(env, params):
    buffer = env.call('irregular_buffer', {}, env.tr(_t('Surprise must-pays', 'Yllättävät pakolliset menot', 'Oväntade måsten')))
    profile = env.call('spender_profile', {})
    must_pays = (((profile.get('figures') or {}).get('baskets') or {}).get('fixed_obligation') or {}).get('monthly_average_cents')
    months = env.personal.buffer_months or (6 if env.personal.steady or env.personal.life_stage in ('between_jobs', 'self_employed') else 3)
    env.personal.use('buffer_months', 'steady', 'life_stage', 'household')
    lines = []
    target = None
    if must_pays:
        target = int((Decimal(must_pays) * Decimal(str(months))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        lines.append(env.tr(_t('That is {0} months of your Must-pays (about {1} a month).', 'Se on {0} kuukauden pakolliset menot (noin {1} kuukaudessa).',
                               'Det motsvarar {0} månader av dina fasta måsten (ungefär {1} i månaden).'), _number(months, env.locale), env.money(must_pays)))
    if buffer.get('available') and buffer.get('count'):
        largest = buffer.get('largest') or {}
        lines.append(env.tr(_t('Surprise must-pays averaged {0} a month; the biggest was {1} ({2}).',
                               'Yllättävät pakolliset menot olivat keskimäärin {0} kuukaudessa; suurin oli {1} ({2}).',
                               'Oväntade måsten var i snitt {0} i månaden; det största var {1} ({2}).'),
                            env.money(buffer['monthly_average_cents']), env.money(largest.get('amount_cents', 0)), env.cat(largest.get('category', ''))))
    if env.personal.steady:
        lines.append(env.tr(_t('While things are uncertain, building this comes before other goals.', 'Kun tilanne on epävarma, tämä kannattaa koota ennen muita tavoitteita.',
                               'När läget är osäkert går det här före andra mål.')))
    return _card(env, 'goals.buffer', env.tr(_t('Your emergency buffer', 'Hätävarasi', 'Din sparkudde')),
                 env.tr(_t('A buffer of about', 'Hätävaraksi noin', 'En sparkudde på ungefär')), env.money(target) if target is not None else '—', target,
                 lines=lines,
                 caveat=env.tr(_t('A common guide is 3–6 months of essential costs; the right size depends on your situation.',
                                  'Yleinen nyrkkisääntö on 3–6 kuukauden välttämättömät menot; sopiva koko riippuu tilanteestasi.',
                                  'En vanlig tumregel är 3–6 månaders nödvändiga kostnader; rätt storlek beror på din situation.')),
                 params={'months': months})


# ---- Bills & coming up ------------------------------------------------------------------

@_question('bills.upcoming', 'bills', _t('What bills are coming up before payday?', 'Mitä laskuja on tulossa ennen palkkapäivää?',
                                         'Vilka räkningar kommer före lönedagen?'),
           followups=('room.week', 'bills.recurring', 'bills.payday'),
           keywords=('bills coming up due upcoming before payday next', 'laskut tulossa erääntyy ennen palkkapäivää', 'räkningar kommer förfaller före lönedagen'),
           tools=('safe_to_spend',))
def _bills_upcoming(env, params):
    plan = env.plan()
    _plan_evidence(env, plan)
    bills = _held(plan, ('bill', 'loan', 'tax'))
    total = sum(item['amount_cents'] for item in bills)
    lines = ['%s · %s · %s' % (env.date(item['date'], False).strip() if item.get('date') else env.tr(_t('this pay cycle', 'tällä jaksolla', 'den här perioden')),
                               _held_label(env, item), env.money(item['amount_cents'])) for item in bills[:3]]
    if len(bills) > 3:
        lines.append(env.tr(_t('…and {0} more.', '…ja {0} muuta.', '…och {0} till.'), len(bills) - 3))
    if not bills:
        lines.append(env.tr(_t('No regular bills are expected before payday.', 'Ennen palkkapäivää ei odoteta säännöllisiä laskuja.',
                               'Inga regelbundna räkningar väntas före lönedagen.')))
    env.personal.use('debts', 'upcoming')
    return _card(env, 'bills.upcoming', env.tr(_t('Bills before payday on {0}', 'Laskut ennen palkkapäivää {0}', 'Räkningar före lönedagen {0}'), env.date(plan['next_payday'])),
                 env.tr(_t('Held back for bills', 'Laskuihin varattu', 'Avsatt för räkningar')), env.money(total), total, lines=lines,
                 caveat=env.tr(_t('Expected from your regular payments; a new or changed bill may not show yet.',
                                  'Arvioitu säännöllisistä maksuistasi; uusi tai muuttunut lasku ei välttämättä näy vielä.',
                                  'Uppskattat från dina regelbundna betalningar; en ny eller ändrad räkning syns kanske inte än.')),
                 params={'next_payday': plan['next_payday']})


def _ordinal_day(day, locale):
    if locale == 'fi':
        return '%d. päivän' % day
    if locale == 'sv':
        return 'den %d:%s' % (day, 'a' if day % 10 in (1, 2) and day not in (11, 12) else 'e')
    suffix = 'th' if 10 <= day % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return 'the %d%s' % (day, suffix)


@_question('bills.recurring', 'bills', _t('What are my recurring payments?', 'Mitkä ovat toistuvat maksuni?', 'Vilka återkommande betalningar har jag?'),
           followups=('bills.upcoming', 'me.peers', 'room.week'),
           keywords=('recurring regular monthly payments subscriptions bill phone rent', 'toistuvat säännölliset maksut tilaukset lasku vuokra',
                     'återkommande regelbundna betalningar abonnemang räkning hyra'),
           tools=('recurring_payments',))
def _bills_recurring(env, params):
    result = env.call('recurring_payments', {}, env.tr(_t('Regular payments', 'Säännölliset maksut', 'Regelbundna betalningar')))
    items = sorted(result['items'], key=lambda item: item['amount_cents'])
    total = -sum(item['amount_cents'] for item in items)
    lines = [env.tr(_t('{0} · about {1} around {2}', '{0} · noin {1} kuun {2} tienoilla', '{0} · ungefär {1} runt {2}'),
                    _bill_label(env, item['category'] or item['transaction_type']), env.money(-item['amount_cents']), _ordinal_day(int(item['median_day']), env.locale))
             for item in items[:3]]
    if not items:
        lines.append(env.tr(_t('I did not find payments that repeat every month.', 'En löytänyt joka kuukausi toistuvia maksuja.',
                               'Jag hittade inga betalningar som återkommer varje månad.')))
    env.personal.use('debts')
    chart = {'kind': 'bars', 'data': _bars(env, [(_bill_label(env, item['category'] or item['transaction_type']), -item['amount_cents']) for item in items[:6]])} if items else None
    return _card(env, 'bills.recurring', env.tr(_t('Your recurring payments', 'Toistuvat maksusi', 'Dina återkommande betalningar')),
                 env.tr(_t('A month in regular payments', 'Säännöllisiä maksuja kuukaudessa', 'Regelbundna betalningar per månad')), env.money(total), total,
                 lines=lines, chart=chart,
                 caveat=env.tr(_t('Found from payments that repeated in recent months; merchant names are not available.',
                                  'Tunnistettu viime kuukausina toistuneista maksuista; kauppojen nimiä ei ole saatavilla.',
                                  'Hittade utifrån betalningar som upprepats de senaste månaderna; butiksnamn finns inte.')))


@_question('bills.payday', 'bills', _t('When is my next payday?', 'Milloin on seuraava palkkapäiväni?', 'När är min nästa lönedag?'),
           followups=('room.week', 'room.payday', 'money.inout'),
           keywords=('when next payday salary', 'milloin palkkapäivä palkka seuraava', 'när lönedag lön nästa'),
           tools=('payday_pattern',))
def _bills_payday(env, params):
    plan = env.plan()
    pattern = env.call('payday_pattern', {}, env.tr(_t('Salary payments', 'Palkanmaksut', 'Löneutbetalningar')))
    payday = pattern.get('payday') or {}
    lines = []
    if payday.get('salary_median_cents'):
        lines.append(env.tr(_t('Your salary has been about {0} after tax.', 'Palkkasi on ollut noin {0} verojen jälkeen.', 'Din lön har varit ungefär {0} efter skatt.'),
                            env.money(payday['salary_median_cents'])))
    events = payday.get('events') or []
    if events:
        lines.append(env.tr(_t('Recent paydays: {0}.', 'Viimeisimmät palkkapäivät: {0}.', 'Senaste lönedagar: {0}.'),
                            ', '.join(env.date(event['salary_date'], False).strip() for event in events[-4:])))
        if not payday.get('qualified') and not payday.get('low_balance_event_count'):
            lines.append(env.tr(_t('Your balance has not run low before payday.', 'Saldosi ei ole käynyt matalalla ennen palkkapäivää.',
                                   'Ditt saldo har inte blivit lågt före lönedagen.')))
    env.personal.use('life_stage')
    return _card(env, 'bills.payday', env.tr(_t('Your next payday', 'Seuraava palkkapäiväsi', 'Din nästa lönedag')),
                 env.tr(_t('in {0} days', '{0} päivän päästä', 'om {0} dagar'), plan['days_to_payday']), env.date(plan['next_payday']), None,
                 lines=lines, caveat=env.tr(_t('Expected from your past salary days; salary counts only once it arrives.',
                                               'Arvioitu aiemmista palkkapäivistäsi; palkka huomioidaan vasta, kun se on tilillä.',
                                               'Uppskattat från dina tidigare lönedagar; lönen räknas först när den kommit in.')),
                 params={'next_payday': plan['next_payday']})


# ---- My profile & life events -----------------------------------------------------------

_ALL_PERSONAL = ('life_stage', 'steady', 'events', 'household', 'saving_target', 'buffer_months', 'protected', 'upcoming', 'debts', 'style')


@_question('me.known', 'me', _t('What do you know about me?', 'Mitä tiedät minusta?', 'Vad vet du om mig?'),
           followups=('me.life_change', 'spend.spender', 'goals.progress'),
           keywords=('what do you know about me profile told', 'mitä tiedät minusta profiili', 'vad vet du om mig profil'),
           tools=('get_profile',))
def _me_known(env, params):
    env.call('get_profile')
    facts = env.personal.facts(_ALL_PERSONAL)
    notes = len([e for e in env.personal.profile.get('entries', []) if e.get('active') and e['key'] == 'note'])
    lines = ['; '.join(facts[index:index + 2]) + '.' for index in range(0, min(len(facts), 6), 2)]
    if notes:
        lines.append(env.tr(_t('Plus {0} notes in your own words.', 'Lisäksi {0} omin sanoin kirjoitettua muistiinpanoa.', 'Plus {0} anteckningar med dina egna ord.'), notes))
    if not facts and not notes:
        lines = [env.tr(_t('You have not told me anything yet. I only use your transactions.', 'Et ole vielä kertonut minulle mitään. Käytän vain tilitapahtumiasi.',
                           'Du har inte berättat något för mig än. Jag använder bara dina transaktioner.')),
                 env.tr(_t('You can add things, change them or forget everything under Me.', 'Voit lisätä, muuttaa tai poistaa tietoja kohdassa Minä.',
                           'Du kan lägga till, ändra eller glömma allt under Jag.'))]
    else:
        lines.append(env.tr(_t('You can change or forget any of this under Me.', 'Voit muuttaa tai poistaa näitä kohdassa Minä.', 'Du kan ändra eller glömma allt detta under Jag.')))
    count = len(facts) + notes
    return _card(env, 'me.known', env.tr(_t('What I know about you', 'Mitä tiedän sinusta', 'Vad jag vet om dig')),
                 env.tr(_t('Things you have told me', 'Asioita, jotka olet kertonut', 'Saker du har berättat')), str(count), None,
                 lines=lines[:4], personal=False,
                 caveat=env.tr(_t('Nothing is saved without your OK.', 'Mitään ei tallenneta ilman lupaasi.', 'Inget sparas utan ditt godkännande.')))


@_question('me.life_change', 'me', _t('Tell the coach about a life change', 'Kerro valmentajalle elämänmuutoksesta', 'Berätta för coachen om en livsförändring'),
           followups=('room.week', 'goals.buffer', 'me.known'),
           keywords=('life change lost job baby moving divorce sick new situation', 'elämänmuutos menetin työn vauva muutto ero sairas',
                     'livsförändring förlorade jobbet bebis flytt skilsmässa sjuk'),
           tools=('get_profile',))
def _me_life_change(env, params):
    steady = env.personal.steady
    env.personal.use('steady', 'events', 'life_stage')
    lines = [env.tr(_t('If something big happens, such as a lost job, a baby or a move, you can tell me under Me.',
                       'Jos elämässäsi tapahtuu jotain isoa, kuten työn menetys, vauva tai muutto, voit kertoa siitä kohdassa Minä.',
                       'Om något stort händer, som ett förlorat jobb, en bebis eller en flytt, kan du berätta det under Jag.')),
             env.tr(_t('Then I hold back more for Must-pays and your buffer, and suggest smaller steps.',
                       'Silloin varaan enemmän pakollisiin menoihin ja turvatyynyyn ja ehdotan pienempiä askelia.',
                       'Då avsätter jag mer för fasta måsten och säkerhetsmarginalen och föreslår mindre steg.')),
             env.tr(_t('Nothing is saved until you confirm it, and you can end it any time.', 'Mitään ei tallenneta ennen kuin vahvistat, ja voit lopettaa sen milloin vain.',
                       'Inget sparas förrän du bekräftar, och du kan avsluta det när som helst.'))]
    actions = [{'kind': 'open_profile', 'label': env.tr(_t('Tell the coach about you', 'Kerro itsestäsi valmentajalle', 'Berätta om dig för coachen')), 'params': {}}]
    return _card(env, 'me.life_change', env.tr(_t('Tell me about a life change', 'Kerro elämänmuutoksesta', 'Berätta om en livsförändring')),
                 env.tr(_t('Coaching right now', 'Valmennus nyt', 'Coachning just nu')),
                 env.tr(_t('Steady mode', 'Rauhallinen tahti', 'Lugnt tempo') if steady else _t('Normal', 'Tavallinen', 'Normal')), None,
                 lines=lines, actions=actions)


@_question('me.peers', 'me', _t('How do I compare with others my age?', 'Miten pärjään ikäisiini verrattuna?', 'Hur står jag mig mot andra i min ålder?'),
           pickers=('category',), followups=('money.category', 'room.save_more', 'spend.spender'),
           keywords=('compare others my age people peers average normal typical', 'vertaa ikäisiini muihin keskimäärin', 'jämför andra min ålder snitt'),
           tools=('compare_to_peers',))
def _me_peers(env, params):
    category = _param_category(params, PEER_CATEGORIES, 'Restaurants')
    result = env.call('compare_to_peers', {'category': category}, env.tr(_t('{0}, last 12 months', '{0}, 12 kk', '{0}, 12 månader'), env.cat(category)))
    title = env.tr(_t('{0}: you and others your age', '{0}: sinä ja ikäisesi', '{0}: du och andra i din ålder'), env.cat(category))
    caveat = env.tr(_t('Statistics Finland 2022 household survey, per person. Prices have changed since and categories only roughly match, so treat this as orientation, not a ranking.',
                       'Tilastokeskuksen kotitaloustiedustelu 2022, henkeä kohden. Hinnat ovat muuttuneet ja luokat vastaavat toisiaan vain karkeasti, joten pidä tätä suuntaa antavana, ei paremmuusjärjestyksenä.',
                       'Statistikcentralens hushållsundersökning 2022, per person. Priserna har ändrats sedan dess och kategorierna motsvarar varandra bara ungefär, så se det som en fingervisning, inte en rangordning.'))
    pickers = [_category_picker(env, category, list(PEER_CATEGORIES))]
    if not result.get('available'):
        return _card(env, 'me.peers', title, env.tr(_t('No comparison available', 'Vertailua ei ole saatavilla', 'Ingen jämförelse tillgänglig')), '—',
                     lines=[env.tr(_t('There is not enough data for this category to compare.', 'Tälle luokalle ei ole tarpeeksi tietoja vertailuun.',
                                      'Det finns inte tillräckligt med data för att jämföra den här kategorin.'))],
                     caveat=caveat, pickers=pickers, params={'category': category}, personal=False)
    mine = result['customer']['monthly_average_cents']
    peers = result['peers']['per_consumption_unit_cents']
    band = str(result['peers']['age_band']).replace('-', '–')
    diff = result.get('difference_percent')
    lines = [env.tr(_t('You: about {0} a month. People aged {1}: about {2} a month.', 'Sinä: noin {0} kuukaudessa. {1}-vuotiaat: noin {2} kuukaudessa.',
                       'Du: ungefär {0} i månaden. Personer i åldern {1}: ungefär {2} i månaden.'), env.money(mine), band, env.money(peers))]
    if diff is not None and Decimal(diff) != 0:
        lines.append(env.tr(_t('That is {0} {1} than the survey average.', 'Se on {0} {1} kuin kyselyn keskiarvo.', 'Det är {0} {1} än genomsnittet i undersökningen.'),
                            env.pct(abs(Decimal(diff))), env.tr(_t('more', 'enemmän', 'mer') if Decimal(diff) > 0 else _t('less', 'vähemmän', 'mindre'))))
    if env.personal.is_protected(category):
        env.personal.use('protected')
    env.personal.use('household')
    chart = {'kind': 'bars', 'data': _bars(env, [(env.tr(_t('You', 'Sinä', 'Du')), mine), (env.tr(_t('Aged {0}', '{0}-vuotiaat', '{0} år'), band), peers)])}
    return _card(env, 'me.peers', title, env.tr(_t('Your monthly average', 'Kuukausikeskiarvosi', 'Ditt månadssnitt')), env.money(mine), mine,
                 lines=lines, chart=chart, caveat=caveat, pickers=pickers, params={'category': category})


# ---- Compare, taxes & year ----------------------------------------------------------------

@_question('extra.year', 'extras', _t('Show my year in review', 'Näytä vuosikatsaukseni', 'Visa min årsöversikt'),
           followups=('money.inout', 'spend.spender', 'goals.new'),
           keywords=('year review my year annual 2025', 'vuosikatsaus vuoteni vuosi', 'årsöversikt mitt år året'),
           tools=('year_review',))
def _extra_year(env, params):
    from .spender import ARCHETYPE_LABELS
    from .year_story import default_year
    year = params.get('year') or default_year(env.conn, env.customer_id)
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError('year must be a calendar year')
    result = env.call('year_review', {'year': year}, env.tr(_t('Your {0}', 'Vuotesi {0}', 'Ditt år {0}'), year))
    title = env.tr(_t('Your {0} in money', 'Rahavuotesi {0}', 'Ditt år {0} i pengar'), year)
    if not result.get('available'):
        return _card(env, 'extra.year', title, env.tr(_t('Not enough history', 'Liian vähän historiaa', 'För lite historik')), '—',
                     lines=[env.tr(_t('There is not enough account history for this year yet.', 'Tältä vuodelta ei ole vielä tarpeeksi tilihistoriaa.',
                                      'Det finns inte tillräckligt med kontohistorik för det här året än.'))], params={'year': year})
    lines = [env.tr(_t('Money out: {0}.', 'Menot: {0}.', 'Pengar ut: {0}.'), env.money(result['money_out_cents']))]
    top = result.get('top_category')
    if top:
        lines.append(env.tr(_t('Top category: {0} ({1} of spending).', 'Suurin menoluokka: {0} ({1} kulutuksesta).', 'Största kategori: {0} ({1} av utgifterna).'),
                            env.cat(top['category']), env.pct(top['share_percent'])))
    biggest = result.get('biggest_month')
    if biggest:
        lines.append(env.tr(_t('Biggest spending month: {0}.', 'Suurin kulutuskuukausi: {0}.', 'Månaden med mest utgifter: {0}.'), env.month_label(biggest['month'])))
    if result.get('archetype_label'):
        key = next((k for k, v in ARCHETYPE_LABELS.items() if v.get('en') == result['archetype_label']), None)
        lines.append(env.tr(_t('Spending style: {0}.', 'Rahankäyttötyyli: {0}.', 'Utgiftsstil: {0}.'),
                            ARCHETYPE_LABELS[key][env.locale] if key else result['archetype_label']))
    actions = [{'kind': 'open_year_review', 'label': env.tr(_t('Open my year', 'Avaa vuoteni', 'Öppna mitt år')), 'params': {'year': year}}]
    caveat = None if result.get('complete', True) else env.tr(_t('This year is not complete yet.', 'Vuosi on vielä kesken.', 'Året är inte slut än.'))
    return _card(env, 'extra.year', title, env.tr(_t('Money in', 'Tulot', 'Pengar in')), env.money(result['money_in_cents']), result['money_in_cents'],
                 lines=lines, caveat=caveat, actions=actions, params={'year': year}, personal=False)


_TAX_STAGES = {
    'return_coming': _t('Your pre-completed tax return is coming', 'Esitäytetty veroilmoitus on tulossa', 'Din förhandsifyllda skattedeklaration är på väg'),
    'check_return': _t('Time to check your tax return', 'On aika tarkistaa veroilmoitus', 'Dags att granska skattedeklarationen'),
    'decision_pending': _t('Waiting for your tax decision', 'Odotetaan verotuspäätöstä', 'Väntar på ditt skattebeslut'),
    'refund_expected': _t('Tax refund expected', 'Veronpalautus odotettavissa', 'Skatteåterbäring väntas'),
    'back_tax_due': _t('Back taxes to pay', 'Jäännösveroa maksettavana', 'Kvarskatt att betala'),
    'year_end': _t('End of the tax year', 'Verovuosi päättyy', 'Skatteåret tar slut'),
}


@_question('extra.tax', 'extras', _t('How are my taxes looking?', 'Miltä verotilanteeni näyttää?', 'Hur ser det ut med min skatt?'),
           followups=('extra.taxcard', 'extra.vat', 'me.known'),
           keywords=('tax taxes refund back tax withheld decision', 'vero verot veronpalautus jäännösvero pidätys verotuspäätös', 'skatt skatter återbäring kvarskatt'),
           tools=('tax_overview',))
def _extra_tax(env, params):
    result = env.call('tax_overview')
    cycle = result.get('cycle') or {}
    withholding = result.get('withholding') or {}
    lines = []
    if withholding.get('available'):
        lines.append(env.tr(_t('Tax withheld so far this year: about {0}.', 'Veroa pidätetty tänä vuonna noin {0}.', 'Skatt som dragits hittills i år: ungefär {0}.'),
                            env.money(withholding.get('withheld_ytd_cents', 0))))
    else:
        lines.append(env.tr(_t('Your account shows salary after tax, so I need your tax-card rate and gross salary to estimate withholding.',
                               'Tililläsi näkyy palkka verojen jälkeen, joten tarvitsen veroprosenttisi ja bruttopalkkasi pidätyksen arvioimiseen.',
                               'Kontot visar lönen efter skatt, så jag behöver din skattesats och bruttolön för att uppskatta skatteavdraget.')))
    stage = cycle.get('stage')
    if stage in _TAX_STAGES:
        text = env.tr(_TAX_STAGES[stage])
        if cycle.get('next_date'):
            text += ' · ' + env.date(cycle['next_date'])
        lines.append(text + '.')
    plan = result.get('back_tax_plan') or {}
    if plan.get('available') and plan.get('monthly_cents'):
        lines.append(env.tr(_t('Set aside about {0} a month for back taxes.', 'Varaa jäännösveroa varten noin {0} kuukaudessa.', 'Sätt undan ungefär {0} i månaden för kvarskatt.'),
                            env.money(plan['monthly_cents'])))
    if not result.get('has_tax_data'):
        lines.append(env.tr(_t('You can add your tax-card details under Me.', 'Voit lisätä verokorttisi tiedot kohdassa Minä.', 'Du kan lägga till uppgifter från skattekortet under Jag.')))
    env.personal.use('steady')
    value = env.date(cycle['next_date']) if cycle.get('next_date') else '—'
    return _card(env, 'extra.tax', env.tr(_t('Your taxes this year', 'Verosi tänä vuonna', 'Din skatt i år')),
                 env.tr(_t('Next tax date', 'Seuraava veropäivä', 'Nästa skattedatum')), value, None, lines=lines,
                 caveat=env.tr(_t('General information, not tax advice. MyTax is the official source.', 'Yleistä tietoa, ei veroneuvontaa. OmaVero on virallinen lähde.',
                                  'Allmän information, inte skatterådgivning. MinSkatt är den officiella källan.')))


def _rate_text(labels, locale):
    rates = []
    for label in labels or []:
        number = re.sub(r'[^0-9.]', '', str(label))
        rates.append(percent(number, locale) if number else str(label))
    return join(rates, locale)


@_question('extra.vat', 'extras', _t('How much VAT was in my spending?', 'Paljonko ostoksissani oli arvonlisäveroa?', 'Hur mycket moms ingick i mina köp?'),
           pickers=('month',), followups=('extra.tax', 'money.where', 'extra.taxcard'),
           keywords=('vat value added tax in prices', 'alv arvonlisävero', 'moms mervärdesskatt'),
           tools=('vat_in_my_spending',))
def _extra_vat(env, params):
    month = _param_month(env, params)
    result = env.call('vat_in_my_spending', {'month': month}, env.tr(_t('Purchases in {0}', 'Ostokset: {0}', 'Köp i {0}'), env.month_label(month)))
    title = env.tr(_t('VAT inside your purchases in {0}', 'Arvonlisävero ostoksissasi {0}', 'Moms i dina köp i {0}'), env.month_label(month, 'in'))
    if not result.get('available'):
        return _card(env, 'extra.vat', title, env.tr(_t('Estimated VAT', 'Arvioitu alv', 'Uppskattad moms')), '—',
                     lines=[env.tr(_t('I could not estimate VAT for this month.', 'En pystynyt arvioimaan arvonlisäveroa tälle kuulle.', 'Jag kunde inte uppskatta momsen för den här månaden.'))],
                     pickers=[_month_picker(env, month)], params={'month': month}, personal=False)
    lines = [env.tr(_t('{0}: about {1} VAT in {2} of purchases ({3}).', '{0}: ostoksia {2}, joista arvonlisäveroa noin {1} ({3}).', '{0}: ungefär {1} moms i köp för {2} ({3}).'),
                    env.cat(result['category']), env.money(result['estimated_vat_cents']), env.money(result['spending_cents']),
                    _rate_text(result.get('rate_labels'), env.locale)),
             env.tr(_t('VAT is already inside the prices you paid; it is not something you owe.', 'Arvonlisävero sisältyy jo maksamiisi hintoihin; sitä ei tarvitse maksaa erikseen.',
                       'Momsen ingår redan i priserna du betalat; det är inget du är skyldig.'))]
    total = result.get('month_estimated_vat_cents', result['estimated_vat_cents'])
    return _card(env, 'extra.vat', title, env.tr(_t('Estimated VAT this month', 'Arvioitu alv tässä kuussa', 'Uppskattad moms den här månaden')),
                 env.money(total), total, lines=lines, personal=False,
                 caveat=env.tr(_t('An estimate from purchase categories, not a personal tax calculation.', 'Arvio ostosten luokista, ei henkilökohtainen verolaskelma.',
                                  'En uppskattning utifrån köpkategorier, ingen personlig skatteberäkning.')),
                 pickers=[_month_picker(env, month)], params={'month': month})


@_question('extra.baskets', 'extras', _t('Explain the three baskets', 'Selitä kolme koria', 'Förklara de tre korgarna'),
           pickers=('month',), followups=('money.where', 'spend.leaks', 'goals.buffer'),
           keywords=('three baskets explain basket must pays surprise', 'kolme koria kori selitä pakolliset', 'tre korgarna korg förklara måsten'),
           tools=('get_overview', 'explain_concept'))
def _extra_baskets(env, params):
    month = _param_month(env, params)
    env.call('explain_concept', {'topic': 'three baskets'})
    overview = env.call('get_overview', {'month': month}, env.tr(_t('Spending in {0}', 'Kulutus: {0}', 'Utgifter i {0}'), env.month_label(month)))
    baskets = {row['role']: row['amount_cents'] for row in overview['baskets']}
    total = sum(baskets.values())
    lines = ['%s %s: %s.' % (env.tr(BASKETS[role]), env.money(baskets.get(role, 0)), env.tr(BASKET_HELP[role])) for role in BASKETS]
    lines.append(env.tr(_t('Knowing the basket tells you how to plan: hold Must-pays back, keep a buffer for surprises, and choose your Little leaks.',
                           'Kun tiedät korin, tiedät miten suunnitella: varaa pakolliset menot, pidä yllätyspuskuri yllättäviä menoja varten ja valitse pikkumenosi itse.',
                           'När du vet korgen vet du hur du planerar: avsätt fasta måsten, ha en buffert för oväntat och välj dina småutgifter.')))
    chart = {'kind': 'ring', 'data': _bars(env, [(env.tr(BASKETS[role]), baskets.get(role, 0)) for role in BASKETS])}
    return _card(env, 'extra.baskets', env.tr(_t('Your three baskets in {0}', 'Kolme koriasi {0}', 'Dina tre korgar i {0}'), env.month_label(month, 'in')),
                 env.tr(_t('Spending in {0}', 'Menot {0}', 'Utgifter i {0}'), env.month_label(month, 'in')), env.money(total), total,
                 lines=lines, chart=chart, pickers=[_month_picker(env, month)], params={'month': month}, personal=False)


@_question('extra.taxcard', 'extras', _t('What is a tax card?', 'Mikä on verokortti?', 'Vad är ett skattekort?'),
           followups=('extra.tax', 'money.inout', 'me.known'),
           keywords=('what is tax card withholding rate', 'mikä verokortti veroprosentti', 'vad skattekort skattesats'),
           tools=())
def _extra_taxcard(env, params):
    lines = [env.tr(_t('A tax card tells your employer how much tax to withhold from your salary.', 'Verokortti kertoo työnantajallesi, kuinka paljon palkastasi pidätetään veroa.',
                       'Skattekortet talar om för arbetsgivaren hur mycket skatt som ska dras från din lön.')),
             env.tr(_t('It has a base rate, an additional rate and an income limit: income above the limit is taxed at the additional rate.',
                       'Siinä on perusprosentti, lisäprosentti ja tuloraja: rajan ylittävästä tulosta pidätetään lisäprosentin mukaan.',
                       'Det har en grundskattesats, en tilläggsskattesats och en inkomstgräns: inkomst över gränsen beskattas med tilläggssatsen.')),
             env.tr(_t('If your income changes, you can update the card in MyTax so you do not get back taxes later.',
                       'Jos tulosi muuttuvat, voit päivittää verokortin OmaVerossa, jottei jäännösveroa tule myöhemmin.',
                       'Om din inkomst ändras kan du uppdatera kortet i MinSkatt så att du inte får kvarskatt senare.'))]
    for entry in env.personal.tax:
        if entry.get('base_rate_bp') is not None:
            lines.append(env.tr(_t('You told me your base rate is {0}.', 'Kerroit perusprosenttisi olevan {0}.', 'Du berättade att din grundskattesats är {0}.'),
                                env.pct(Decimal(entry['base_rate_bp']) / 100)))
            break
    return _card(env, 'extra.taxcard', env.tr(_t('What a tax card is', 'Mikä verokortti on', 'Vad ett skattekort är')),
                 env.tr(_t('In short', 'Lyhyesti', 'Kort sagt')), env.tr(_t('Your withholding instructions', 'Ohje veron pidättämiseen', 'Instruktion för skatteavdrag')), None,
                 lines=lines, personal=False,
                 caveat=env.tr(_t('General information, not tax advice.', 'Yleistä tietoa, ei veroneuvontaa.', 'Allmän information, inte skatterådgivning.')))


# --------------------------------------------------------------------------- public API

STEADY_STARTERS = ('money.where', 'room.week', 'bills.upcoming', 'goals.buffer', 'me.known', 'extra.baskets')


def catalogue(locale, steady=False):
    """GET /api/catalogue payload: groups with questions in display order, plus 6 starter ids.

    In steady mode the starters never invite saving or cutting back (calmer questions instead).
    """
    if locale not in LOCALES:
        raise ValueError('locale must be en, fi, or sv')
    groups = []
    for gid, title in GROUPS:
        questions = [{'id': q.id, 'text': q.text[locale]} for q in QUESTIONS.values() if q.group == gid]
        groups.append({'id': gid, 'title': title[locale], 'questions': questions})
    return {'groups': groups, 'starters': list(STEADY_STARTERS if steady else STARTERS)}


def _unavailable(env, qid, error):
    return _card(env, qid, QUESTIONS[qid].text[env.locale],
                 env.tr(_t('Not available right now', 'Ei saatavilla juuri nyt', 'Inte tillgängligt just nu')), '—',
                 lines=[env.tr(_t('I could not answer this from your account history for the selected month. Try another month.',
                                  'En pystynyt vastaamaan tähän valitun kuukauden tilihistoriasta. Kokeile toista kuukautta.',
                                  'Jag kunde inte svara på det här utifrån kontohistoriken för den valda månaden. Prova en annan månad.'))],
                 personal=False)


def answer(conn, customer_id, month, question_id, params=None, locale='en'):
    """Build one answer card. Raises ValueError for an unknown question or invalid params."""
    if question_id not in QUESTIONS:
        raise ValueError('Unknown question_id')
    params = params or {}
    if not isinstance(params, dict):
        raise ValueError('params must be an object')
    env = CardEnv(conn, customer_id, month, locale)
    question = QUESTIONS[question_id]
    _validate_params(params)
    try:
        return question.builder(env, params)
    except ValueError as error:
        if _is_param_error(error):
            raise
        env.evidence.clear()
        return _unavailable(env, question_id, error)


_PARAM_ERRORS = ('must', 'Unknown or unsupported', 'outside observed')


def _is_param_error(error):
    return any(part in str(error) for part in _PARAM_ERRORS)


_PARAM_KEYS = {'month', 'category', 'percent', 'amount_cents', 'target_cents', 'target_date', 'name', 'year'}


def _validate_params(params):
    unknown = set(params) - _PARAM_KEYS
    if unknown:
        raise ValueError('Unknown params: ' + ', '.join(sorted(unknown)))
    for key in ('month', 'category', 'target_date', 'name'):
        if key in params and params[key] is not None and not isinstance(params[key], str):
            raise ValueError(key + ' must be text')


# --------------------------------------------------------------------------- free-text matching

_STOP = set('''a an the i me my mine you your we our is am are was were be been do does did can could would should will
of on in at to for from with and or but if what how much many when where which who why this that these those it its
there here about please tell show give get let just some any than then so very really also like want need
mitä mikä miten miksi paljonko kuinka minä minun mun sinä on oli olen ovat ja tai että se ne tämä tässä tällä mitkä
jos kun voi voin voisin minulla minua minun mulla nyt ihan vähän kanssa mutta myös
vad hur mycket många när var vilken vilka jag mig min mitt mina du din är var och eller att det den denna detta
den här kan kunde skulle vill har hade på i av för med om till från så också bara lite'''.split())

_EN_LEMMAS = {'spent': 'spend', 'spending': 'spend', 'spends': 'spend', 'went': 'go', 'goes': 'go', 'gone': 'go', 'going': 'go',
              'saving': 'save', 'saved': 'save', 'saves': 'save', 'savings': 'save', 'bills': 'bill', 'payments': 'payment',
              'purchases': 'purchase', 'transactions': 'transaction', 'goals': 'goal', 'months': 'month', 'taxes': 'tax',
              'leaks': 'leak', 'baskets': 'basket', 'others': 'other', 'paid': 'pay', 'paying': 'pay', 'afford': 'spend'}


def _fold(text):
    return unicodedata.normalize('NFC', text).casefold()


def _tokens(text):
    return re.findall(r"[a-zåäöéü0-9]+", _fold(text))


def _stem(token):
    token = _EN_LEMMAS.get(token, token)
    return token[:6]


def _content_stems(text):
    return [_stem(token) for token in _tokens(text) if token not in _STOP and not token.isdigit()]


def _same(a, b):
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 4 and longer.startswith(shorter)


_SIGNATURES = None


def _signatures():
    global _SIGNATURES
    if _SIGNATURES is None:
        signatures = {}
        for question in QUESTIONS.values():
            stems = set()
            for text in list(question.text.values()) + list(question.keywords):
                stems.update(_content_stems(text))
            signatures[question.id] = stems
        frequency = {}
        for stems in signatures.values():
            for stem in stems:
                frequency[stem] = frequency.get(stem, 0) + 1
        count = len(signatures)
        weights = {stem: math.log(1 + count / frequency[stem]) for stem in frequency}
        _SIGNATURES = (signatures, weights)
    return _SIGNATURES


# Phrase rules: (compiled pattern over the folded message, question id, bonus).
_RULES = [(re.compile(pattern), qid, bonus) for pattern, qid, bonus in (
    (r'\b(safe(ly)?|turvallis\w*|tryggt?)\b', 'room.week', 2.5),
    (r'\b(this week|tällä viikolla|viiko\w*|veckan|vecka)\b', 'room.week', 2.0),
    (r'\b(per day|a day|päivässä|om dagen)\b', 'room.week', 1.0),
    (r'\b(what|how much) can i (safely )?spend\b|\bcan i afford\b|\bpaljonko voin käyttää\b|\bhur mycket kan jag (tryggt )?spendera\b', 'room.week', 4.0),
    (r'\b(money )?leaks?\b|\bvuoto\w*', 'spend.leaks', 3.0),
    (r'\b(did i save|i saved|säästin|säästimme|sparade jag|jag sparade)\b', 'money.inout', 3.5),
    (r'\bwhere\b.*\b(money|go|went)\b|\bmihin\b.*\braha\w*|\bvart\b.*\bpengar\w*|\bminne\b.*\braha\w*', 'money.where', 4.0),
    (r'\bkind of spender\b|\bwhat kind\b|\bmillainen\b.*\b(kuluttaja|rahankäyttäjä)|\bvilken typ\b|\bcareful with money\b|\bspending style\b', 'spend.spender', 4.0),
    (r'\bsave more\b|\bsäästää enemmän\b|\bspara mer\b|\bsave money\b', 'room.save_more', 4.0),
    (r'\bhow much can i save\b|\bpaljonko voin säästää\b|\bhur mycket kan jag spara\b', 'room.save_now', 4.0),
    (r'\b(payday|palkkapäiv\w*|lönedag\w*)\b', 'room.payday', 1.0),
    (r'\b(last|enough|make it|run out|riittä\w*|räcker)\b', 'room.payday', 1.5),
    (r'\b(compare|vertaa\w*|vertaud\w*|jämför\w*)\b.*\b(age|others|people|ikäis\w*|muihin|ålder|andra)\b|\bothers my age\b', 'me.peers', 5.0),
    (r'\b(last|previous) month\b|\bviime kuu\w*|\bedelli\w*|\bförra månaden\b', 'money.compare', 2.0),
    (r'\btax card\b|\bverokortti\w*|\bskattekort\w*', 'extra.taxcard', 5.0),
    (r'\b(refund|back tax\w*|veronpalautu\w*|jäännösver\w*|återbäring|kvarskatt)\b', 'extra.tax', 4.0),
    (r'\b(vat|alv|arvonlisäver\w*|moms)\b', 'extra.vat', 5.0),
    (r'\b(three baskets|basket|kolme kori\w*|kori\w*|korg\w*)\b', 'extra.baskets', 4.0),
    (r'\b(little leaks?|pikkumeno\w*|småutgift\w*)\b', 'spend.leaks', 4.0),
    (r'\b(weekday|viikonpäiv\w*|veckodag\w*)\b', 'spend.weekday', 5.0),
    (r'\b(transactions?|tapahtum\w*|transaktion\w*)\b', 'spend.recent', 3.0),
    (r'\b(biggest|largest|suurim\w*|största)\b', 'spend.biggest', 2.0),
    (r'\b(recurring|subscriptions?|toistuv\w*|tilauks\w*|återkommande|abonnemang)\b', 'bills.recurring', 4.0),
    (r'\b(phone bill|puhelinlasku\w*|telefonräkning\w*|mobilabonnemang\w*)\b', 'bills.recurring', 3.0),
    (r'\b(bills?|laskut|laskuja|räkning\w*)\b.*\b(coming|due|upcoming|tulossa|eräänty\w*|kommer|förfaller)\b', 'bills.upcoming', 4.0),
    (r'\b(when|milloin|när)\b.*\b(payday|paid|salary|palkka\w*|lön\w*)\b', 'bills.payday', 4.0),
    (r'\b(goals?|tavoittee\w*|tavoite|mål)\b', 'goals.progress', 2.0),
    (r'\b(emergency|buffer|cushion|hätävar\w*|puskuri\w*|buffert\w*|nödbuffert)\b', 'goals.buffer', 4.0),
    (r'\b(what if|entä jos|vad händer om)\b|\b(cut|less on|vähemmän|mindre)\b', 'room.cut', 2.5),
    (r'\bknow about me\b|\btiedät minusta\b|\bvet du om mig\b', 'me.known', 5.0),
    (r'\b(year in review|my year|vuosikatsau\w*|vuoteni|årsöversikt|mitt år)\b', 'extra.year', 5.0),
    (r'\b(money in|income|tulot|inkomst\w*)\b', 'money.inout', 2.0),
    (r'\b(how much|paljonko|hur mycket)\b.*\b(on|spend|spent|käytin|kulutin|spenderade|lade)\b', 'money.category', 1.5),
    (r'\b(lately|trend|over time|viime aikoina|på sistone)\b', 'money.trend', 3.0),
)]

_SUPPORT = [
    ('job_loss', re.compile(r"\b(lost my job|lose my job|laid off|unemployed|fired|redundan\w*|menetin työ\w*|työtön|irtisan\w*|lomaut\w*|"
                            r"potku\w*|förlorade (mitt )?jobb\w*|förlorat (mitt )?jobb\w*|mist (mitt )?jobb\w*|arbetslös|uppsagd|permitter\w*|blev av med jobbet)\b")),
    ('baby', re.compile(r"\b(baby|pregnant|expecting a child|vauva\w*|raskaana|odotamme lasta|bebis|gravid|väntar barn)\b")),
    ('separation', re.compile(r"\b(divorce\w*|separat\w*|break.?up|avioer\w*|erosimme|eroamme|ero|skilsmässa|skiljer oss|separera\w*)\b")),
    ('illness', re.compile(r"\b(ill|illness|sick|hospital|diagnos\w*|sairas\w*|sairaala\w*|sjuk\w*)\b")),
    ('distress', re.compile(r"\b(stress\w*|worried|worry|anxious|anxiety|scared|afraid|panic\w*|broke|overwhelm\w*|can't cope|"
                            r"huoli\w*|huolissani|huolestu\w*|ahdist\w*|pelotta\w*|rahat loppu\w*|persaukinen|"
                            r"orolig|oro|ängslig|rädd|pank|panik)\b")),
]
_SUPPORT_TEXT = {
    'job_loss': _t('I am sorry to hear that. Let us make sure the essentials are covered first; you do not have to sort everything out today.',
                   'Ikävä kuulla. Varmistetaan ensin, että välttämättömät menot on katettu. Kaikkea ei tarvitse ratkaista tänään.',
                   'Vad tråkigt att höra. Låt oss först se till att det nödvändiga är täckt; du behöver inte lösa allt i dag.'),
    'baby': _t('Congratulations! A baby changes a lot, and planning a little ahead makes it easier.',
               'Onnea! Vauva muuttaa paljon, ja pieni ennakkosuunnittelu helpottaa.',
               'Grattis! En bebis förändrar mycket, och lite framförhållning gör det lättare.'),
    'separation': _t('That is a big change. We can look at what is coming up and what you can count on, one step at a time.',
                     'Se on iso muutos. Katsotaan yhdessä, mitä on tulossa ja mihin voit luottaa, askel kerrallaan.',
                     'Det är en stor förändring. Vi kan titta på vad som väntar och vad du kan räkna med, ett steg i taget.'),
    'illness': _t('I am sorry you are dealing with that. Let us keep things simple and check that the essentials are covered.',
                  'Ikävä kuulla. Pidetään asiat yksinkertaisina ja varmistetaan, että välttämättömät menot on katettu.',
                  'Vad tråkigt. Låt oss hålla det enkelt och se till att det nödvändiga är täckt.'),
    'distress': _t('Money worries are hard. Let us look at one clear thing at a time, starting with what is safe until payday.',
                   'Rahahuolet ovat raskaita. Katsotaan yksi selkeä asia kerrallaan, aloitetaan siitä, mikä riittää palkkapäivään.',
                   'Pengaoro är tungt. Låt oss ta en tydlig sak i taget och börja med vad som räcker till lönedagen.'),
}
_SUPPORT_QUESTIONS = {
    'job_loss': ('room.week', 'goals.buffer', 'me.life_change'),
    'baby': ('me.life_change', 'goals.buffer', 'room.save_now'),
    'separation': ('bills.upcoming', 'room.week', 'me.life_change'),
    'illness': ('room.week', 'bills.upcoming', 'me.life_change'),
    'distress': ('room.week', 'bills.upcoming', 'goals.buffer'),
}
_SMALLTALK = re.compile(r"^\s*(ok(ay)?|thanks?|thank you|thx|cool|great|nice|hi|hello|hey|kiitos|kiitti|moi|hei|tack|hej|okej|bra|super)"
                        r"([\s,!.]+(ok(ay)?|thanks?|thank you|so much|kiitos|paljon|tack|så mycket|då))*[\s!.]*$")

_MONTH_WORDS = (('january', 'jan', 'tammik', 'januari'), ('february', 'feb', 'helmik', 'februari'), ('march', 'mar', 'maalisk', 'mars'),
                ('april', 'apr', 'huhtik'), ('may', 'toukok', 'maj'), ('june', 'jun', 'kesäk', 'juni'), ('july', 'jul', 'heinäk', 'juli'),
                ('august', 'aug', 'elok', 'augusti'), ('september', 'sep', 'syysk'), ('october', 'oct', 'lokak', 'oktober'),
                ('november', 'nov', 'marrask'), ('december', 'dec', 'jouluk'))


def _month_number(token):
    for index, words in enumerate(_MONTH_WORDS):
        for word in words:
            if token == word or (len(word) >= 5 and token.startswith(word)):
                return index + 1
    return None


def _category_from(text):
    from .query_scope import CATEGORY_TERMS
    folded = _fold(text)
    extra = (('Groceries', ('food', 'mat', 'ruoka', 'ruuat', 'ruokaan')),)
    for category, terms in tuple(CATEGORY_TERMS) + extra:
        for term in terms:
            if re.search(r'(?<![a-zåäö])' + re.escape(term), folded):
                if term in ('mat', 'food', 'bio', 'spel', 'resa') and not re.search(r'(?<![a-zåäö])' + re.escape(term) + r'(?![a-zåäö])', folded):
                    continue
                return category
    return None


def extract_amount_date(message, locale='en', today=None):
    """Find a money amount and a target date in free text.

    Examples: "save €2,000 for a trip by June", "säästää 3000 euroa kesäkuuhun mennessä",
    "spara 5 000 kr till nästa sommar". Returns {'amount_cents': int|None,
    'target_date': ISO date|None, 'name': str|None}. Month targets resolve to the last
    day of the next such month after ``today`` (ISO date string or date; default today).
    """
    if isinstance(today, str):
        today = date.fromisoformat(today)
    today = today or date.today()
    text = _fold(message)
    amount = None
    pattern = re.compile(r'(?:€|eur\s*)?\s*(\d{1,3}(?:[ ,. ]\d{3})+|\d+)(?:[.,](\d{1,2}))?\s*(k\b|t\b|tuhatta|tusen|thousand)?\s*(€|eur\w*|e\b|euro\w*)?')
    for match in pattern.finditer(text):
        whole, fraction, thousand, unit = match.groups()
        prefix_euro = '€' in match.group(0)[:2] or match.group(0).lstrip().startswith('eur')
        if not (unit or prefix_euro or thousand):
            continue
        digits = re.sub(r'[ ,. ]', '', whole)
        cents = int(digits) * 100 + (int((fraction or '0').ljust(2, '0')) if fraction and not thousand else 0)
        if thousand:
            cents *= 1000
        if 0 < cents <= 10_000_000_000:
            amount = cents
            break
    target = None
    months_ahead = re.search(r'\b(?:in|within|om|inom)\s+(\d{1,2})\s+(months?|månader|månad)\b|\b(\d{1,2})\s+(?:kuukauden|kuukaudessa|kk)\b', text)
    if months_ahead:
        count = int(months_ahead.group(1) or months_ahead.group(3))
        year, month = today.year + (today.month - 1 + count) // 12, (today.month - 1 + count) % 12 + 1
        target = date(year, month, 1)
    elif re.search(r'\b(next summer|this summer|by summer|ensi kesä\w*|kesään|kesäksi|nästa sommar|till sommaren|i sommar)\b', text):
        year = today.year + (1 if today.month >= 6 else 0)
        target = date(year, 6, 1)
    elif re.search(r'\b(christmas|joulu\w*|jul)\b', text):
        target = date(today.year if today < date(today.year, 12, 1) else today.year + 1, 12, 1)
    elif re.search(r'\b(next year|ensi vuo\w*|nästa år)\b', text):
        target = date(today.year + 1, 12, 31)
    elif re.search(r'\b(in a year|within a year|vuoden päästä|vuodessa|om ett år)\b', text):
        target = date(today.year + 1, today.month, 1)
    else:
        for token_match in re.finditer(r'[a-zåäö]+', text):
            token = token_match.group(0)
            number = _month_number(token)
            if not number:
                continue
            if len(token) <= 3 and not re.search(r'\b(by|until|till|before|in|i|före)\s+' + token + r'\b', text):
                continue
            year_match = re.search(r'\b' + token + r'\w*\s+(20\d\d)\b', text)
            year = int(year_match.group(1)) if year_match else today.year + (1 if number <= today.month else 0)
            target = date(year, number, 1)
            break
    if target is not None and target.day == 1:
        target = date(target.year + (target.month == 12), target.month % 12 + 1, 1) - timedelta(days=1)
    name = None
    original = ' '.join(message.split())
    found = re.search(r'\bfor (?:a |an |the |my )?(.+?)(?:\s+(?:by|before|until|in|next|this|within)\b|[.?!,]|$)', original, re.I)
    if found:
        candidate = found.group(1).strip()
        if candidate and not re.match(r'^\d', candidate) and len(candidate) <= 60:
            name = candidate[:1].upper() + candidate[1:]
    if name is None:
        sv = re.search(r'\btill (?:en |ett )?([a-zåäö][\wåäö -]{2,40}?)(?:\s+(?:till|före|innan|nästa|om)\b|[.?!,]|$)', original, re.I)
        if sv and locale == 'sv':
            name = sv.group(1).strip().capitalize()
    return {'amount_cents': amount, 'target_date': target.isoformat() if target else None, 'name': name}


def _param_hints(message, today):
    """Optional pickers prefilled from the message: category, month, percent."""
    hints = {}
    category = _category_from(message)
    if category:
        hints['category'] = category
    folded = _fold(message)
    pct = re.search(r'(\d{1,2}(?:[.,]\d)?)\s*(%|percent|prosent\w*|procent)', folded)
    if pct:
        hints['percent'] = float(pct.group(1).replace(',', '.')) if '.' in pct.group(1) or ',' in pct.group(1) else int(pct.group(1))
    for token in re.findall(r'[a-zåäö]+', folded):
        number = _month_number(token)
        if number and token not in ('mar', 'may', 'maj', 'jul', 'jun', 'apr', 'aug', 'sep', 'oct', 'nov', 'dec', 'jan', 'feb'):
            year = today.year if number <= today.month else today.year - 1
            hints['month'] = '%04d-%02d' % (year, number)
            break
    return hints


def match_message(message, locale='en', *, today=None, observed=None):
    """Rank catalogue questions for free text; never answers.

    Returns {'suggestions': [{id, text, params?}] (max 3), 'supportive': str|None,
    'intent_hint': str|None, 'confident': bool}. ``confident`` is True only when the
    top question clearly beats the rest (used by the agent fallback).
    """
    if locale not in LOCALES:
        raise ValueError('locale must be en, fi, or sv')
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        raise ValueError('A message of one to two thousand characters is required')
    today = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    folded = _fold(message)
    signatures, weights = _signatures()
    stems = _content_stems(message)
    scores = {}
    for qid, signature in signatures.items():
        score = 0.0
        for stem in set(stems):
            best = max((weights[s] for s in signature if _same(stem, s)), default=0.0)
            score += best
        scores[qid] = score
    for pattern, qid, bonus in _RULES:
        if pattern.search(folded):
            scores[qid] += bonus
    supportive, hint, support_kind = None, None, None
    for kind, pattern in _SUPPORT:
        if pattern.search(folded):
            support_kind = kind
            break
    goal = extract_amount_date(message, locale, today)
    wants_goal = bool(re.search(r'\b(save|saving|säästä\w*|spara)\b.*\b(for|by|until|johonkin|varten|till|mennessä)\b', folded)) and (goal['amount_cents'] or goal['target_date'])
    hints = _param_hints(message, today)
    if observed:
        if hints.get('month') and not observed[0][:7] <= hints['month'] <= observed[1][:7]:
            hints.pop('month')
    ranked = sorted(scores.items(), key=lambda item: (-item[1], list(QUESTIONS).index(item[0])))
    chosen = []
    if support_kind:
        supportive = _SUPPORT_TEXT[support_kind][locale]
        hint = 'life_event' if support_kind in ('job_loss', 'baby', 'separation', 'illness') else 'distress'
        chosen = list(_SUPPORT_QUESTIONS[support_kind])
    elif wants_goal or (goal['amount_cents'] and re.search(r'\b(save|säästä\w*|spara)\b', folded)):
        hint = 'goal'
        chosen = ['goals.new', 'room.save_now', 'goals.progress']
    elif _SMALLTALK.match(folded) or not stems:
        hint = 'smalltalk'
        chosen = list(STARTERS[:3])
    else:
        chosen = [qid for qid, score in ranked if score >= 1.5][:3]
        if hints.get('category') and 'money.category' not in chosen and not any(q in chosen for q in ('room.cut', 'room.save_more', 'me.peers')):
            chosen = (['money.category'] + chosen)[:3]
        if not chosen:
            hint = 'unknown'
            chosen = list(STARTERS[:3])
    suggestions = []
    for qid in chosen[:3]:
        question = QUESTIONS[qid]
        entry = {'id': qid, 'text': question.text[locale]}
        params = {}
        if qid == 'goals.new':
            params = {key: value for key, value in (('amount_cents', goal['amount_cents']), ('target_date', goal['target_date']), ('name', goal['name'])) if value}
        else:
            for key in ('category', 'month', 'percent'):
                if key in hints and key in question.pickers:
                    if key == 'category' and qid in ('room.cut', 'room.save_more') and hints[key] not in CUTTABLE:
                        continue
                    if key == 'category' and qid == 'me.peers' and hints[key] not in PEER_CATEGORIES:
                        continue
                    params[key] = hints[key]
        if params:
            entry['params'] = params
        suggestions.append(entry)
    top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    exact = any(_fold(re.sub(r'[?!.]+$', '', text)).strip() == re.sub(r'[?!.]+$', '', folded).strip()
                for question in QUESTIONS.values() for text in question.text.values())
    confident = bool(not support_kind and hint is None and suggestions and suggestions[0]['id'] == top[0] and
                     (exact or (top[1] >= 6 and top[1] >= 2 * max(second, 0.1))))
    return {'suggestions': suggestions, 'supportive': supportive, 'intent_hint': hint, 'confident': confident}


def fallback_response(conn, customer_id, month, locale, message, reason, scope=None):
    """Offline answer for /api/agent: closest catalogue questions, never a guessed answer.

    A card is attached only when the match is unambiguous and the question needs no
    customer-chosen parameters.
    """
    ctx_scope = None
    try:
        env_scope = ToolContext(conn, customer_id, month)
        ctx_scope = env_scope.scope
        today = env_scope.reference_date
    except ValueError:
        today = None
    matched = match_message(message, locale, today=today, observed=(ctx_scope['observed_start'], ctx_scope['observed_end']) if ctx_scope else None)
    card = None
    if matched['confident']:
        top = matched['suggestions'][0]
        question = QUESTIONS[top['id']]
        params = top.get('params') or {}
        if not question.required or all(params.get(key) for key in question.required):
            try:
                card = answer(conn, customer_id, month, top['id'], params, locale)
            except ValueError:
                card = None
    return {'source': 'catalogue', 'fallback_reason': reason, 'supportive': matched['supportive'],
            'suggestions': matched['suggestions'], 'intent_hint': matched['intent_hint'], 'card': card,
            'answer': [], 'highlight': None, 'chart': None, 'steps': [], 'evidence': [], 'actions': [],
            'scope': scope}


# --------------------------------------------------------------------------- AI path: tool calls -> cards

def _month_of(start, end):
    if isinstance(start, str) and isinstance(end, str) and len(start) == 10 and start[:7] == end[:7]:
        return start[:7]
    return None


def question_for_tool(name, args):
    """Map one model tool call to (question_id, params) or None."""
    args = args or {}
    if name == 'get_overview':
        return 'money.where', {k: v for k, v in (('month', args.get('month')),) if v}
    if name == 'spending_total' and args.get('category') and not ({'role', 'transaction_type', 'mcc_code', 'merchant_id'} & set(args)):
        month = _month_of(args.get('start'), args.get('end'))
        return ('money.category', {'category': args['category'], **({'month': month} if month else {})}) if month else None
    if name == 'compare_periods':
        month = _month_of(args.get('start'), args.get('end'))
        previous = _month_of(args.get('comparison_start'), args.get('comparison_end'))
        if month and previous == shift_month(month, -1) and not args.get('category'):
            return 'money.compare', {'month': month}
        return None
    if name == 'monthly_trend':
        return 'money.trend', {k: v for k, v in (('category', args.get('category')), ('month', args.get('end_month'))) if v}
    if name == 'safe_to_spend':
        return 'room.week', {}
    if name == 'safe_to_save':
        return 'room.save_now', {}
    if name == 'forecast_30_days':
        return 'room.payday', {}
    if name == 'what_if_reduce':
        return 'room.cut', {k: v for k, v in (('category', args.get('category')), ('percent', args.get('percent')), ('month', args.get('month'))) if v is not None}
    if name == 'goal_plan':
        return 'goals.new', {'name': args.get('name'), 'amount_cents': args.get('target_cents'), 'target_date': args.get('target_date')}
    if name == 'list_goals':
        return 'goals.progress', {}
    if name == 'payday_pattern':
        return 'bills.payday', {}
    if name == 'recurring_payments':
        return 'bills.recurring', {}
    if name == 'spender_profile':
        return 'spend.spender', {}
    if name == 'irregular_buffer':
        return 'goals.buffer', {}
    if name == 'explore':
        if args.get('group_by') == 'weekday' and not args.get('category'):
            return 'spend.weekday', {}
        if args.get('group_by') == 'category' and args.get('role') == 'discretionary':
            return 'spend.leaks', {}
        return None
    if name == 'cashflow_summary':
        end = args.get('end_month')
        return 'money.inout', ({'month': end} if isinstance(end, str) else {})
    if name == 'get_profile':
        return 'me.known', {}
    if name == 'compare_to_peers':
        return 'me.peers', {'category': args.get('category')}
    if name == 'vat_in_my_spending':
        return 'extra.vat', {k: v for k, v in (('month', args.get('month')),) if v}
    if name == 'year_review':
        return 'extra.year', {'year': args.get('year')}
    if name == 'tax_overview':
        return 'extra.tax', {}
    if name == 'explain_concept' and isinstance(args.get('topic'), str) and args['topic'].strip().casefold() == 'three baskets':
        return 'extra.baskets', {}
    return None


def cards_for_tool_calls(conn, customer_id, month, locale, calls, limit=2):
    """Cards for successful model tool calls [(name, args)], same builders as offline. Never raises."""
    cards, seen = [], set()
    for name, args in calls:
        mapped = question_for_tool(name, args)
        if not mapped or mapped[0] in seen:
            continue
        qid, params = mapped
        params = {key: value for key, value in params.items() if value is not None}
        try:
            card = answer(conn, customer_id, month, qid, params, locale)
        except (ValueError, TypeError, KeyError):
            continue
        if card['headline']['value_text'] == '—' and not card['evidence']:
            continue
        seen.add(qid)
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards
