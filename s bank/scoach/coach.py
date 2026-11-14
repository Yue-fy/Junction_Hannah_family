"""Deterministic coaching with a bounded, validated optional language adapter."""
import json
import os
import queue
import re
import threading
from typing import TypedDict
from .gemini import MODEL_TIMEOUT_SECONDS, minimized_context, rest_transport, sanitize_user_message, validate_response
from .query_scope import (
    resolve_statistics, resolve_period, clarify, is_vat_question, has_reduction_verb,
    is_exploratory_goal, resolve_cashflow_parameters, resolve_investment_parameters,
    has_current_safe_to_spend_scope, planning_request, MONTHS,
)
from .percentages import parse_percentage
from .money import euros_to_cents, cents_to_euros


class CoachResponse(TypedDict):
    intent: str
    parameters: dict
    selected_candidate_id: str | None
    needs_clarification: bool
    clarification_question: str | None
    proposed_action: dict | None
    explanation_blocks: list[dict]
    source: str
    fallback_reason: str | None
    locale: str
    response_language_source: str
    offline_language_limitation: str | None


def rank_candidates(candidates, goal=None):
    goal_id = goal.get('id') if isinstance(goal, dict) else goal
    def score(candidate):
        relevance = 1 if goal_id and candidate.get('goal_id') == goal_id else 0
        dimensions = sum(float(candidate.get(key, 0) or 0) * weight for key, weight in [('materiality', 4), ('urgency', 3), ('explainability', 2), ('addressability', 1)])
        return (-relevance, -dimensions, str(candidate['id']))
    return sorted((dict(item) for item in candidates), key=score)


def _statistics_category(text):
    groups = [
        ('Transportation', ['taxi', 'taxis', 'transportation', 'taks', 'kuljetus', 'transport']),
        ('Restaurants', ['restaurant', 'dining', 'eating out', 'ravintol', 'restaurang']),
        ('Groceries', ['grocer', 'food shopping', 'ruokaostos', 'ruokaost', 'elintarvik', 'matvar', 'matinköp', 'livsmedel']),
        ('Entertainment', ['entertainment', 'cinema', 'movie', 'games', 'viih', 'elokuv', 'pelit', 'underhållning', 'nöje', 'bio', 'spel']),
        ('Health', ['health', 'medical', 'doctor', 'dentist', 'pharmacy', 'tervey', 'lääkäri', 'hammaslääkäri', 'apteek', 'häls', 'läkare', 'tandläkare', 'apotek']),
        ('Home & Tech', ['home & tech', 'home appliance', 'appliance', 'electronics', 'washing machine', 'koti ja tekniikka', 'kodinkone', 'elektroniikka', 'pesukone', 'hem och teknik', 'hemelektronik', 'vitvar', 'tvättmaskin']),
        ('Housing', ['housing', 'rent', 'asumismen', 'vuokra', 'boende', 'hyra']),
        ('Lifestyle', ['lifestyle', 'shopping', 'ostokset', 'ostoksiin', 'clothes', 'clothing', 'fashion', 'elämäntyyli', 'vaatte', 'muoti', 'livsstil', 'kläder']),
        ('Travel', ['travel', 'flight', 'hotel', 'matkail', 'matkamen', 'lento', 'hotelli', 'resor', 'resa', 'flyg', 'hotell']),
        ('Utilities', ['utilities', 'electricity', 'water bill', 'phone bill', 'sähkö', 'vesilask', 'puhelinlask', 'käyttölask', 'elräkning', 'vattenräkning', 'telefonräkning']),
    ]
    for category, words in groups:
        if any(
            re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text)
            if word in {'rent', 'shopping', 'ostokset', 'ostoksiin'} else word in text
            for word in words
        ):
            return category
    return None


def _adjustment_percent(text):
    try:
        return parse_percentage(text)
    except ValueError:
        return None


def _tax_planning_request(text):
    tax = re.search(r'\b(?:tax(?:es)?|vero\w*|skatt\w*)\b', text)
    planning = re.search(r'\b(?:plan(?:ning)?|budget(?:ing)?|set aside|put aside|save for|'
                         r'suunnit\w*|varata|varaan|sääst\w*|planera|budgetera|lägga undan|sätta undan)\b', text)
    recorded = re.search(r'\b(?:did i pay|have i paid|paid|maksoin|betalade|betalat)\b', text)
    return bool(tax and planning and not recorded)


def _tax_liability_request(text):
    tax = re.search(r'\b(?:tax(?:es)?|vero\w*|skatt\w*)\b', text)
    liability = re.search(r'\b(?:owes?|owed|liability|liable|should i pay|must i pay|tax bill|'
                          r'velkaa|verovelka\w*|verovelvoll\w*|(?:minun )?(?:pitää|täytyy|tulee) maksaa|'
                          r'skyldig|skatteskuld\w*|(?:ska|måste|behöver) jag betala)\b', text)
    return bool(tax and liability and not is_vat_question(text) and not _tax_planning_request(text))


def _planned_cost(message):
    """Accept one exact euro total, never a range, bare number or partial token."""
    text = message.casefold().replace('’', "'")
    amount = r'\d+(?:[.,]\d{1,2})?'
    currency = r'(?:€|(?<![a-z])(?:eur|euros?|euroa)(?![a-z]))'
    matches = list(re.finditer(r'(?:' + currency + r'\s*(?P<before>' + amount + r')|(?P<after>' + amount + r')\s*' + currency + r')', text))
    if len(matches) != 1 or re.search(r'[$£]|\b(?:usd|gbp|dollars?|pounds?)\b', text):
        return None
    if re.search(r'\b(?:each|per person|excluding|without|after refunds|before tax|discount|ilman|per henkilö|exklusive|per person)\b', text):
        return None
    match = matches[0]
    before, after = text[:match.start()], text[match.end():]
    if re.search(r'[\d.,+\-−–—]\s*$', before) or re.match(r'\s*[\d,\-−–—]|\.\d', after):
        return None
    if re.search(r'\b(?:under|over|about|around|between|less than|more than|at most|up to|alle|yli|noin|under|över|ungefär)\s*$', before):
        return None
    # Other quantities are safe only when they are an explicit ISO date. This
    # prevents a multi-item price or a range without a repeated currency sign.
    remaining = before + ' ' + after
    remaining = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', remaining)
    remaining = re.sub(r'\b(?:in|next|last|past|within|over|for)\s+(?:the\s+)?(?:next\s+)?\d+\s+(?:hours?|days?|weeks?|months?|years?)\b', '', remaining)
    if re.search(r'\d', remaining):
        return None
    return euros_to_cents((match['before'] or match['after']).replace(',', '.'))


def _planned_response(message, context):
    topic = planning_request(message)
    if not topic:
        return None
    locale = context.get('interface_locale', context.get('locale', 'en'))
    def copy(en, fi, sv):
        return {'en': en, 'fi': fi, 'sv': sv}[locale]
    base = {'intent': 'safe_to_spend', 'parameters': {}, 'selected_candidate_id': None,
            'proposed_action': None, 'explanation_blocks': []}
    if topic == 'mixed':
        return {**base, **clarify(context, 'mixed_request',
            'Would you like to plan the purchase first, or review earlier spending? I will keep the planning dates and the history period separate.',
            'Haluatko ensin suunnitella ostosta vai tarkastella aiempia menoja? Pidän suunnitelman ja historian ajanjaksot erillään.',
            'Vill du planera köpet först eller granska tidigare utgifter? Jag håller planens datum och historikens period åtskilda.')}
    cost = _planned_cost(message)
    if topic in {'commitment', 'wish'} or (cost is not None and cost > 50000):
        return {**base, 'intent': 'plan_goal', **clarify(context, 'planned_commitment',
            'Let’s make room for that plan. A weekly spending estimate is too limited for a larger or recurring commitment. What would you like to work out first: the overall budget or a monthly saving amount?',
            'Tehdään tälle suunnitelmalle tilaa. Viikon käyttövara ei riitä suuren tai toistuvan menon arviointiin. Haluatko ensin miettiä kokonaisbudjettia vai kuukausittaista säästösummaa?',
            'Vi kan skapa utrymme för den planen. En veckas spenderingsutrymme räcker inte för att bedöma ett större eller återkommande åtagande. Vill du börja med totalbudgeten eller ett månatligt sparbelopp?'),
            'clarification_options': [copy('I want to save for a goal', 'Haluan säästää tavoitetta varten', 'Jag vill spara till ett mål')]}
    subjects = {
        'movie': ('the movie, including any travel or snacks', 'elokuvaan, mahdollisiin matkoihin ja herkkuihin', 'biobesöket, inklusive eventuell resa och snacks'),
        'meal': ('the meal, including any travel', 'ruokailuun ja mahdollisiin matkoihin', 'måltiden, inklusive eventuell resa'),
        'coffee': ('the café visit', 'kahvilakäyntiin', 'kafébesöket'),
        'groceries': ('this grocery shop', 'näihin ruokaostoksiin', 'de här matinköpen'),
        'clothes': ('the clothes', 'vaatteisiin', 'kläderna'),
        'outing': ('the outing, including any extras', 'menoon ja mahdollisiin lisäkuluihin', 'utflykten, inklusive eventuella extra kostnader'),
    }
    subject = subjects[topic]
    if cost is None:
        without_dates = re.sub(r'\b\d{4}-\d{2}(?:-\d{2})?\b', '', message.casefold())
        if re.search(r'\d|[€$£]|\b(?:eur|euro\w*|usd|gbp|dollars?|pounds?)\b', without_dates):
            return {**base, **clarify(context, 'planned_purchase_price',
                'Please restate the plan with one total budget in euros, including any extras. I cannot compare a range, an amount per person, or a price in another currency.',
                'Kerro suunnitelma uudelleen käyttäen yhtä kokonaisbudjettia euroina, lisäkulut mukaan lukien. En voi verrata vaihteluväliä, henkilökohtaista hintaa tai muuta valuuttaa.',
                'Beskriv planen igen med en totalbudget i euro, inklusive extra kostnader. Jag kan inte jämföra ett intervall, ett pris per person eller en annan valuta.')}
        return {**base, **clarify(context, 'planned_purchase_cost',
            f'How much would you like to budget in total for {subject[0]}? Please give one amount in euros.',
            f'Kuinka paljon haluaisit budjetoida yhteensä {subject[1]}? Anna yksi summa euroina.',
            f'Hur mycket vill du budgetera totalt för {subject[2]}? Ange ett belopp i euro.')}
    text = message.casefold()
    # This bounded preview uses the supplied account snapshot. A different
    # calendar window cannot silently become its seven-day modeled allowance.
    named_month = any(re.search(r'(?<!\w)' + re.escape(term) + (r'uu\w*' if term.endswith('k') else r'(?!\w)'), text)
                      for terms in MONTHS for term in terms)
    if named_month or re.search(
        r'\b\d{4}-\d{2}(?:-\d{2})?\b|\b(?:next|last|this) (?:month|year)|'
        r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend\w*|today|tonight|tomorrow|yesterday|payday|paycheck)\b|'
        r'\b(?:in|next|last|past|coming|following|within|over|for)\s+(?:the\s+)?(?:next\s+)?'
        r'(?:(?:\d+|a|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+)?(?:hours?|days?|weeks?|months?|years?)\b|'
        r'\b(?:maanantai\w*|tiistai\w*|keskiviik\w*|torstai\w*|perjantai\w*|lauantai\w*|sunnuntai\w*|viikonlopp\w*|palkkapäiv\w*|huomenna|tänään|eilen)\b|'
        r'(?:ennen|kunnes)\s+(?:seuraavaa\s+)?palk\w*|palk\w*\s+(?:asti|mennessä|jälkeen)|'
        r'ensi kuussa|viime kuussa|tässä kuussa|tänä kuukautena|ensi viikolla|viime viikolla|tänä iltana|'
        r'\b(?:måndag\w*|tisdag\w*|onsdag\w*|torsdag\w*|fredag\w*|lördag\w*|söndag\w*|helg\w*|imorgon|idag|ikväll)\b|'
        r'(?:före|innan|till)\s+(?:nästa\s+)?lön\w*|nästa månad|förra månaden|den här månaden|denna månad|nästa vecka|förra veckan|i morgon|i dag|i kväll',
        text,
    ):
        return {**base, **clarify(context, 'planned_purchase_timing',
            'I can compare a small purchase with the seven-day estimate after the selected account snapshot. For that different date, would you like to build a saving plan instead?',
            'Voin verrata pientä ostosta valitun tilinäkymän jälkeisen viikon arvioon. Haluatko tehdä säästösuunnitelman tätä muuta ajankohtaa varten?',
            'Jag kan jämföra ett mindre köp med uppskattningen för veckan efter den valda kontobilden. Vill du göra en sparplan för det andra datumet i stället?'),
            'clarification_options': [copy('I want to save for a goal', 'Haluan säästää tavoitetta varten', 'Jag vill spara till ett mål')]}
    candidate = next((item for item in context.get('candidates', []) if item.get('kind') == 'safe_to_spend'), None)
    references = candidate.get('fact_ids', []) if candidate else []
    fact = next((item for item in context.get('facts', []) if item.get('id') in references), None)
    allowance = fact.get('value_cents') if fact else None
    available = candidate and candidate.get('available', True) and fact and fact.get('available', True) and type(allowance) is int
    reference = context.get('reference_date')
    if not available or not reference:
        narrative = copy(
            'I do not have enough account history to compare this plan with a reliable spending estimate. We can keep the budget as a wish and check upcoming bills before deciding.',
            'Tilihistoria ei vielä riitä suunnitelman vertaamiseen luotettavaan käyttövara-arvioon. Voimme säilyttää budjetin toiveena ja tarkistaa tulevat laskut ennen päätöstä.',
            'Kontohistoriken räcker inte för att jämföra planen med en tillförlitlig uppskattning. Vi kan behålla budgeten som en önskan och kontrollera kommande räkningar före beslutet.')
    else:
        amount, budget = cents_to_euros(cost), cents_to_euros(allowance)
        difference = cents_to_euros(abs(allowance - cost))
        if allowance == 0 and cost > 0:
            narrative = copy(
                f'Using the account snapshot dated {reference}, the modeled seven-day allowance is €0.00, so this €{amount} plan has no room in the estimate. Review upcoming bills or a later date before choosing a new budget.',
                f'Tilinäkymän {reference} perusteella mallinnettu viikon käyttövara on 0.00 euroa, joten {amount} euron suunnitelmalle ei ole tilaa arviossa. Tarkista tulevat laskut tai myöhempi ajankohta ennen uuden budjetin valintaa.',
                f'Med kontobilden från {reference} är det modellerade veckoutrymmet 0.00 euro, så planen på {amount} euro ryms inte i uppskattningen. Granska kommande räkningar eller ett senare datum innan du väljer en ny budget.')
        elif cost <= allowance:
            narrative = copy(
                f'Using the account snapshot dated {reference}, your €{amount} plan fits within the modeled seven-day allowance of €{budget}, leaving €{difference}.',
                f'Tilinäkymän {reference} perusteella {amount} euron suunnitelmasi mahtuu mallinnettuun viikon {budget} euron käyttövaraan. Jäljelle jäisi {difference} euroa.',
                f'Med kontobilden från {reference} ryms din plan på {amount} euro inom det modellerade veckoutrymmet på {budget} euro. Då återstår {difference} euro.')
        else:
            narrative = copy(
                f'Using the account snapshot dated {reference}, your €{amount} plan exceeds the modeled seven-day allowance of €{budget} by €{difference}. A smaller budget or more time would give this plan more room.',
                f'Tilinäkymän {reference} perusteella {amount} euron suunnitelmasi ylittää mallinnetun viikon {budget} euron käyttövaran {difference} eurolla. Pienempi budjetti tai lisäaika antaisi suunnitelmalle enemmän tilaa.',
                f'Med kontobilden från {reference} överstiger din plan på {amount} euro det modellerade veckoutrymmet på {budget} euro med {difference} euro. En mindre budget eller mer tid skulle ge planen mer utrymme.')
        narrative += ' ' + copy(
            'The calculation deducts the reserve and expected costs before showing spending room. This is a planning comparison with recorded history; your current balance and upcoming bills may be different.',
            'Laskelma vähentää vararahat ja ennakoidut menot ennen käyttövaran näyttämistä. Vertailu perustuu kirjattuun historiaan; nykyinen saldosi ja tulevat laskusi voivat olla erilaisia.',
            'Beräkningen drar av bufferten och förväntade utgifter innan spenderingsutrymmet visas. Jämförelsen bygger på registrerad historik; ditt aktuella saldo och kommande räkningar kan vara annorlunda.')
    return {**base, 'parameters': {key: context[key] for key in ('reference_date', 'days') if key in context},
            'selected_candidate_id': candidate['id'] if candidate else None,
            'needs_clarification': False, 'clarification_question': None, 'clarification_options': [],
            'clarification_code': 'planned_purchase_preview', 'query_scope': None,
            'explanation_blocks': [{'text': narrative, 'fact_ids': references}] if references else []}


def _relevant_explanation(message, candidate):
    """A ranked insight is useful only after the user asked about that subject."""
    text = ' '.join(message.casefold().split()).rstrip('.?!')
    if any(term in text for term in ('balance', 'saldo')):
        return False
    asked = bool(re.search(r'\b(?:explain|changed?|happened|pattern|overview|why|increased?|decreased?|rose|fell)\b|'
                          r'selitä|muuttu|kasvo|vähen|förklara|förändr|ökad|minskad', text))
    if not asked:
        return False
    if any(term in text for term in ('salary', 'palkka', 'lön')):
        return candidate.get('kind') == 'salary_change'
    if any(term in text for term in ('payday', 'palkkapäiv', 'lönedag')):
        return candidate.get('kind') == 'payday_timing'
    if any(term in text for term in ('unusual', 'uncommon', 'epätavalli', 'ovanlig')):
        return candidate.get('kind') == 'explain_change' and 'restaurant' not in candidate['id']
    if _statistics_category(text):
        return _statistics_category(text) == 'Restaurants' and 'restaurant' in candidate['id']
    return bool(re.fullmatch(r'(?:what (?:has )?changed|what happened|(?:show|explain)(?: me)? (?:my )?(?:account|spending|overview|this change)|'
                             r'(?:my )?(?:spending |account )?overview|selitä (?:muutos|tilini)|vad har förändrats)'
                             r'(?: (?:this month|last month|in .+))?', text))


def _deterministic(message, context):
    text = message.lower()
    locale = context.get('interface_locale', context.get('locale', 'en'))
    if locale not in {'en', 'fi', 'sv'}:
        raise ValueError('locale must be en, fi, or sv')
    intent = 'explain_change'
    if is_vat_question(text):
        intent = 'vat_estimate'
    elif _tax_planning_request(text):
        intent = 'plan_tax'
    elif _tax_liability_request(text):
        intent = 'plan_tax'
    elif any(word in text for word in ['mortgage history', 'mortgage data', 'linked mortgage', 'home financing history', 'asuntolainahistoria', 'asuntolainatiedot', 'asuntorahoitushistoria', 'bolånehistor', 'bolåneuppgift', 'bostadsfinansieringshistor']):
        intent = 'home_financing_history'
    elif any(word in text for word in ['safe to spend', 'spend this week', 'can i spend', 'turvallista käyttää', 'voin käyttää', 'tällä viikolla', 'säkert att spendera', 'kan jag spendera', 'tryggt för mig att spendera', 'den här veckan']):
        intent = 'safe_to_spend'
    elif any(word in text for word in ['invest', 'contribution', 'portfolio', 'sijoit', 'placering']):
        intent = 'investment_cashflow'
    elif _statistics_category(text) and has_reduction_verb(text):
        intent = 'spending_adjustment'
    elif any(phrase in text for phrase in ['what kind of spender', 'spending profile', 'spender profile', 'millainen rahankäyttäjä', 'kulutusprofiili', 'vilken typ av spenderare', 'utgiftsprofil']):
        intent = 'spending_profile'
    elif _statistics_category(text) and any(word in text for word in ['how much', 'spent on', 'spend on', 'total', 'average', 'count', 'paljonko', 'kuinka paljon', 'käytin', 'hur mycket', 'spenderade', 'summa']):
        intent = 'transaction_statistics'
    elif any(word in text for word in ['plan for a tax', 'plan tax', 'tax payment plan', 'set aside for tax', 'verosuunnitel', 'suunnitella ver', 'veromaksu', 'skatteplan', 'planera skatt']):
        intent = 'plan_tax'
    elif any(word in text for word in ['pay tax', 'pay taxes', 'paid tax', 'paid taxes', 'tax records', 'tax did i pay', 'verotied', 'maksoin', 'veroja', 'veroa', 'betalat skatt', 'skatteuppgift', 'skatt betal']) or re.search(r'\b(?:tax|taxes|verot|skatter)\b', text):
        intent = 'observed_tax_evidence'
    elif any(word in text for word in ['how much did i spend', 'spending statistics', 'spending total', 'paljonko käytin', 'kulutustilasto', 'hur mycket spenderade', 'utgiftsstatistik']):
        intent = 'transaction_statistics'
    elif is_exploratory_goal(text) or any(word in text for word in ['goal', 'save', 'car', 'home purchase', 'tavoite', 'sääst', 'auto', 'asunto', 'mål', 'spara', 'bil', 'bostad']):
        intent = 'plan_goal'
    elif any(word in text for word in ['cashflow', 'cash flow', 'runway', 'next month', 'kassavir', 'ensi kuussa', 'kassaflöde', 'nästa månad']):
        intent = 'preview_cashflow'
    elif any(word in text for word in ['transaction', 'show rows', 'tapahtuma', 'transaktion']):
        intent = 'show_transactions'
    elif any(word in text for word in ['compare', 'vertaa', 'jämför']):
        intent = 'compare_periods'
    if intent in {'compare_periods', 'explain_change'}:
        params = {key: context[key] for key in ['period', 'comparison_period'] if key in context}
    elif intent == 'safe_to_spend':
        params = {key: context[key] for key in ['reference_date', 'days'] if key in context}
    elif intent == 'investment_cashflow':
        params = {key: context[key] for key in ['period', 'months'] if key in context}
    elif intent == 'spending_adjustment':
        params = {key: context[key] for key in ['period'] if key in context}
        category = _statistics_category(text)
        percent = _adjustment_percent(text)
        if category in context.get('filter_catalog', {}).get('categories', []):
            params['category'] = category
        if percent is not None:
            params['percent'] = percent
    elif intent == 'spending_profile':
        params = {key: context[key] for key in ['period'] if key in context}
    elif intent == 'transaction_statistics':
        params = {key: context[key] for key in ['period'] if key in context}
        category = _statistics_category(text)
        if category in context.get('filter_catalog', {}).get('categories', []):
            params['category'] = category
    elif intent in {'observed_tax_evidence', 'vat_estimate'}:
        params = {key: context[key] for key in ['period'] if key in context}
    else:
        params = {}
    ranked = rank_candidates(context.get('candidates', []), context.get('goal'))
    explanatory_kinds = {'explain_change', 'salary_change', 'payday_timing', 'home_financing_history'}
    matching = [candidate for candidate in ranked if candidate.get('kind') == intent or (intent == 'explain_change' and candidate.get('kind') in explanatory_kinds)]
    if intent == 'explain_change':
        matching = [item for item in matching if _relevant_explanation(message, item)]
    candidate = matching[0] if matching else None
    blocks = []
    if candidate and candidate.get('fact_ids'):
        localized = {
            'en': {
                'home_financing_history': 'Linked past mortgage data is historical context only. It is not a current approval or affordability assessment.',
            },
            'fi': {
                'safe_to_spend': 'Arvio suojaa vararahasi, tulevat maksut ja aiempaan joustavaan kulutukseesi perustuvan puskurin.',
                'safe_unavailable': 'Tarvitsen enemmän tilihistoriaa ennen kuin voin arvioida turvallisen käyttövaran.',
                'investment_cashflow': 'Nämä ovat havaitut sijoitussiirrot ja nostot, eivät salkun arvoa tai tuottoa.',
                'explain_change': 'Selitys perustuu havaittuihin tilitapahtumiin.',
                'home_financing_history': 'Linkitetyt aiemmat asuntolainatiedot ovat vain historiallista taustatietoa. Ne eivät ole nykyinen maksukyky- tai hyväksyntäarvio.',
            },
            'sv': {
                'safe_to_spend': 'Uppskattningen skyddar din reserv, kommande utgifter och en buffert baserad på dina tidigare flexibla utgifter.',
                'safe_unavailable': 'Jag behöver mer kontohistorik innan jag kan uppskatta ett säkert belopp att spendera.',
                'investment_cashflow': 'Det här är observerade insättningar och uttag, inte portföljvärde eller avkastning.',
                'explain_change': 'Förklaringen bygger på observerade kontohändelser.',
                'home_financing_history': 'Länkade tidigare bolåneuppgifter är endast historisk bakgrund. De är inte en aktuell bedömning av betalningsförmåga eller godkännande.',
            },
        }
        copy_key = candidate.get('copy_key', intent)
        copy = localized.get(locale, {}).get(copy_key, candidate.get('text', 'Explore this change using the observed transactions.'))
        blocks = [{'text': copy, 'fact_ids': candidate['fact_ids']}]
    questions = {
        'en': {'goal': 'What target amount and target date would you like for your goal?', 'compare': 'Which period and comparison period would you like?', 'statistics': 'Which category or exact filter and month should I use?', 'tax_plan': 'What tax amount and due date do you want to plan for?'},
        'fi': {'goal': 'Mikä on tavoitesumma ja tavoitepäivä?', 'compare': 'Mitä ajanjaksoa ja vertailujaksoa haluat verrata?', 'statistics': 'Mitä luokkaa tai tarkkaa suodatinta ja kuukautta käytän?', 'tax_plan': 'Minkä verosumman ja eräpäivän haluat suunnitella?'},
        'sv': {'goal': 'Vilket målbelopp och måldatum vill du använda?', 'compare': 'Vilken period och jämförelseperiod vill du jämföra?', 'statistics': 'Vilken kategori eller exakt filtrering och månad ska jag använda?', 'tax_plan': 'Vilket skattebelopp och förfallodatum vill du planera för?'},
    }
    needs_clarification = intent in {'plan_goal', 'plan_tax'} or (intent == 'transaction_statistics' and ('period' not in params or not any(key in params for key in ['category', 'role', 'transaction_type', 'merchant_id']))) or (intent == 'spending_adjustment' and not all(key in params for key in ['period', 'category', 'percent']))
    clarification_question = questions[locale]['goal'] if intent == 'plan_goal' else (questions[locale]['tax_plan'] if intent == 'plan_tax' else (questions[locale]['statistics'] if needs_clarification else None))
    response = {'intent': intent, 'parameters': params, 'selected_candidate_id': candidate['id'] if candidate else None,
                'needs_clarification': needs_clarification, 'clarification_question': clarification_question,
                'proposed_action': None, 'explanation_blocks': blocks, 'source': 'deterministic', 'fallback_reason': None, 'locale': locale,
                'response_language_source': 'interface_locale_offline',
                'offline_language_limitation': 'Offline responses support English, Finnish, and Swedish only.'}
    local_scope = resolve_statistics(message, context)
    if local_scope is None and _tax_liability_request(text):
        options = {
            'en': 'Help me plan for a tax payment',
            'fi': 'Auta suunnittelemaan veromaksu',
            'sv': 'Hjälp mig planera en skattebetalning',
        }
        return {**response, **clarify(context, 'liability_unavailable',
            'Account transactions cannot determine your personal tax liability. If you have a declared amount and due date, I can help plan for that payment. What amount and due date would you like to use?',
            'Tilin tapahtumista ei voi määrittää henkilökohtaista maksettavaa veroasi. Jos sinulla on tiedossa summa ja eräpäivä, voin auttaa maksun suunnittelussa. Mitä summaa ja eräpäivää haluat käyttää?',
            'Kontotransaktioner kan inte fastställa din personliga skatteskuld. Om du har ett angivet belopp och förfallodatum kan jag hjälpa dig planera betalningen. Vilket belopp och förfallodatum vill du använda?',
            (options[locale],)),
            'intent': 'plan_tax', 'parameters': {}, 'selected_candidate_id': None,
            'proposed_action': None, 'explanation_blocks': []}
    planned = _planned_response(message, context) if local_scope is None else None
    if planned:
        return {**response, **planned}
    if local_scope is not None:
        response.update(local_scope)
        response['selected_candidate_id'] = None
        response['explanation_blocks'] = []
        response['proposed_action'] = None
    elif intent == 'safe_to_spend' and not has_current_safe_to_spend_scope(message):
        response.update(clarify(context, 'period_scope',
            'This estimate uses the selected data month and its reference date. Please select the month you want, then ask what is safe to spend this week.',
            'Tämä arvio käyttää valittua datakuukautta ja sen viitepäivää. Valitse haluamasi kuukausi ja kysy sitten, paljonko voit käyttää tällä viikolla.',
            'Den här uppskattningen använder vald datamånad och dess referensdag. Välj önskad månad och fråga sedan hur mycket du kan spendera den här veckan.'))
        response.update(parameters={}, selected_candidate_id=None, explanation_blocks=[])
    elif intent in {'preview_cashflow', 'investment_cashflow'}:
        try:
            resolver = resolve_cashflow_parameters if intent == 'preview_cashflow' else resolve_investment_parameters
            response['parameters'] = resolver(message, context)
            if response['parameters'] != params:
                response.update(selected_candidate_id=None, explanation_blocks=[])
        except (ValueError, TypeError, KeyError):
            if intent == 'preview_cashflow':
                response.update(clarify(context, 'period_scope',
                    'The cash-flow preview models thirty days after a reference date. Which date within the available history should I use? You can ask “Show cash flow as of YYYY-MM-DD”.',
                    'Kassavirta-arvio mallintaa viitepäivää seuraavat kolmekymmentä päivää. Mitä historian päivää käytän? Voit kysyä ”Näytä kassavirta alkaen YYYY-MM-DD”.',
                    'Kassaflödesprognosen modellerar trettio dagar efter en referensdag. Vilken dag i historiken ska jag använda? Du kan fråga ”Visa kassaflöde från YYYY-MM-DD”.'))
            else:
                response.update(clarify(context, 'period_scope',
                    'Which single complete month within the available history should I use for investment transfers? I cannot apply that requested window from this wording.',
                    'Mitä kokonaista kuukautta käytettävissä olevasta historiasta käytän sijoitussiirtoihin? En voi käyttää pyydettyä ajanjaksoa tämän sanamuodon perusteella.',
                    'Vilken hel månad i den tillgängliga historiken ska jag använda för investeringsöverföringar? Jag kan inte tillämpa det begärda intervallet med den här formuleringen.'))
            response.update(parameters={}, selected_candidate_id=None, explanation_blocks=[])
    elif intent in {'observed_tax_evidence', 'vat_estimate', 'spending_adjustment', 'spending_profile'}:
        try:
            scoped_start, scoped_end = resolve_period(message, context)
            from .ledger import month_bounds
            if (scoped_start, scoped_end) == month_bounds(scoped_start[:7]):
                response['parameters']['period'] = scoped_start[:7]
            elif intent in {'observed_tax_evidence', 'vat_estimate'}:
                response['parameters'].pop('period', None)
                response['parameters'].update(start=scoped_start, end=scoped_end)
            else:
                raise ValueError('This tool needs a complete month')
        except (ValueError, TypeError):
            response.update(clarify(context, 'period_scope',
                'Which complete month within the available history should I use for this calculation?',
                'Mitä kokonaista kuukautta käytettävissä olevasta historiasta käytän laskentaan?',
                'Vilken hel månad i den tillgängliga historiken ska jag använda för beräkningen?'))
            response['explanation_blocks'] = []
    elif intent == 'explain_change' and candidate is None:
        response.update(clarify(context, 'supported_scope',
            'I can help with a spending decision, explain recorded spending, or explore a saving plan. What would you like to work out?',
            'Voin tarkistaa kululuokkia, tilin kassavirtaa ja säästösuunnitelmia. Mitä haluat tutkia?',
            'Jag kan kontrollera utgiftskategorier, kontots kassaflöde och sparplaner. Vad vill du utforska?',
            ('How much did I spend on restaurants?', 'What is safe for me to spend this week?', 'I want to save for a goal.')))
        if re.fullmatch(r'(?:hi|hello|hey|thanks|thank you|hei|moi|kiitos|hej|tack)[.! ]*', text.strip()):
            response.update(clarify(context, 'conversation_start',
                'Hi. What is on your mind: something you would like to do, a purchase, or a money question?',
                'Hei. Mitä mielessäsi on: jokin tekeminen, ostos vai rahaan liittyvä kysymys?',
                'Hej. Vad funderar du på: något du vill göra, ett köp eller en fråga om pengar?'))
        elif any(term in text for term in ('stressed', 'worried', 'overwhelmed', 'stressa', 'huolissa', 'orolig', 'överväldig')):
            response.update(clarify(context, 'coaching_support',
                'We can take this one step at a time. What feels most urgent: upcoming bills, day-to-day spending, or building a small buffer?',
                'Voimme edetä yksi askel kerrallaan. Mikä tuntuu tärkeimmältä: tulevat laskut, arjen menot vai pieni vararahasto?',
                'Vi kan ta ett steg i taget. Vad känns mest angeläget: kommande räkningar, vardagsutgifter eller en liten buffert?'))
        elif any(term in text for term in ('what should i do', 'help me decide', 'balance', 'saldo')):
            response.update(clarify(context, 'coaching_focus',
                'What would help most: checking room for a small purchase, reviewing upcoming cash flow, or starting a saving plan?',
                'Mikä auttaisi eniten: pienen ostoksen käyttövaran arviointi, tulevan kassavirran tarkastelu vai säästösuunnitelman aloittaminen?',
                'Vad skulle hjälpa mest: utrymme för ett mindre köp, kommande kassaflöde eller en sparplan?'))
        response['selected_candidate_id'] = None
        response['explanation_blocks'] = []
    if response['intent'] == 'explain_change' and not response['needs_clarification']:
        # Explanation candidates were built for the selected month. Changing only
        # their parameters would leave them citing that month's unrelated facts.
        try:
            from .ledger import month_bounds
            if resolve_period(message, context) != month_bounds(context['period']):
                raise ValueError('Explanation facts belong to another period')
        except (ValueError, TypeError, KeyError):
            response.update(clarify(context, 'period_scope',
                'This explanation uses the selected data month. Please select the month you want to explain, or ask for category spending in a specific month or date range within the available history.',
                'Tämä selitys käyttää valittua datakuukautta. Valitse kuukausi, jonka muutosta haluat tutkia, tai kysy tietyn kululuokan menoista käytettävissä olevan historian kuukaudelta tai päiväväliltä.',
                'Den här förklaringen använder vald datamånad. Välj månaden du vill utforska, eller fråga om en kategoris utgifter under en månad eller ett datumintervall i den tillgängliga historiken.'))
            response.update(parameters={}, selected_candidate_id=None, explanation_blocks=[])
    if local_scope is None and intent == 'plan_goal' and is_exploratory_goal(text):
        response.update(clarify(context, 'exploratory_goal',
            'We can start with a wish. You do not need an amount or a date yet. Would you like to name your wish first, or explore a comfortable monthly amount?',
            'Voimme aloittaa toiveesta. Summaa tai päivämäärää ei vielä tarvita. Haluatko ensin nimetä toiveesi vai tutkia sinulle sopivaa kuukausisummaa?',
            'Vi kan börja med en önskan. Du behöver inget belopp eller datum ännu. Vill du först ge din önskan ett namn eller utforska ett månadsbelopp som passar dig?'))
        response.update(parameters={}, selected_candidate_id=None, explanation_blocks=[])
    if intent == 'spending_adjustment' and params.get('category') not in {'Restaurants', 'Lifestyle', 'Entertainment', 'Travel'}:
        response.update(clarify(context, 'essential_adjustment',
            'I keep essential costs protected in these optional saving experiments. Would you like to review the bills, change your goal date, or try a discretionary category instead?',
            'Suojaan välttämättömät menot näissä vapaaehtoisissa säästökokeiluissa. Haluatko tarkistaa laskut, muuttaa tavoitepäivää tai kokeilla valinnaista kululuokkaa?',
            'Jag skyddar nödvändiga utgifter i de här frivilliga sparexperimenten. Vill du granska räkningarna, ändra måldatum eller prova en valfri utgiftskategori?'))
        response['explanation_blocks'] = []
        response['selected_candidate_id'] = None
    if intent == 'spending_adjustment' and params.get('percent') is None:
        response.update(clarify(context, 'adjustment_percentage',
            'What single percentage should I use? Please choose a value from zero to one hundred; I will not guess a missing, invalid or ambiguous amount.',
            'Mitä yhtä prosenttiosuutta käytän? Valitse arvo nollasta sataan. En arvaa puuttuvaa, virheellistä tai epäselvää määrää.',
            'Vilken enda procentsats ska jag använda? Välj ett värde från noll till hundra. Jag gissar inte en saknad, ogiltig eller tvetydig andel.'))
        response['explanation_blocks'] = []
        response['selected_candidate_id'] = None
    if intent == 'vat_estimate' and (re.search(r'\b(?:owe|reclaim|deduct|liability|refund|file)\b', text) or _statistics_category(text)):
        response.update(clarify(context, 'vat_definition',
            'I can estimate VAT already included in all recorded purchases for a selected period. I cannot establish VAT you owe or can reclaim, or a category-specific VAT amount. Would you like the whole-period estimate?',
            'Voin arvioida valitun ajanjakson kaikkiin kirjattuihin ostoksiin sisältyvän ALV:n. En voi määrittää maksettavaa tai palautettavaa veroa tai luokkakohtaista ALV:tä. Haluatko koko ajanjakson arvion?',
            'Jag kan uppskatta moms som ingår i alla registrerade köp under en vald period. Jag kan inte fastställa moms att betala eller återkräva, eller ett kategorispecifikt momsbelopp. Vill du se hela periodens uppskattning?'))
        response['explanation_blocks'] = []
        response['selected_candidate_id'] = None
    response.setdefault('query_scope', None)
    response.setdefault('clarification_options', [])
    response.setdefault('clarification_code', None)
    if intent == 'compare_periods' and not all(key in params for key in ['period', 'comparison_period']):
        response.update(needs_clarification=True, clarification_question=questions[locale]['compare'])
    return response


def interpret(message, context, transport=None, *, api_key=None):
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        raise ValueError('A message of one to two thousand characters is required')
    fallback = _deterministic(message, context)
    locale = context.get('interface_locale', context.get('locale', 'en'))
    if fallback['intent'] in {'plan_tax', 'observed_tax_evidence', 'vat_estimate'}:
        return {**fallback, 'fallback_reason': 'sensitive_tax_query_local_only'}
    if fallback['intent'] in {'spending_adjustment', 'preview_cashflow', 'investment_cashflow'} or fallback.get('clarification_code') == 'planned_purchase_preview':
        return {**fallback, 'fallback_reason': 'deterministic_financial_tool'}
    # A missing definition cannot be repaired by a model choosing a convenient
    # category. Narrow MCC concepts and resolved follow-ups stay local as well.
    scope = fallback.get('query_scope')
    # An unrecognized local phrase can still be understood by the optional
    # language adapter. Data limitations and ambiguous definitions stay local.
    if fallback.get('needs_clarification') and fallback.get('clarification_code') and fallback['clarification_code'] != 'supported_scope':
        return {**fallback, 'fallback_reason': 'clarification_required'}
    if scope and (scope['metric'] == 'inflow_total' or 'mcc_code' in scope['filters'] or 'consumption_only' in scope['filters'] or not scope['filters'] or context.get('previous_query')):
        return {**fallback, 'fallback_reason': 'deterministic_query_scope'}
    key = os.environ.get('GEMINI_API_KEY', '') if api_key is None else api_key
    if not key and transport is None:
        return {**fallback, 'fallback_reason': 'not_configured'}
    safe_message, message_redacted = sanitize_user_message(message)
    payload = {'message': safe_message, 'context': minimized_context(context)}
    output = queue.Queue(maxsize=1)
    def invoke():
        try:
            result = transport(payload, timeout=MODEL_TIMEOUT_SECONDS) if transport else rest_transport(payload, timeout=MODEL_TIMEOUT_SECONDS, api_key=key)
            output.put((True, result))
        except Exception:
            output.put((False, None))
    # A daemon avoids waiting on an uncooperative transport after the fallback deadline.
    threading.Thread(target=invoke, daemon=True).start()
    try:
        success, value = output.get(timeout=MODEL_TIMEOUT_SECONDS)
    except queue.Empty:
        return {**fallback, 'fallback_reason': 'timeout'}
    if not success:
        return {**fallback, 'fallback_reason': 'unavailable'}
    try:
        if isinstance(value, str):
            value = json.loads(value)
        validated = validate_response(value, context)
    except (ValueError, TypeError, KeyError):
        return {**fallback, 'fallback_reason': 'invalid_response'}
    if scope:
        # Wording may come from Gemini, but a locally understood question keeps
        # its definition and dates through the tool and evidence view.
        if validated['intent'] != 'transaction_statistics' or any(
            validated['parameters'].get(name) != item
            for name, item in fallback['parameters'].items()
        ):
            return {**fallback, 'fallback_reason': 'model_scope_mismatch'}
        validated.update(query_scope=scope, clarification_options=[], clarification_code=None)
    return {**validated, 'source': 'gemini', 'fallback_reason': None, 'locale': locale,
            'response_language_source': 'query_language_gemini', 'offline_language_limitation': None,
            'model_input_redacted': message_redacted}
