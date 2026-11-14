"""Dependency-free Gemini and DeepSeek transports; callers own the tool loop."""
import copy
import json
import os
import re
import urllib.request
from pathlib import Path

from .gemini import DEFAULT_GEMINI_MODEL

DEFAULT_DEEPSEEK_MODEL = 'deepseek-flash'


def agent_configured():
    return any(os.environ.get(name, '').strip() for name in ('DEEPSEEK_API_KEY', 'GEMINI_API_KEY'))


def generate(contents, *, system, tools, timeout=20.0):
    """Prefer the explicitly configured DeepSeek provider; otherwise use Gemini."""
    transport = deepseek_generate if os.environ.get('DEEPSEEK_API_KEY', '').strip() else gemini_generate
    return transport(contents, system=system, tools=tools, timeout=timeout)


def load_env(path):
    """Read literal KEY=VALUE pairs without shell evaluation or overwriting env."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = (part.strip() for part in line.split('=', 1))
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def gemini_generate(contents, *, system, tools, api_key=None, model=None, timeout=20.0):
    key = api_key if api_key is not None else os.environ.get('GEMINI_API_KEY', '')
    model = model or os.environ.get('GEMINI_MODEL') or DEFAULT_GEMINI_MODEL
    if not key or not key.strip():
        raise ValueError('Gemini is not configured')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise ValueError('Invalid model name')
    if timeout <= 0:
        raise TimeoutError('Agent deadline reached')
    body = {
        'systemInstruction': {'parts': [{'text': system}]},
        'contents': contents,
        'tools': [{'functionDeclarations': tools}],
        'generationConfig': {'temperature': 0.3},
    }
    request = urllib.request.Request(
        'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent',
        data=json.dumps(body, allow_nan=False).encode(),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        # Bound unexpected upstream output as well as the request history.
        raw = response.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError('Gemini response is too large')
    envelope = json.loads(raw)
    try:
        content = envelope['candidates'][0]['content']
        if not isinstance(content, dict) or not isinstance(content.get('parts'), list) or not content['parts']:
            raise ValueError('Gemini returned no content')
    except (KeyError, IndexError, TypeError):
        raise ValueError('Gemini returned no content') from None
    # Preserve opaque thoughtSignature and functionCall.id fields verbatim.
    return content


def _json_schema(value):
    if isinstance(value, dict):
        return {key: item.lower() if key == 'type' and isinstance(item, str) else _json_schema(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_json_schema(item) for item in value]
    return value


def _deepseek_messages(contents, system):
    messages = [{'role': 'system', 'content': system}]
    for content in contents:
        if '_deepseek_message' in content:
            # Thinking-mode tool follow-ups require the original reasoning_content.
            messages.append(copy.deepcopy(content['_deepseek_message']))
            continue
        parts = content['parts']
        responses = [part['functionResponse'] for part in parts if 'functionResponse' in part]
        if responses:
            for response in responses:
                if not isinstance(response.get('id'), str) or not response['id']:
                    raise ValueError('DeepSeek tool response requires its call ID')
                messages.append({'role': 'tool', 'tool_call_id': response['id'],
                                 'content': json.dumps(response['response'], ensure_ascii=False, allow_nan=False)})
        else:
            messages.append({'role': 'assistant' if content['role'] == 'model' else 'user',
                             'content': '\n'.join(part['text'] for part in parts if isinstance(part.get('text'), str) and not part.get('thought'))})
    return messages


def deepseek_generate(contents, *, system, tools, api_key=None, model=None, timeout=20.0):
    key = api_key if api_key is not None else os.environ.get('DEEPSEEK_API_KEY', '')
    model = model or os.environ.get('DEEPSEEK_MODEL') or DEFAULT_DEEPSEEK_MODEL
    if not key or not key.strip():
        raise ValueError('DeepSeek is not configured')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise ValueError('Invalid model name')
    if timeout <= 0:
        raise TimeoutError('Agent deadline reached')
    body = {'model': model, 'messages': _deepseek_messages(contents, system),
            'stream': False, 'max_tokens': 2048, 'thinking': {'type': 'disabled'}}
    if tools:
        body['tools'] = [{'type': 'function', 'function': _json_schema(declaration)} for declaration in tools]
    request = urllib.request.Request('https://api.deepseek.com/chat/completions',
        data=json.dumps(body, allow_nan=False).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}, method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError('DeepSeek response is too large')
    envelope = json.loads(raw)
    try:
        message = envelope['choices'][0]['message']
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            raise ValueError('Invalid DeepSeek response')
        parts = []
        if isinstance(message.get('content'), str) and message['content'].strip():
            parts.append({'text': message['content']})
        for call in message.get('tool_calls') or []:
            if call.get('type') != 'function' or not isinstance(call.get('id'), str) or not call['id']:
                raise ValueError('Invalid DeepSeek tool call')
            function = call['function']
            try:
                args = json.loads(function['arguments'])
            except (ValueError, TypeError):
                args = None  # The agent returns a correctable tool argument error.
            parts.append({'functionCall': {'name': function['name'], 'args': args, 'id': call['id']}})
        if not parts:
            raise ValueError('DeepSeek returned no content')
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError('Invalid DeepSeek response') from None
    return {'role': 'model', 'parts': parts, '_deepseek_message': message}
