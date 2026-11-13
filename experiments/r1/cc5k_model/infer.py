"""Run the pretrained CubiCasa5K network (our re-implementation in net.py) on cubicasa drawings, on CPU, and
cache per-drawing segmentation maps for counting experiments.

Leak safety (DECISIONS D3): the checkpoint was trained on the ORIGINAL CubiCasa5K train list. Only report
numbers on drawings in the original val/test lists (artifacts/R1/cc5k_split/ours_in_original_{val,test}.txt),
never on drawings in our sealed test split. Tune on `val`, report on `test`.

Cache per drawing (npz, artifacts/R1/cc5k_seg/<stem>.npz): icons (argmax, uint8), rooms (argmax, uint8),
iprob (softmax prob of the argmax icon class, uint8 0..255).
Run: <torch-python> -I infer.py --lists val,test [--tta] [--procs 4 --threads 6]
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
WEIGHTS = os.environ.get("CC5K_WEIGHTS", "/data/User/fangy4/r1_cc5k/model_best_val_loss_var.pkl")
SPLITS = os.path.join(SHARED, "artifacts", "R1", "cc5k_split")
OUT = os.path.join(SHARED, "artifacts", "R1", "cc5k_seg")


def sealed_paths():
    return {json.loads(l)["path"] for l in open(os.path.join(SHARED, "results", "splits", "test.jsonl"))}


def stems(lists):
    sealed = sealed_paths()
    out = []
    for s in lists:
        for line in open(os.path.join(SPLITS, f"ours_in_original_{s}.txt")):
            st = line.strip()
            if st and f"data/cubicasa5k/{st}.png" not in sealed:
                out.append(st)
    return out


_M = None


def _init(threads):
    global _M
    import torch
    sys.path.insert(0, HERE)
    import net
    torch.set_num_threads(threads)
    _M = net.load(WEIGHTS)


def _run(args):
    stem, tta, scale = args
    import torch
    import torch.nn.functional as F
    tag = ("tta_" if tta else "") + (f"s{scale:g}_" if scale != 1 else "")
    dst = os.path.join(OUT, tag + stem + ".npz")
    if os.path.exists(dst):
        return stem, 0.0
    t0 = time.time()
    im = np.asarray(Image.open(os.path.join(DATA, "data", "cubicasa5k", stem + ".png")).convert("RGB"), np.float32)
    x = torch.from_numpy(2 * (im / 255.0) - 1).permute(2, 0, 1)[None]
    H, W = im.shape[:2]
    if scale != 1:
        x = F.interpolate(x, scale_factor=scale, mode="bicubic", align_corners=False).clamp(-1, 1)
    with torch.no_grad():
        acc = 0
        for k in ((0, 1, 2, 3) if tta else (0,)):
            y = _M(torch.rot90(x, k, (2, 3)))
            y = torch.rot90(y[:, 21:], -k, (2, 3))  # rooms + icons only; heatmaps would need channel swaps
            y = F.interpolate(y, size=(H, W), mode="bilinear", align_corners=True)
            acc = acc + torch.cat([F.softmax(y[:, :12], 1), F.softmax(y[:, 12:], 1)], 1)
        p = (acc / (4 if tta else 1))[0]
    rooms = p[:12].argmax(0).numpy().astype(np.uint8)
    ip = p[12:]
    icons = ip.argmax(0).numpy().astype(np.uint8)
    iprob = (ip.max(0).values.numpy() * 255).astype(np.uint8)
    np.savez_compressed(dst, icons=icons, rooms=rooms, iprob=iprob)
    return stem, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lists", default="val,test")
    ap.add_argument("--stems", default="", help="comma list overrides --lists")
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--scale", type=float, default=1.0, help="upscale the input; maps are saved at original size")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    todo = a.stems.split(",") if a.stems else stems(a.lists.split(","))
    if a.limit:
        todo = todo[: a.limit]
    t0, n, secs = time.time(), 0, []
    with mp.get_context("spawn").Pool(a.procs, initializer=_init, initargs=(a.threads,)) as pool:
        for stem, s in pool.imap_unordered(_run, [(s, a.tta, a.scale) for s in todo]):
            n += 1
            if s:
                secs.append(s)
            if n % 25 == 0 or n == len(todo):
                print(f"{n}/{len(todo)} done, {time.time() - t0:.0f}s wall, median {np.median(secs) if secs else 0:.1f}s/img",
                      flush=True)
    print(json.dumps({"n": len(todo), "wall_s": round(time.time() - t0, 1),
                      "cpu_s_per_img_median": float(np.median(secs)) if secs else 0}))


if __name__ == "__main__":
    main()
