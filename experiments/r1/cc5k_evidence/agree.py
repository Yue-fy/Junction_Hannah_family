"""LoRA (R2's cc-v2) vs CC5K detector agreement on cubicasa counts: is agreement a usable confidence signal,
and on disagreement who is right?  Usage:
  python agree.py PRED.jsonl [PRED2.jsonl ...]     (eval prediction files of vlm_lora / pipeline runs)
Prints per concept: n, LoRA acc, CC5K acc, agree rate, P(right|agree), P(LoRA right|disagree),
P(CC5K right|disagree), P(|LoRA-gold|<=1 ...).  Concept key comes from stoa.router.intent.parse."""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from stoa.router.intent import parse  # noqa: E402

SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
CACHE = os.path.join(SHARED, "artifacts", "R1", "cc5k_counts.jsonl")
KEY2CC = {"window": ("counts", "windows"), "door": ("counts", "doors"), "wc": ("counts", "wc_seats"),
          "sink": ("counts", "sinks"), "bedroom": ("rooms", "bedrooms"), "balcony": ("rooms", "balconies"),
          "bathroom": ("rooms", "bathrooms"), "kitchen": ("rooms", "kitchens")}


def load_cache():
    return {d["path"]: d for d in map(json.loads, open(CACHE))}


def rows(pred_files, cache):
    out = []
    for f in pred_files:
        for r in map(json.loads, open(f)):
            if r.get("source") != "cubicasa5k" or r.get("type") != "count" or r.get("gold") is None:
                continue
            it = parse(r["question"])
            if it.key is None or not it.key.startswith("count:") or not it.key.endswith(":drawing"):
                continue
            tgt = it.key.split(":")[1]
            if tgt not in KEY2CC or r["path"] not in cache:
                continue
            grp, k = KEY2CC[tgt]
            det = cache[r["path"]][grp][k]["count"]
            try:
                v = None if r["value"] is None else int(round(float(r["value"])))
            except (TypeError, ValueError):
                v = None
            out.append(dict(qid=r["qid"], path=r["path"], tgt=tgt, gold=int(r["gold"]), lora=v, det=det,
                            conf=r.get("confidence") or 0.0, cc5k_list=cache[r["path"]].get("cc5k_list")))
    return out


def table(rs, title):
    by = defaultdict(list)
    for r in rs:
        by[r["tgt"]].append(r)
    print(f"\n== {title}  (n={len(rs)})")
    print(f"{'concept':9} {'n':>4} {'LoRA':>5} {'CC5K':>5} {'agree':>6} {'P|agr':>6} {'L|dis':>6} {'C|dis':>6} "
          f"{'C±1':>5} {'L≤conf':>6}")
    res = {}
    for t in sorted(by):
        g = by[t]
        n = len(g)
        L = sum(r["lora"] == r["gold"] for r in g) / n
        C = sum(r["det"] == r["gold"] for r in g) / n
        agr = [r for r in g if r["lora"] == r["det"]]
        dis = [r for r in g if r["lora"] != r["det"]]
        pa = sum(r["lora"] == r["gold"] for r in agr) / len(agr) if agr else float("nan")
        ld = sum(r["lora"] == r["gold"] for r in dis) / len(dis) if dis else float("nan")
        cd = sum(r["det"] == r["gold"] for r in dis) / len(dis) if dis else float("nan")
        c1 = sum(abs(r["det"] - r["gold"]) <= 1 for r in g) / n
        mc = sum(r["conf"] for r in g) / n
        res[t] = dict(n=n, lora=L, cc5k=C, agree=len(agr) / n, p_agree=pa, lora_dis=ld, cc5k_dis=cd,
                      n_agree=len(agr), n_dis=len(dis))
        print(f"{t:9} {n:4d} {100*L:5.1f} {100*C:5.1f} {100*len(agr)/n:6.1f} {100*pa:6.1f} {100*ld:6.1f} "
              f"{100*cd:6.1f} {100*c1:5.1f} {mc:6.2f}")
    return res


if __name__ == "__main__":
    cache = load_cache()
    rs = rows(sys.argv[1:], cache)
    table(rs, " + ".join(os.path.basename(f) for f in sys.argv[1:]))
