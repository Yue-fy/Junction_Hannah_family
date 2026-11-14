"""Add LoRA-vs-raster agreement rates (train_gate, leak-free for the LoRA) to stoa/router/gating.json.

For each cubicasa key: among train_gate questions, how often vlm_lora is right when raster gives the same count
(agree) and when it does not (disagree). The pipeline uses the smoothed rate as the LoRA answer's confidence and
raster's label boxes as evidence when they agree.   python experiments/w4/lora_agree.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from stoa.eval.splits import shared_root  # noqa: E402
from stoa.router import gating  # noqa: E402
from stoa.router.calibrate import sample  # noqa: E402

C = shared_root() / "artifacts" / "W4" / "calib"
lora = {json.loads(x)["qid"]: json.loads(x) for x in open(C / "vlm_lora.jsonl")}
ras = {json.loads(x)["qid"]: json.loads(x) for x in open(C / "raster.jsonl")}
g = json.loads(gating.GATING_PATH.read_text())
t: dict = {}
for k, q in sample(1000, sources={"cubicasa5k"}, split="train_gate"):
    lo, ra = lora.get(q.qid), ras.get(q.qid)
    if not lo or lo["value"] is None or not ra or ra["value"] is None:
        continue
    try:
        agree = round(float(lo["value"])) == round(float(ra["value"]))
    except (TypeError, ValueError):
        agree = False
    cell = t.setdefault(f"{k[0]}|{k[1]}", {"agree": [0, 0], "disagree": [0, 0]})["agree" if agree else "disagree"]
    cell[0] += bool(lo["correct"])
    cell[1] += 1
for key, v in t.items():
    if key in g["entries"]:
        g["entries"][key]["lora_vs_raster"] = v
        print(key, v)
gating.GATING_PATH.write_text(json.dumps(g, indent=1, sort_keys=True))
