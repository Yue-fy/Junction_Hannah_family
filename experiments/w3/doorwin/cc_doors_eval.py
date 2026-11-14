"""NEGATIVE (09:33): doorarcs on 40 TRAIN CubiCasa door Qs (one per drawing; list in argv[1]/cc_doors.json).
px/m guessed as max(W,H)/span. Best 7/40 exact vs the prior mode 8/40. Usage: cc_doors_eval.py <dir> <span> <r_lo> <r_hi> <thr>"""
import json, os, sys, collections
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, '/data/User/fangy4/projects/junction-wt/W3')
from PIL import Image
S = sys.argv[1]; span = float(sys.argv[2]); rlo, rhi, thr = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
sel = json.load(open(f'{S}/cc_doors.json'))

def one(s):
    from stoa.solvers.raster import doorarcs as DA
    p = os.path.join(os.environ['STOA_DATA'], s['path'])
    W, H = Image.open(p).size
    ppm = max(W, H) / span
    d = DA.detect(p, ppm, r_m=(rlo, rhi), thr=thr)
    return len(d), int(s['gold'])

with ProcessPoolExecutor(8) as ex:
    res = list(ex.map(one, sel))
ex_ = sum(a == g for a, g in res); w1 = sum(abs(a - g) <= 1 for a, g in res)
err = sorted(a - g for a, g in res)
mode = collections.Counter(g for _, g in res).most_common(1)[0]
print(f'span {span} r {rlo}-{rhi} thr {thr}: exact {ex_}/{len(res)} within1 {w1} median err {err[len(err)//2]:+d}  (mode {mode})', res[:12])
