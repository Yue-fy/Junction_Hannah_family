"""Robustness sweep: index every IFC (ifc_models + ifc_bench), record build time and quantity coverage, and
how well the geometry fallback agrees with Qto where both exist (calibrates the fallback's confidence).

IFC_GEOM_THREADS=4 PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w1/index_all.py LIST OUT.jsonl [--procs 8]
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
import traceback


def stats(path: str) -> dict:
    from stoa.solvers.ifc.index import load_index
    from stoa.solvers.ifc.solver import QTO_KEYS, _qto, IfcSolver

    t = time.perf_counter()
    try:
        idx = load_index(path)
    except Exception as ex:  # noqa: BLE001
        return {"path": path, "error": f"{type(ex).__name__}: {ex}", "tb": traceback.format_exc(limit=2)}
    out = {"path": path, "seconds": round(time.perf_counter() - t, 2), "schema": idx.schema,
           "n_elements": len(idx.elements), "n_storeys": len(idx.storeys)}
    sp = idx.by_class("IfcSpace")
    out["n_spaces"] = len(sp)
    out["spaces_geo"] = sum(1 for e in sp if e.geo and e.geo.footprint_area)
    out["spaces_no_storey"] = sum(1 for e in sp if not e.storey)
    for kind, classes in (("wall", ("IfcWall", "IfcWallStandardCase")), ("slab", ("IfcSlab",))):
        els = idx.by_class(*classes)
        out[f"n_{kind}"] = len(els)
        out[f"{kind}_no_storey"] = sum(1 for e in els if not e.storey)
        for q in (("volume", "net"), ("length", "net"), ("side", "net")):
            if kind == "slab" and q[0] != "volume":
                continue
            agree = n_both = n_q = 0
            for e in els:
                v = _qto(e, QTO_KEYS[q])
                if v is None:
                    continue
                n_q += 1
                g = IfcSolver._geo_value(e, q[0])
                if g is not None and v:
                    n_both += 1
                    agree += abs(g - v) <= 0.02 * abs(v)
            out[f"{kind}_{q[0]}_qto"] = n_q
            out[f"{kind}_{q[0]}_geo_agree"] = f"{agree}/{n_both}"
    return out


def main():
    lst, out = sys.argv[1], sys.argv[2]
    procs = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 8
    paths = [l.strip() for l in open(lst) if l.strip()]
    with mp.get_context("spawn").Pool(procs, maxtasksperchild=4) as pool, open(out, "w") as f:
        for r in pool.imap_unordered(stats, paths):
            f.write(json.dumps(r) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
