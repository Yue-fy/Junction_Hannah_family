"""lang_guess confusion on every OPEN labelled multilingual set (no model calls).

Sources (labels): hardL_open meta.lang, R2 lang4 meta.lang, W4 lang4b meta.lang, Q multilingual_probe kind '<x>:<lang>',
F apt_wording_ml/comp_ml probe_kind '<lang>_...' when present. Held-out sets (hardL, hard2p/q/r, test) are NOT read.
Usage: python experiments/r2/probes/lang_id.py [--short N] [--show K]
"""
import argparse
import collections
import json
import os
import re
import sys

from stoa.llm import COVERED_LANGS, lang_guess

S = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
FILES = [f"{S}/results/splits/hardL_open.jsonl", f"{S}/artifacts/R2/lang4.jsonl", f"{S}/artifacts/W4/lang4b.jsonl",
         f"{S}/artifacts/Q/multilingual_probe.jsonl", f"{S}/artifacts/F/comp_ml.jsonl", f"{S}/artifacts/F/comp_ml_cc.jsonl",
         f"{S}/artifacts/F/apt_wording_ml.jsonl", f"{S}/artifacts/F/apt_wording_ml2.jsonl"]
CODES = {"en", "fi", "de", "fr", "it", "sv", "nl", "pl", "cs", "sk", "hu", "ro", "tr", "pt", "es", "et", "lt", "lv",
         "hr", "nb", "no", "da", "el", "sl"}


def label(row):
    m = row.get("meta") or {}
    if m.get("lang") in CODES:
        return m["lang"]
    for key in ("kind", "probe_kind"):
        k = str(m.get(key) or "")
        mm = re.search(r":([a-z]{2})$", k) or re.match(r"([a-z]{2})_", k)
        if mm and mm.group(1) in CODES:
            return mm.group(1)
    return None


def load(extra=None):
    rows = []
    for f in FILES + (extra or []):
        if not os.path.exists(f):
            continue
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            lab = label(r)
            if lab:
                rows.append((lab, r["question"], os.path.basename(f)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=40)
    ap.add_argument("--extra", nargs="*", default=[])
    a = ap.parse_args()
    rows = load(a.extra)
    seen = set()
    rows = [r for r in rows if not (r[1] in seen or seen.add(r[1]))]
    conf = collections.Counter()
    per = collections.Counter()
    bad = []
    for lab, q, f in rows:
        g = lang_guess(q)
        lab2 = "no" if lab == "nb" else lab
        g2 = "no" if g in ("nb", "da") and lab2 in ("no", "da") else g
        ok = g2 == lab2 or (lab2 in ("cs", "sk") and g in ("cs", "sk"))
        per[(lab2, ok)] += 1
        if not ok:
            conf[(lab2, g)] += 1
            bad.append((lab2, g, q, f))
    # severity: non-English read as 'en' (never translated) and uncovered read as covered (translation suppressed)
    sev = collections.Counter()
    for lab, g, q, f in bad:
        if g == "en" and lab != "en":
            sev["non-en -> en (never translated)"] += 1
        elif lab not in COVERED_LANGS and g in COVERED_LANGS:
            sev["uncovered -> covered (translation suppressed when a target parses)"] += 1
        elif lab in COVERED_LANGS and g not in COVERED_LANGS:
            sev["covered -> uncovered (extra translation)"] += 1
        else:
            sev["other"] += 1
    langs = sorted({k[0] for k in per})
    tot_ok = sum(v for (l, ok), v in per.items() if ok)
    print(f"{len(rows)} unique labelled questions, lang_guess right {tot_ok}/{len(rows)}")
    print(" ".join(f"{l}:{per[(l, True)]}/{per[(l, True)] + per[(l, False)]}" for l in langs))
    print("severity:", dict(sev))
    print("top confusions:", conf.most_common(15))
    for lab, g, q, f in bad[: a.show]:
        print(f"  {lab}->{g} [{f}] {q[:110]}")


if __name__ == "__main__":
    sys.exit(main())
