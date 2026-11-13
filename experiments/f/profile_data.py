"""Profile the full dataset for research/data-profile.md. Run from the repo root:
    PYTHONPATH=. $JUNCTION_VENV/bin/python -I experiments/f/profile_data.py > /tmp/profile.txt
"""

import collections
import json
import os
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.data import data_root, drawing_group, load_questions, template_of  # noqa: E402
from stoa.eval.splits import load_split  # noqa: E402

LANG_HINTS = [
    ("fi", r"^(kuinka|mikä|montako|paljonko)|pohjapiirustu|huonei"),
    ("de", r"^(wie|welche|was ist|gibt es)|grundriss|geschoss|raums?\b"),
    ("fr", r"^(quel|quelle|combien)|étage|pièces?"),
    ("it", r"^(qual|quant[ie])|piano\b|locale\b"),
    ("nl", r"^(wat|hoeveel|welke)|ruimte|vloer"),
    ("es", r"^(¿|cuál|cuánt)"),
    ("da", r"^(hvad|hvor mange)|rummet|etage"),
    ("et", r"^(kui|mitu|mis)\b|ruumi"),
    ("en", r"^(how|what|which|is|are|on sheet|list|does|do|give|name|in)\b"),
]


def lang(q: str) -> str:
    s = q.strip().lower()
    for code, pat in LANG_HINTS:
        if re.search(pat, s):
            return code
    return "?"


def main():
    root = data_root()
    qs = load_questions()
    print(f"# questions: {len(qs)}; distinct files with questions: {len({q.path for q in qs})}")

    # 1. source x type x language
    c = collections.Counter((q.source, q.type, lang(q.question)) for q in qs)
    print("\n## source x type x lang")
    for k, v in sorted(c.items()):
        print("|", " | ".join(k), "|", v, "|")

    # 2. files on disk per source and extension, sizes
    print("\n## files on disk")
    asked = collections.Counter(q.path for q in qs)
    for src in sorted(p.name for p in (root / "data").iterdir() if p.is_dir()):
        exts = collections.defaultdict(list)
        for f in (root / "data" / src).rglob("*"):
            if f.is_file() and f.name != "LICENSE.md":
                exts[f.suffix.lower()].append(f.stat().st_size)
        n_asked = len({p for p in asked if p.startswith(f"data/{src}/")})
        parts = ", ".join(f"{e or '(none)'}: {len(v)} (median {statistics.median(v)/1e6:.2f} MB, max {max(v)/1e6:.1f} MB)"
                          for e, v in sorted(exts.items(), key=lambda kv: -len(kv[1])))
        print(f"- {src}: files asked about: {n_asked}; {parts}")

    # 3. siblings coverage for asked files
    print("\n## sibling formats of asked files")
    sib = collections.Counter()
    for p in {q.path for q in qs}:
        pp = root / p
        exts = tuple(sorted(x.suffix.lower() for x in pp.parent.glob(pp.stem + ".*")))
        sib[(p.split("/")[1], pp.suffix.lower(), exts)] += 1
    for k, v in sorted(sib.items()):
        print(f"- {k}: {v}")

    # 4. answer distributions per template (count questions): share of the mode
    print("\n## count answers: mode share per template (top templates)")
    by_t = collections.defaultdict(list)
    for q in qs:
        if q.type == "count":
            by_t[(q.source, template_of(q.question))].append(q.answer)
    rows = sorted(by_t.items(), key=lambda kv: -len(kv[1]))[:40]
    for (src, t), vals in rows:
        cc = collections.Counter(vals)
        mode, n = cc.most_common(1)[0]
        print(f"- {src} | n={len(vals)} | mode={mode} ({100*n/len(vals):.0f}%) | mean={statistics.fmean(vals):.2f} "
              f"| max={max(vals)} | zeros={100*cc[0]/len(vals):.0f}% | {t[:90]}")

    # 5. numeric answers
    print("\n## numeric answers per source/type")
    num = collections.defaultdict(list)
    for q in qs:
        if q.type in ("area", "length", "volume") and isinstance(q.answer, (int, float)):
            num[(q.source, q.type, q.unit)].append(float(q.answer))
    for k, v in sorted(num.items()):
        v.sort()
        print(f"- {k}: n={len(v)} min={v[0]} p50={v[len(v)//2]} max={v[-1]} decimals<=2:"
              f"{100*sum(1 for x in v if round(x, 2) == x)/len(v):.0f}% zeros={sum(1 for x in v if x == 0)}")

    # 6. oddities
    print("\n## oddities")
    pairs = collections.defaultdict(set)
    for q in qs:
        pairs[(q.path, template_of(q.question))].add(json.dumps(q.answer))
    conflicts = [(k, v) for k, v in pairs.items() if len(v) > 1]
    print(f"- same file + same template with different answers: {len(conflicts)} (e.g. {conflicts[:3]})")
    types = collections.Counter((q.type, type(q.answer).__name__) for q in qs)
    print(f"- type x python answer type: {dict(types)}")
    # cubicasa EN/FI pairs agree?
    cub = collections.defaultdict(dict)
    for q in qs:
        if q.source == "cubicasa5k":
            cub[q.path][template_of(q.question)] = q.answer
    print(f"- cubicasa files: {len(cub)}; questions per file: {collections.Counter(len(v) for v in cub.values()).most_common(6)}")
    neg = [q for q in qs if isinstance(q.answer, (int, float)) and q.answer < 0]
    print(f"- negative answers: {len(neg)}")
    dup = len(qs) - len({(q.path, q.question) for q in qs})
    print(f"- duplicated (path, question) rows dropped by loader: see raw count vs loaded")

    # 7. split composition
    print("\n## splits")
    for s in ("smoke", "dev", "test", "train", "unused"):
        try:
            sq = load_split(s)
        except FileNotFoundError:
            continue
        cc = collections.Counter((q.source, q.type) for q in sq)
        print(f"- {s}: {len(sq)} questions, {len({drawing_group(q.path) for q in sq})} groups; "
              + ", ".join(f"{a}/{b} {n}" for (a, b), n in sorted(cc.items())))


if __name__ == "__main__":
    main()
