"""Turn example questions (e.g. the ones Stoa shows on Saturday noon) into red-team variants, run-ready.

    PYTHONPATH=. $JUNCTION_VENV/bin/python redteam/from_examples.py EXAMPLES.jsonl --out OUT.jsonl [--translate fi,de,sv]
    $JUNCTION_VENV/bin/python -m stoa.eval --solver pipeline --split OUT.jsonl --no-leaderboard --workers 4
    PYTHONPATH=. $JUNCTION_VENV/bin/python redteam/from_examples.py --report RUN.jsonl

EXAMPLES rows: {"path", "question"} plus, when known, "answer", "unit" (count|m2|m|m3|...), "type", and
"translations": {"fi": "..."} (hand-written, used as is; machine translations are kept only when our own to_english
front end reads them back as the same task and object class). A path may be
absolute (a file Stoa hands us) or dataset-relative. Without a gold answer every variant is checked for CONSISTENCY
with the example's own answer in the same run (meta.expect = "consistent"): a variant that changes the answer, or
keeps it at a different confidence band, is listed by --report. With a gold answer the eval scores it as usual.

Variants per example (meta.kind):
  control                 the example as given
  perturb:<k>             casual / context / distractor number / prompt injection / typo / CAPS (as in build.py)
  lang:<code>             translated by the local LLM (quoted names, numbers and labels kept; --translate)
  unit:ft2 / unit:mm      the same area in square feet / length in millimetres (gold converted), when the unit is named
  premise                 a quoted storey/room name replaced by one the drawing does not have -> expect a flag
  multi                   two examples on the same file asked as "how many X and how many Y"-style pairs -> both
                          numbers expected (meta.parts; analyze.py's parts_ok)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import FT2, perturbations, row  # noqa: E402

LANGS = {"fi": "Finnish", "de": "German", "sv": "Swedish", "fr": "French", "it": "Italian", "nl": "Dutch",
         "et": "Estonian", "pl": "Polish", "es": "Spanish"}
QUOTED = re.compile(r"'([^']+)'|«([^»]+)»|\"([^\"]+)\"")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def translate(q: str, lang: str) -> str | None:
    from stoa.llm import chat
    prompt = (f"Translate this question about a construction drawing into {LANGS[lang]}, the way a site engineer "
              f"would ask it. Keep every quoted name, room or storey label, number and unit exactly as written. "
              f"Reply with the translated question only.\n\n{q}")
    try:
        t = chat(prompt, max_tokens=200, temperature=0.0).text.strip().strip('"')
    except Exception as e:  # server down: skip the language, say so
        print(f"  translate {lang}: {e}", file=sys.stderr)
        return None
    keep = [next(g for g in m.groups() if g) for m in QUOTED.finditer(q)]
    if not t or not all(k in t for k in keep):  # a translation that lost a name is not the same question
        return None
    # the 8B mistranslates domain nouns ('bathtubs' -> 'bathrooms' in Finnish): translate back with our own front end
    # and keep the variant only if it parses to the same (task, object class) as the example
    from stoa.llm import to_english
    from stoa.router.intent import parse
    back = to_english(t, force=True)
    a, b = parse(q), parse(back.text)
    if not back.ok or (a.task, a.target) != (b.task, b.target):
        print(f"  {lang} dropped (back: {back.text!r} -> {b.task}/{b.target}, want {a.task}/{a.target}): {t!r}",
              file=sys.stderr)
        return None
    return t


def premise_name(name: str) -> str:
    """A name the drawing does not have: bump every number by 7 ('1.korrus' -> '8.korrus'), else a ballroom."""
    if re.search(r"\d", name):
        return re.sub(r"\d+", lambda m: str(int(m.group()) + 7), name, count=1)
    return "Ballroom"


def variants(ex: dict, langs: list[str]):
    q, path = ex["question"], ex["path"]
    gold, unit, typ = ex.get("answer"), ex.get("unit"), ex.get("type") or ("count" if ex.get("unit") == "count" else
                                                                            "area" if ex.get("unit") == "m2" else "text")
    expect = "same" if gold is not None else "consistent"
    base = row(path, q, gold, unit, typ, "control", expect)
    yield base
    b = {"question": q, "gold": _num(gold) if _num(gold) is not None else 17, "gold_unit": unit or "count",
         "qid": base["qid"]}
    for k, v in perturbations(b):
        yield row(path, v, gold, unit, typ, f"perturb:{k}", expect, base=b)
    given = ex.get("translations") or {}  # hand-written translations win: {"fi": "...", "sv": "..."}
    for lang in list(given) + [x for x in langs if x not in given]:
        t = given.get(lang) or translate(q, lang)
        if t:
            yield row(path, t, gold, unit, typ, f"lang:{lang}", expect, base=b, note="local-LLM translation")
    g = _num(gold)
    if re.search(r"\b(m²|m2|square met(?:re|er)s)\b", q) and (unit in (None, "m2")):
        q2 = re.sub(r"\b(m²|m2|square met(?:re|er)s)\b", "square feet", q)
        yield row(path, q2, round(g * FT2, 2) if g is not None else None, "ft2" if g is not None else None, typ,
                  "unit:ft2", expect, base=b)
    elif re.search(r"\bin (metres|meters|m)\b", q) and unit in (None, "m"):
        q2 = re.sub(r"\bin (metres|meters|m)\b", "in millimetres", q)
        yield row(path, q2, round(g * 1000, 1) if g is not None else None, "mm" if g is not None else None, typ,
                  "unit:mm", expect, base=b)
    m = QUOTED.search(q)
    if m:
        name = next(x for x in m.groups() if x)
        q2 = q.replace(name, premise_name(name), 1)
        yield row(path, q2, None, None, "other", "premise", "flag", base=b, note=f"'{premise_name(name)}' is made up")


def pairs(examples: list[dict]):
    """Two numeric examples on the same file, asked as one question: both answers expected."""
    by = defaultdict(list)
    for ex in examples:
        if _num(ex.get("answer")) is not None:
            by[ex["path"]].append(ex)
    for path, exs in by.items():
        for a, b in zip(exs, exs[1:]):
            q = a["question"].rstrip(" ?") + ", and " + b["question"][0].lower() + b["question"][1:]
            r = row(path, q, f"{a['answer']} ; {b['answer']}", None, "text", "multi", "same",
                    note="two examples joined; both numbers expected")
            r["meta"]["parts"] = [_num(a["answer"]), _num(b["answer"])]
            yield r


def report(run: str):
    from analyze import rescore
    rows = rescore([json.loads(line) for line in open(run)])
    ctrl = {r["qid"]: r for r in rows if r["meta"]["kind"] == "control"}
    band = lambda c: "high" if (c or 0) >= 0.8 else "mid" if (c or 0) >= 0.5 else "low"
    same = lambda a, b: (_num(a) is not None and _num(b) is not None and abs(_num(a) - _num(b)) <= 0.02 * max(1, abs(_num(b)))) \
        or str(a).strip().lower() == str(b).strip().lower()
    out, n_changed = [], 0
    for r in rows:
        k, m = r["meta"]["kind"], r["meta"]
        if k == "control":
            continue
        c = ctrl.get(m.get("base_qid"))
        if m["expect"] == "flag":
            bad = (r["confidence"] or 0) >= 0.5
            tag = "PREMISE ANSWERED" if bad else "flagged"
        elif m.get("parts"):
            bad = not r.get("correct")
            tag = "PART MISSING" if bad else "both parts"
        elif r.get("correct") is not None and m["expect"] == "same":
            bad = not r["correct"]
            tag = "WRONG" if bad else "right"
        elif c is not None:
            bad = not same(r["value"], c["value"]) or band(r["confidence"]) != band(c["confidence"])
            tag = "CHANGED" if bad else "same"
        else:
            bad, tag = False, "?"
        n_changed += bad
        if bad:
            base_v = f"{c['value']} @{(c['confidence'] or 0):.2f}" if c else "-"
            out.append(f"- [{k}] {tag}: {r['question'][:90]!r} -> {str(r['value'])[:50]} @{(r['confidence'] or 0):.2f} "
                       f"({r['solver']}); example: {base_v}; gold {r.get('gold')}")
    hi_wrong = [r for r in rows if r.get("correct") is False and (r["confidence"] or 0) >= 0.8]
    print(f"{len(rows)} rows, {len(ctrl)} examples: {n_changed} variants changed / wrong / unflagged; "
          f"{len(hi_wrong)} scored answers wrong at conf >= 0.8")
    print("\n".join(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("examples", nargs="?")
    ap.add_argument("--out", default="redteam-examples.jsonl")
    ap.add_argument("--translate", default="fi,de,sv", help="comma list of language codes ('' = none)")
    ap.add_argument("--report", default=None, help="a run over OUT: list changed / wrong / unflagged variants")
    a = ap.parse_args()
    if a.report:
        return report(a.report)
    examples = [json.loads(line) for line in open(a.examples) if line.strip()]
    langs = [x for x in a.translate.split(",") if x]
    out = []
    for ex in examples:
        out.extend(variants(ex, langs))
    out.extend(pairs(examples))
    seen, rows = set(), []
    for r in out:
        if r["qid"] not in seen:
            seen.add(r["qid"])
            rows.append(r)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(len(rows), "rows ->", a.out, dict(Counter(r["meta"]["kind"].split(":")[0] for r in rows)))


if __name__ == "__main__":
    main()
