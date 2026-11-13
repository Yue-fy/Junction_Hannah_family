"""Tiny stdlib DXF reader (LWPOLYLINE + TEXT per layer) so R1 can test area definitions before ezdxf is installed."""
import math


def read_entities(path):
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    pairs = [(lines[i].strip(), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]
    ents, cur, inent = [], None, False
    for code, val in pairs:
        if code == "2" and val == "ENTITIES":
            inent = True
            continue
        if not inent:
            continue
        if code == "0":
            if cur:
                ents.append(cur)
            cur = {"type": val, "layer": None, "x": [], "y": [], "text": None, "closed": 0, "r": None, "a": []}
            if val == "ENDSEC":
                inent, cur = False, None
            continue
        if cur is None:
            continue
        if code == "8":
            cur["layer"] = val
        elif code == "10":
            cur["x"].append(float(val))
        elif code == "20":
            cur["y"].append(float(val))
        elif code == "40" and cur["type"] in ("ARC", "CIRCLE"):
            cur["r"] = float(val)
        elif code in ("50", "51") and cur["type"] == "ARC":
            cur["a"].append(float(val))
        elif code == "1":
            cur["text"] = val
        elif code == "70" and cur["type"] == "LWPOLYLINE":
            cur["closed"] = int(val)
    return ents


def shoelace(xs, ys):
    n = len(xs)
    return abs(sum(xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i] for i in range(n))) / 2


def pip(x, y, xs, ys):
    inside, n, j = False, len(xs), len(xs) - 1
    for i in range(n):
        if (ys[i] > y) != (ys[j] > y) and x < (xs[j] - xs[i]) * (y - ys[i]) / (ys[j] - ys[i]) + xs[i]:
            inside = not inside
        j = i
    return inside
