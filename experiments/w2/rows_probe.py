import os, sys, pymupdf, statistics
D = os.environ['STOA_DATA'] + '/data/opening_design/'
f = sys.argv[1]
doc = pymupdf.open(D + f); p = doc[0]
M = p.rotation_matrix
ws = []
for w in p.get_text('words'):
    r = pymupdf.Rect(w[:4]) * M
    ws.append((r.x0, r.y0, r.x1, r.y1, w[4]))
h = statistics.median(w[3] - w[1] for w in ws)
print('median h', h, 'n', len(ws))
ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
rows, cur = [], []
for w in ws:
    yc = (w[1] + w[3]) / 2
    if cur and abs(yc - statistics.mean((c[1] + c[3]) / 2 for c in cur)) > 0.4 * h:
        rows.append(cur); cur = []
    cur.append(w)
rows.append(cur)
for r in rows:
    r.sort(key=lambda w: w[0])
    segs, s = [], [r[0]]
    for a, b in zip(r, r[1:]):
        if b[0] - a[2] > 0.6 * h:
            segs.append(s); s = []
        s.append(b)
    segs.append(s)
    y = (r[0][1] + r[0][3]) / 2
    print(f"{y:7.1f} " + " | ".join(f"[{s[0][0]:.0f}]" + " ".join(w[4] for w in s) for s in segs))
