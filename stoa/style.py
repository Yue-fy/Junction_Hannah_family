"""Drawing-style guess from image CONTENT (not the folder): which of our raster readers fits an unknown image (R2).

W5 09:21: the CubiCasa readers (LoRA cc-v2 gate, raster_cc5k) are gated on stoa.data.source_of(path), i.e. the folder;
the same plan uploaded from elsewhere (or a hidden-set file in a new folder) loses them. guess_style(path) returns
("cubicasa5k" | "swiss_dwellings" | "ifc_models" | "scan", prob) from cheap image features (no model call, ~0.1 s).
Features avoid dataset artifacts (file mode, pixel size): the image is flattened on white and thumbnailed first.
Train/eval: python experiments/r2/style/style.py --train   (weights -> stoa/style_weights.json)
Runtime only here (numpy + PIL); the training code lives in experiments/r2/style/style.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

CLASSES = ["cubicasa5k", "swiss_dwellings", "ifc_models", "scan"]
SCANS = ("habs", "finna", "europeana", "wikimedia")
WEIGHTS = Path(__file__).with_name("style_weights.json")
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
