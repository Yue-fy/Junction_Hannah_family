"""LoRA x raster (W4's second opinion) x CC5K detector on cubicasa counts: is a joint confidence table better than
either cross-check alone, and does a 2-vs-1 vote beat the LoRA?  Fit on train_gate (W4's calib caches; the LoRA never
trained there), evaluate on a dev pipeline run that carries 'cross-check: vlm_lora X = raster Y' trace lines.
  python three_way.py DEV_PIPELINE_RUN.jsonl"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cc5k_evidence"))
from agree import KEY2CC, load_cache  # noqa: E402

SH = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
GROUP = {"window": "openings", "door": "openings", "wc": "fixtures", "sink": "fixtures",
         "bedroom": "rooms", "balcony": "rooms", "bathroom": "rooms", "kitchen": "rooms"}
RX = re.compile(r"cross-check: vlm_lora (\S+) [=≠] raster (\S+)")


def num(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def train_rows(cache):
    split = {json.loads(l)["qid"]: json.loads(l) for l in open(f"{SH}/results/splits/train_gate.jsonl")}
    gold = {}
    for l in open(f"{SH}/artifacts/eval/20261114-012403-vlm_direct-train_gate-ee1b.jsonl"):
        r = json.loads(l)
        gold[r["qid"]] = r.get("gold")
    lo = {json.loads(l)["qid"]: json.loads(l) for l in open(f"{SH}/artifacts/W4/calib/vlm_lora.jsonl")}
    ra = {json.loads(l)["qid"]: json.loads(l) for l in open(f"{SH}/artifacts/W4/calib/raster.jsonl")}
    out = []
    for q, L in lo.items():
        tgt = L["key"].split("|")[1].split(":")[1]
        if tgt not in KEY2CC or q not in ra or q not in split or gold.get(q) is None:
            continue
        p = split[q]["path"]
        if p not in cache:
            continue
        g, k = KEY2CC[tgt]
        out.append(dict(tgt=tgt, path=p, lora=num(L["value"]), ras=num(ra[q]["value"]),
                        det=cache[p][g][k]["count"], gold=num(gold[q])))
    return [r for r in out if r["lora"] is not None]


def dev_rows(run, cache):
    out = []
    for l in open(run):
        r = json.loads(l)
        if r["source"] != "cubicasa5k" or "vlm_lora" not in (r.get("solver") or "") or r.get("gold") is None:
            continue
        m = next((RX.search(t) for t in r["trace"] if RX.search(t)), None)
        key = next((t for t in r["trace"] if t.startswith("gate")), "")
        tgt = None
        for t in r["trace"]:
            mm = re.search(r"count:(\w+):drawing", t)
            if mm:
                tgt = mm.group(1)
                break
        if m is None or r["path"] not in cache:
            continue
        if tgt is None:  # fall back on the intent parser
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
            from stoa.router.intent import parse
            k = parse(r["question"]).key or ""
            tgt = k.split(":")[1] if k.count(":") == 2 else None
        if tgt not in KEY2CC:
            continue
        g, k = KEY2CC[tgt]
        out.append(dict(tgt=tgt, path=r["path"], lora=num(m.group(1)), ras=num(m.group(2)),
                        det=cache[r["path"]][g][k]["count"], gold=num(r["gold"]), conf_w4=r["confidence"]))
    return [r for r in out if r["lora"] is not None]


def cell(r, which):
    a_r, a_c = r["lora"] == r["ras"], r["lora"] == r["det"]
    return {"raster": (a_r,), "cc5k": (a_c,), "joint": (a_r, a_c)}[which]


def fit(rs, which, by="tgt"):
    t = defaultdict(lambda: [0, 0])
    for r in rs:
        for k in ((r[by] if by == "tgt" else GROUP[r["tgt"]], cell(r, which)), (GROUP[r["tgt"]], cell(r, which))):
            pass
        t[(r["tgt"], cell(r, which))][0] += r["lora"] == r["gold"]
        t[(r["tgt"], cell(r, which))][1] += 1
        t[("G:" + GROUP[r["tgt"]], cell(r, which))][0] += r["lora"] == r["gold"]
        t[("G:" + GROUP[r["tgt"]], cell(r, which))][1] += 1
    return t


def conf(t, r, which, nmin=8):
    k, n = t.get((r["tgt"], cell(r, which)), [0, 0])
    if n < nmin:  # back off to the group cell
        k, n = t.get(("G:" + GROUP[r["tgt"]], cell(r, which)), [0, 0])
    return min(0.95, (k + 1) / (n + 2))


def metrics(ys, ps):
    n = len(ys)
    brier = sum((p - y) ** 2 for y, p in zip(ys, ps)) / n
    bins = defaultdict(lambda: [0, 0, 0])
    for y, p in zip(ys, ps):
        b = bins[min(9, int(p * 10))]
        b[0] += y; b[1] += p; b[2] += 1
    ece = sum(abs(b[0] - b[1]) for b in bins.values()) / n
    pos = [p for y, p in zip(ys, ps) if y]
    neg = [p for y, p in zip(ys, ps) if not y]
    auc = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / max(1, len(pos) * len(neg))
    return f"brier {brier:.4f} ece {ece:.3f} auroc {auc:.3f}"


if __name__ == "__main__":
    cache = load_cache()
    tr, dv = train_rows(cache), dev_rows(sys.argv[1], cache)
    print(f"train_gate n={len(tr)}  dev n={len(dv)}")
    ys = [r["lora"] == r["gold"] for r in dv]
    print(f"dev LoRA acc {100*sum(ys)/len(ys):.1f}")
    if all("conf_w4" in r for r in dv):
        print("pipeline conf (W4 raster table)  ", metrics(ys, [r["conf_w4"] for r in dv]))
    for which in ("raster", "cc5k", "joint"):
        t = fit(tr, which)
        print(f"{which:7} table (train_gate) on dev ", metrics(ys, [conf(t, r, which) for r in dv]))
    print("\njoint cells on train_gate / dev: P(LoRA right) (n)")
    tt, td = fit(tr, "joint"), fit(dv, "joint")
    for g in ("G:openings", "G:fixtures", "G:rooms"):
        print(g, "  ".join(f"r{int(c[0])}c{int(c[1])}: {tt.get((g, c), [0, 0])[0]}/{tt.get((g, c), [0, 0])[1]}"
                           f" | {td.get((g, c), [0, 0])[0]}/{td.get((g, c), [0, 0])[1]}"
                           for c in ((True, True), (True, False), (False, True), (False, False))))
    print("\nvote: LoRA unless raster == CC5K != LoRA (2 vs 1)")
    for name, rs in (("train_gate", tr), ("dev", dv)):
        by = defaultdict(lambda: [0, 0, 0])
        for r in rs:
            v = r["ras"] if (r["ras"] == r["det"] and r["ras"] != r["lora"]) else r["lora"]
            b = by[r["tgt"]]
            b[0] += r["lora"] == r["gold"]; b[1] += v == r["gold"]; b[2] += 1
        print(name, " ".join(f"{t}:{100*a/n:.0f}->{100*b/n:.0f}(n{n})" for t, (a, b, n) in sorted(by.items())))


def write_joint(tr, path):
    """crosscheck_calib.json["joint"]: [k, n] per (target | G:group) x cell r<agree raster>c<agree CC5K>."""
    t = fit(tr, "joint")
    d = json.load(open(path))
    cells = defaultdict(dict)
    for (who, c), (k, n) in sorted(t.items(), key=str):
        cells[who][f"r{int(c[0])}c{int(c[1])}"] = [k, n]
    d["joint"] = {"fitted_on": "train_gate: artifacts/W4/calib/vlm_lora.jsonl + raster.jsonl + CC5K cache",
                  "rule": "P(LoRA right | agrees with raster?, agrees with CC5K?) = (k+1)/(n+2) capped 0.95; "
                          "cell n < nmin -> the group's cell", "nmin": 8, "groups": GROUP, "cells": cells}
    json.dump(d, open(path, "w"), indent=1)


if __name__ == "__main__" and "--write" in sys.argv:
    write_joint(train_rows(load_cache()), sys.argv[sys.argv.index("--write") + 1])
