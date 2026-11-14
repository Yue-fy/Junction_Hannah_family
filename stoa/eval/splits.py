"""Fixed, drawing-grouped splits: smoke / dev / test / train (+ unused, + generated `hard`).

Rules (v2, per S0 DECISION D1 and R1's cluster-bootstrap analysis):
- All questions of a drawing group (`stoa.data.drawing_group`) land in one split: sibling formats, floors of
  one Swiss site, plans/discipline models/variants of one IFC project never straddle splits.
- One language per concept: the dataset repeats most questions in English and in the drawing's language
  with the same answer (`stoa.data.concept_map`). Eval splits keep one of the two (random language); the
  partner goes to `unused`, so translations don't double-count and the `hard` split can reuse them.
- cubicasa5k / swiss_dwellings: many small groups -> sampled with a per-group cap (4 / 8 concepts,
  round-robin over types and templates) so dev spans hundreds of drawings. Capped-out questions -> `unused`.
- ifc_models / ifc_bench: few, large projects -> whole projects assigned ~50% train / 25% dev / 25% test
  by question count (best of many random assignments, balancing types). Smoke = the smallest project that
  has every type of the source.
- opening_design (3 sheets): smallest -> smoke, the others -> dev. No test (dev-only bucket).

Files: $JUNCTION_SHARED/results/splits/<split>.jsonl, one line per question:
    {"qid", "path", "type", "source", "group", "concept"}   (answers are NOT in these files; join via qid)
`test` is sealed: only S0 runs it. Never train on dev/test/smoke/unused drawings (`split_of_group()`).
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import random
import sys
from pathlib import Path

from stoa.data import Question, concept_map, dataset_rel, drawing_group, load_questions, make_qid, template_of

SEED = 20261113
SPLITS = ("smoke", "dev", "test", "train")
VERSION = "v2"

# capped sources: questions (concepts) per split per type, filled greedily drawing by drawing
TARGETS: dict[str, dict[tuple[str, str], int]] = {
    "smoke": {("cubicasa5k", "count"): 80, ("swiss_dwellings", "count"): 40, ("swiss_dwellings", "area"): 30},
    "dev": {("cubicasa5k", "count"): 800, ("swiss_dwellings", "count"): 400, ("swiss_dwellings", "area"): 300},
    "test": {("cubicasa5k", "count"): 800, ("swiss_dwellings", "count"): 400, ("swiss_dwellings", "area"): 300},
}
CAPS = {"cubicasa5k": 4, "swiss_dwellings": 8}
WHOLE = {"ifc_models": {"train": 0.5, "dev": 0.25, "test": 0.25},
         "ifc_bench": {"train": 0.5, "dev": 0.25, "test": 0.25}}
TINY = ("opening_design",)  # smallest group -> smoke, rest -> dev


def shared_root() -> Path:
    return Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))


def splits_dir() -> Path:
    return shared_root() / "results" / "splits"


def _one_per_concept(qs: list[Question], rng: random.Random) -> tuple[list[Question], list[Question]]:
    """Keep one random-language question per concept; return (kept, partners)."""
    cm = concept_map()
    by_c = collections.defaultdict(list)
    for q in qs:
        by_c[cm[q.qid]].append(q)
    keep, drop = [], []
    for c in sorted(by_c):
        rows = sorted(by_c[c], key=lambda q: q.qid)
        k = rng.randrange(len(rows))
        keep.append(rows[k])
        drop.extend(rows[:k] + rows[k + 1:])
    return keep, drop


def _capped(qs: list[Question], cap: int | None, rng: random.Random) -> tuple[list[Question], list[Question]]:
    """Keep at most `cap` questions: round-robin over types (rarest first) and, within a type, over
    question templates, so a capped group still covers many kinds of questions."""
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
        queues[t] = inter[::-1]
    keep: list[Question] = []
    types = sorted(queues, key=lambda t: (len(queues[t]), t))
    while len(keep) < cap and any(queues.values()):
        for t in types:
            if queues[t] and len(keep) < cap:
                keep.append(queues[t].pop())
    kept = {q.qid for q in keep}
    return [q for q in qs if q.qid in kept], [q for q in qs if q.qid not in kept]


def _assign_whole(groups: dict[str, list[Question]], fracs: dict[str, float], rng: random.Random,
                  trials: int = 4000) -> dict[str, str]:
    """Assign whole groups to splits so that every split gets ~frac of the questions of every type."""
    names = sorted(groups)
    types = sorted({q.type for g in names for q in groups[g]})
    cnt = {g: collections.Counter(q.type for q in groups[g]) for g in names}
    tot = {t: sum(cnt[g][t] for g in names) for t in types}
    n_tot = sum(tot.values())
    splits, probs = list(fracs), [fracs[s] for s in fracs]
    best, best_err = None, float("inf")
    for _ in range(trials):
        a = {g: rng.choices(splits, probs)[0] for g in names}
        err = 0.0
        for s in splits:
            n_all = sum(sum(cnt[g].values()) for g in names if a[g] == s)
            err += 2 * abs(n_all - fracs[s] * n_tot) / n_tot
            for t in types:
                n = sum(cnt[g][t] for g in names if a[g] == s)
                err += abs(n - fracs[s] * tot[t]) / tot[t]
                if n == 0 and fracs[s] > 0:
                    err += 1.0  # every split should see every type
        if err < best_err:
            best, best_err = a, err
    return best


def make_splits(seed: int = SEED) -> dict[str, list[Question]]:
    qs = load_questions()
    by_source: dict[str, dict[str, list[Question]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for q in qs:
        by_source[q.source][drawing_group(q.path)].append(q)

    rng = random.Random(seed)
    out: dict[str, list[Question]] = {s: [] for s in (*SPLITS, "unused")}

    def put(split: str, rows: list[Question]):
        """Eval splits: one language per concept; partners -> unused. Train: everything."""
        if split == "train":
            out["train"].extend(rows)
            return
        keep, drop = _one_per_concept(rows, random.Random(f"{seed}/{rows[0].path}"))
        out[split].extend(keep)
        out["unused"].extend(drop)

    for source in sorted(by_source):
        groups = by_source[source]
        names = sorted(groups)
        if source in TINY:
            names.sort(key=lambda g: (len(groups[g]), g))
            put("smoke", groups[names[0]])
            for g in names[1:]:
                put("dev", groups[g])
            continue
        if source in WHOLE:
            types = {q.type for g in names for q in groups[g]}
            full = [g for g in names if {q.type for q in groups[g]} >= types] or names
            smoke = min(full, key=lambda g: (len(groups[g]), g))
            put("smoke", groups[smoke])
            rest = {g: groups[g] for g in names if g != smoke}
            for g, s in sorted(_assign_whole(rest, WHOLE[source], random.Random(f"{seed}/{source}")).items()):
                put(s, groups[g])
            continue
        # capped sources: greedy, drawing by drawing, while any type of the split is below target
        rng.shuffle(names)
        cap = CAPS.get(source)
        for split in ("smoke", "dev", "test"):
            targets = {t: n for (s, t), n in TARGETS[split].items() if s == source}
            taken = collections.Counter()
            used = set()
            for g in names:
                deficit = {t: n - taken[t] for t, n in targets.items() if n - taken[t] > 0}
                if not deficit:
                    break
                grng = random.Random(f"{seed}/{g}")
                keep, drop = _one_per_concept(groups[g], grng)
                keep, drop2 = _capped(keep, cap, grng)
                if not any(q.type in deficit for q in keep):
                    continue
                out[split].extend(keep)
                out["unused"].extend(drop + drop2)
                taken.update(q.type for q in keep)
                used.add(g)
            names = [g for g in names if g not in used]
        for g in names:
            out["train"].extend(groups[g])
    return out


GATE_TARGETS = {"cubicasa5k": 480, "swiss_dwellings": 320, "ifc_models": 160}


def make_train_gate(seed: int = SEED) -> list[Question]:
    """A fixed sample of TRAIN questions for choosing gates/thresholds (S0 D4: never tune on dev).
    One language per concept, at most 2 questions per drawing group (ifc: 40 per project), round-robin over
    templates so every template is represented."""
    rng = random.Random(f"{seed}/gate")
    train = load_split("train")
    by_src = collections.defaultdict(lambda: collections.defaultdict(list))
    for q in train:
        by_src[q.source][drawing_group(q.path)].append(q)
    out = []
    for src, target in GATE_TARGETS.items():
        cap = 40 if src == "ifc_models" else 2
        pool = []
        for g in sorted(by_src[src]):
            grng = random.Random(f"{seed}/gate/{g}")
            keep, _ = _one_per_concept(by_src[src][g], grng)
            keep, _ = _capped(keep, cap, grng)
            pool.extend(keep)
        by_tpl = collections.defaultdict(list)
        for q in pool:
            by_tpl[template_of(q.question)].append(q)
        for v in by_tpl.values():
            rng.shuffle(v)
        tpls = sorted(by_tpl, key=lambda t: -len(by_tpl[t]))
        picked = []
        while len(picked) < target and any(by_tpl[t] for t in tpls):
            for t in tpls:
                if by_tpl[t] and len(picked) < target:
                    picked.append(by_tpl[t].pop())
        out.extend(picked)
    return out


def write_train_gate(seed: int = SEED) -> int:
    qs = make_train_gate(seed)
    cm = concept_map()
    with open(splits_dir() / "train_gate.jsonl", "w", encoding="utf-8") as f:
        for q in qs:
            f.write(json.dumps({"qid": q.qid, "path": q.path, "type": q.type, "source": q.source,
                                "group": drawing_group(q.path), "concept": cm[q.qid]}) + "\n")
    return len(qs)


def write_splits(seed: int = SEED, force: bool = False) -> dict[str, int]:
    d = splits_dir()
    d.mkdir(parents=True, exist_ok=True)
    if not force and all((d / f"{s}.jsonl").exists() for s in SPLITS):
        raise FileExistsError(f"splits already exist in {d}; pass force=True to overwrite (never do this tonight)")
    splits = make_splits(seed)
    cm = concept_map()
    counts = {}
    for name, qs in splits.items():
        with open(d / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for q in qs:
                f.write(json.dumps({"qid": q.qid, "path": q.path, "type": q.type, "source": q.source,
                                    "group": drawing_group(q.path), "concept": cm[q.qid]}) + "\n")
        counts[name] = len(qs)
    (d / "README.md").write_text(
        f"Splits {VERSION}, generated by `python -m stoa.eval.splits --write` (seed {seed}). Do not edit by hand.\n"
        "See the docstring of stoa/eval/splits.py for the rules. test is sealed: only S0 runs it.\n"
        "unused = translations and capped-out questions of smoke/dev/test drawings: never train on them.\n"
        + "".join(f"- {k}: {v}\n" for k, v in counts.items()),
        encoding="utf-8",
    )
    return counts


def human_file() -> Path:
    """Expert-made questions from agent H's workbench (D24-pre addendum): append-only, one row per save."""
    return shared_root() / "human" / "questions.jsonl"


def _split_file(name: str) -> Path:
    if name == "human":
        return human_file()
    return Path(name) if (name.endswith(".jsonl") or "/" in name) else splits_dir() / f"{name}.jsonl"


def _human_rows(f: Path) -> list[dict]:
    """`human` split: the last saved row per qid wins (the workbench appends edits; a last row with "deleted": true drops
    the qid); the expert's sureness, page and
    method go to meta (meta.kind = "human:<sureness>"), so results can be read per sureness. Reported separately
    from dev (its own split name in the leaderboard)."""
    last: dict[str, dict] = {}
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if not r.get("question") or not r.get("path"):
                continue
            qid = r.get("qid") or make_qid(r["path"], r["question"])
            if r.get("deleted"):  # H 10:57: the workbench's Delete button appends the row with "deleted": true
                last.pop(qid, None)
                continue
            ans = r.get("answer")
            if isinstance(ans, str):
                try:
                    ans = float(ans.replace(",", ".")) if ans.strip() else None
                except ValueError:
                    pass  # a text answer stays text
            last[qid] = dict(qid=qid, path=r["path"], question=r["question"], answer=ans, unit=r.get("unit") or None,
                             type=r.get("type") or "other",
                             meta={"kind": f"human:{r.get('sureness') or 'unknown'}", "sureness": r.get("sureness"),
                                   "page": r.get("page"), "method": r.get("method"), "author": "expert"})
    return list(last.values())


def load_split(name: str) -> list[Question]:
    """Questions of a split, in file order. `name` is a split name or a path to a .jsonl file. Rows that carry their
    own `question` + `path` (generated splits such as `hard`, ad-hoc files) are used as-is (`answer`, `qid`, `unit`,
    `type` optional); rows with only a `qid` are joined with questions.jsonl. `human` = the expert's questions
    ($JUNCTION_SHARED/human/questions.jsonl, see _human_rows)."""
    if name == "all":
        return list(load_questions())
    f = _split_file(name)
    if not f.exists():
        if name == "human":
            raise FileNotFoundError(f"{f} missing: no expert questions saved yet (agent H's workbench writes it)")
        raise FileNotFoundError(f"{f} missing; run `python -m stoa.eval.splits --write`")
    if name == "human":
        out = []
        for r in _human_rows(f):
            q = Question(r["qid"], dataset_rel(r["path"]), r["question"], r["answer"], r["unit"], r["type"])
            object.__setattr__(q, "meta", r["meta"])
            out.append(q)
        return out
    by_id = None
    out = []
    with open(f, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            r = json.loads(line)
            # Rows that carry their own question are used as-is: generated splits (hard, hard2, ...) and ad-hoc files
            # written by hand, e.g. Stoa's example questions. `answer` and `qid` are optional there: no answer =
            # unscored (predictions and evidence only), qid defaults to a hash of path + question.
            if "question" in r and "path" in r:
                r["path"] = dataset_rel(r["path"])  # hand-written files may use absolute paths
                q = Question(r.get("qid") or make_qid(r["path"], r["question"]), r["path"], r["question"],
                             r.get("answer"), r.get("unit"), r.get("type", "other"))
                if r.get("meta"):
                    object.__setattr__(q, "meta", r["meta"])  # frozen dataclass; meta is eval-only
                out.append(q)
                continue
            if "qid" not in r:  # R2 11:03: a typed-in question without a drawing crashed here (KeyError 'qid')
                print(f"[splits] {f.name} line {lineno}: no 'path' (and no dataset 'qid'): row skipped; attach a drawing "
                      f"(e.g. experiments/r2/attach_drawings.py)", file=sys.stderr)
                continue
            if by_id is None:
                by_id = {q.qid: q for q in load_questions()}
            if r["qid"] in by_id:
                out.append(by_id[r["qid"]])
    return out


def split_hash(name: str) -> str | None:
    """Short content hash of a split file, recorded in leaderboard lines (detects regenerated splits)."""
    f = _split_file(name)
    return hashlib.sha1(f.read_bytes()).hexdigest()[:8] if f.exists() else None


def split_of_group() -> dict[str, str]:
    """group -> split name, for agents that want to check they never train on dev/test drawings."""
    m = {}
    for s in (*SPLITS, "unused"):
        f = splits_dir() / f"{s}.jsonl"
        if f.exists():
            for line in open(f, encoding="utf-8"):
                if line.strip():
                    r = json.loads(line)
                    if "group" in r:
                        m.setdefault(r["group"], s)
    return m


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--write-gate", action="store_true", help="write train_gate.jsonl (sample of train for gating)")
    a = ap.parse_args()
    if a.write_gate:
        print("train_gate:", write_train_gate())
    elif a.write:
        print(write_splits(force=a.force))
    else:
        sp = make_splits()
        for name, qs in sp.items():
            c = collections.Counter((q.source, q.type) for q in qs)
            g = collections.Counter(q.source for q in {drawing_group(q.path): q for q in qs}.values())
            print(name, len(qs), dict(sorted(c.items())), "groups:", dict(g))
