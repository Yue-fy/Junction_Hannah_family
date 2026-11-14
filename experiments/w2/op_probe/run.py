"""Run dxf on hand-written probe questions (gold from the floor's room table, written BEFORE any fix).
gold None = unanswerable / false premise: right = abstain or conf <= 0.3.
Usage: PYTHONPATH=. python experiments/w2/op_probe/run.py experiments/w2/op_probe/probe1.jsonl [solver args k=v]"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

from stoa.solvers import get_solver


def right(gold, unit, a) -> bool:
    if isinstance(gold, str) and " ; " in gold:  # two numbers asked: both in the answer, or conf <= 0.5 (S0 D19)
        parts = gold.split(" ; ")
        got = re.findall(r"\d+(?:\.\d+)?", str(a.value)) if a.value is not None else []
        return all(p in got for p in parts) or a.value is None or a.confidence <= 0.5
    if gold is None:
        return a.value is None or a.confidence <= 0.3
    if a.value is None:
        return False
    if isinstance(gold, str):
        return str(a.value).strip().lower() == gold.lower() or gold.lower() in str(a.value).lower()
    try:
        v = float(a.value)
    except (TypeError, ValueError):
        return False
    if unit == "count":
        return round(v) == gold
    return abs(v - gold) <= 0.02 * abs(gold) + 1e-9


def main():
    rows = [json.loads(l) for l in open(sys.argv[1])]
    kw = dict(a.split("=", 1) for a in sys.argv[2:])
    workers = int(kw.pop("workers", "4"))
    s = get_solver(kw.pop("solver", "dxf"), **kw)
    by = defaultdict(lambda: [0, 0, 0])
    with ThreadPoolExecutor(workers) as ex:
        answers = list(ex.map(lambda r: s.solve(r["path"], r["question"]), rows))
    for r, a in zip(rows, answers):
        ok = right(r["gold"], r["unit"], a)
        cw = (not ok) and a.value is not None and a.confidence >= 0.5
        b = by[r["kind"].split("-")[0]]
        b[0] += 1; b[1] += ok; b[2] += cw
        parsed = next((t for t in a.trace if t.startswith("parsed:")), "")
        print(f"{'OK ' if ok else ('CW ' if cw else 'xx ')} {a.value!s:>18.18} {a.unit!s:>5} {a.confidence:4.2f} | gold {r['gold']!s:>8.8} | {r['question'][:70]} | {parsed[8:90]}")
        if not ok:
            for t in a.trace:
                if any(k in t for k in ("operation check", "translated", "table QA", "rewritten", "name check")):
                    print("      ", t[:200])
    tot = [sum(v[i] for v in by.values()) for i in range(3)]
    print("\nkind            n  right  conf-wrong(>=0.5)")
    for k, (n, ok, cw) in sorted(by.items()):
        print(f"{k:<14} {n:3d} {ok:6d} {cw:6d}")
    print(f"{'ALL':<14} {tot[0]:3d} {tot[1]:6d} {tot[2]:6d}")


if __name__ == "__main__":
    main()
