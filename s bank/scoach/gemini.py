"""Constrained optional Gemini transport. No ledger data or mutation execution."""
import json
import os
import re
import urllib.request
from datetime import date

INTENTS = {'compare_periods', 'explain_change', 'show_transactions', 'preview_cashflow', 'plan_goal', 'safe_to_spend', 'investment_cashflow'}
PARAMETERS = {
    'compare_periods': {'period': str, 'comparison_period': str, 'category': str},
    'explain_change': {'period': str, 'comparison_period': str, 'category': str},
    'show_transactions': {'period': str, 'category': str, 'transaction_ref': str},
    'preview_cashflow': {'reference_date': str, 'days': int},
    'plan_goal': {'name': str, 'target_cents': int, 'current_saved_cents': int, 'reserve_floor_cents': int, 'target_date': str},
    'safe_to_spend': {'reference_date': str, 'days': int, 'reserve_floor_cents': int},
    'investment_cashflow': {'period': str, 'months': int},
}
REQUIRED = {'compare_periods': ['period', 'comparison_period'], 'plan_goal': ['target_cents', 'target_date']}
ACTIONS = {
    'classify_row': {'transaction_ref': str, 'role': str},
    'exclude_from_scenario': {'transaction_ref': str, 'scenario_id': str},
    'create_rule': {'category': str, 'role': str, 'merchant': str},
    'link_goal': {'goal_id': str, 'scenario_id': str},
}
ROLES = {'income', 'fixed_obligation', 'flexible_essential', 'discretionary', 'saving_or_transfer', 'needs_review'}


def fact_ids(context):
    facts = context.get('facts', [])
    return set(facts if isinstance(facts, dict) else (x.get('id', x.get('fact_id')) for x in facts))


def _validate_display_text(text):
    # Displayed figures always come from deterministic facts, never model prose.
    if re.search(r'[\d€$£%]', text):
        raise ValueError('Numeric model copy is not a deterministic fact')


def validate_response(value, context):
    """Reject invented references/types; proposed actions always require confirmation."""
    if not isinstance(value, dict) or type(value.get('intent')) is not str or value.get('intent') not in INTENTS:
        raise ValueError('Unknown coach intent')
    if set(value) - {'intent', 'parameters', 'selected_candidate_id', 'needs_clarification', 'clarification_question', 'proposed_action', 'explanation_blocks'}:
        raise ValueError('Unknown response field')
    intent = value['intent']
    params = value.get('parameters', {})
    if not isinstance(params, dict):
        raise ValueError('Parameters must be an object')
    for name, item in params.items():
        kind = PARAMETERS[intent].get(name)
        if kind is None or type(item) is not kind:
            raise ValueError('Unknown or invalid intent parameter')
        if name.endswith('_cents') and item < 0:
            raise ValueError('Amounts must be nonnegative integer cents')
        if name in {'period', 'comparison_period'}:
            if not re.fullmatch(r'\d{4}-\d{2}', item):
                raise ValueError('Invalid month')
            date.fromisoformat(item + '-01')
        if name.endswith('_date'):
            date.fromisoformat(item)
        if name == 'days':
            if intent == 'preview_cashflow' and item != 30:
                raise ValueError('Only the confirmed thirty-day preview is supported')
            if intent == 'safe_to_spend' and not 1 <= item <= 30:
                raise ValueError('safe-to-spend days must be 1–30')
        if name == 'months' and not 1 <= item <= 24:
            raise ValueError('months must be 1–24')
    selected = value.get('selected_candidate_id')
    if selected is not None and (type(selected) is not str or selected not in {x['id'] for x in context.get('candidates', [])}):
        raise ValueError('Unknown candidate')
    clarification = value.get('needs_clarification', False)
    question = value.get('clarification_question')
    if type(clarification) is not bool or (question is not None and not isinstance(question, str)):
        raise ValueError('Invalid clarification')
    if question is not None:
        _validate_display_text(question)
    blocks = value.get('explanation_blocks', [])
    if not isinstance(blocks, list):
        raise ValueError('Invalid explanation blocks')
    for block in blocks:
        if not isinstance(block, dict) or set(block) - {'text', 'fact_ids'} or not isinstance(block.get('text'), str):
            raise ValueError('Invalid explanation')
        refs = block.get('fact_ids')
        if not isinstance(refs, list) or not refs or any(type(ref) is not str or ref not in fact_ids(context) for ref in refs):
            raise ValueError('Unknown fact reference')
        _validate_display_text(block['text'])
    action = value.get('proposed_action')
    if action is not None:
        if not isinstance(action, dict) or type(action.get('type')) is not str or action.get('type') not in ACTIONS:
            raise ValueError('Unknown proposed action')
        fields = action.get('parameters')
        schema = ACTIONS[action['type']]
        if not isinstance(fields, dict) or any(name not in schema or type(item) is not schema[name] for name, item in fields.items()):
            raise ValueError('Invalid action parameters')
        required = set(schema) - {'merchant'}
        if not required.issubset(fields):
            raise ValueError('Missing action parameters')
        for field, allowlist in [('transaction_ref', 'transaction_refs'), ('scenario_id', 'scenario_ids'), ('goal_id', 'goal_ids')]:
            if field in fields and fields[field] not in context.get(allowlist, []):
                raise ValueError('Unknown action reference')
        if 'role' in fields and fields['role'] not in ROLES:
            raise ValueError('Unknown role')
        action = {'type': action['type'], 'parameters': dict(fields), 'requires_confirmation': True}
    missing = [key for key in REQUIRED.get(intent, []) if key not in params]
    if missing:
        clarification = True
        question = 'Please provide ' + ' and '.join(missing) + '.'
    if clarification and not question:
        raise ValueError('Clarification requires a question')
    return {'intent': intent, 'parameters': dict(params), 'selected_candidate_id': selected,
            'needs_clarification': clarification, 'clarification_question': question,
            'proposed_action': action, 'explanation_blocks': blocks}


def minimized_context(context):
    """An explicit allowlist prevents customer/account/ledger leakage."""
    facts = context.get('facts', [])
    if isinstance(facts, dict):
        facts = [{'id': key, **(value if isinstance(value, dict) else {'value': value})} for key, value in facts.items()]
    safe_facts = [{key: value for key, value in fact.items() if key in {'id', 'fact_id', 'value', 'value_cents', 'unit', 'label', 'status', 'available', 'reserve_floor_cents', 'reserve_floor_source'}} for fact in facts]
    candidates = [{key: value for key, value in item.items() if key in {'id', 'kind', 'text', 'fact_ids'}} for item in context.get('candidates', [])]
    locale = context.get('interface_locale', context.get('locale', 'en'))
    if locale not in {'en', 'fi', 'sv'}:
        raise ValueError('Unknown response locale')
    return {'facts': safe_facts, 'candidates': candidates, 'period': context.get('period'), 'comparison_period': context.get('comparison_period'), 'interface_locale': locale, 'response_language_policy': 'match_query_language_when_clear', **{key: list(context.get(key, [])) for key in ['transaction_refs', 'scenario_ids', 'goal_ids']}}


def rest_transport(payload, timeout=4.0, *, api_key=None, model=None):
    key = api_key if api_key is not None else os.environ.get('GEMINI_API_KEY', '')
    model = model or os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise ValueError('Invalid model name')
    instruction = ('Return JSON only with intent, parameters, selected_candidate_id, needs_clarification, clarification_question, proposed_action, explanation_blocks. '
                   'Allowed intents: ' + ', '.join(sorted(INTENTS)) + '. Allowed actions: ' + ', '.join(sorted(ACTIONS)) + '. '
                   "Use supplied candidate/fact IDs only. Explanation blocks contain text and fact_ids. Write displayed prose in the same language as the user's message when that language is clear; otherwise use the interface locale from context.interface_locale. The interface locale is separate from the conversational response language. Never put numeric values or currency/percent symbols in any displayed prose, including clarification_question; the client renders deterministic facts. Never perform actions. "
                   'Parameter schemas: ' + json.dumps({intent: {name: kind.__name__ for name, kind in fields.items()} for intent, fields in PARAMETERS.items()}))
    body = {'system_instruction': {'parts': [{'text': instruction}]}, 'contents': [{'role': 'user', 'parts': [{'text': json.dumps(payload)}]}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.1}}
    request = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        envelope = json.load(response)
    return json.loads(envelope['candidates'][0]['content']['parts'][0]['text'])
