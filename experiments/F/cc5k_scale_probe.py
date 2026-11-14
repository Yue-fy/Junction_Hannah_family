"""Probe: does upscaling small cubicasa PNGs (and/or a smaller morphology kernel) fix the CC5K detector's undercount?

Read-only use of R1's model code (experiments/r1/cc5k_model: net, predict.boxes, config.FROZEN); nothing of R1's is
edited. Per image and per upscale factor, one CPU forward pass; then counts for every template under kernel k in
{0, 3, 5} (FROZEN uses 5 for windows/WC/sinks, 0 for doors), min_area as in FROZEN (relative to H*W, scale-free).
Needs a python with torch (e.g. /data/User/fangy4/envs/junction-train/bin/python).

<torch-python> experiments/F/cc5k_scale_probe.py GOLD.json OUT.jsonl SHARD NSHARDS
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "r1", "cc5k_model"))
import numpy as np, torch, torch.nn.functional as F
from PIL import Image
import predict  # R1's module (model(), boxes())
from config import FROZEN

DATA = os.environ["STOA_DATA"]
gold_f, out_f, shard, nsh = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
gold = json.load(open(gold_f))
paths = sorted(gold)[shard::nsh]
FACTORS = [1.0, 1.5, 2.0]
with open(out_f, "a") as fh:
    for p in paths:
        pil0 = Image.open(os.path.join(DATA, p)).convert("RGB")
        rec = {"path": p, "size": list(pil0.size), "gold": gold[p], "counts": {}}
        for f in FACTORS:
            t0 = time.time()
            pil = pil0 if f == 1.0 else pil0.resize((round(pil0.size[0] * f), round(pil0.size[1] * f)), Image.LANCZOS)
            im = np.asarray(pil, np.float32)
            x = torch.from_numpy(2 * (im / 255.0) - 1).permute(2, 0, 1)[None]
            with torch.no_grad():
                y = predict.model()(x)[:, 21:]
                y = F.interpolate(y, size=im.shape[:2], mode="bilinear", align_corners=True)[0]
            icons = y[12:].argmax(0).numpy().astype(np.uint8)
            H, W = icons.shape
            for t, (cls, mf, k0) in FROZEN.items():
                for k in (0, 3, 5, 7):
                    n = sum(len(predict.boxes(icons == c, max(1, mf * H * W), k)) for c in cls)
                    rec["counts"][f"{t}|{f}|{k}"] = n
            rec[f"sec|{f}"] = round(time.time() - t0, 1)
        fh.write(json.dumps(rec) + "\n"); fh.flush()
