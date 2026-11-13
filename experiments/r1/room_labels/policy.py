"""Hybrid label/prior policy for cubicasa room-type counts. Tuned on TRAIN drawings, then scored once on DEV.

Policies per template (k = count of unique labels mapped to the class; loop = output degenerated):
  prior          : most common train answer for the template
  labels         : k
  max1           : max(1, k)            (rooms that nearly always exist but are often unlabelled)
  labels|prior0  : k if k > 0 else prior
Any policy falls back to the prior when the VLM output looped (one text repeated > LOOP times).
Run: $JUNCTION_VENV/bin/python -I policy.py  (uses the cached v2 label outputs from run.py)
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run  # noqa: E402

LOOP = 6


def tpl(q):
    for k, rx in run.TEMPLATES.items():
        if re.search(rx, q):
            return k


def looped(text):
    c = collections.Counter(t for _, t in run.parse_items(text))
    return bool(c) and c.most_common(1)[0][1] > LOOP


# Chosen on TRAIN (60 drawings, 574 Qs), then frozen before looking at dev:
HYBRID = {"bedroom": "labels", "kitchen": "prior", "bathroom": "max1", "wc_room": "labels", "sauna": "labels",
          "balcony": "labels"}
POLICIES = {
    "prior": lambda k, p: p,
    "labels": lambda k, p: k,
    "max1": lambda k, p: max(1, k),
    "labels|prior0": lambda k, p: k if k > 0 else p,
}


def evaluate(split):
    import hashlib
    q = {}
    for line in open(os.path.join(run.DATA, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/cubicasa5k/") and tpl(d["question"]):
            q[hashlib.sha1(f"{d['path']}\n{d['question']}".encode()).hexdigest()[:12]] = d
    rows = [q[json.loads(l)["qid"]] for l in open(os.path.join(run.SHARED, "results", "splits", f"{split}.jsonl"))
            if json.loads(l)["qid"] in q]
    prior_c = collections.defaultdict(collections.Counter)
    for l in open(os.path.join(run.SHARED, "results", "splits", "train.jsonl")):
        d = q.get(json.loads(l)["qid"])
        if d:
            prior_c[tpl(d["question"])][d["answer"]] += 1
    prior = {k: v.most_common(1)[0][0] for k, v in prior_c.items()}
    S = collections.defaultdict(collections.Counter)
    S["_rows"] = []
    for d in rows:
        f = os.path.join(run.CACHE, os.path.basename(d["path"]) + ".labels.v2.json")
        if not os.path.exists(f):
            continue
        text = json.load(open(f))["text"]
        k = run.count_labels(text)[tpl(d["question"])]
        loop = looped(text)
        t = tpl(d["question"])
        S[t]["n"] += 1
        S[t]["loops"] += loop
        for name, fn in POLICIES.items():
            pred = prior[t] if loop else fn(k, prior[t])
            S[t][name] += pred == d["answer"]
        pred = prior[t] if loop else POLICIES[HYBRID[t]](k, prior[t])
        S[t]["hybrid"] += pred == d["answer"]
        qid = hashlib.sha1(f"{d['path']}\n{d['question']}".encode()).hexdigest()[:12]
        S["_rows"].append({"qid": qid, "path": d["path"], "source": "cubicasa5k", "type": "count", "template": t,
                           "gold": d["answer"], "hybrid": pred, "prior": prior[t], "loop": loop})
    return S


if __name__ == "__main__":
    for split in sys.argv[1:] or ["train"]:
        S = evaluate(split)
        rows = S.pop("_rows")
        out = os.path.join(run.CACHE, f"policy_{split}")
        for name in ("prior", "hybrid"):
            with open(f"{out}_{name}.jsonl", "w") as f:
                for r in rows:
                    f.write(json.dumps({**r, "value": r[name], "correct": r[name] == r["gold"], "abstained": False,
                                        "confidence": None}) + "\n")
        print(f"== {split}  (accuracy per policy; loops = outputs that degenerated)")
        cols = [*POLICIES, "hybrid"]
        print(f"{'template':10s} {'n':>4s} {'loops':>5s} " + " ".join(f"{p:>13s}" for p in cols))
        tot = collections.Counter()
        for t, s in S.items():
            tot.update(s)
            print(f"{t:10s} {s['n']:4d} {s['loops']:5d} " + " ".join(f"{s[p]/s['n']:13.1%}" for p in cols))
        print(f"{'ALL':10s} {tot['n']:4d} {tot['loops']:5d} " + " ".join(f"{tot[p]/tot['n']:13.1%}" for p in cols))
