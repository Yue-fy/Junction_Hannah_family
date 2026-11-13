"""Smoke-sized: hosted Nemotron direct counts for windows/doors on TRAIN drawings (rate-limited API)."""
import collections, concurrent.futures as cf, json, random, re, sys, time
from stoa import llm
from stoa.data import abspath
from stoa.eval.splits import load_split
from stoa.solvers.raster.classes import question_class

n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
gold = collections.defaultdict(dict)
for q in load_split("train"):
    if q.source == "cubicasa5k" and q.question.lower().startswith("how"):
        c = question_class(q.question)
        if c:
            gold[q.path][c] = (q.answer, q.question)
paths = sorted(p for p, d in gold.items() if len(d) >= 8)
random.Random(7).shuffle(paths)
tasks = [(p, c) for p in paths[:n] for c in ("window", "door") if c in gold[p]]


def run(t):
    p, c = t
    ans, q = gold[p][c]
    try:
        r = llm.chat(q + "\n\nCount carefully. Reply with the final count as a single integer on the last line, like `ANSWER: 7`.",
                     images=[abspath(p)], backend="nvidia", max_tokens=2048, thinking=None, cache=True)
        m = re.findall(r"ANSWER:\s*(\d+)", r.text) or re.findall(r"\d+", r.text)
        return dict(path=p, cls=c, gold=ans, value=int(m[-1]) if m else None, tok=[r.prompt_tokens, r.completion_tokens],
                    s=round(r.latency_s, 1))
    except Exception as e:
        return dict(path=p, cls=c, gold=ans, error=str(e)[:200])


t0 = time.time()
with cf.ThreadPoolExecutor(4) as ex:
    rows = list(ex.map(run, tasks))
open("/home/fangy4/work/projects/junction-shared/artifacts/W3/calib/nemotron-wd.jsonl", "w").write(
    "".join(json.dumps(r) + "\n" for r in rows))
for c in ("window", "door"):
    rs = [r for r in rows if r["cls"] == c and r.get("value") is not None]
    print(c, len(rs), "exact", sum(r["value"] == r["gold"] for r in rs), "within1",
          sum(abs(r["value"] - r["gold"]) <= 1 for r in rs), [(r["value"], r["gold"]) for r in rs],
          "tok", [r["tok"] for r in rs][:3])
print("errors", [r["error"] for r in rows if "error" in r][:3], f"{time.time() - t0:.0f}s")
