"""Sheet kind (floor plan or not) on hand-labelled scans: text rule (cached text layer, free) vs one VLM call vs both.

    $JUNCTION_VENV/bin/python experiments/w3/sheet_kind_eval.py [--gold artifacts/W3/sheet_kind_gold.jsonl]
Gold: artifacts/W3/sheet_kind_gold.jsonl (has_plan by eye from thumbnails, written before any run; null = ambiguous).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.llm import cost_meter  # noqa: E402
from stoa.solvers.raster import sheet as S  # noqa: E402

SH = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ap = argparse.ArgumentParser()
ap.add_argument("--gold", default=str(SH / "artifacts/W3/sheet_kind_gold.jsonl"))
ap.add_argument("--out", default=str(SH / "artifacts/W3/sheet_kind_eval.jsonl"))
a = ap.parse_args()
rows = [json.loads(line) for line in open(a.gold)]
res = {"text": [], "vlm": [], "both": []}
with open(a.out, "w") as f:
    for r in rows:
        if r["has_plan"] is None:
            continue
        with cost_meter() as cm:
            kt = S.sheet_kind(r["path"], use_vlm=False)
            kb = S.sheet_kind(r["path"], use_vlm=True)
        v = kb.get("vlm") or {}
        v = v or (S.vlm_kinds(r["path"]) or {})
        kv = None if not v else ("floor_plan" in v["views"] or bool(v.get("rooms_visible")))
        for name, pred in (("text", kt["has_plan"]), ("vlm", kv), ("both", kb["has_plan"])):
            res[name].append((r["has_plan"], pred))
        rec = {"path": r["path"], "gold": r["has_plan"], "gold_main": r.get("main"), "text": kt["has_plan"],
               "text_title": (kt["title"] or {}).get("text"), "vlm": v, "both": kb["has_plan"],
               "views": kb["views"], "main": kb["main"], "cost": cm.as_dict()}
        f.write(json.dumps(rec, default=str) + "\n")
        print(f"{r['path'][-44:]:44s} gold={r['has_plan']!s:5s} text={kt['has_plan']!s:5s} vlm={kv!s:5s} "
              f"both={kb['has_plan']!s:5s} main={kb['main']} title={(kt['title'] or {}).get('text', '')[:30]!r}")
for name, pairs in res.items():
    n = len(pairs)
    dec = [(g, p) for g, p in pairs if p is not None]
    ok = sum(g == p for g, p in dec)
    false_veto = sum(g is True and p is False for g, p in pairs)
    missed = sum(g is False and p is not False for g, p in pairs)
    print(f"{name:5s}: decided {len(dec)}/{n}, right {ok}/{len(dec)}; false veto (plan sheet called no-plan) "
          f"{false_veto}/{sum(g for g, _ in pairs)}; no-plan sheets not caught {missed}/{sum(not g for g, _ in pairs)}")
