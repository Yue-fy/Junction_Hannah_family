"""Stoa's example questions as plain text -> an eval split with real drawings attached (R2, noon reveal).

Stoa will show *kinds* of questions at noon, perhaps without the drawings they were asked on. stoa.eval needs a
`path` on every row, so this pairs each question with a fixed, seeded sample of drawings per source: open dev
drawings for the sources that have questions (cubicasa5k, swiss_dwellings, ifc_models, ifc_bench, opening_design)
and folder files for the historical scans (habs, finna, europeana, wikimedia). Every question gets the SAME drawings
of a source, so the answers of different questions are comparable. Rows have answer null (unscored): grade them by
eye in the side-by-side file that experiments/r2/noon_models.sh writes.

Input, either
  .txt   one question per line; '#' starts a comment; optional leading tags in brackets:
         [habs] [cubicasa5k,swiss_dwellings] = sources; [data/habs/x.jpg] = that file only; [kind=area_sum] = label;
         [answer=12] = gold (scored then)
  .jsonl rows with "question" and optional "path" | "sources" (list or comma string) | "kind" | "answer" | "type"
Output: rows {qid?, path, question, answer, type, meta: {kind, source, from}} for stoa.eval --split OUT.jsonl.

  python experiments/r2/attach_drawings.py examples.txt --out $JUNCTION_SHARED/artifacts/R2/noon_examples.jsonl
  python experiments/r2/attach_drawings.py examples.txt --per-source 3 --sources cubicasa5k,habs --out x.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

QUESTION_SOURCES = ("cubicasa5k", "swiss_dwellings", "ifc_models", "ifc_bench", "opening_design")
SCAN_SOURCES = ("habs", "finna", "europeana", "wikimedia")
DEFAULT_SOURCES = ("cubicasa5k", "swiss_dwellings", "ifc_models", "habs")
_TAG = re.compile(r"^\s*\[([^\]]*)\]\s*")
_COUNT = re.compile(r"^\s*(how many|count|number of|kuinka monta|wie viele|combien|cu[aá]nt[oa]s|hur m[aå]nga)\b", re.I)


def _pool(source: str, data_root: Path) -> list[str]:
    """Dataset-relative drawing paths of one source, sorted (the seeded sample is drawn from this)."""
    if source in QUESTION_SOURCES:
        from stoa.data import source_of
        from stoa.eval.splits import load_split
        return sorted({q.path for q in load_split("dev") if source_of(q.path) == source})
    if source in SCAN_SOURCES:
        d = data_root / "data" / source
        return sorted(str(p.relative_to(data_root)) for p in d.rglob("*")
                      if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff"))
    raise SystemExit(f"unknown source {source!r}; known: {', '.join(QUESTION_SOURCES + SCAN_SOURCES)}")


def parse_line(line: str) -> dict | None:
    """One .txt line -> {question, sources?, path?, kind?, answer?}; None for blank lines and comments."""
    s = line.split("#", 1)[0].strip() if line.lstrip().startswith("#") else line.strip()
    if not s:
        return None
    row: dict = {}
    while (m := _TAG.match(s)):
        for tag in (t.strip() for t in m.group(1).split(",")):
            if not tag:
                continue
            if "=" in tag:
                k, v = (x.strip() for x in tag.split("=", 1))
                row[k] = v
            elif "/" in tag or "." in tag:
                row["path"] = tag
            else:
                row.setdefault("sources", []).append(tag)
        s = s[m.end():]
    row["question"] = s.strip()
    return row if row["question"] else None


def read_input(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        for r in rows:
            if isinstance(r.get("sources"), str):
                r["sources"] = [t.strip() for t in r["sources"].split(",") if t.strip()]
        return [r for r in rows if r.get("question")]
    return [r for r in map(parse_line, path.read_text(encoding="utf-8").splitlines()) if r]


def _answer(v):
    if v is None or isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return v  # text answer


def attach(rows: list[dict], sources: tuple[str, ...], per_source: int, seed: int, data_root: Path) -> list[dict]:
    samples: dict[str, list[str]] = {}

    def sample(src: str) -> list[str]:
        if src not in samples:
            pool = _pool(src, data_root)
            samples[src] = random.Random(f"{seed}:{src}").sample(pool, min(per_source, len(pool)))
        return samples[src]

    out = []
    for i, r in enumerate(rows, 1):
        kind = r.get("kind") or f"q{i:02d}"
        base = dict(question=r["question"], answer=_answer(r.get("answer")),
                    type=r.get("type") or ("count" if _COUNT.match(r["question"]) else "other"))
        if r.get("path"):
            from stoa.data import source_of
            out.append({**base, "path": r["path"], "meta": {"kind": kind, "source": source_of(r["path"]), "from": "given"}})
            continue
        for src in r.get("sources") or sources:
            for p in sample(src):
                out.append({**base, "path": p, "meta": {"kind": kind, "source": src, "from": f"sample seed={seed}"}})
    return out


def main(argv=None) -> int:
    from stoa.data import data_root as _data_root
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-source", type=int, default=2, help="drawings per source for a question without a path")
    ap.add_argument("--sources", default=",".join(DEFAULT_SOURCES),
                    help=f"default sources for untagged questions (known: {', '.join(QUESTION_SOURCES + SCAN_SOURCES)})")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    rows = read_input(a.input)
    if not rows:
        print(f"no questions in {a.input}", file=sys.stderr)
        return 2
    out = attach(rows, tuple(s.strip() for s in a.sources.split(",") if s.strip()), a.per_source, a.seed, _data_root())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    files = sorted({r["path"] for r in out})
    print(f"{len(rows)} questions -> {len(out)} rows on {len(files)} drawings: {a.out}")
    for f in files:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
