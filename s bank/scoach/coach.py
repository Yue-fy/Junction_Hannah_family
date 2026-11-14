"""Deterministic coaching with a bounded, validated optional language adapter."""
import json
import os
import queue
import re
import threading
from typing import TypedDict
from .gemini import MODEL_TIMEOUT_SECONDS, minimized_context, rest_transport, sanitize_user_message, validate_response


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
        ('Restaurants', ['restaurant', 'dining', 'ravintol', 'restaurang']),
        ('Groceries', ['grocer', 'food shopping', 'ruokaostos', 'ruokaost', 'elintarvik', 'matvar', 'livsmedel']),
        ('Entertainment', ['entertainment', 'cinema', 'movie', 'games', 'viih', 'elokuva', 'pelit', 'underhållning', 'bio', 'spel']),
        ('Health', ['health', 'medical', 'doctor', 'dentist', 'pharmacy', 'tervey', 'lääkäri', 'hammaslääkäri', 'apteek', 'häls', 'läkare', 'tandläkare', 'apotek']),
        ('Home & Tech', ['home & tech', 'home appliance', 'appliance', 'electronics', 'washing machine', 'koti ja tekniikka', 'kodinkone', 'elektroniikka', 'pesukone', 'hem och teknik', 'hemelektronik', 'vitvar', 'tvättmaskin']),
        ('Housing', ['housing', 'rent', 'asumismen', 'vuokra', 'boende', 'hyra']),
        ('Lifestyle', ['lifestyle', 'clothes', 'clothing', 'fashion', 'elämäntyyli', 'vaatte', 'muoti', 'livsstil', 'kläder']),
        ('Travel', ['travel', 'flight', 'hotel', 'matkail', 'matkamen', 'lento', 'hotelli', 'resor', 'resa', 'flyg', 'hotell']),
        ('Utilities', ['utilities', 'electricity', 'water bill', 'phone bill', 'sähkö', 'vesilask', 'puhelinlask', 'käyttölask', 'elräkning', 'vattenräkning', 'telefonräkning']),
    ]
    for category, words in groups:
        if any(
            re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text)
            if word in {'rent'} else word in text
            for word in words
        ):
            return category
    return None


def _adjustment_percent(text):
    match = re.search(r'(?<!\d)(\d{1,3})\s*(?:%|percent|prosent|procent)', text)
    if not match:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 100 else None


def _deterministic(message, context):
    text = message.lower()
    locale = context.get('interface_locale', context.get('locale', 'en'))
    if locale not in {'en', 'fi', 'sv'}:
        raise ValueError('locale must be en, fi, or sv')
    intent = 'explain_change'
    if any(word in text for word in ['mortgage history', 'mortgage data', 'linked mortgage', 'home financing history', 'asuntolainahistoria', 'asuntolainatiedot', 'asuntorahoitushistoria', 'bolånehistor', 'bolåneuppgift', 'bostadsfinansieringshistor']):
        intent = 'home_financing_history'
    elif any(word in text for word in ['safe to spend', 'spend this week', 'can i spend', 'turvallista käyttää', 'voin käyttää', 'tällä viikolla', 'säkert att spendera', 'kan jag spendera', 'den här veckan']):
        intent = 'safe_to_spend'
    elif any(word in text for word in ['invest', 'contribution', 'portfolio', 'sijoit', 'placering']):
        intent = 'investment_cashflow'
    elif (_statistics_category(text) and _adjustment_percent(text) is not None
          and any(word in text for word in ['reduce', 'reduced', 'cut', 'lower', 'vähent', 'pienent', 'minska', 'minskade'])):
        intent = 'spending_adjustment'
    elif any(phrase in text for phrase in ['what kind of spender', 'spending profile', 'spender profile', 'millainen rahankäyttäjä', 'kulutusprofiili', 'vilken typ av spenderare', 'utgiftsprofil']):
        intent = 'spending_profile'
    elif _statistics_category(text) and any(word in text for word in ['how much', 'spent on', 'spend on', 'total', 'average', 'count', 'paljonko', 'kuinka paljon', 'käytin', 'hur mycket', 'spenderade', 'summa']):
        intent = 'transaction_statistics'
    elif any(word in text for word in ['plan for a tax', 'plan tax', 'tax payment plan', 'set aside for tax', 'verosuunnitel', 'suunnitella ver', 'veromaksu', 'skatteplan', 'planera skatt']):
        intent = 'plan_tax'
    elif any(word in text for word in ['pay tax', 'pay taxes', 'paid tax', 'paid taxes', 'tax records', 'tax did i pay', 'verotied', 'maksoin', 'veroja', 'veroa', 'betalat skatt', 'skatteuppgift', 'skatt betal']):
        intent = 'observed_tax_evidence'
    elif any(word in text for word in ['how much did i spend', 'spending statistics', 'spending total', 'paljonko käytin', 'kulutustilasto', 'hur mycket spenderade', 'utgiftsstatistik']):
        intent = 'transaction_statistics'
    elif any(word in text for word in ['goal', 'save', 'car', 'home purchase', 'tavoite', 'sääst', 'auto', 'asunto', 'mål', 'spara', 'bil', 'bostad']):
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
    elif intent == 'observed_tax_evidence':
        params = {key: context[key] for key in ['period'] if key in context}
    else:
        params = {}
    ranked = rank_candidates(context.get('candidates', []), context.get('goal'))
    explanatory_kinds = {'explain_change', 'salary_change', 'payday_timing', 'home_financing_history'}
    matching = [candidate for candidate in ranked if candidate.get('kind') == intent or (intent == 'explain_change' and candidate.get('kind') in explanatory_kinds)]
    candidate = matching[0] if matching else (ranked[0] if intent == 'explain_change' and ranked else None)
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
    if intent == 'compare_periods' and not all(key in params for key in ['period', 'comparison_period']):
        response.update(needs_clarification=True, clarification_question=questions[locale]['compare'])
    return response


def interpret(message, context, transport=None, *, api_key=None):
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        raise ValueError('A message of one to two thousand characters is required')
    fallback = _deterministic(message, context)
    locale = context.get('interface_locale', context.get('locale', 'en'))
    if fallback['intent'] in {'plan_tax', 'observed_tax_evidence'}:
        return {**fallback, 'fallback_reason': 'sensitive_tax_query_local_only'}
    if fallback['intent'] == 'spending_adjustment':
        return {**fallback, 'fallback_reason': 'deterministic_financial_tool'}
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
    return {**validated, 'source': 'gemini', 'fallback_reason': None, 'locale': locale,
            'response_language_source': 'query_language_gemini', 'offline_language_limitation': None,
            'model_input_redacted': message_redacted}
