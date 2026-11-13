"""Offline threshold sweep over raw door candidates (TRAIN): count = #candidates after NMS passing score/inner/r
filters; report exact / within-1 / median ratio per setting.  python experiments/w3/cv/sweep_doors.py <raw.jsonl>"""
import itertools, json, math, sys, statistics, collections

def box(d):
    """Swing box of a door candidate (x, y, r, q, ...): the quarter disc's bounding square."""
    x, y, r, q = d[0], d[1], d[2], d[3]
    sx = 1 if q in (0, 3) else -1
    sy = 1 if q in (0, 1) else -1
    x0, x1 = sorted((x, x + sx * r)); y0, y1 = sorted((y, y + sy * r))
    return x0, y0, x1, y1


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(1e-6, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def nms(c, thr=0.2):
    """Greedy NMS by swing-box IoU (best score first). Returns kept candidates."""
    out = []
    for d in sorted(c, key=lambda d: d[4]):
        b = box(d)
        if all(iou(b, box(o)) <= thr for o in out):
            out.append(d)
    return out


def main():
    rows = [json.loads(l) for l in open(sys.argv[1])]
    prior = collections.Counter(r["gold"] for r in rows).most_common(1)[0]
    print(len(rows), "prior", prior[0], f"{prior[1]/len(rows):.1%}")
    res = []
    for sthr, ithr, rfrac in itertools.product((0.15, 0.25, 0.35, 0.5, 0.7, 1.0, 1.5), (0.1, 0.2, 0.35), (0.022, 0.03, 0.04)):
        preds = []
        for r in rows:
            m = max(r["shape"])
            c = [d for d in r["raw"] if d[4] <= sthr and d[5] <= ithr and d[2] >= rfrac * m]
            preds.append(len(nms(c)))
        ex = sum(p == r["gold"] for p, r in zip(preds, rows)) / len(rows)
        w1 = sum(abs(p - r["gold"]) <= 1 for p, r in zip(preds, rows)) / len(rows)
        ratio = statistics.median(p / max(1, r["gold"]) for p, r in zip(preds, rows))
        res.append((ex, w1, ratio, sthr, ithr, rfrac))
    for x in sorted(res, reverse=True)[:12]:
        print(f"exact {x[0]:.1%} w1 {x[1]:.1%} ratio {x[2]:.2f}  score<={x[3]} inner<={x[4]} r>={x[5]}")


if __name__ == "__main__":
    main()
