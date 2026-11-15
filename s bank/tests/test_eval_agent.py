"""scripts/eval_agent.py: question list, heuristic flags and the markdown table, against a stub server."""
import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'eval_agent.py'
_SPEC = importlib.util.spec_from_file_location('eval_agent', _PATH)
eval_agent = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(eval_agent)


class _Stub(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode())
        _Stub.seen.append(body)
        text = 'Palkkapäivään asti voit käyttää €162.00 päivässä.' if body['locale'] == 'fi' else 'You can use €162.00 a day until payday.'
        data = {'source': 'agent', 'fallback_reason': None, 'verification': 'complete', 'answer': [text]}
        out = json.dumps({'ok': True, 'data': data}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


class EvalAgentTests(unittest.TestCase):
    def test_question_list_covers_the_brief_languages_and_kinds(self):
        questions = eval_agent.QUESTIONS
        self.assertEqual(len(questions), 30)
        self.assertEqual(len({q[0] for q in questions}), 30)
        texts = {q[3] for q in questions}
        for brief in ('Where did my money go this month?', 'What kind of spender am I?',
                      'What can I safely spend this week?', 'How could I save more?'):
            self.assertIn(brief, texts)
        self.assertEqual({q[1] for q in questions}, {'en', 'fi', 'sv'})
        kinds = {q[2] for q in questions}
        for kind in ('brief', 'emotional', 'life event', 'multi-part', 'follow-up'):
            self.assertIn(kind, kinds)
        ids = [q[0] for q in questions]
        for qid, _, _, _, follows in questions:
            if follows:
                self.assertLess(ids.index(follows), ids.index(qid))

    def test_flags(self):
        self.assertIn('apology', eval_agent.flags('en', "My apologies for the mix-up. You can use €5.", 'brief'))
        self.assertIn('apology', eval_agent.flags('en', "You're right — I misstated that.", 'brief'))
        self.assertIn('EN money format', eval_agent.flags('fi', 'Kulutit €225.70 ravintoloihin.', 'brief'))
        self.assertNotIn('EN money format', eval_agent.flags('fi', 'Kulutit 225,70 € ravintoloihin.', 'brief'))
        self.assertIn('percent >= 100', eval_agent.flags('en', 'That is +226.4% above average.', 'benchmark'))
        self.assertIn('several questions', eval_agent.flags('en', 'Which month? Which category?', 'brief'))
        self.assertIn('basket talk in emotional answer', eval_agent.flags('en', "Let's sort money into three baskets.", 'emotional'))
        self.assertEqual(eval_agent.flags('en', 'You can use €162.00 a day until payday.', 'brief'), [])

    def test_run_against_stub_server_writes_table_with_history_for_follow_ups(self):
        _Stub.seen = []
        server = ThreadingHTTPServer(('127.0.0.1', 0), _Stub)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_address[1]}'
        rows = eval_agent.run(base, 'CUST00001', '2026-09', 5, only={'en03', 'en20', 'fi02'})
        self.assertEqual([r['id'] for r in rows], ['en03', 'en20', 'fi02'])
        self.assertEqual(_Stub.seen[0]['history'], [])
        self.assertEqual(_Stub.seen[1]['history'][0], {'role': 'user', 'text': 'What can I safely spend this week?'})
        self.assertEqual(_Stub.seen[1]['history'][1]['role'], 'coach')
        self.assertEqual(rows[2]['flags'], ['EN money format'])
        report = eval_agent.markdown(rows, base, 'CUST00001', '2026-09')
        self.assertIn('| # | lang | kind | question | source | ms | verification | flags | answer |', report)
        self.assertIn('source=agent 3/3', report)
        self.assertIn('| en03 | en | brief |', report)

    def test_unreachable_server_is_reported_not_raised(self):
        rows = eval_agent.run('http://127.0.0.1:9', 'CUST00001', '2026-09', 1, only={'en01'})
        self.assertEqual(rows[0]['source'], 'error')
        self.assertEqual(rows[0]['flags'], ['no answer'])


if __name__ == '__main__':
    unittest.main()
