"""Offline routing simulation: what would the pipeline score if atomic cubicasa counts went to the LoRA?

No model calls: it merges existing prediction files question by question.
The per-concept choice (pipeline vs LoRA) and the per-concept confidence are fitted on TRAIN_GATE runs
(drawings the LoRA never saw) and then applied to DEV, so the dev number is an honest estimate.

    python experiments/F/lora_route_sim.py PIPE_DEV LORA_DEV PIPE_GATE LORA_GATE [--margin 0.0]

Policies printed:
  pipeline      the pipeline run as is
  lora_all      every cubicasa count question answered by the LoRA (its own confidence)
  per_concept   per concept (EN+FI merged), the solver with the higher train_gate accuracy; confidence =
                that solver's train_gate hit rate for the concept (never the LoRA's own number)
  agree_boost   per_concept, plus: if pipeline and LoRA give the same number, confidence = the train_gate
                hit rate of the "both agree" case for that concept
"""
from __future__ import annotations

import argparse
import collections
import functools
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from stoa.eval.runner import summarize  # noqa: E402

EVAL = os.path.join(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"), "artifacts", "eval")



@functools.lru_cache(maxsize=None)
def concept_of(question: str) -> str | None:
    """The pipeline's own concept key: stoa.router.intent target (e.g. window, wc, sink, shower_bathtub)."""
    from stoa.router.intent import parse
    return getattr(parse(question), "target", None)


def concept(row: dict) -> str | None:
    return concept_of(row["question"])


def load(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        path = os.path.join(EVAL, path if path.endswith(".jsonl") else path + ".jsonl")
    return {r["qid"]: r for r in map(json.loads, open(path))}


def hit_rates(pipe: dict, lora: dict) -> dict[str, dict]:
    """Per concept on the gate split: accuracy of each solver and of the agree / disagree cases."""
    acc = collections.defaultdict(lambda: collections.Counter())
    for qid, p in pipe.items():
        if p["source"] != "cubicasa5k" or p["type"] != "count" or qid not in lora:
            continue
        c = concept(p)
        l = lora[qid]
        k = acc[c]
        k["n"] += 1
        k["pipe"] += bool(p["correct"])
        k["lora"] += bool(l["correct"])
        same = l["value"] is not None and p["value"] is not None and round(float(l["value"])) == round(float(p["value"]))
        if same:
            k["agree_n"] += 1
            k["agree_ok"] += bool(p["correct"])
    out = {}
    for c, k in acc.items():
        n = k["n"]
        out[c] = {
            "n": n, "pipe": k["pipe"] / n, "lora": k["lora"] / n,
            "agree_share": k["agree_n"] / n,
            "agree_acc": (k["agree_ok"] / k["agree_n"]) if k["agree_n"] else None,
        }
    return out


def apply(dev_pipe: dict, dev_lora: dict, gate: dict, policy: str, margin: float) -> list[dict]:
    rows = []
    for qid, p in dev_pipe.items():
        r = dict(p)
        if p["source"] == "cubicasa5k" and p["type"] == "count" and qid in dev_lora:
            c = concept(p)
            l = dev_lora[qid]
            g = gate.get(c)
            use_lora = False
            if policy == "lora_all":
                use_lora = True
            elif g and policy in ("per_concept", "agree_boost"):
                use_lora = g["lora"] > g["pipe"] + margin
            if use_lora:
                for k in ("value", "unit", "correct", "abstained", "solver", "evidence"):
                    r[k] = l.get(k)
                r["confidence"] = l["confidence"]
                cost = dict(p.get("cost") or {})
                lc = l.get("cost") or {}
                # the pipeline still runs its cheap path (labels) for evidence; add the LoRA call on top
                for k in ("llm_calls", "llm_tokens_in", "llm_tokens_out", "gpu_seconds", "usd"):
                    cost[k] = (cost.get(k) or 0) + (lc.get(k) or 0)
                r["cost"] = cost
            if g and policy in ("per_concept", "agree_boost"):
                r["confidence"] = g["lora"] if use_lora else g["pipe"]
                if policy == "agree_boost":
                    same = l["value"] is not None and p["value"] is not None and round(float(l["value"])) == round(float(p["value"]))
                    if same and g["agree_acc"] is not None:
                        r["confidence"] = g["agree_acc"]
                    elif not same:
                        # disagreement: the chosen solver's rate when they disagree is lower; approximate it
                        n_dis = g["n"] * (1 - g["agree_share"])
                        ok_chosen = (g["lora"] if use_lora else g["pipe"]) * g["n"]
                        ok_agree = (g["agree_acc"] or 0) * g["n"] * g["agree_share"]
                        r["confidence"] = max(0.05, (ok_chosen - ok_agree) / n_dis) if n_dis > 0 else r["confidence"]
        rows.append(r)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pipe_dev")
    ap.add_argument("lora_dev")
    ap.add_argument("pipe_gate")
    ap.add_argument("lora_gate")
    ap.add_argument("--json", help="write the per-concept gate table (choice + confidences) to this path")
    ap.add_argument("--margin", type=float, default=0.0, help="LoRA must beat the pipeline on train_gate by this much")
    a = ap.parse_args(argv)
    dp, dl, gp, gl = (load(x) for x in (a.pipe_dev, a.lora_dev, a.pipe_gate, a.lora_gate))
    gate = hit_rates(gp, gl)
    dev_rates = hit_rates(dp, dl)
    print("## Per concept: train_gate (choice) and dev (check)\n")
    print("| concept | gate n | gate pipe | gate LoRA | gate agree share / acc | -> choose | dev n | dev pipe | dev LoRA |")
    print("|---|---:|---:|---:|---:|---|---:|---:|---:|")
    for c in sorted(gate, key=lambda c: -(gate[c]["lora"] - gate[c]["pipe"])):
        g, d = gate[c], dev_rates.get(c, {})
        pick = "LoRA" if g["lora"] > g["pipe"] + a.margin else "pipeline"
        aa = f"{g['agree_share']:.0%} / {g['agree_acc']:.0%}" if g["agree_acc"] is not None else "-"
        print(f"| {c} | {g['n']} | {g['pipe']:.0%} | {g['lora']:.0%} | {aa} | {pick} | {d.get('n', 0)} | "
              f"{d.get('pipe', 0):.0%} | {d.get('lora', 0):.0%} |")
    if a.json:
        table = {}
        for c, g in gate.items():
            use = g["lora"] > g["pipe"] + a.margin
            n_dis = g["n"] * (1 - g["agree_share"])
            ok_chosen = (g["lora"] if use else g["pipe"]) * g["n"]
            ok_agree = (g["agree_acc"] or 0) * g["n"] * g["agree_share"]
            table[c] = {"use_lora": use, "n": g["n"], "acc_pipeline": round(g["pipe"], 4), "acc_lora": round(g["lora"], 4),
                        "conf_chosen": round(g["lora"] if use else g["pipe"], 4),
                        "conf_agree": round(g["agree_acc"], 4) if g["agree_acc"] is not None else None,
                        "conf_disagree": round(max(0.05, (ok_chosen - ok_agree) / n_dis), 4) if n_dis > 0 else None}
        json.dump({"fitted_on": [a.pipe_gate, a.lora_gate], "key": "stoa.router.intent.parse(q).target",
                   "lora_model": "cc-v2", "concepts": table}, open(a.json, "w"), indent=1)
        print(f"wrote {a.json}")
    print("\n## Dev, whole split, per policy\n")
    print("| policy | weighted | micro | cubicasa count acc | ECE | AUROC | conf>=0.8 share / acc | $/1k |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for pol in ("pipeline", "lora_all", "per_concept", "agree_boost"):
        rows = apply(dp, dl, gate, pol, a.margin)
        m = summarize(rows)
        cc = [r for r in rows if r["source"] == "cubicasa5k" and r["type"] == "count"]
        cal = m.get("calibration") or {}
        hi = cal.get("hi_conf_share"), cal.get("hi_conf_acc")
        cost = m.get("usd_per_1k_q")
        print(f"| {pol} | {m['weighted_acc']:.1%} | {m['accuracy']:.1%} | {sum(bool(r['correct']) for r in cc) / len(cc):.1%} | "
              f"{cal.get('ece', float('nan')):.3f} | {cal.get('auroc', float('nan')):.3f} | "
              f"{(hi[0] or 0):.0%} / {(hi[1] or 0):.1%} | {cost if cost is None else round(cost, 3)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
