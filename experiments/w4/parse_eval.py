"""Measure the intent parser: twin agreement (EN vs local-language twin parse to the same key), unknown rate,
task accuracy vs the dataset's type, and per-source coverage. Run: PYTHONPATH=. python experiments/w4/parse_eval.py"""
import collections
import sys

from stoa.data import concept_map, load_questions
from stoa.router.intent import parse

qs = [q for q in load_questions() if q.source != "ifc_bench"]
cm = concept_map()
cache = {}


def P(q):
    if q.question not in cache:
        cache[q.question] = parse(q.question)
    return cache[q.question]


task_ok = collections.Counter(); n = collections.Counter(); unk = collections.Counter()
for q in qs:
    it = P(q)
    n[q.source] += 1
    task_ok[q.source] += (it.task == q.type)
    unk[q.source] += (it.target == "unknown")
by_c = collections.defaultdict(list)
for q in qs:
    by_c[cm[q.qid]].append(q)
pairs = [v for v in by_c.values() if len(v) == 2]
agree = collections.Counter(); npairs = collections.Counter(); bad = collections.Counter()
for a, b in pairs:
    ka, kb = P(a), P(b)
    same = ka.key == kb.key and ka.filters.get("apartment") == kb.filters.get("apartment") and \
        ka.filters.get("room_no") == kb.filters.get("room_no")
    npairs[a.source] += 1
    agree[a.source] += same
    if not same:
        bad[(a.source, ka.key, kb.key)] += 1
print(f"{'source':16s} {'n':>7s} {'task%':>6s} {'unknown%':>8s} {'pairs':>7s} {'twin-agree%':>11s}")
for s in sorted(n):
    print(f"{s:16s} {n[s]:7d} {100*task_ok[s]/n[s]:6.1f} {100*unk[s]/n[s]:8.2f} {npairs[s]:7d} "
          f"{(100*agree[s]/npairs[s]) if npairs[s] else float('nan'):11.1f}")
tot = sum(n.values())
print(f"ALL {tot} task {100*sum(task_ok.values())/tot:.1f}% unknown {100*sum(unk.values())/tot:.2f}% "
      f"twin-agree {100*sum(agree.values())/max(1,sum(npairs.values())):.1f}%")
for k, v in bad.most_common(int(sys.argv[1]) if len(sys.argv) > 1 else 12):
    print("  disagree", v, k)
