"""Windows / fixtures in swiss PDFs: map each PDF path (style + item signature) to the DXF entity it renders
(IoU > 0.5 after the DXF->PDF fit) and print signature -> layer:type:vertices votes. Run with PYTHONPATH=$PWD."""
import collections
import os
import sys

import ezdxf
import pymupdf
from ezdxf import bbox as ezbbox

from stoa.solvers.vector.pdfmap import fit_transform

D = os.environ["STOA_DATA"] + "/data/swiss_dwellings/"
stems = sorted(f[:-4] for f in os.listdir(D) if f.endswith(".dxf"))[3::97][: int(sys.argv[1]) if len(sys.argv) > 1 else 8]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


votes = collections.defaultdict(collections.Counter)
for st in stems:
    tf = fit_transform(D + st + ".pdf", D + st + ".dxf")
    ents = []
    for e in ezdxf.readfile(D + st + ".dxf").modelspace():
        if e.dxf.layer not in ("WINDOW", "FIXTURE"):
            continue
        b = ezbbox.extents([e])
        nv = len(list(e.get_points())) if e.dxftype() == "LWPOLYLINE" else 0
        ents.append((f"{e.dxf.layer}:{e.dxftype()}:{nv}", tf.box((b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y))))
    for d in pymupdf.open(D + st + ".pdf")[0].get_drawings():
        r = d["rect"]
        pb = (r.x0, r.y0, r.x1, r.y1)
        sig = (d["type"], tuple(round(x, 2) for x in (d.get("color") or ())), tuple(round(x, 2) for x in (d.get("fill") or ())),
               round(d.get("width") or 0, 2), "".join(sorted(collections.Counter(i[0] for i in d["items"]).elements()))[:12])
        best = max(ents, key=lambda le: iou(pb, le[1]), default=None)
        if best and iou(pb, best[1]) > 0.5:
            votes[sig][best[0]] += 1
for sig, c in sorted(votes.items(), key=lambda kv: -sum(kv[1].values()))[:20]:
    print(sum(c.values()), sig, c.most_common(4))
