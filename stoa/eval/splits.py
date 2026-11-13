"""Fixed, drawing-grouped splits: smoke / dev / test / train.

All questions of a drawing group (see `stoa.data.drawing_group`) land in the same split, so no split
leaks a drawing (or a sibling format, or a floor of the same Swiss site, or a plan rendered from the same
IFC model) into another. Small sources are over-sampled in smoke/dev/test so every source × type bucket
can be measured; overall accuracy is therefore reported both micro (per question) and macro (per bucket).

Files: $JUNCTION_SHARED/results/splits/<split>.jsonl, one line per question:
    {"qid", "path", "type", "source", "group"}   (answers are NOT in the split files; join via qid)
`test` is sealed: only S0 runs it.
"""

from __future__ import annotations

import collections
import json
import os
import random
from pathlib import Path

from stoa.data import Question, drawing_group, load_questions, template_of

SEED = 20261113
SPLITS = ("smoke", "dev", "test", "train")

# Target questions per (source, type) per split. Whole groups are taken (capped, see CAPS), greedily
# filling the largest remaining type deficit, so rare types (ifc length/volume) get represented.
TARGETS: dict[str, dict[tuple[str, str], int]] = {
    "smoke": {("cubicasa5k", "count"): 80, ("swiss_dwellings", "count"): 40, ("swiss_dwellings", "area"): 30,
              ("ifc_models", "area"): 15, ("ifc_models", "count"): 12, ("ifc_models", "length"): 4,
              ("ifc_models", "volume"): 6, ("ifc_bench", "text"): 20},
    "dev": {("cubicasa5k", "count"): 800, ("swiss_dwellings", "count"): 400, ("swiss_dwellings", "area"): 250,
            ("ifc_models", "area"): 180, ("ifc_models", "count"): 100, ("ifc_models", "length"): 20,
            ("ifc_models", "volume"): 40, ("ifc_bench", "text"): 150},
    "test": {("cubicasa5k", "count"): 800, ("swiss_dwellings", "count"): 400, ("swiss_dwellings", "area"): 250,
             ("ifc_models", "area"): 180, ("ifc_models", "count"): 100, ("ifc_models", "length"): 20,
             ("ifc_models", "volume"): 40, ("ifc_bench", "text"): 150},
}
# Max questions one group contributes to smoke/dev/test (round-robin over its types, so rare types first).
# The group's other questions go to `unused` (never train: that would leak the drawing).
CAPS = {"cubicasa5k": 6, "swiss_dwellings": 10, "ifc_models": 100, "ifc_bench": 35}
# Sources with <= 3 question-carrying groups: largest -> dev, next -> test, next -> smoke.
TINY_ORDER = ("dev", "test", "smoke")


def shared_root() -> Path:
    return Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))


def splits_dir() -> Path:
    return shared_root() / "results" / "splits"


def _capped(qs: list[Question], cap: int | None, rng: random.Random) -> tuple[list[Question], list[Question]]:
    """Keep at most `cap` questions of one group: round-robin over types (rarest first) and, within a type,
    over question templates, so a capped group still covers many kinds of questions."""
    if not cap or len(qs) <= cap:
        return qs, []
    by_t: dict[str, list[Question]] = collections.defaultdict(list)
    for q in qs:
        by_t[q.type].append(q)
    queues: dict[str, list[Question]] = {}
    for t, rows in by_t.items():
        by_tpl = collections.defaultdict(list)
        for q in rows:
            by_tpl[template_of(q.question)].append(q)
        tpls = sorted(by_tpl)
        rng.shuffle(tpls)
        for v in by_tpl.values():
            rng.shuffle(v)
        inter = []
        while any(by_tpl[k] for k in tpls):
            for k in tpls:
                if by_tpl[k]:
                    inter.append(by_tpl[k].pop())
        queues[t] = inter[::-1]  # pop() from the end = interleaved order
    keep: list[Question] = []
    types = sorted(queues, key=lambda t: (len(queues[t]), t))  # rarest first
    while len(keep) < cap and any(queues.values()):
        for t in types:
            if queues[t] and len(keep) < cap:
                keep.append(queues[t].pop())
    kept = {q.qid for q in keep}
    return [q for q in qs if q.qid in kept], [q for q in qs if q.qid not in kept]


def make_splits(seed: int = SEED) -> dict[str, list[Question]]:
    qs = load_questions()
    by_source: dict[str, dict[str, list[Question]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for q in qs:
        by_source[q.source][drawing_group(q.path)].append(q)

    rng = random.Random(seed)
    out: dict[str, list[Question]] = {s: [] for s in (*SPLITS, "unused")}
    for source in sorted(by_source):
        groups = sorted(by_source[source])
        rng.shuffle(groups)
        if len(groups) <= len(TINY_ORDER):
            for split, g in zip(TINY_ORDER, sorted(groups, key=lambda g: -len(by_source[source][g]))):
                out[split].extend(by_source[source][g])
            continue
        cap = CAPS.get(source)
        capped = {g: _capped(by_source[source][g], cap, random.Random(f"{seed}/{g}")) for g in groups}
        for split in ("smoke", "dev", "test"):
            targets = {t: n for (s, t), n in TARGETS[split].items() if s == source}
            taken = collections.Counter()
            while groups:
                deficit = {t: n - taken[t] for t, n in targets.items() if n - taken[t] > 0}
                if not deficit:
                    break
                best, best_gain = None, 0
                for g in groups:  # shuffled order breaks ties
                    c = collections.Counter(q.type for q in capped[g][0])
                    gain = sum(min(c[t], d) for t, d in deficit.items())
                    # don't let one group overshoot a type by more than 50%
                    if any(taken[t] + c[t] > 1.5 * targets.get(t, 0) + 10 for t in c):
                        continue
                    if gain > best_gain:
                        best, best_gain = g, gain
                if best is None:
                    break
                keep, drop = capped[best]
                out[split].extend(keep)
                out["unused"].extend(drop)
                taken.update(q.type for q in keep)
                groups.remove(best)
        for g in groups:
            out["train"].extend(by_source[source][g])
    return out


def write_splits(seed: int = SEED, force: bool = False) -> dict[str, int]:
    d = splits_dir()
    d.mkdir(parents=True, exist_ok=True)
    if not force and all((d / f"{s}.jsonl").exists() for s in SPLITS):
        raise FileExistsError(f"splits already exist in {d}; pass force=True to overwrite (never do this tonight)")
    splits = make_splits(seed)
    counts = {}
    for name, qs in splits.items():
        with open(d / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for q in qs:
                f.write(json.dumps({"qid": q.qid, "path": q.path, "type": q.type, "source": q.source,
                                    "group": drawing_group(q.path)}) + "\n")
        counts[name] = len(qs)
    (d / "README.md").write_text(
        f"Generated by `python -m stoa.eval.splits --write` (seed {seed}). Do not edit by hand.\n"
        "Grouped by drawing (stoa.data.drawing_group). test is sealed: only S0 runs it.\n"
        + "".join(f"- {k}: {v}\n" for k, v in counts.items()),
        encoding="utf-8",
    )
    return counts


def load_split(name: str) -> list[Question]:
    """Questions (with answers) of a split, in file order."""
    if name == "all":
        return list(load_questions())
    f = splits_dir() / f"{name}.jsonl"
    if not f.exists():
        raise FileNotFoundError(f"{f} missing; run `python -m stoa.eval.splits --write`")
    by_id = {q.qid: q for q in load_questions()}
    out = []
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                qid = json.loads(line)["qid"]
                if qid in by_id:
                    out.append(by_id[qid])
    return out


def split_hash(name: str) -> str | None:
    """Short content hash of a split file, recorded in leaderboard lines (detects regenerated splits)."""
    import hashlib

    f = splits_dir() / f"{name}.jsonl"
    return hashlib.sha1(f.read_bytes()).hexdigest()[:8] if f.exists() else None


def split_of_group() -> dict[str, str]:
    """group -> split name, for agents that want to check they never train on dev/test drawings."""
    m = {}
    for s in (*SPLITS, "unused"):
        f = splits_dir() / f"{s}.jsonl"
        if f.exists():
            for line in open(f, encoding="utf-8"):
                if line.strip():
                    m[json.loads(line)["group"]] = s
    return m


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.write:
        print(write_splits(force=a.force))
    else:
        sp = make_splits()
        for name, qs in sp.items():
            c = collections.Counter((q.source, q.type) for q in qs)
            print(name, len(qs), dict(sorted(c.items())))
