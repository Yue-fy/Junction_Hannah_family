"""Check the room graph without any dataset labels (D3): printed room labels as independent truth + plausibility.

(1) Label <-> region class: a printed label read by the VLM (cached, artifacts/R1/room_labels; independent of CC5K)
    sits inside a region; is the region's class the one the Finnish code implies (MH -> bedroom, KH/PH/WC -> bath,
    K/KEITTIÖ -> kitchen, OH -> living, ET/TK -> entry, VH/VAR -> storage, PARVEKE -> outdoor)?
(2) Plausibility on rooms named by their printed label (so CC5K's class is not used to pick them):
    bedrooms (MH) with >= 1 window (Finnish habitable rooms need one), bath/WC rooms with a toilet or sink,
    kitchens with a sink, rooms with any door or open connection.
(3) Graph health on any cached plans: doors linking two sides, windows assigned, rooms reachable from 'outside'.

Run: $JUNCTION_VENV/bin/python -m experiments.r1.room_graph.validate [--n 400] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from experiments.r1.room_graph.graph import ART, _labels_index, room_graph  # noqa: E402

CODE2CLS = [  # (regex on the normalised first token, expected CC5K class)
    (r"^(MH|MAKUUH(UONE)?)$", "bedroom"),
    (r"^(OH|OLOH(UONE)?|TUPA|RT|RUOKAILU(TILA)?)$", "living"),
    (r"^(K|KK|KT|KEITTIO|KEITTOKOMERO|AVOK|TUPAKEITTIO)$", "kitchen"),
    (r"^(KH|PH|KPH|PESUH|SH|KYLPYH(UONE)?|PESUHUONE|WC|PS)$", "bath"),
    (r"^(S|SAUNA|LH|LOYLYH(UONE)?)$", "sauna"),
    (r"^(ET|ETEINEN|TK|TUULIKAAPPI|AULA|HALL|KAYT|KAYTAVA)$", "entry"),
    (r"^(VH|VAR|VARASTO|VAATEH(UONE)?)$", "storage"),
    (r"^(PARV|PARVEKE|LASPARV|TERASSI|TER)$", "outdoor"),
]


def norm(t: str) -> str:
    t = t.upper().replace("Ö", "O").replace("Ä", "A").replace("Å", "A")
    tok = re.split(r"[\s+/,.:;()\d-]+", t.strip())
    return tok[0] if tok else ""


def expected(text: str) -> str | None:
    n = norm(text)
    for rx, c in CODE2CLS:
        if re.match(rx, n):
            return c
    return None


def reachable(g: dict) -> tuple[int, int]:
    """(# interior rooms reachable from 'outside' via doors/open connections, # interior rooms)."""
    adj = defaultdict(set)
    for r in g["rooms"]:
        for o in r["door_to"] + r["open_to"]:
            adj[r["id"]].add(o)
            adj[o].add(r["id"])
    interior = {r["id"] for r in g["rooms"] if r["cls"] != "outdoor"}
    start = {"outside"} | {r["id"] for r in g["rooms"] if r["cls"] == "outdoor"}  # balconies count as outside
    seen, todo = set(start), list(start)
    while todo:
        x = todo.pop()
        for y in adj[x]:
            if y not in seen:
                seen.add(y)
                todo.append(y)
    return len(interior & seen), len(interior)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400, help="random cached plans for the graph-health part")
    ap.add_argument("--out", default=str(ART / "room_graph" / "validate.json"))
    a = ap.parse_args()

    # ---- (1) + (2) on plans with cached printed labels ---------------------------------------------------------
    labels = _labels_index()
    conf = Counter()            # (expected, region cls) pairs
    plaus = defaultdict(list)   # metric -> [bool]
    per_room_windows = []
    for stem, items in sorted(labels.items()):
        g = room_graph(f"data/cubicasa5k/{stem}.png", labels=items)
        if not g:
            continue
        by_id = {r["id"]: r for r in g["rooms"]}
        # map each label to its region again (graph keeps texts only); re-derive from label boxes
        import numpy as np  # noqa: F401
        for r in g["rooms"]:
            for t in (r["label"] or "").split(" / "):
                e = expected(t) if t else None
                if e:
                    conf[(e, r["cls"])] += 1
        # labels that fall on no region at all
        for text, _, box in items:
            e = expected(text)
            if not e:
                continue
            hit = any(text in (r["label"] or "").split(" / ") for r in g["rooms"])
            if not hit:
                conf[(e, "<none>")] += 1
        for r in g["rooms"]:
            ex = {expected(t) for t in (r["label"] or "").split(" / ") if t} - {None}
            if "bedroom" in ex:
                plaus["bedroom (MH) has >=1 window"].append(len(r["windows"]) > 0)
                per_room_windows.append(len(r["windows"]))
            if "bath" in ex:
                plaus["bath/WC (KH/PH/WC) has toilet or sink"].append(bool(r["fixtures"].get("toilet") or r["fixtures"].get("sink")))
            if "kitchen" in ex:
                plaus["kitchen (K/KEITTIÖ) has sink"].append(bool(r["fixtures"].get("sink")))
            if "sauna" in ex:
                plaus["sauna (S/SAUNA) has sauna bench"].append(bool(r["fixtures"].get("sauna_bench")))
            if ex and "outdoor" not in ex:
                plaus["labelled interior room has a door or open link"].append(bool(r["door_to"] or r["open_to"]))
        _ = by_id

    # ---- (3) graph health on random cached plans --------------------------------------------------------------
    stems = sorted(p.stem for p in (ART / "cc5k_seg").glob("*.npz"))
    random.Random(0).shuffle(stems)
    health = defaultdict(list)
    for stem in stems[:a.n]:
        g = room_graph(f"data/cubicasa5k/{stem}.png", labels=[])
        if not g or not g["rooms"]:
            health["plans with no rooms"].append(1)
            continue
        health["plans with no rooms"].append(0)
        for d in g["doors"]:
            health["door links two sides (room-room or room-outside)"].append(len(d["between"]) == 2)
            health["door is room-outside"].append("outside" in d["between"])
        for w in g["windows"]:
            health["window assigned to a room"].append(w["room"] is not None)
            health["window on an exterior wall"].append(w["side"] == "exterior")
        k, n = reachable(g)
        health["interior rooms reachable from outside (share)"].append(k / n if n else 0)
        health["all interior rooms reachable"].append(k == n)
        outd = {r["id"] for r in g["rooms"] if r["cls"] == "outdoor"} | {"outside"}
        health["has an entrance (door to outside)"].append(any("outside" in d["between"] for d in g["doors"]))
        health["has a door to outside or a balcony"].append(any(set(d["between"]) & outd for d in g["doors"]))
        health["rooms per plan"].append(len(g["rooms"]))

    def pct(v):
        return round(100 * sum(v) / len(v), 1) if v else None

    exp_tot = Counter()
    for (e, c), n in conf.items():
        exp_tot[e] += n
    label_table = {e: {"n": exp_tot[e], "agree%": round(100 * conf[(e, e)] / exp_tot[e], 1),
                       "top": Counter({c: n for (e2, c), n in conf.items() if e2 == e}).most_common(4)}
                   for e in sorted(exp_tot)}
    out = {
        "label_plans": len(labels),
        "label_vs_region": label_table,
        "label_overall_agree%": round(100 * sum(conf[(e, e)] for e in exp_tot)
                                      / max(1, sum(exp_tot.values())), 1),
        "plausibility": {k: {"n": len(v), "%": pct(v)} for k, v in plaus.items()},
        "bedroom windows distribution": dict(Counter(per_room_windows)),
        "health_plans": min(a.n, len(stems)),
        "health": {k: ({"n": len(v), "mean": round(st.mean(v), 2)} if k in ("rooms per plan",
                       "interior rooms reachable from outside (share)") else {"n": len(v), "%": pct(v)})
                   for k, v in health.items()},
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
