import sys, glob, os, json, time, statistics
sys.path.insert(0, ".")
from stoa.solvers import get_solver
s = get_solver("ifc")
files = sorted(glob.glob(os.environ["STOA_DATA"] + "/data/ifc_models/*.ifc"))
# one per project: skip near-duplicate copies (same stem prefix)
seen, pick = set(), []
for f in files:
    stem = os.path.basename(f).rsplit("_", 1)[0] if "_" in os.path.basename(f) else os.path.basename(f)
    if stem in seen: continue
    seen.add(stem); pick.append(f)
out, t0 = [], time.time()
for f in pick:
    if time.time() - t0 > 150: break
    try:
        w = s.solve(f, "What is the total net side area of all walls in the model?")
        a = s.solve(f, "What is the total floor area of all spaces in the model?")
    except Exception as ex:
        continue
    if isinstance(w.value, (int, float)) and isinstance(a.value, (int, float)) and a.value > 20 and w.value > 0:
        out.append((os.path.basename(f), round(w.value, 1), round(a.value, 1), round(w.value / a.value, 2), w.confidence, a.confidence))
for r in out: print(r)
rs = [r[3] for r in out]
if rs: print("n", len(rs), "median ratio", statistics.median(rs), "q25/q75", statistics.quantiles(rs, n=4)[0], statistics.quantiles(rs, n=4)[2])
print("files tried", len(pick), "time", round(time.time() - t0))
