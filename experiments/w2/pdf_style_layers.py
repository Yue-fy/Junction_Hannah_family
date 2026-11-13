"""Which PDF drawing style (type, stroke colour, fill, width) renders which DXF layer? (swiss, PDF-only path prep)
Maps every DXF entity bbox to PDF points with the text-anchored fit, then assigns each PDF path to the layer whose
mapped entity bbox matches best (IoU). Prints style -> layer votes over N floors.
Run: PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w2/pdf_style_layers.py [n_floors]
"""
import collections
import os
import sys

import ezdxf
import pymupdf
from ezdxf import bbox as ezbbox

from stoa.solvers.vector.pdfmap import fit_transform

D = os.environ["STOA_DATA"] + "/data/swiss_dwellings/"
n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
stems = sorted(f[:-4] for f in os.listdir(D) if f.endswith(".dxf"))[::97][:n]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else (1.0 if inter == 0 and a == b else 0.0)


votes = collections.defaultdict(collections.Counter)
for st in stems:
    tf = fit_transform(D + st + ".pdf", D + st + ".dxf")
    if tf is None:
        continue
    ents = []
    for e in ezdxf.readfile(D + st + ".dxf").modelspace():
        try:
            b = ezbbox.extents([e])
        except Exception:
            continue
        if not b.has_data:
            continue
        ents.append((f"{e.dxf.layer}:{e.dxftype()}", tf.box((b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y))))
    page = pymupdf.open(D + st + ".pdf")[0]
    for d in page.get_drawings():
        r = d["rect"]
        pb = (r.x0, r.y0, r.x1, r.y1)
        style = (d["type"], tuple(round(x, 2) for x in (d.get("color") or ())), tuple(round(x, 2) for x in (d.get("fill") or ())),
                 round(d.get("width") or 0, 2))
        best = max(ents, key=lambda le: iou(pb, le[1]), default=None)
        lab = best[0] if best and iou(pb, best[1]) > 0.5 else "<none>"
        votes[style][lab] += 1
for style, c in sorted(votes.items(), key=lambda kv: -sum(kv[1].values())):
    print(sum(c.values()), style, c.most_common(3))
