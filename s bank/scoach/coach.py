"""Deterministic coaching with a bounded, validated optional language adapter."""
import json
import os
import queue
import threading
from typing import TypedDict
from .gemini import minimized_context, rest_transport, validate_response


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


def _deterministic(message, context):
    text = message.lower()
    locale = context.get('interface_locale', context.get('locale', 'en'))
    if locale not in {'en', 'fi', 'sv'}:
        raise ValueError('locale must be en, fi, or sv')
    intent = 'explain_change'
    if any(word in text for word in ['safe to spend', 'spend this week', 'can i spend', 'turvallista käyttää', 'voin käyttää', 'tällä viikolla', 'säkert att spendera', 'kan jag spendera', 'den här veckan']):
        intent = 'safe_to_spend'
    elif any(word in text for word in ['invest', 'contribution', 'portfolio', 'sijoit', 'placering']):
        intent = 'investment_cashflow'
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
    else:
        params = {}
    ranked = rank_candidates(context.get('candidates', []), context.get('goal'))
    matching = [candidate for candidate in ranked if candidate.get('kind') == intent]
    candidate = matching[0] if matching else (ranked[0] if intent == 'explain_change' and ranked else None)
    blocks = []
    if candidate and candidate.get('fact_ids'):
        localized = {
            'fi': {
                'safe_to_spend': 'Arvio suojaa vararahasi, tulevat maksut ja aiempaan joustavaan kulutukseesi perustuvan puskurin.',
                'safe_unavailable': 'Tarvitsen enemmän tilihistoriaa ennen kuin voin arvioida turvallisen käyttövaran.',
                'investment_cashflow': 'Nämä ovat havaitut sijoitussiirrot ja nostot, eivät salkun arvoa tai tuottoa.',
                'explain_change': 'Selitys perustuu havaittuihin tilitapahtumiin.',
            },
            'sv': {
                'safe_to_spend': 'Uppskattningen skyddar din reserv, kommande utgifter och en buffert baserad på dina tidigare flexibla utgifter.',
                'safe_unavailable': 'Jag behöver mer kontohistorik innan jag kan uppskatta ett säkert belopp att spendera.',
                'investment_cashflow': 'Det här är observerade insättningar och uttag, inte portföljvärde eller avkastning.',
                'explain_change': 'Förklaringen bygger på observerade kontohändelser.',
            },
        }
        copy_key = candidate.get('copy_key', intent)
        copy = localized.get(locale, {}).get(copy_key, candidate.get('text', 'Explore this change using the observed transactions.'))
        blocks = [{'text': copy, 'fact_ids': candidate['fact_ids']}]
    questions = {
        'en': {'goal': 'What target amount and target date would you like for your goal?', 'compare': 'Which period and comparison period would you like?'},
        'fi': {'goal': 'Mikä on tavoitesumma ja tavoitepäivä?', 'compare': 'Mitä ajanjaksoa ja vertailujaksoa haluat verrata?'},
        'sv': {'goal': 'Vilket målbelopp och måldatum vill du använda?', 'compare': 'Vilken period och jämförelseperiod vill du jämföra?'},
    }
    response = {'intent': intent, 'parameters': params, 'selected_candidate_id': candidate['id'] if candidate else None,
                'needs_clarification': intent == 'plan_goal', 'clarification_question': questions[locale]['goal'] if intent == 'plan_goal' else None,
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
    key = os.environ.get('GEMINI_API_KEY', '') if api_key is None else api_key
    if not key and transport is None:
        return {**fallback, 'fallback_reason': 'not_configured'}
    payload = {'message': message, 'context': minimized_context(context)}
    output = queue.Queue(maxsize=1)
    def invoke():
        try:
            result = transport(payload, timeout=4.0) if transport else rest_transport(payload, timeout=4.0, api_key=key)
            output.put((True, result))
        except Exception:
            output.put((False, None))
    # A daemon avoids waiting on an uncooperative transport after the fallback deadline.
    threading.Thread(target=invoke, daemon=True).start()
    try:
        success, value = output.get(timeout=4.0)
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
            'response_language_source': 'query_language_gemini', 'offline_language_limitation': None}
