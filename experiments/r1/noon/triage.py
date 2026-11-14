"""Noon triage: which of our routes would catch each of Stoa's example questions, and how new is each one?
0 LLM calls, ~20 s (most of it indexing questions.jsonl). Run it BEFORE the first pipeline run on the examples.

    $JUNCTION_VENV/bin/python experiments/r1/noon/triage.py EXAMPLES.jsonl [--out triage.jsonl] [--k 1]
    $JUNCTION_VENV/bin/python experiments/r1/noon/triage.py questions.txt --path data/ifc_models/<sheet>.pdf

EXAMPLES.jsonl rows: {"path": "data/...", "question": "...", "answer": ...} (path and answer optional); a .txt file
is one question per line (all on --path, if given).

Per question it prints:
  source   stoa.data.source_of(path) (the pipeline's route depends on it)
  intent   W4's rule parser (stoa.router.intent.parse): task / target / scope. 'other' or target 'unknown' = the
           template cascade can't read it; the agent or a new parser rule must
  tmpl     the question's template occurs in train (compose leaves it atomic)
  compose  compose.decompose's plan (sum / diff / argmax / ... over simpler questions), if any
  link     R1's kg_qa trigger (experiments/r1/kg_qa/kgqa.py is_link_question) and its reason
  room     R1's room-graph trigger (experiments/r1/room_graph/route.py per_room; CubiCasa rasters only)
  est      R1's out-of-drawing kind (experiments/r1/estimate/estimate.py kind_of; NOT wired, research/methods.md 8m)
  nn       the most similar question we tuned on (TF-IDF cosine over word tokens + char 4-grams, over the distinct
           questions of train + dev; test is sealed and never read) and its answer type. nn < 0.5 and no train
           template = a kind nobody tuned for. Calibrated (calibrate.py, nearest TRAIN question, 400 rows each):
           flagged new = dev 14%, hard 33%, hard2 77%, Q's red team 70%
  todo     where a fix would go (stoa/router/README.md section 3)
and a summary: how many examples each route catches and how many are new kinds.

Why this is useful: tonight's rule was 'measure the trigger before the run' (a route that fires on the right rows
and on 0 dataset rows cannot move dev). This shows, before spending a token, which examples land on a route that was
measured tonight and which fall through to the generic cascade/agent, i.e. where to write probes first.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
_WORD = re.compile(r"[^\W\d_]+|\d+", re.U)


def _feats(q: str) -> list[str]:
    q = " ".join(q.lower().split())
    words = _WORD.findall(q)
    grams = [q[i:i + 4] for i in range(max(0, len(q) - 3))]
    return ["w:" + w for w in words] + ["c:" + g for g in grams]


class NN:
    """Cosine nearest neighbour over TF-IDF vectors with an inverted index (distinct dataset questions only)."""

    def __init__(self, rows: list[dict]):
        by_q: dict[str, dict] = {}
        for r in rows:
            by_q.setdefault(r["question"], r)
        self.rows = list(by_q.values())
        df: collections.Counter = collections.Counter()
        tfs = []
        for r in self.rows:
            tf = collections.Counter(_feats(r["question"]))
            tfs.append(tf)
            df.update(tf.keys())
        n = len(self.rows)
        self.idf = {f: math.log((n + 1) / (c + 1)) + 1.0 for f, c in df.items()}
        self.vecs = []
        self.index: dict[str, list[int]] = collections.defaultdict(list)
        for i, tf in enumerate(tfs):
            v = {f: (1 + math.log(c)) * self.idf[f] for f, c in tf.items()}
            norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
            v = {f: x / norm for f, x in v.items()}
            self.vecs.append(v)
            for f in v:
                if f.startswith("w:"):
                    self.index[f].append(i)

    def query(self, q: str, k: int = 1) -> list[tuple[float, dict]]:
        tf = collections.Counter(_feats(q))
        v = {f: (1 + math.log(c)) * self.idf.get(f, math.log(len(self.rows) + 1) + 1.0) for f, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        v = {f: x / norm for f, x in v.items()}
        # candidates: rows sharing one of the query's 6 rarest known words (keeps it fast; all rows if none known)
        words = sorted((f for f in v if f.startswith("w:") and f in self.index), key=lambda f: -self.idf[f])[:6]
        cand: set[int] = set()
        for f in words:
            cand.update(self.index[f])
        if not cand:
            cand = set(range(len(self.rows)))
        scored = []
        for i in cand:
            u = self.vecs[i]
            s = sum(x * u.get(f, 0.0) for f, x in v.items())
            scored.append((s, i))
        scored.sort(reverse=True)
        return [(round(s, 3), self.rows[i]) for s, i in scored[:k]]


def _safe(fn, *a, default=None):
    try:
        return fn(*a)
    except Exception as e:  # a triage tool must never stop on one question
        return default if default is not None else {"error": f"{type(e).__name__}: {e}"}


def triage_one(q: str, path: str | None, nn: NN, k: int = 1) -> dict:
    from experiments.r1.estimate.estimate import kind_of
    from experiments.r1.kg_qa.kgqa import is_link_question
    from experiments.r1.room_graph.route import per_room
    from stoa.router.compose import decompose
    from stoa.router.intent import parse
    from stoa.router.prior import known_template

    src = _safe(lambda p: __import__("stoa.data", fromlist=["source_of"]).source_of(p), path, default="?") if path else "?"
    it = _safe(parse, q)
    intent = it.describe() if hasattr(it, "describe") else str(it)
    task = getattr(it, "task", "?")
    target = getattr(it, "target", "?")
    tmpl = bool(_safe(known_template, q, default=False))
    plan = _safe(decompose, src if src != "?" else "", q, default=None)
    comp = f"{plan.op} over {len(plan.subs)}" if plan is not None and hasattr(plan, "op") else ""
    link = _safe(is_link_question, q)
    room = _safe(per_room, q, path) if path else _safe(per_room, q)
    est = _safe(kind_of, q)
    near = nn.query(q, k)
    s0, r0 = near[0] if near else (0.0, {})

    todo = []
    if link.get("fire"):
        todo.append("link route (kg_qa + W1 plan_vs_model); probes: experiments/r1/kg_qa/compare.py")
    if room.get("fire") or room.get("fire_any"):
        todo.append("room graph (R1, CubiCasa)")
    if est.get("fire"):
        todo.append("out-of-drawing: estimate route (methods 8m, not wired; hook experiments/r1/estimate/pipeline_est.py)")
    if comp:
        todo.append("compose.py")
    if task in ("other", "?") or target == "unknown":
        todo.append("parser gap: intent.py rule or the agent (agent.py)")
    novel = (s0 < 0.5) and not tmpl
    if novel:
        todo.append("NEW KIND: write gold + 5-10 rewordings before the first run")
    return {
        "question": q, "path": path, "source": src, "intent": intent, "template": tmpl, "compose": comp,
        "link": link.get("why") if link.get("fire") else "", "room": (room.get("kind") or room.get("why") or "")
        if (room.get("fire") or room.get("fire_any")) else "", "est": est.get("kind") if est.get("fire") else "",
        "nn": s0, "nn_question": r0.get("question", ""), "nn_type": r0.get("type", ""), "nn_path": r0.get("path", ""),
        "novel": novel, "todo": todo,
    }


def load_examples(fn: str, path: str | None) -> list[tuple[str, str | None, object]]:
    out = []
    with open(fn, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if fn.endswith(".jsonl"):
                r = json.loads(line)
                out.append((r["question"], r.get("path") or path, r.get("answer")))
            else:
                out.append((line, path, None))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("examples")
    ap.add_argument("--path", default=None, help="drawing for every question of a .txt file (or rows without one)")
    ap.add_argument("--out", default=None, help="write one JSON row per question here")
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--index", default="train,dev", help="splits to index (never 'test': it is sealed)")
    a = ap.parse_args()

    from stoa.eval.splits import load_split

    rows = [{"question": q.question, "path": q.path, "type": q.type}
            for s in a.index.split(",") if s.strip() and s.strip() != "test" for q in load_split(s.strip())]
    nn = NN(rows)
    ex = load_examples(a.examples, a.path)
    res = []
    for i, (q, p, gold) in enumerate(ex, 1):
        r = triage_one(q, p, nn, a.k)
        r["answer"] = gold
        res.append(r)
        flags = " ".join(x for x in (
            "TEMPLATE" if r["template"] else "", f"COMPOSE({r['compose']})" if r["compose"] else "",
            f"LINK({r['link']})" if r["link"] else "", f"ROOM({r['room']})" if r["room"] else "",
            f"EST({r['est']})" if r["est"] else "", "NEW" if r["novel"] else "") if x)
        print(f"[{i}] {q}")
        print(f"     source={r['source']}  intent: {r['intent']}  {flags}")
        print(f"     nn {r['nn']:.2f} ({r['nn_type']}): {r['nn_question'][:110]}")
        for t in r["todo"]:
            print(f"     -> {t}")
    n = len(res) or 1
    c = collections.Counter()
    for r in res:
        c["template"] += r["template"]
        c["compose"] += bool(r["compose"])
        c["link"] += bool(r["link"])
        c["room"] += bool(r["room"])
        c["est"] += bool(r["est"])
        c["parser gap"] += any(t.startswith("parser gap") for t in r["todo"])
        c["NEW kind (nn<0.5, no template)"] += r["novel"]
    print(f"\n{len(res)} questions; nn similarity median "
          f"{sorted(r['nn'] for r in res)[len(res) // 2] if res else 0:.2f}")
    for key, v in c.items():
        print(f"  {key:32s} {v:4d}  ({100 * v / n:.0f}%)")
    print("  by intent task: " + ", ".join(f"{k} {v}" for k, v in collections.Counter(
        r["intent"].split(" ")[0] for r in res).most_common()))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            for r in res:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"rows: {a.out}")


if __name__ == "__main__":
    main()
