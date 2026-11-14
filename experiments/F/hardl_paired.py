"""Paired language penalty on hardL (stoa/eval/hardl.py): each translated question is matched to its English base
question (meta.base_qid) answered in an English run, so acc(en) - acc(xx) on the SAME items is the language penalty.
Aggregates only (safe for the held-out hardL file).

    python experiments/F/hardl_paired.py EN_RUN.jsonl RUN.jsonl [RUN2.jsonl ...]
EN_RUN = a run on hardL_open (it holds the 'en' rows). Each RUN is reported per language and per origin
(dev atomic vs hard2 composition), with conf>=0.8 precision and confident-wrong counts.
"""
from __future__ import annotations

import collections
import json
import sys


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def main():
    en_rows = [r for r in load(sys.argv[1]) if (r.get("meta") or {}).get("lang") == "en"]
    en = {r["meta"]["base_qid"]: bool(r.get("correct")) for r in en_rows}
    print(f"en base: {len(en)} questions, {100 * sum(en.values()) / max(1, len(en)):.1f}% right ({sys.argv[1][-30:]})")
    for path in sys.argv[2:]:
        rows = [r for r in load(path) if (r.get("meta") or {}).get("lang") not in (None, "en")]
        print(f"== {path.rsplit('/', 1)[-1]}")
        groups = collections.defaultdict(list)
        for r in rows:
            m = r["meta"]
            if m["base_qid"] not in en:
                continue
            for key in (m["lang"], f"{m['lang']}/{m['recipe'].split(':')[0]}", "ALL", f"ALL/{m['recipe'].split(':')[0]}",
                        f"ALL/{r['source']}"):
                groups[key].append(r)
        for key in sorted(groups, key=lambda k: (k.startswith("ALL"), k)):
            v = groups[key]
            n = len(v)
            ok = sum(bool(r.get("correct")) for r in v)
            base = sum(en[r["meta"]["base_qid"]] for r in v)
            hi = [r for r in v if (r.get("confidence") or 0) >= 0.8]
            hiok = sum(bool(r.get("correct")) for r in hi)
            lost = sum(en[r["meta"]["base_qid"]] and not r.get("correct") for r in v)
            won = sum((not en[r["meta"]["base_qid"]]) and bool(r.get("correct")) for r in v)
            fe = collections.Counter((r.get("meta") or {}).get("frontend") for r in v if (r.get("meta") or {}).get("frontend"))
            print(f"  {key:22s} n={n:3d}  xx {100 * ok / n:5.1f}  en {100 * base / n:5.1f}  delta {100 * (ok - base) / n:+6.1f}"
                  f"  (lost {lost}, won {won})  conf>=0.8 {len(hi):3d} @ {100 * hiok / max(1, len(hi)):5.1f}%"
                  f"  confident-wrong {len(hi) - hiok}" + (f"  frontend {dict(fe)}" if fe else ""))


if __name__ == "__main__":
    main()
