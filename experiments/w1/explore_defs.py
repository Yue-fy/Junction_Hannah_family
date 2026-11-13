"""Reverse-engineer how the ifc_models gold values were computed. TRAIN split only.

PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w1/explore_defs.py [--split train] [--show N]
For each question: parse, resolve names, compute several candidate definitions, report which match.
"""

from __future__ import annotations

import argparse
import collections
import sys

from stoa.data import ifc_model_for, source_of
from stoa.eval.splits import load_split
from stoa.solvers.ifc.index import load_index
from stoa.solvers.ifc.parse import parse
from stoa.solvers.ifc.resolve import match_model, match_space, match_storey


def close(a, b, tol=0.02):
    if a is None or b is None:
        return False
    if isinstance(b, int) or (isinstance(b, float) and b.is_integer() and isinstance(a, int)):
        return round(a) == b
    return abs(a - b) <= tol * abs(b) + 1e-9


def q_sum(els, key_suffixes):
    tot, n = 0.0, 0
    for e in els:
        v = None
        for k, val in e.qto.items():
            if any(k.endswith(s) for s in key_suffixes):
                v = val
                break
        if v is not None:
            tot += v
            n += 1
    return tot if n else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--show", type=int, default=3)
    a = ap.parse_args()
    qs = [q for q in load_split(a.split) if source_of(q.path) == "ifc_models"]
    stats = collections.defaultdict(collections.Counter)
    shown = collections.Counter()
    for q in qs:
        model = ifc_model_for(q.path)
        idx = load_index(model)
        it = parse(q.question)
        key = f"{it.metric}/{it.kind}/{it.scope}{'/side' if it.side_area else ''}"
        cands = {}
        st = None
        if it.scope in ("storey", "room") and it.names:
            m = match_storey(idx, it.names[-1])
            st = m.obj if m else None
            if st is None:
                stats[key]["storey-unresolved"] += 1
        if it.metric == "area" and it.scope == "room":
            ms = match_space(idx, it.names[0], st.guid if st else None)
            if ms:
                e = ms[0].obj
                cands["geo.footprint"] = e.geo.footprint_area if e.geo else None
                for k, v in e.qto.items():
                    cands["q:" + k.split(".", 1)[1] if "Qto" in k else "p:" + k] = v
            else:
                stats[key]["room-unresolved"] += 1
        elif it.scope == "model" and it.metric == "count":
            els = idx.by_class(*it.classes)
            cands["all"] = len(els)
            cands["no-parent"] = len([e for e in els if not e.parent])
            cands["with-storey"] = len([e for e in els if e.storey])
            cands["with-geo"] = len([e for e in els if e.geo is not None])
            mm = match_model(idx, it.names[0]) if it.names else None
            if not mm:
                stats[key]["model-name-unmatched"] += 1
        elif st is not None:
            els = idx.in_storey(st.guid, *it.classes)
            if it.metric == "count":
                cands["all"] = len(els)
                cands["no-parent"] = len([e for e in els if not e.parent])
                cands["with-geo"] = len([e for e in els if e.geo is not None])
                if it.kind == "wall":
                    cands["walls+cw"] = len(els) + len(idx.in_storey(st.guid, "IfcCurtainWall"))
            elif it.metric == "area" and it.kind == "space":
                cands["geo.footprint"] = sum((e.geo.footprint_area or 0) for e in els if e.geo)
                cands["q.NetFloorArea"] = q_sum(els, (".NetFloorArea",))
                cands["q.GrossFloorArea"] = q_sum(els, (".GrossFloorArea",))
            elif it.metric == "area" and it.side_area:
                cands["q.NetSideArea"] = q_sum(els, ("Quantities.NetSideArea",))
                cands["q.GrossSideArea"] = q_sum(els, ("Quantities.GrossSideArea",))
                cands["geo.lateral/2"] = sum((e.geo.lateral_area or 0) for e in els if e.geo) / 2
            elif it.metric == "volume":
                cands["q.NetVolume"] = q_sum(els, ("Quantities.NetVolume",))
                cands["q.GrossVolume"] = q_sum(els, ("Quantities.GrossVolume",))
                cands["geo.volume"] = sum((e.geo.volume or 0) for e in els if e.geo)
            elif it.metric == "length":
                cands["q.Length"] = q_sum(els, ("Quantities.Length",))
                cands["geo.bbox-long"] = sum(max(e.geo.bbox[3] - e.geo.bbox[0], e.geo.bbox[4] - e.geo.bbox[1])
                                             for e in els if e.geo and e.geo.bbox)
        stats[key]["n"] += 1
        hit = [k for k, v in cands.items() if close(v, q.answer)]
        for k in hit:
            stats[key]["hit:" + k] += 1
        if not hit and shown[key] < a.show:
            shown[key] += 1
            print(f"MISS [{key}] {model.split('/')[-1]} | {q.question} | gold={q.answer} | "
                  f"storey={getattr(st, 'name', None)} | " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                                                                  for k, v in list(cands.items())[:12]))
    for key, c in sorted(stats.items(), key=lambda x: -x[1]["n"]):
        n = c.pop("n")
        print(f"\n{key}: n={n}")
        for k, v in c.most_common(10):
            print(f"   {k}: {v} ({v / n:.0%})")


if __name__ == "__main__":
    sys.exit(main())
