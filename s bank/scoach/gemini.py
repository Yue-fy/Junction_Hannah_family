"""Constrained optional Gemini transport. No ledger data or mutation execution."""
import json
import os
import re
import unicodedata
import urllib.request
from datetime import date

DEFAULT_GEMINI_MODEL = 'gemini-3-flash-preview'
MODEL_TIMEOUT_SECONDS = 9.0

INTENTS = {'compare_periods', 'explain_change', 'show_transactions', 'preview_cashflow', 'plan_goal', 'safe_to_spend', 'investment_cashflow', 'home_financing_history', 'transaction_statistics', 'spending_profile', 'observed_tax_evidence', 'plan_tax'}
PARAMETERS = {
    'compare_periods': {'period': str, 'comparison_period': str, 'category': str},
    'explain_change': {'period': str, 'comparison_period': str, 'category': str},
    'show_transactions': {'period': str, 'category': str, 'transaction_ref': str},
    'preview_cashflow': {'reference_date': str, 'days': int},
    'plan_goal': {'name': str, 'target_cents': int, 'current_saved_cents': int, 'reserve_floor_cents': int, 'target_date': str},
    'safe_to_spend': {'reference_date': str, 'days': int, 'reserve_floor_cents': int},
    'investment_cashflow': {'period': str, 'months': int},
    'home_financing_history': {},
    'transaction_statistics': {'period': str, 'comparison_period': str, 'category': str, 'role': str, 'transaction_type': str, 'merchant_id': str},
    'spending_profile': {'period': str},
    'observed_tax_evidence': {'period': str},
    'plan_tax': {},
}
REQUIRED = {'compare_periods': ['period', 'comparison_period'], 'plan_goal': ['target_cents', 'target_date'], 'spending_profile': ['period']}
ACTIONS = {
    'classify_row': {'transaction_ref': str, 'role': str},
    'exclude_from_scenario': {'transaction_ref': str, 'scenario_id': str},
    'create_rule': {'category': str, 'role': str, 'merchant': str},
    'link_goal': {'goal_id': str, 'scenario_id': str},
}
ROLES = {'income', 'fixed_obligation', 'flexible_essential', 'discretionary', 'saving_or_transfer', 'needs_review'}
CATALOG_FIELDS = {'category': 'categories', 'role': 'roles', 'transaction_type': 'transaction_types', 'merchant_id': 'merchant_ids'}
CATALOG_LIMITS = {'categories': 64, 'roles': 8, 'transaction_types': 32, 'merchant_ids': 100}

_CURRENCY_WORDS = {
    'eur', 'euro', 'euros', 'euroa', 'eurot', 'euron', 'eurolla', 'eurosta', 'euroissa',
    'usd', 'dollar', 'dollars', 'dollaria', 'dollari', 'gbp', 'pound', 'pounds', 'punta', 'puntaa',
    'chf', 'franc', 'francs', 'jpy', 'yen', 'cny', 'rmb', 'yuan', 'sek', 'nok', 'dkk',
    'cad', 'aud', 'nzd', 'krona', 'kronor', 'kronan', 'kroner', 'kruunu', 'kruunua',
}
_PERCENT_WORDS = {
    'percent', 'percentage', 'prosentti', 'prosenttia', 'prosentin', 'prosent', 'procent',
    'prozenten', 'prozent', 'pourcent', 'porcentaje',
}
_NUMBER_WORDS = {
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
    'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen',
    'nineteen', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety',
    'hundred', 'thousand', 'million', 'billion',
    'nolla', 'yksi', 'yhden', 'kaksi', 'kahden', 'kolme', 'neljä', 'viisi', 'kuusi',
    'seitsemän', 'kahdeksan', 'yhdeksän', 'kymmenen', 'sata', 'sataa', 'tuhat', 'tuhatta',
    'miljoona', 'miljoonaa',
    'noll', 'ett', 'två', 'tre', 'fyra', 'fem', 'sex', 'sju', 'åtta', 'nio', 'tio',
    'elva', 'tolv', 'tjugo', 'trettio', 'fyrtio', 'femtio', 'sextio', 'sjuttio', 'åttio',
    'nittio', 'hundra', 'tusen', 'miljon',
    'null', 'eins', 'eine', 'zwei', 'drei', 'vier', 'fünf', 'sechs', 'sieben', 'acht', 'neun',
    'zehn', 'zwanzig', 'hundert', 'tausend', 'millionen',
    'zéro', 'zero', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf',
    'dix', 'vingt', 'cent', 'mille', 'million',
    'cero', 'uno', 'una', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve',
    'diez', 'veinte', 'cien', 'ciento', 'mil', 'millón',
}
_NUMBER_PREFIXES = ('yhdeksänsata', 'kahdeksansata', 'seitsemänsata', 'kuusisata', 'viisisata', 'neljäsata', 'kolmesata', 'kaksisata', 'niohundra', 'åttahundra', 'sjuhundra')
_FI_CARDINAL_STEMS = ('yksi', 'yhden', 'kaksi', 'kahden', 'kolme', 'neljä', 'viisi', 'kuusi', 'seitsemän', 'kahdeksan', 'yhdeksän')
_SV_CARDINAL_STEMS = ('ett', 'en', 'två', 'tre', 'fyra', 'fem', 'sex', 'sju', 'åtta', 'nio')
_DE_CARDINAL_STEMS = ('ein', 'eins', 'zwei', 'drei', 'vier', 'fünf', 'sechs', 'sieben', 'acht', 'neun')
_DE_TENS = ('zwanzig', 'dreißig', 'dreissig', 'vierzig', 'fünfzig', 'sechzig', 'siebzig', 'achtzig', 'neunzig')


def fact_ids(context):
    facts = context.get('facts', [])
    return set(facts if isinstance(facts, dict) else (x.get('id', x.get('fact_id')) for x in facts))


def _sensitive_word(word):
    value = word.casefold()
    if value in _CURRENCY_WORDS:
        return 'currency'
    if value in _PERCENT_WORDS:
        return 'percent'
    if value in _NUMBER_WORDS or value.startswith(_NUMBER_PREFIXES):
        return 'number'
    if any(value.startswith(stem + scale) for stem in _FI_CARDINAL_STEMS for scale in ('kymment', 'sata', 'tuhat')):
        return 'number'
    if any(value.startswith(stem + scale) for stem in _SV_CARDINAL_STEMS for scale in ('hundra', 'tusen')):
        return 'number'
    if any(value.startswith(stem + scale) for stem in _DE_CARDINAL_STEMS for scale in ('hundert', 'tausend')):
        return 'number'
    if value in _DE_TENS or any(value.startswith(stem + 'und') and value.endswith(_DE_TENS) for stem in _DE_CARDINAL_STEMS):
        return 'number'
    return None


def _replace_currency_symbols(text):
    return ''.join('[currency]' if unicodedata.category(char) == 'Sc' else char for char in text)


def _has_currency_symbol(text):
    return any(unicodedata.category(char) == 'Sc' for char in text)


def sanitize_user_message(text):
    """Redact exact numeric, currency, and percent expressions before transport."""
    sanitized = re.sub(r'\d(?:[\d\s.,\'\u2019]*\d)?', '[number]', text)
    sanitized = _replace_currency_symbols(sanitized)
    sanitized = re.sub(r'[%‰]', '[percent]', sanitized)
    def replace_word(match):
        kind = _sensitive_word(match.group(0))
        return '[' + kind + ']' if kind else match.group(0)
    sanitized = re.sub(r'[^\W\d_]+', replace_word, sanitized, flags=re.UNICODE)
    return sanitized, sanitized != text


def _validate_display_text(text):
    # Displayed figures always come from deterministic facts, never model prose.
    if re.search(r'[\d%‰]', text) or _has_currency_symbol(text):
        raise ValueError('Numeric model copy is not a deterministic fact')
    # Keep the established nonnumeric "one-off" clarification usable.
    checked = re.sub(r'\bone[- ]off\b', '', text, flags=re.IGNORECASE)
    if any(_sensitive_word(word) for word in re.findall(r'[^\W\d_]+', checked, flags=re.UNICODE)):
        raise ValueError('Spelled numeric or unit model copy is not a deterministic fact')


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
        if intent == 'transaction_statistics' and name in CATALOG_FIELDS:
            catalog = context.get('filter_catalog', {})
            allowed = catalog.get(CATALOG_FIELDS[name], []) if isinstance(catalog, dict) else []
            if item not in allowed:
                raise ValueError('Statistics filter is outside the customer catalog')
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
    locale = context.get('interface_locale', context.get('locale', 'en'))
    prompts = {
        'en': {'statistics': 'Which category or exact filter and month should I use?', 'tax': 'Which month should I check for explicit tax records?', 'tax_plan': 'What tax amount and due date do you want to plan for?'},
        'fi': {'statistics': 'Mitä luokkaa tai tarkkaa suodatinta ja kuukautta käytän?', 'tax': 'Miltä kuukaudelta tarkistan nimenomaiset verotiedot?', 'tax_plan': 'Minkä verosumman ja eräpäivän haluat suunnitella?'},
        'sv': {'statistics': 'Vilken kategori eller exakt filtrering och månad ska jag använda?', 'tax': 'Vilken månad ska jag kontrollera efter uttryckliga skatteuppgifter?', 'tax_plan': 'Vilket skattebelopp och förfallodatum vill du planera för?'},
    }
    if intent == 'transaction_statistics' and ('period' not in params or not any(key in params for key in CATALOG_FIELDS)):
        clarification, question = True, prompts[locale]['statistics']
    if intent == 'observed_tax_evidence' and 'period' not in params:
        clarification, question = True, prompts[locale]['tax']
    if intent == 'plan_tax':
        clarification, question = True, prompts[locale]['tax_plan']
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
    safe_facts = []
    for fact in facts:
        keys = {'id', 'fact_id', 'status', 'historical_context_only'} if fact.get('historical_context_only') else {'id', 'fact_id', 'value', 'value_cents', 'unit', 'label', 'status', 'available', 'reserve_floor_cents', 'reserve_floor_source'}
        safe_facts.append({key: value for key, value in fact.items() if key in keys})
    candidates = []
    for item in context.get('candidates', []):
        keys = {'id', 'kind', 'fact_ids', 'historical_context_only', 'copy_key'} if item.get('historical_context_only') else {'id', 'kind', 'text', 'fact_ids'}
        candidates.append({key: value for key, value in item.items() if key in keys})
    locale = context.get('interface_locale', context.get('locale', 'en'))
    if locale not in {'en', 'fi', 'sv'}:
        raise ValueError('Unknown response locale')
    raw_catalog = context.get('filter_catalog', {})
    if not isinstance(raw_catalog, dict) or set(raw_catalog) - set(CATALOG_LIMITS):
        raise ValueError('Invalid filter catalog')
    catalog = {}
    for key, limit in CATALOG_LIMITS.items():
        values = raw_catalog.get(key, [])
        if not isinstance(values, list) or len(values) > limit or any(type(value) is not str or not value for value in values):
            raise ValueError('Invalid or unbounded filter catalog')
        catalog[key] = list(values)
    return {'facts': safe_facts, 'candidates': candidates, 'period': context.get('period'), 'comparison_period': context.get('comparison_period'), 'filter_catalog': catalog, 'interface_locale': locale, 'response_language_policy': 'match_query_language_when_clear'}


def rest_transport(payload, timeout=MODEL_TIMEOUT_SECONDS, *, api_key=None, model=None):
    key = api_key if api_key is not None else os.environ.get('GEMINI_API_KEY', '')
    model = model or os.environ.get('GEMINI_MODEL', DEFAULT_GEMINI_MODEL)
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise ValueError('Invalid model name')
    instruction = ('Return JSON only with intent, parameters, selected_candidate_id, needs_clarification, clarification_question, proposed_action, explanation_blocks. '
                   'Allowed intents: ' + ', '.join(sorted(INTENTS)) + '. Allowed actions: ' + ', '.join(sorted(ACTIONS)) + '. '
                   "Use supplied candidate/fact IDs and exact filter_catalog values only. The model selects validated periods and filters; it never receives ledger rows, transaction references, customer identifiers, tax values or rates, and it never calculates totals. Explanation blocks contain text and fact_ids. Write displayed prose in the same language as the user's message when that language is clear; otherwise use the interface locale from context.interface_locale. The interface locale is separate from the conversational response language. Historical financing facts are context only: never infer current eligibility, affordability, approval probability, a recommended loan amount, a recommended product, or an offer. Never infer a tax amount, rate, liability, deduction, or filing rule. Never put digits, spelled-out numbers, currency words or symbols, or percent words or symbols in any displayed prose, including clarification_question; the client renders deterministic facts. Never perform actions. "
                   'Parameter schemas: ' + json.dumps({intent: {name: kind.__name__ for name, kind in fields.items()} for intent, fields in PARAMETERS.items()}))
    body = {'system_instruction': {'parts': [{'text': instruction}]}, 'contents': [{'role': 'user', 'parts': [{'text': json.dumps(payload)}]}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.1}}
    request = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        envelope = json.load(response)
    return json.loads(envelope['candidates'][0]['content']['parts'][0]['text'])
