"""Drawing-style guess from image CONTENT (not the folder): which of our raster readers fits an unknown image.

W5 09:21: the CubiCasa readers (LoRA cc-v2 gate, raster_cc5k) are gated on stoa.data.source_of(path), i.e. the folder;
the same plan uploaded from elsewhere (or a hidden-set file in a new folder) loses them. guess_style(path) returns
("cubicasa5k" | "swiss_dwellings" | "ifc_models" | "scan", prob) from cheap image features (no model call, ~0.1 s).
Features avoid dataset artifacts (file mode, pixel size): the image is flattened on white and thumbnailed first.
Train/eval: python experiments/r2/style/style.py --train   (weights -> experiments/r2/style/weights.json)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

CLASSES = ["cubicasa5k", "swiss_dwellings", "ifc_models", "scan"]
SCANS = ("habs", "finna", "europeana", "wikimedia")
WEIGHTS = Path(__file__).with_name("weights.json")
Image.MAX_IMAGE_PIXELS = None


def _load(img_or_path) -> Image.Image:
    im = img_or_path if isinstance(img_or_path, Image.Image) else Image.open(img_or_path)
    im.draft("RGB", (512, 512))  # fast JPEG decode at reduced size
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    im = im.convert("RGB")
    im.thumbnail((384, 384), Image.BILINEAR)
    return im


def features(img_or_path) -> np.ndarray:
    im = _load(img_or_path)
    a = np.asarray(im, dtype=np.float32) / 255.0
    g = a.mean(axis=2)
    h, w = g.shape
    f = [min(h, w) / max(h, w)]
    f += list(np.histogram(g, bins=16, range=(0, 1))[0] / g.size)
    hsv = np.asarray(im.convert("HSV"), dtype=np.float32) / 255.0
    sat, hue = hsv[..., 1], hsv[..., 0]
    f += list(np.histogram(sat, bins=8, range=(0, 1))[0] / sat.size)
    f += list(np.histogram(hue, bins=12, range=(0, 1), weights=sat)[0] / (sat.sum() + 1e-6))
    f += [(g > 0.94).mean(), (g < 0.16).mean(), g.std()]
    bright = a[g >= np.median(g)]
    f += list(bright.mean(axis=0)) + [bright[:, 0].mean() - bright[:, 2].mean()]  # paper tone (yellowed scans)
    gx, gy = np.abs(np.diff(g, axis=1)), np.abs(np.diff(g, axis=0))
    ex, ey = (gx > 0.2).mean(), (gy > 0.2).mean()
    f += [ex + ey, ex / (ex + ey + 1e-6), (gx > 0.05).mean() + (gy > 0.05).mean()]
    # long straight runs of dark pixels (plan walls) per row/column
    dark = g < 0.5
    f += [dark.mean(axis=1).max(), dark.mean(axis=0).max(), (dark.mean(axis=1) > 0.3).mean()]
    small = np.asarray(ImageOps.grayscale(im).resize((8, 8), Image.BILINEAR), dtype=np.float32).ravel() / 255.0
    f += list(small)
    # paper texture: scans have a noisy, non-white background and many mid tones; digital plans are flat
    bg = g[g >= np.quantile(g, 0.6)]
    bg = bg if bg.size > 1 else g.ravel()
    f += [bg.std(), ((g > 0.3) & (g < 0.85)).mean(), len(np.unique((g * 63).astype(np.int32))) / 64.0,
          np.abs(np.diff(g[:, ::4], axis=0)).mean()]
    return np.nan_to_num(np.asarray(f, dtype=np.float32))


_W = None


def guess_style(img_or_path) -> tuple[str, float]:
    """(style, probability). Cheap; meant for files whose folder is not a known source."""
    global _W
    if _W is None:
        d = json.loads(WEIGHTS.read_text())
        _W = (np.asarray(d["mu"]), np.asarray(d["sd"]), np.asarray(d["W"]), np.asarray(d["b"]), d["classes"])
    mu, sd, W, b, classes = _W
    x = (features(img_or_path) - mu) / sd
    z = x @ W + b
    p = np.exp(z - z.max())
    p /= p.sum()
    i = int(p.argmax())
    return classes[i], float(p[i])


# ------------------------------------------------------------------------------------------------- training
def _group(path: str) -> str:
    name = Path(path).name
    src = Path(path).parent.name
    if src == "swiss_dwellings":
        return src + name.split("_")[0]          # site
    if src == "ifc_models":
        return src + name.split("_")[0]          # model
    if src == "habs":
        return src + name.split("_")[0]          # building
    if src == "cubicasa5k":
        return src + name
    return src + name


def _is_test(path: str) -> bool:
    return int(hashlib.md5(_group(path).encode()).hexdigest(), 16) % 10 < 3


def _label(path: str) -> str:
    src = Path(path).parent.name
    return "scan" if src in SCANS else src


def _files(root: Path, per_class: int, seed: int = 0):
    import random

    rng = random.Random(seed)
    out = []
    for src in ["cubicasa5k", "swiss_dwellings", "ifc_models", *SCANS]:
        fs = sorted([*root.glob(f"data/{src}/*.png"), *root.glob(f"data/{src}/*.jpg")])
        rng.shuffle(fs)
        n = per_class // (len(SCANS) if src in SCANS else 1)
        out += [str(f) for f in fs[: n * 2]]
    return out


def _augment(path: str, k: int) -> Image.Image:
    """Upload-like variants: grayscale, JPEG re-encode, crop, downscale."""
    import io

    im = _load(path)
    if k == 1:
        im = ImageOps.grayscale(im).convert("RGB")
    elif k == 2:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=40)
        im = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    elif k == 3:
        w, h = im.size
        im = im.crop((int(w * 0.1), int(h * 0.1), int(w * 0.85), int(h * 0.9)))
    elif k == 4:
        im = im.resize((max(1, im.size[0] // 3), max(1, im.size[1] // 3)), Image.BILINEAR)
    return im


def _feat_aug(fk):
    return features(_augment(*fk))


def train(per_class: int = 600):
    from concurrent.futures import ProcessPoolExecutor

    root = Path("/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
    files = _files(root, per_class)
    te0 = np.asarray([_is_test(f) for f in files])
    # training rows = every image + one upload-like variant of each TRAIN image (grayscale / JPEG / crop / downscale)
    aug = [(f, 1 + i % 4) for i, f in enumerate(files) if not _is_test(f)]
    with ProcessPoolExecutor(24) as ex:
        X = np.stack(list(ex.map(features, files, chunksize=8)))
        Xa = np.stack(list(ex.map(_feat_aug, aug, chunksize=8)))
    y = np.asarray([CLASSES.index(_label(f)) for f in files] + [CLASSES.index(_label(f)) for f, _ in aug])
    X = np.concatenate([X, Xa])
    te = np.concatenate([te0, np.zeros(len(aug), dtype=bool)])
    files = files + [f for f, _ in aug]
    mu, sd = X[~te].mean(0), X[~te].std(0) + 1e-6
    Xs = (X - mu) / sd
    rng = np.random.default_rng(0)
    W = rng.normal(0, 0.01, (X.shape[1], len(CLASSES)))
    b = np.zeros(len(CLASSES))
    Xtr, ytr = Xs[~te], y[~te]
    cw = np.bincount(ytr, minlength=len(CLASSES))
    sw = (len(ytr) / (len(CLASSES) * cw))[ytr]
    Y = np.eye(len(CLASSES))[ytr]
    for it in range(3000):
        z = Xtr @ W + b
        p = np.exp(z - z.max(1, keepdims=True))
        p /= p.sum(1, keepdims=True)
        gz = (p - Y) * sw[:, None] / len(ytr)
        W -= 0.5 * (Xtr.T @ gz + 1e-3 * W)
        b -= 0.5 * gz.sum(0)

    def acc(Xe, ye):
        pr = (Xe @ W + b).argmax(1)
        return (pr == ye).mean(), np.asarray([[int(((ye == i) & (pr == j)).sum()) for j in range(len(CLASSES))]
                                              for i in range(len(CLASSES))])

    a_tr, _ = acc(Xtr, ytr)
    a_te, cm = acc(Xs[te], y[te])
    print(f"n={len(files)} train {(~te).sum()} acc {a_tr:.3f} | held-out groups {te.sum()} acc {a_te:.3f}")
    print("confusion (rows true, cols pred)", CLASSES)
    print(cm)
    test_files = [f for f, t in zip(files, te) if t]
    for k, name in [(1, "grayscale"), (2, "jpeg q40"), (3, "crop"), (4, "downscale /3")]:
        with ProcessPoolExecutor(24) as ex:
            Xa = np.stack(list(ex.map(_feat_aug, [(f, k) for f in test_files], chunksize=8)))
        ya = np.asarray([CLASSES.index(_label(f)) for f in test_files])
        a, cm = acc((Xa - mu) / sd, ya)
        print(f"held-out, {name}: acc {a:.3f}; per class", [f"{CLASSES[i][:5]} {cm[i, i]}/{cm[i].sum()}" for i in range(4)])
    WEIGHTS.write_text(json.dumps({"classes": CLASSES, "mu": mu.tolist(), "sd": sd.tolist(), "W": W.tolist(),
                                   "b": b.tolist(), "n_train": int((~te).sum()), "heldout_acc": float(a_te)}))
    print("wrote", WEIGHTS)


if __name__ == "__main__":
    if "--train" in sys.argv:
        train()
    else:
        for p in sys.argv[1:]:
            print(p, guess_style(p))
