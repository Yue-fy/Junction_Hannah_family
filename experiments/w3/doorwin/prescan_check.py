"""Does windows.prescan (scale-free, before the text layer) drop any Swiss floor the full window path answers?
Reads a raster eval run on artifacts/W3/swiss_png_windows_dev.jsonl (twins=0) and re-checks every answered floor;
also counts how many clean CubiCasa-style uploads (Q's uploads_dev) the pre-scan skips. CPU only, 0 tokens.
Usage: python experiments/w3/doorwin/prescan_check.py <run.jsonl>"""
import glob
import json
import os
import sys
import time

from stoa.solvers.raster import windows as WS

SH = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
D = os.environ["STOA_DATA"]
rows = [json.loads(line) for line in open(sys.argv[1])]
lost = kept = skipped_unanswered = 0
t = time.time()
for r in rows:
    p = r["path"] if r["path"].startswith("/") else os.path.join(D, r["path"])
    ok = WS.prescan(p)
    answered = r.get("value") is not None and r.get("solver") == "raster"
    if answered and not ok:
        lost += 1
        print("LOST", r["path"], r.get("value"), r.get("gold"), r.get("correct"))
    elif answered:
        kept += 1
    elif not ok:
        skipped_unanswered += 1
print(f"swiss: answered kept {kept}, lost {lost}; unanswered now skipped before the text layer {skipped_unanswered}; "
      f"{(time.time() - t) / max(1, len(rows)):.2f} s/floor")
ups = sorted(glob.glob(f"{SH}/artifacts/Q/redteam/img/uploads_dev/*/plan.png"))
clean = [p for p in ups if WS.clean_render(p)[0]]
skip = sum(not WS.prescan(p) for p in clean)
print(f"uploads_dev: {len(ups)} images, {len(clean)} clean renders, pre-scan skips {skip} of them")
