"""Simulate R2's translate-first front end (stoa.llm.to_english + the should_translate trigger, R2 04:20) BEFORE W4
wires it into the pipeline: rewrite a split file's questions the way the front end would, then run the unchanged
pipeline on the rewritten file. The paired comparison against the original file is the front end's gain.

Trigger (as R2's should_translate, night-R2 a244c80): non-English (lang_guess) AND the intent parser failed (lang '?',
no target / unknown, or a free-text task). Translate with force=True; keep the English only if its re-parse finds a
target. Rows keep qid (so runs pair up), gold and meta; meta.frontend records what happened.

    python experiments/F/lang_frontend_sim.py IN.jsonl OUT.jsonl [--workers 4]
Then: python -m stoa.eval --solver pipeline --split OUT.jsonl --workers 4
Prints counts only (safe on held-out files).
"""
from __future__ import annotations

import argparse
import collections
import json
from concurrent.futures import ThreadPoolExecutor

from stoa.llm import lang_guess, to_english
from stoa.router.intent import parse


def failed(intent) -> bool:
    return (getattr(intent, "lang", "?") == "?" or getattr(intent, "target", None) in (None, "unknown")
            or getattr(intent, "task", None) == "text")


def front(q: str) -> tuple[str, str]:
    if lang_guess(q) == "en":
        return q, "english"
    if not failed(parse(q)):
        return q, "parsed"
    t = to_english(q, force=True)
    if not t.ok or not t.translated:
        return q, "translation-failed"
    if failed(parse(t.text)):
        return q, "reparse-failed"
    return t.text, "translated"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    rows = [json.loads(line) for line in open(a.inp, encoding="utf-8") if line.strip()]
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(lambda r: front(r["question"]), rows))
    stats = collections.Counter()
    with open(a.out, "w", encoding="utf-8") as fh:
        for r, (q, how) in zip(rows, res):
            lg = (r.get("meta") or {}).get("lang", "?")
            stats[(lg, how)] += 1
            fh.write(json.dumps({**r, "question": q, "meta": {**(r.get("meta") or {}), "frontend": how}},
                                ensure_ascii=False) + "\n")
    for (lg, how), n in sorted(stats.items()):
        print(f"{lg:3s} {how:20s} {n}")


if __name__ == "__main__":
    main()
