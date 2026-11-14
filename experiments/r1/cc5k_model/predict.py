"""Live CC5K symbol counts for any raster floor plan (for W3's raster solver; runs on CPU, ~1 s per image).

Output JSON per image: {"path", "cpu_seconds", "model", "counts": {template: {"count", "confidence",
"boxes": [[x0, y0, x1, y1], ...] (image px)}}} for templates windows, doors, wc_seats, sinks.
Confidence = P(gold == count | template, count bucket), Laplace-smoothed, fit on CC5K *val* drawings
(calib_plain.json, calib.py). Settings frozen on CC5K val (offline_preds.FROZEN).

Needs torch + numpy + PIL + cv2 (e.g. /data/User/fangy4/envs/junction-train/bin/python).
Run: <torch-python> -I predict.py IMG.png [IMG2.png ...]   → one JSON line per image on stdout
Licence: the weights are CC BY-NC 4.0 (CubiCasa5K). Leak note (DECISIONS D3): the model was trained on the
original CubiCasa5K train list; accuracy is only meaningful on drawings outside it (cc5k_heldout).
"""
import json
import os
import sys
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import net  # noqa: E402

WEIGHTS = os.environ.get("CC5K_WEIGHTS", "/data/User/fangy4/r1_cc5k/model_best_val_loss_var.pkl")
from config import FROZEN, ROOMS_FROZEN, confidence  # noqa: E402
_M = None


def model():
    global _M
    if _M is None:
        torch.set_num_threads(int(os.environ.get("CC5K_THREADS", "6")))
        _M = net.load(WEIGHTS)
    return _M


MAX_SIDE = int(os.environ.get("CC5K_MAX_SIDE", "3000"))  # larger images (e.g. 7572 px ResBIM plans) are resized
RESIZE_TO = int(os.environ.get("CC5K_RESIZE_TO", "2000"))  # to this long side: windows 77% vs IFC on ResBIM


def maps(path):
    """(icons, rooms, scale) argmax maps at the working size; scale = working px / original px."""
    pil = Image.open(path).convert("RGB")
    scale = 1.0
    if max(pil.size) > MAX_SIDE:
        scale = RESIZE_TO / max(pil.size)
        pil = pil.resize((round(pil.size[0] * scale), round(pil.size[1] * scale)), Image.LANCZOS)
    im = np.asarray(pil, np.float32)
    x = torch.from_numpy(2 * (im / 255.0) - 1).permute(2, 0, 1)[None]
    with torch.no_grad():
        y = model()(x)[:, 21:]
        y = F.interpolate(y, size=im.shape[:2], mode="bilinear", align_corners=True)[0]
    return y[12:].argmax(0).numpy().astype(np.uint8), y[:12].argmax(0).numpy().astype(np.uint8), scale


def boxes(mask, min_area, k):
    m = mask.astype(np.uint8)
    if k:
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    return [[int(st[i, 0]), int(st[i, 1]), int(st[i, 0] + st[i, 2]), int(st[i, 1] + st[i, 3])]
            for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= min_area]


def predict(path):
    t0 = time.process_time()
    icons, rooms, sc = maps(path)
    H, W = icons.shape
    orig = lambda bs: [[round(v / sc) for v in b] for b in bs]  # boxes in ORIGINAL image px
    out = {}
    for t, (cls, mf, k) in FROZEN.items():
        bx = orig([b for c in cls for b in boxes(icons == c, max(1, mf * H * W), k)])
        out[t] = {"count": len(bx), "confidence": confidence(t, len(bx)), "boxes": bx}
    room_counts = {t: {"count": len(b), "boxes": orig(b)} for t, (c, mf) in ROOMS_FROZEN.items()
                   for b in [boxes(rooms == c, mf * H * W, 0)]}
    save = os.environ.get("CC5K_SAVE_MAPS")  # optional: room map at ORIGINAL size for raster_scale/scale.py
    if save:
        os.makedirs(save, exist_ok=True)
        size = Image.open(path).size
        r = rooms if sc == 1.0 else cv2.resize(rooms, size, interpolation=cv2.INTER_NEAREST)
        i = icons if sc == 1.0 else cv2.resize(icons, size, interpolation=cv2.INTER_NEAREST)  # room_graph needs both
        np.savez_compressed(os.path.join(save, os.path.splitext(os.path.basename(path))[0] + ".npz"), rooms=r, icons=i)
    return {"path": path, "cpu_seconds": round(time.process_time() - t0, 2),
            "model": "CubiCasa5K multi-task (Kalervo et al. 2019), CC BY-NC 4.0 weights",
            "work_scale": round(sc, 4), "counts": out, "rooms": room_counts}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps(predict(p)), flush=True)
