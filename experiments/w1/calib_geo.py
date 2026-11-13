"""Calibrate geometry fallbacks for wall length / side area against Qto on models that have both.
PYTHONPATH=$PWD python experiments/w1/calib_geo.py  (reads artifacts/W1/index_all.jsonl for the model list)"""
import json, collections
from shapely.geometry import Polygon, MultiPolygon
from stoa.solvers.ifc.index import load_index
from stoa.solvers.ifc.solver import QTO_KEYS, _qto

rows = [json.loads(l) for l in open('/home/fangy4/work/projects/junction-shared/artifacts/W1/index_all.jsonl')]
models = [r['path'] for r in rows if 'error' not in r and (r.get('wall_length_qto') or r.get('wall_side_qto'))]
hit = collections.Counter(); tot = collections.Counter()


def obb(e):
    if not e.geo or not e.geo.footprint:
        return None
    polys = [Polygon(r) for r in e.geo.footprint if len(r) >= 3]
    if not polys:
        return None
    g = MultiPolygon(polys) if len(polys) > 1 else polys[0]
    r = g.minimum_rotated_rectangle
    xs = list(r.exterior.coords)
    import math
    a = math.dist(xs[0], xs[1]); b = math.dist(xs[1], xs[2])
    return max(a, b), min(a, b), g.area


def ok(a, b):
    return a is not None and b and abs(a - b) <= 0.02 * abs(b)


for m in models:
    idx = load_index(m)
    for e in idx.by_class('IfcWall', 'IfcWallStandardCase'):
        L = _qto(e, QTO_KEYS[('length', 'net')]); S = _qto(e, QTO_KEYS[('side', 'net')]); V = _qto(e, QTO_KEYS[('volume', 'net')])
        o = obb(e)
        if o is None or not e.geo:
            continue
        lng, wid, fpa = o
        h = e.geo.bbox[5] - e.geo.bbox[2]
        if L:
            tot['len'] += 1
            hit['len obb_long'] += ok(lng, L)
            hit['len fp_area/width'] += ok(fpa / wid if wid > 1e-3 else None, L)
            hit['len obb_long-width'] += ok(lng - wid, L)
        if S:
            tot['side'] += 1
            hit['side vol/width'] += ok(e.geo.volume / wid if wid > 1e-3 else None, S)
            hit['side lateral/2'] += ok(e.geo.lateral_area / 2, S)
            hit['side obb_long*h'] += ok(lng * h, S)
            hit['side (lateral - 2*wid*h)/2'] += ok((e.geo.lateral_area - 2 * wid * h) / 2, S)
            hit['side fp_len*h - ?'] += ok((fpa / wid) * h if wid > 1e-3 else None, S)
for k, v in sorted(hit.items()):
    t = tot[k.split()[0]]
    print(f"{k:32s} {v}/{t} = {v / t:.0%}")
