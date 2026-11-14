"""Apply the expert's sanity rules (human/rules.jsonl) to an eval predictions file and measure them.

    $JUNCTION_VENV/bin/python -m workbench.rules_check [PRED.jsonl] [--out FILE.md]

Default PRED = the newest `*-pipeline-dev-*.jsonl` in $JUNCTION_SHARED/artifacts/eval. A rule applies to a prediction
when (1) its unit has the same dimension as the predicted unit (length / area / volume / count), and (2) every
content word of the rule's "what" (ignoring words like 'of', 'the', 'typical') or a simple synonym of it appears in the
question. For each rule it reports how many answers it touches, how many it flags (outside [min, max] after unit
conversion), and how many of the flagged answers are actually wrong (precision) vs the base error rate of the touched
ones. A rule is worth wiring into the pipeline (as a confidence cap + an assumption line) when it flags answers that
are wrong much more often than the base rate. This file does not change any answer; it only measures.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from pathlib import Path

from workbench import store

STOP = {"of", "the", "a", "an", "in", "per", "for", "and", "or", "typical", "usual", "normal", "any", "each", "one",
        "single", "plausible", "value", "values", "range", "net", "gross", "clear", "interior", "exterior", "inner",
        "outer", "residential", "building", "buildings", "dwelling", "dwellings", "number", "count", "total", "size",
        "width", "height", "length", "area", "volume", "depth", "(", ")"}
# measure words that must match the question's quantity word when present in the rule
MEASURE = {"width": ("width", "wide", "breite", "leveys"), "height": ("height", "high", "tall", "höhe", "korkeus"),
           "length": ("length", "long", "länge", "pituus"), "depth": ("depth", "deep", "tiefe")}
SYN = {"room": ("room", "rooms", "zimmer", "raum", "räume", "pièce", "huone", "space", "spaces"),
       "door": ("door", "doors", "tür", "türen", "porte", "portes", "ovi", "ovea", "ovia", "doorway"),
       "window": ("window", "windows", "fenster", "fenêtre", "fenêtres", "ikkuna", "ikkunaa", "ikkunat"),
       "storey": ("storey", "story", "stories", "storeys", "floor", "level", "geschoss", "stockwerk", "kerros"),
       "apartment": ("apartment", "apartments", "flat", "unit", "wohnung", "appartement", "asunto"),
       "wall": ("wall", "walls", "wand", "wände", "mur", "seinä"),
       "kitchen": ("kitchen", "küche", "cuisine", "keittiö"), "bathroom": ("bathroom", "bath", "bad", "salle de bain", "kylpyhuone"),
       "bedroom": ("bedroom", "schlafzimmer", "chambre", "makuuhuone"), "stair": ("stair", "stairs", "treppe", "escalier", "porras"),
       "balcony": ("balcony", "balkon", "balcon", "parveke")}


def _dim(unit: str | None) -> str | None:
    from stoa.eval.scoring import _UNITS, norm_unit

    u = norm_unit(unit)
    if u in (None, "", "text"):
        return None
    return _UNITS.get(u, (None,))[0]


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-zäöüåéèàç]+", (s or "").lower()) if w not in STOP and len(w) > 2]


def _stem(w: str) -> str:
    return re.sub(r"(ies|es|s)$", "", w)


def matches(rule: dict, question: str) -> bool:
    q = question.lower()
    qw = set(re.findall(r"[a-zäöüåéèàç]+", q))
    what = (rule.get("what") or "").lower()
    for m, forms in MEASURE.items():
        if re.search(rf"\b{m}\b", what) and not any(f in qw or f in q for f in forms):
            return False
    for w in _words(what):
        forms = next((v for k, v in SYN.items() if _stem(w) == _stem(k) or w in v), (w,))
        if not any(f in qw or (" " in f and f in q) or any(_stem(x) == _stem(f) for x in qw) for f in forms):
            return False
    return bool(_words(what)) or any(re.search(rf"\b{m}\b", what) for m in MEASURE)


def violations(rules: list[dict], question: str, value, unit: str | None, typ: str | None = None) -> list[str]:
    """The expert's rules that ONE answer breaks, as short sentences for the page (same matching as check())."""
    pred = {"question": question, "value": value, "unit": unit, "type": typ}
    out = []
    for res in check(rules, [pred]):
        if res.get("flagged"):
            r = res["rule"]
            rng = f"{r.get('min') if r.get('min') is not None else '…'}–{r.get('max') if r.get('max') is not None else '…'} {r.get('unit') or ''}"
            out.append(f"outside your rule “{r.get('what')}”: {rng.strip()}" + (f" ({r['why']})" if r.get("why") else ""))
    return out


def check(rules: list[dict], preds: list[dict]) -> list[dict]:
    from stoa.eval.scoring import convert, parse_number

    out = []
    for i, r in enumerate(rules, 1):
        lo, hi = r.get("min"), r.get("max")
        lo = lo if isinstance(lo, (int, float)) else None
        hi = hi if isinstance(hi, (int, float)) else None
        rd = _dim(r.get("unit") or "")
        res = {"i": i, "rule": r, "touched": 0, "touched_wrong": 0, "flagged": 0, "flagged_wrong": 0, "examples": []}
        if (lo is None and hi is None) or rd is None:
            res["skip"] = "no numeric range or no known unit"
            out.append(res)
            continue
        for p in preds:
            pd = _dim(p.get("unit") or ("count" if p.get("type") == "count" else None))
            if pd != rd or not matches(r, p.get("question", "")):
                continue
            x = parse_number(p.get("value"))
            if x is None:
                continue
            y = convert(x, p.get("unit"), r.get("unit"))
            if y is None:
                continue
            res["touched"] += 1
            wrong = p.get("correct") is False
            res["touched_wrong"] += wrong
            if (lo is not None and y < lo) or (hi is not None and y > hi):
                res["flagged"] += 1
                res["flagged_wrong"] += wrong
                if len(res["examples"]) < 5:
                    res["examples"].append({"qid": p.get("qid"), "question": p.get("question"), "value": p.get("value"),
                                            "unit": p.get("unit"), "gold": p.get("gold"), "correct": p.get("correct"),
                                            "confidence": p.get("confidence")})
        out.append(res)
    return out


def render(results: list[dict], pred_path: str, n_preds: int) -> str:
    L = [f"# Expert rules vs predictions", "", f"Predictions: `{pred_path}` ({n_preds} rows).", "",
         "| # | rule | touched | wrong among touched | flagged | wrong among flagged | verdict |", "|---|---|---|---|---|---|---|"]
    for r in results:
        ru = r["rule"]
        desc = f"{ru.get('what')}: {ru.get('min', '')}–{ru.get('max', '')} {ru.get('unit', '')}"
        if r.get("skip"):
            L.append(f"| {r['i']} | {desc} | – | – | – | – | skipped: {r['skip']} |")
            continue
        t, tw, f, fw = r["touched"], r["touched_wrong"], r["flagged"], r["flagged_wrong"]
        base = tw / t if t else 0
        prec = fw / f if f else 0
        verdict = ("no matching questions" if not t else "flags nothing" if not f else
                   "USEFUL: flagged answers are wrong far more often" if prec >= max(2 * base, 0.5) else "not selective")
        L.append(f"| {r['i']} | {desc} | {t} | {tw} ({base:.0%}) | {f} | {fw} ({prec:.0%}) | {verdict} |")
    for r in results:
        if r["examples"]:
            L += ["", f"Rule {r['i']} flagged examples:"]
            for e in r["examples"]:
                L.append(f"- {e['qid']}: {e['question'][:120]} → {e['value']} {e['unit'] or ''} "
                         f"(gold {e['gold']}, correct {e['correct']}, conf {e['confidence']})")
    return "\n".join(L) + "\n"


def latest_dev_preds(min_rows: int = 2000) -> str | None:
    """Newest full pipeline dev run (a partial run, e.g. `--limit`, has fewer rows)."""
    shared = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
    files = sorted(glob.glob(f"{shared}/artifacts/eval/*-pipeline-dev-*.jsonl"), key=os.path.getmtime, reverse=True)
    for f in files[:30]:
        with open(f, encoding="utf-8") as fh:
            if sum(1 for _ in fh) >= min_rows:
                return f
    return files[0] if files else None


def load_preds(path: str) -> list[dict]:
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    return [r for r in rows if "question" in r]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pred", nargs="?")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    pred = a.pred or latest_dev_preds()
    preds = load_preds(pred)
    rules = store.read("rules")
    text = render(check(rules, preds), pred, len(preds))
    out = Path(a.out) if a.out else store.human_dir() / "RULES_CHECK.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
