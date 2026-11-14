"""Run a solver on open probe files in F/Q format ({path, question, answer, unit, meta.kind}), Swiss rows only,
a fixed sample of up to N rows per kind. Right = within 2% (counts exact); string gold 'a ; b' = both numbers or
conf <= 0.5. Usage: PYTHONPATH=. python experiments/w2/op_probe/run_open.py N file.jsonl [file2 ...] [solver=dxf]"""
import json
import random
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from stoa.solvers import get_solver


def right(gold, unit, a) -> bool:
    if a.value is None:
        return False
    if isinstance(gold, str):
        if " ; " in gold:
            parts = [p for p in re.findall(r"\d+(?:\.\d+)?", gold.split(" ; ")[0])]
            got = re.findall(r"\d+(?:\.\d+)?", str(a.value))
            alt = gold.split(" ; ")[1]
            return all(p in got for p in parts) or a.confidence <= 0.5 or (alt.strip("[]") in got and len(got) == 1)
        return gold.lower() in str(a.value).lower()
    try:
        v = float(a.value)
    except (TypeError, ValueError):
        return False
    if unit == "count":
        return round(v) == round(float(gold))
    return abs(v - float(gold)) <= 0.02 * abs(float(gold)) + 1e-9


def main():
    n = int(sys.argv[1])
    files = [a for a in sys.argv[2:] if "=" not in a]
    kw = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
    s = get_solver(kw.pop("solver", "dxf"), **kw)
    rows = [json.loads(l) for f in files for l in open(f)]
    rows = [r for r in rows if "swiss_dwellings" in r["path"]]
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["meta"].get("kind", "?")].append(r)
    rng = random.Random(7)
    sample = [r for k in sorted(by_kind) for r in rng.sample(by_kind[k], min(n, len(by_kind[k])))]
    with ThreadPoolExecutor(4) as ex:
        answers = list(ex.map(lambda r: s.solve(r["path"], r["question"]), sample))
    agg = defaultdict(lambda: [0, 0, 0])
    for r, a in zip(sample, answers):
        ok = right(r["answer"], r.get("unit"), a)
        cw = (not ok) and a.value is not None and a.confidence >= 0.5
        b = agg[r["meta"].get("kind", "?")]
        b[0] += 1; b[1] += ok; b[2] += cw
        if not ok:
            parsed = next((t for t in a.trace if t.startswith("parsed:")), "")
            print(f"{'CW' if cw else 'xx'} {a.value!s:>14.14} {a.confidence:4.2f} | gold {r['answer']!s:>9.9} | "
                  f"{r['meta'].get('kind')} | {r['question'][:80]} | {parsed[8:70]}")
    tot = [sum(v[i] for v in agg.values()) for i in range(3)]
    print("\nkind                                  n  right  cw")
    for k, (m, ok, cw) in sorted(agg.items()):
        print(f"{k:<36} {m:3d} {ok:6d} {cw:4d}")
    print(f"{'ALL':<36} {tot[0]:3d} {tot[1]:6d} {tot[2]:4d}")


if __name__ == "__main__":
    main()
