"""Score pipeline vs pipeline_est on probe_e2e.jsonl: Q's handled_flag (conf < 0.5 AND a missing line / flag words),
'gives a number or an estimate sentence' (not 'unknown'), derived rows untouched, LLM calls and tokens.

    python experiments/r1/estimate/compare.py RUN_BASE RUN_EST
"""
import json
import re
import sys

FLAG = re.compile(r"(not (shown|stated|recorded|available|on the|in the)|missing|cannot|no .{0,20} data|unanswerable|"
                  r"estimate|assum)", re.I)


def load(p):
    return {r["qid"]: r for r in map(json.loads, open(p))}


def handled(r):
    c = r.get("confidence") or 0
    text = " ".join(map(str, (r.get("missing") or []) + (r.get("assumptions") or [])))
    return c < 0.5 and bool(r.get("missing") or FLAG.search(text))


def useful(r):
    v = r.get("value")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return True
    return isinstance(v, str) and bool(re.search(r"\d", v)) and "unknown" not in v.lower()


def main(a, b):
    A, B = load(a), load(b)
    qs = [q for q in A if q in B]
    for name, sel in (("unanswerable/out-of-drawing", lambda r: (r.get("meta") or {}).get("expect") == "flag"),
                      ("derived (states its rate)", lambda r: (r.get("meta") or {}).get("expect") == "derived")):
        ids = [q for q in qs if sel(A[q])]
        for tag, R in (("pipeline    ", A), ("pipeline_est", B)):
            rs = [R[q] for q in ids]
            calls = sum(((r.get("cost") or {}).get("llm_calls") or 0) for r in rs)
            tok = sum(((r.get("cost") or {}).get("llm_tokens_in") or 0) + ((r.get("cost") or {}).get("llm_tokens_out") or 0)
                      for r in rs)
            wall = sum(r.get("latency_s") or 0 for r in rs)
            print(f"{name:28s} {tag} n={len(rs)} handled {sum(map(handled, rs))}  number/estimate "
                  f"{sum(map(useful, rs))}  'unknown'/None {sum(1 for r in rs if r.get('value') is None or str(r.get('value')).lower() in ('unknown', 'none'))}"
                  f"  conf>=0.5 {sum(1 for r in rs if (r.get('confidence') or 0) >= 0.5)}  LLM calls {calls}  tokens {tok}  wall {wall:.0f}s")
        if "derived" in name:
            ch = [q for q in ids if str(A[q].get("value")) != str(B[q].get("value"))]
            print(f"   derived rows whose value changed: {len(ch)}", [(B[q]['question'][:50], A[q]['value'], B[q]['value']) for q in ch][:5])
    print("\nexamples (pipeline -> pipeline_est):")
    for q in qs:
        if (A[q].get("meta") or {}).get("expect") == "flag" and q.startswith("rt"):
            print(f" {A[q]['question'][:60]!r}: {str(A[q]['value'])[:40]!r} @{A[q]['confidence']:.2f} -> "
                  f"{str(B[q]['value'])[:90]!r} {B[q].get('unit') or ''} @{B[q]['confidence']:.2f} [{B[q]['solver']}]")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
