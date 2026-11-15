#!/usr/bin/env python3
"""Ask a running S-Coach server's /api/agent 30 fixed questions and write a markdown table.

Usage (server already running, model configured on the server):
  python3 "s bank/scripts/eval_agent.py" --base-url http://127.0.0.1:8080 \
      --customer CUST00001 --month 2026-09 --out "s bank/docs/critique/eval_agent.md"

Questions cover EN/FI/SV: the brief's four, emotional and life-event messages, multi-part questions,
data limits and follow-ups (a follow-up sends the earlier question and answer as text history).
Each row: id, language, kind, question, source, ms, verification, flags, answer. Flags are cheap
heuristics for the reviewer (apology, English money format in FI/SV, too long, more than one question,
large percentage), not a verdict. Stdlib only; read-only route; nothing is saved.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# (id, locale, kind, message, follows_id or None)
QUESTIONS = [
    ('en01', 'en', 'brief', 'Where did my money go this month?', None),
    ('en02', 'en', 'brief', 'What kind of spender am I?', None),
    ('en03', 'en', 'brief', 'What can I safely spend this week?', None),
    ('en04', 'en', 'brief', 'How could I save more?', None),
    ('en05', 'en', 'follow-up', 'And in August?', 'en01'),
    ('en06', 'en', 'plan', 'Will my money last until payday?', None),
    ('en07', 'en', 'emotional', "I'm really stressed about money right now.", None),
    ('en08', 'en', 'life event', 'I just lost my job. What should I do?', None),
    ('en09', 'en', 'life event', "We're having a baby in March.", None),
    ('en10', 'en', 'multi-part', 'How much did I spend on restaurants and on groceries, and which one grew more?', None),
    ('en11', 'en', 'multi-part', 'What can I spend until payday, and how much could I put aside?', None),
    ('en12', 'en', 'benchmark', 'How do I compare with others my age on groceries?', None),
    ('en13', 'en', 'goal', 'I want to save 2000 euros for a trip to Japan by next June.', None),
    ('en14', 'en', 'what-if', 'What if I spent 20% less on restaurants?', None),
    ('en15', 'en', 'plan', 'What bills are coming up before payday?', None),
    ('en16', 'en', 'plans module', 'Should I pay extra on my home loan?', None),
    ('en17', 'en', 'data limit', 'How much do I spend on coffee?', None),
    ('en18', 'en', 'buffer', 'What is a surprise buffer and how big should mine be?', None),
    ('en19', 'en', 'closing', 'ok thanks', 'en18'),
    ('en20', 'en', 'follow-up', 'How much is that per day?', 'en03'),
    ('fi01', 'fi', 'brief', 'Mihin rahani menivät tässä kuussa?', None),
    ('fi02', 'fi', 'brief', 'Paljonko voin turvallisesti käyttää tällä viikolla?', None),
    ('fi03', 'fi', 'brief', 'Miten voisin säästää enemmän?', None),
    ('fi04', 'fi', 'emotional', 'Olen tosi huolissani rahoistani.', None),
    ('fi05', 'fi', 'follow-up', 'Entä elokuussa?', 'fi01'),
    ('fi06', 'fi', 'brief', 'Millainen kuluttaja olen?', None),
    ('sv01', 'sv', 'brief', 'Vart tog mina pengar vägen den här månaden?', None),
    ('sv02', 'sv', 'plan', 'Hur mycket kan jag spendera fram till lönedagen?', None),
    ('sv03', 'sv', 'brief', 'Hur kan jag spara mer?', None),
    ('sv04', 'sv', 'life event', 'Jag har förlorat jobbet och är orolig.', None),
]

_APOLOGY = re.compile(r'^\s*(my apologies|apologies|sorry|you\'?re right|i misstated|anteeksi|pahoittelen|olet oikeassa|förlåt|ursäkta|du har rätt)', re.I)
_EN_MONEY = re.compile(r'€\s?\d')
_BIG_PERCENT = re.compile(r'(\d{3,}(?:[.,]\d+)?)\s?%')


def flags(locale, text, kind):
    found = []
    if _APOLOGY.search(text):
        found.append('apology')
    if locale in ('fi', 'sv') and _EN_MONEY.search(text):
        found.append('EN money format')
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s]
    if len(sentences) > (7 if kind == 'multi-part' else 5):
        found.append(f'long ({len(sentences)} sentences)')
    if text.count('?') > 1:
        found.append('several questions')
    if _BIG_PERCENT.search(text):
        found.append('percent >= 100')
    if re.search(r'\b(baskets?|korit?|korgar?)\b', text, re.I) and kind in ('emotional', 'life event'):
        found.append('basket talk in emotional answer')
    return found


def post(base_url, payload, timeout):
    url = base_url.rstrip('/') + '/api/agent'
    data = json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    host = urllib.parse.urlparse(url).hostname or ''
    # A local server must not be routed through an outbound proxy.
    handlers = [urllib.request.ProxyHandler({})] if host in ('localhost', '127.0.0.1', '::1') else []
    opener = urllib.request.build_opener(*handlers)
    with opener.open(request, timeout=timeout) as response:
        body = json.loads(response.read().decode())
    return body.get('data', body) if isinstance(body, dict) else body


def cell(text, limit=None):
    text = ' '.join(str(text).split())
    if limit and len(text) > limit:
        text = text[:limit - 1] + '…'
    return text.replace('|', '\\|')


def run(base_url, customer, month, timeout, only=None, pause=0.0):
    answers, rows = {}, []
    for qid, locale, kind, message, follows in QUESTIONS:
        if only and qid not in only:
            continue
        history = []
        if follows and follows in answers:
            previous_message, previous_answer = answers[follows]
            history = [{'role': 'user', 'text': previous_message[:600]}]
            if previous_answer.strip():
                history.append({'role': 'coach', 'text': previous_answer[:600]})
        payload = {'customer_id': customer, 'month': month, 'locale': locale, 'message': message, 'history': history}
        started = time.monotonic()
        try:
            result = post(base_url, payload, timeout)
            error = None
        except (urllib.error.URLError, OSError, ValueError) as problem:
            result, error = {}, f'{type(problem).__name__}: {problem}'
        ms = int((time.monotonic() - started) * 1000)
        text = ' '.join(result.get('answer') or []) if isinstance(result.get('answer'), list) else str(result.get('answer') or '')
        if not text and result.get('source') == 'catalogue':
            text = '[catalogue] ' + '; '.join(s.get('text', '') for s in result.get('suggestions') or [] if isinstance(s, dict))
        answers[qid] = (message, text)
        rows.append({'id': qid, 'locale': locale, 'kind': kind, 'question': message,
                     'source': result.get('source') or 'error', 'fallback': result.get('fallback_reason'),
                     'ms': ms, 'verification': result.get('verification') or '-',
                     'flags': flags(locale, text, kind) if text else ['no answer'],
                     'answer': text or error or ''})
        print(f"{qid} {rows[-1]['source']} {ms}ms {','.join(rows[-1]['flags']) or 'ok'}", file=sys.stderr, flush=True)
        if pause:
            time.sleep(pause)
    return rows


def markdown(rows, base_url, customer, month):
    agent = sum(1 for r in rows if r['source'] == 'agent')
    flagged = sum(1 for r in rows if r['flags'])
    times = sorted(r['ms'] for r in rows if r['source'] == 'agent')
    median = times[len(times) // 2] if times else 0
    lines = [f'# Agent eval ({customer}, {month})', '',
             f'Server: `{base_url}` · run {time.strftime("%Y-%m-%d %H:%M")} · {len(rows)} questions · '
             f'source=agent {agent}/{len(rows)} · median {median} ms · flagged {flagged}', '',
             'Flags are heuristics for the reviewer, not verdicts.', '',
             '| # | lang | kind | question | source | ms | verification | flags | answer |',
             '|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        source = r['source'] + (f" ({r['fallback']})" if r['fallback'] else '')
        lines.append('| ' + ' | '.join([r['id'], r['locale'], r['kind'], cell(r['question']), cell(source), str(r['ms']),
                                        r['verification'], cell(', '.join(r['flags']) or '-'), cell(r['answer'], 900)]) + ' |')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--customer', default='CUST00001')
    parser.add_argument('--month', default='2026-09')
    parser.add_argument('--out', default='-', help='markdown file path, or - for stdout')
    parser.add_argument('--timeout', type=float, default=40.0)
    parser.add_argument('--pause', type=float, default=0.0, help='seconds between questions')
    parser.add_argument('--only', nargs='*', help='question ids to run, e.g. en01 fi02')
    args = parser.parse_args(argv)
    rows = run(args.base_url, args.customer, args.month, args.timeout, set(args.only or []) or None, args.pause)
    report = markdown(rows, args.base_url, args.customer, args.month)
    if args.out == '-':
        sys.stdout.write(report)
    else:
        with open(args.out, 'w', encoding='utf-8') as handle:
            handle.write(report)
        print(f'wrote {args.out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
