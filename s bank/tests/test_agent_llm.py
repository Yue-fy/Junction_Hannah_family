import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class GeminiAgentTransportTests(unittest.TestCase):
    def test_env_is_literal_and_never_overwrites_shell(self):
        from scoach.llm import load_env
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'GEMINI_MODEL': 'shell'}, clear=True):
            path = Path(folder) / '.env'
            path.write_text('# comment\nGEMINI_MODEL=file\nGEMINI_API_KEY="local-test"\nBAD LINE\nBAD-NAME=no\nVALUE=$(echo unsafe)\n')
            load_env(path)
            self.assertEqual(os.environ['GEMINI_MODEL'], 'shell')
            self.assertEqual(os.environ['GEMINI_API_KEY'], 'local-test')
            self.assertEqual(os.environ['VALUE'], '$(echo unsafe)')
            self.assertNotIn('BAD-NAME', os.environ)
            load_env(Path(folder) / 'missing')

    def test_generate_posts_declarations_and_returns_whole_content(self):
        from scoach.llm import gemini_generate
        content = {'role': 'model', 'parts': [{'thoughtSignature': 'opaque',
                   'functionCall': {'name': 'get_overview', 'args': {}, 'id': 'call-1'}}]}
        captured = {}
        def send(request, timeout):
            captured.update(url=request.full_url, body=json.loads(request.data),
                            key=request.get_header('X-goog-api-key'), timeout=timeout)
            return io.BytesIO(json.dumps({'candidates': [{'content': content}]}).encode())
        declarations = [{'name': 'get_overview', 'description': 'Read overview',
                         'parameters': {'type': 'OBJECT', 'properties': {}}}]
        with patch('urllib.request.urlopen', side_effect=send):
            result = gemini_generate([{'role': 'user', 'parts': [{'text': 'Hello'}]}],
                system='Be helpful', tools=declarations, api_key='test-key', model='gemini-test', timeout=2)
        self.assertEqual(result, content)
        self.assertEqual(captured['url'], 'https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent')
        self.assertEqual(captured['body']['tools'], [{'functionDeclarations': declarations}])
        self.assertEqual(captured['body']['systemInstruction']['parts'][0]['text'], 'Be helpful')
        self.assertEqual(captured['key'], 'test-key')
        self.assertEqual(captured['timeout'], 2)

    def test_transport_rejects_missing_key_path_injection_and_empty_candidate(self):
        from scoach.llm import gemini_generate
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                gemini_generate([], system='', tools=[])
        with self.assertRaises(ValueError):
            gemini_generate([], system='', tools=[], api_key='test', model='../escape')
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'{"candidates": []}')):
            with self.assertRaises(ValueError):
                gemini_generate([], system='', tools=[], api_key='test')


class DeepSeekAgentTransportTests(unittest.TestCase):
    def test_deepseek_preserves_reasoning_and_parallel_tool_ids_on_wire(self):
        from scoach.llm import deepseek_generate
        first = {'role': 'assistant', 'content': None, 'reasoning_content': 'opaque reasoning', 'tool_calls': [
            {'id': 'ds-1', 'type': 'function', 'function': {'name': 'get_overview', 'arguments': '{}'}},
            {'id': 'ds-2', 'type': 'function', 'function': {'name': 'list_goals', 'arguments': '{}'}}]}
        captured = []
        def send(request, timeout):
            captured.append({'url': request.full_url, 'auth': request.get_header('Authorization'), 'body': json.loads(request.data)})
            message = first if len(captured) == 1 else {'role': 'assistant', 'content': 'Hello.'}
            return io.BytesIO(json.dumps({'choices': [{'message': message}]}).encode())
        declarations = [{'name': 'get_overview', 'description': 'Read overview', 'parameters': {'type': 'OBJECT', 'properties': {'month': {'type': 'STRING'}}}}]
        contents = [{'role': 'user', 'parts': [{'text': 'Hello'}]}]
        with patch('urllib.request.urlopen', side_effect=send):
            response = deepseek_generate(contents, system='System', tools=declarations, api_key='test', model='deepseek-flash')
            self.assertEqual([p['functionCall']['id'] for p in response['parts']], ['ds-1', 'ds-2'])
            contents.extend([response, {'role': 'user', 'parts': [
                {'functionResponse': {'name': 'get_overview', 'id': 'ds-1', 'response': {'total_cents': 1234}}},
                {'functionResponse': {'name': 'list_goals', 'id': 'ds-2', 'response': {'goals': []}}}]}])
            final = deepseek_generate(contents, system='System', tools=declarations, api_key='test', model='deepseek-flash')
        self.assertEqual(final['parts'], [{'text': 'Hello.'}])
        self.assertEqual(captured[0]['url'], 'https://api.deepseek.com/chat/completions')
        self.assertEqual(captured[0]['auth'], 'Bearer test')
        self.assertEqual(captured[0]['body']['tools'][0]['function']['parameters']['properties']['month']['type'], 'string')
        self.assertEqual(captured[1]['body']['messages'][2], first)
        self.assertEqual([m['tool_call_id'] for m in captured[1]['body']['messages'][3:]], ['ds-1', 'ds-2'])
        self.assertEqual(json.loads(captured[1]['body']['messages'][3]['content']), {'total_cents': 1234})

    def test_configured_deepseek_takes_priority_without_changing_gemini_fallback(self):
        from scoach.llm import generate, agent_configured
        captured = []
        def send(request, timeout):
            captured.append(request.full_url)
            return io.BytesIO(b'{"choices":[{"message":{"role":"assistant","content":"Hello."}}]}')
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'ds-test', 'DEEPSEEK_MODEL': 'deepseek-flash', 'GEMINI_API_KEY': 'gm-test'}, clear=True), patch('urllib.request.urlopen', side_effect=send):
            self.assertTrue(agent_configured())
            self.assertEqual(generate([{'role':'user','parts':[{'text':'Hello'}]}], system='', tools=[])['parts'][0]['text'], 'Hello.')
        self.assertEqual(captured, ['https://api.deepseek.com/chat/completions'])

    def test_deepseek_malformed_responses_and_model_names_fail_closed(self):
        from scoach.llm import deepseek_generate
        for envelope in ({'choices': []}, {'choices': [{'message': {'role': 'assistant', 'content': None}}]}):
            with self.subTest(envelope=envelope), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(envelope).encode())), self.assertRaises(ValueError):
                deepseek_generate([], system='', tools=[], api_key='test')
        with self.assertRaises(ValueError):
            deepseek_generate([], system='', tools=[], api_key='test', model='../bad')
