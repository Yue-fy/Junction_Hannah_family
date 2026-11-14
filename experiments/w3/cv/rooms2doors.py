"""Offline: do door/window counts follow from the room labels already read per drawing? (TRAIN only)

    PYTHONPATH=$PWD $JUNCTION_VENV/bin/python experiments/w3/cv/rooms2doors.py
Reads artifacts/W3/calib/labels-train200.jsonl (R1 v2 label outputs on 200 TRAIN drawings).
"""
import collections, json, os, re, random
from pathlib import Path
SHARED = Path(os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared"))
ROOMISH = {"OH","K","KK","KT","TK","MH","KH","PH","PESUH","SH","S","WC","VH","ET","AH","VAR","TEKN","KHH","PARV",
           "PARVEKE","LASPI","TERASSI","TER","RT","ALK","WC/KH","KPH","TUPA","TOIMISTO","PUKUH","LH","LO","PS","PSH",
           "KUISTI","EHJ","HUONE","VAATEH","IV","TK","TKH","K+OH","OH+K","MH1","MH2","MH3","KEITTIÖ","OLOH","MAKUUH",
           "TAKKAH","AULA","EK","PK","TUULIK","VAR.","SAUNA","PESUHUONE","KYLPYH","KELLARI","AUTOK","AT","VH/KHH",
           "KODINH","KODINHOITOH","KHH/WC","ULKOVAR","TUPAK","HALLI","HUOLTO","EKSP","KIRJASTO","TOIM","PESU","LAPSI"}
def norm(t): return re.sub(r"[^A-ZÄÖ/+.]", "", t.upper()).replace("Ä","A").replace("Ö","O")
rows=[json.loads(l) for l in open(SHARED/"artifacts/W3/calib/labels-train200.jsonl")]
from stoa.solvers.raster.classes import label_classes, type_code
feat=[]
for r in rows:
    g=r["gold"]
    if "door" not in g or "window" not in g: continue
    items=r.get("items") or []
    texts=[norm(t) for t,*_ in items]
    n_code=sum(1 for t,*_ in items if label_classes(t) and not type_code(t))
    n_room=sum(1 for t in texts if t.rstrip("0123456789") in ROOMISH or re.sub(r"\d","",t) in ROOMISH)
    n_alpha=sum(1 for t in texts if re.fullmatch(r"[A-Z/+.]{1,8}", t or "-"))
    n_dim=sum(1 for t,*_ in items if re.search(r"\d+[.,]?\d*\s*[xX×]\s*\d+", t))
    feat.append(dict(door=float(g["door"]),window=float(g["window"]),n_code=n_code,n_room=n_room,n_alpha=n_alpha,
                     n_dim=n_dim, n_items=len(items), bed=g.get("bedroom")))
print(len(feat),"drawings")
for tgt in ("door","window"):
    prior=collections.Counter(f[tgt] for f in feat).most_common(1)[0]
    print(f"\n{tgt}: prior {prior[0]} -> {prior[1]/len(feat):.1%}")
    for k in ("n_code","n_room","n_alpha","n_items"):
        # best offset c in pred = x + c, 2-fold to be honest
        random.Random(0).shuffle(feat); half=len(feat)//2
        accs=[]
        for tr,te in ((feat[:half],feat[half:]),(feat[half:],feat[:half])):
            best=max(range(-3,8),key=lambda c: sum(f[tgt]==f[k]+c for f in tr))
            accs.append(sum(f[tgt]==f[k]+best for f in te)/len(te))
        within1=None
        print(f"  {tgt} = {k}+c : 2-fold acc {sum(accs)/2:.1%}")
    import statistics
    print("  corr-ish: mean gold", statistics.mean(f[tgt] for f in feat), "n_room mean", statistics.mean(f['n_room'] for f in feat))
print("drawings with >=2 dimension strings NxM:", sum(f['n_dim']>=2 for f in feat))
