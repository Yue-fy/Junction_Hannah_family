"""Summarise the expert's input into $JUNCTION_SHARED/human/REPORT.md (also rebuilt after every save).

    $JUNCTION_VENV/bin/python -m workbench.report [--stdout]

Sections: audit verdicts (by source; the interesting disagreements: "wrong" on answers that match the reference =
evidence or reference problem, "supports" on answers that differ = possible reference error), the expert's own
questions (her answer vs ours, scored with the eval's tolerance), and her rules.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter, defaultdict

from workbench import store

VERDICT = {"supports": "✓ supports", "wrong": "✗ wrong", "cant_tell": "? can't tell"}


def _last_by(rows: list[dict], key: str) -> dict[str, dict]:
    out = {}
    for r in rows:
        out[r.get(key)] = r
    return out


def _clip(s, n=140) -> str:
    s = " ".join(str(s if s is not None else "").split()).replace("|", "/")
    return s if len(s) <= n else s[: n - 1] + "…"


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _time_line(done: list[dict]) -> str:
    """'Time to verify' (Stoa: a human can verify an answer in seconds): median seconds from item shown to verdict,
    page-hidden time left out (the browser measures it; rows before 11:20 have none)."""
    secs = [(a["verdict"], float(a["seconds"])) for a in done if isinstance(a.get("seconds"), (int, float))]
    if not secs:
        return ""
    parts = []
    for v in ("supports", "wrong", "cant_tell"):
        xs = [s for vv, s in secs if vv == v]
        if xs:
            parts.append(f"{VERDICT[v]} {_median(xs):.0f} s (n={len(xs)})")
    allx = [s for _, s in secs]
    quick = sum(1 for s in allx if s <= 30)
    return (f"Time to verify (item shown → verdict): median **{_median(allx):.0f} s** over {len(allx)} items; "
            f"{quick} of {len(allx)} within 30 s. By verdict: " + ", ".join(parts) + ".")


def build() -> str:
    from stoa.eval.scoring import score

    items = store.read("audit_items")
    audits = _last_by(store.read("audit"), "item_id")
    live = [q for q in _last_by(store.read("questions"), "qid").values() if not q.get("deleted")]
    qs = [q for q in live if q.get("origin") != "audit"]
    agold = [q for q in live if q.get("origin") == "audit"]
    rules = store.read("rules")
    L = [f"# Expert workbench report (updated {time.strftime('%Y-%m-%d %H:%M')})", "",
         "Source: `$JUNCTION_SHARED/human/` (written by the workbench on :8200, agent H). "
         "Rebuilt after every save; `python -m workbench.report` rebuilds it by hand.", ""]

    # --- audit
    done = [a for a in audits.values() if a.get("item_id") in {i["item_id"] for i in items}]
    c = Counter(a["verdict"] for a in done)
    L += [f"## 1. Audit of our answers: {len(done)} / {len(items)} checked", ""]
    if done:
        L.append(f"Verdicts: {c.get('supports', 0)} ✓ supports, {c.get('wrong', 0)} ✗ wrong, "
                 f"{c.get('cant_tell', 0)} ? can't tell.")
        t = _time_line(done)
        if t:
            L.append(t)
        by_src = defaultdict(Counter)
        it_by = {i["item_id"]: i for i in items}
        for a in done:
            it = it_by.get(a["item_id"]) or {}
            src = (f"batch: {it['batch_label']}" if it.get("batch_label") else
                   a.get("path", "").split("/")[1] if a.get("path", "").count("/") >= 2 else "?")
            by_src[src][a["verdict"]] += 1
        L += ["", "| source (or batch) | ✓ | ✗ | ? |", "|---|---|---|---|"]
        for src, cc in sorted(by_src.items()):
            L.append(f"| {src} | {cc.get('supports', 0)} | {cc.get('wrong', 0)} | {cc.get('cant_tell', 0)} |")
        flagged = [a for a in done if (a["verdict"] == "wrong") or (a["verdict"] == "supports" and a.get("matches_reference") is False)
                   or a.get("comment") or a.get("correct_value")]
        if flagged:
            L += ["", "Items worth a look (✗, ✓ although we differ from the reference, or any comment):", "",
                  "| item | verdict | ours | reference | matches ref | expert's value | question | comment |",
                  "|---|---|---|---|---|---|---|---|"]
            for a in flagged:
                L.append(f"| {a['item_id']} | {VERDICT.get(a['verdict'], a['verdict'])} | {_clip(a.get('our_value'), 30)} "
                         f"{a.get('our_unit') or ''} | {_clip(a.get('gold'), 30)} | {a.get('matches_reference')} | "
                         f"{_clip(a.get('correct_value'), 30)} | "
                         f"{_clip(a.get('question'), 90)} | {_clip(a.get('comment'), 200)} |")
    L.append("")

    # --- questions
    L += [f"## 2. Expert questions: {len(qs)} (eval split `human`, F: `python -m stoa.eval --solver pipeline --split human`)", ""]
    if qs:
        n_sc = n_ok = 0
        L += ["| qid | drawing | question | her answer | sure | ours (when asked) | agree |", "|---|---|---|---|---|---|---|"]
        for q in qs:
            sysa = q.get("system") or {}
            agree = None
            if sysa:
                agree = score(q.get("type") or "other", q.get("answer") or None, q.get("unit") or None,
                              sysa.get("value"), sysa.get("unit"))
                if agree is not None:
                    n_sc += 1
                    n_ok += bool(agree)
            ours = f"{_clip(sysa.get('value'), 40)} {sysa.get('unit') or ''} @ {sysa.get('confidence', 0):.2f}" if sysa else "—"
            L.append(f"| {q.get('qid')} | {_clip(q.get('path', '').split('/')[-1], 40)} | {_clip(q.get('question'), 110)} | "
                     f"{_clip(q.get('answer'), 40)} {q.get('unit') or ''} | {q.get('sureness') or ''} | {ours} | "
                     f"{'✓' if agree else '✗' if agree is False else '–'} |")
        if n_sc:
            L += ["", f"Scored agreement (eval tolerance, only questions where she pressed 'Ask our system'): {n_ok}/{n_sc}."]
    L.append("")
    if agold:
        L += [f"### 2b. Reference answers made by auditing items that had none: {len(agold)} "
              "(also in split `human`, meta.kind `human:audit`)", "",
              "| item | question | expert's reference | ours | agree |", "|---|---|---|---|---|"]
        for q in agold:
            sysa = q.get("system") or {}
            try:
                agree = score(q.get("type") or "other", q.get("answer") or None, q.get("unit") or None,
                              sysa.get("value"), sysa.get("unit"))
            except Exception:  # noqa: BLE001
                agree = None
            L.append(f"| {q.get('item_id')} | {_clip(q.get('question'), 110)} | {_clip(q.get('answer'), 40)} {q.get('unit') or ''} | "
                     f"{_clip(sysa.get('value'), 40)} {sysa.get('unit') or ''} | {'✓' if agree else '✗' if agree is False else '–'} |")
        L.append("")

    # --- rules
    L += [f"## 3. Physics & sanity rules: {len(rules)}", ""]
    if rules:
        L += ["| what | min | max | unit | why | uncertainty |", "|---|---|---|---|---|---|"]
        for r in rules:
            L.append(f"| {_clip(r.get('what'), 60)} | {r.get('min') if r.get('min') is not None else ''} | "
                     f"{r.get('max') if r.get('max') is not None else ''} | {r.get('unit') or ''} | {_clip(r.get('why'), 160)} | "
                     f"{_clip(r.get('uncertainty'), 200)} |")
    L.append("")
    return "\n".join(L)


def write() -> str:
    text = build()
    p = store.human_dir() / "REPORT.md"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)
    return str(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args(argv)
    if a.stdout:
        print(build())
    else:
        print(write())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
