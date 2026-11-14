"""Slide chart, no dependencies: confidently-wrong red-team answers per round, stacked by question family.
Writes demo/redteam-rounds.svg (render to PNG with headless chromium, see REPORT 'Re-run'). Counts: an answer at
conf >= 0.8 that is wrong, or any answer at >= 0.8 to a false-premise/unanswerable row, over the runs in REPORT.md.
Palette: dataviz reference categorical slots 1-5, validated (light); every segment carries its value (relief rule)."""
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dc"
SER = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#e34948", "#6250d6"]
FAMS = ["v1–v2 noise, injection, images, false premises (205 Qs)", "v3–v4 “A and B in total”, 11 languages (78)",
        "v5 everyday storey &amp; room words (70)", "v6–v8 judge questions, “whole building”, 7th floor (65)",
        "v9–v10 Finnish judge, scan follow-ups (22)", "v11 number formats: “1,200 euros”, “1'200 CHF” (10)",
        "v12–v13 Estonian room labels, the plan without its DXF (13)", "v14–v15 two-part questions, comparisons, storey heights (53)"]
SIZES = [205, 78, 70, 65, 22, 10, 13, 53]
ROUNDS = [("04:15", "0589ce3"), ("04:19", "58073d5"), ("04:33", "W4 fix"), ("04:41", "cc1ca5b"), ("04:46", "dde6347"),
          ("04:59", "753eccb"), ("05:05", "+W1/W2/W4"), ("05:12", "+W1 basement"),
          ("08:16", "bb94fe4 = test 2"), ("08:27", "+W1/W3/W4/R2")]
ASKED = {8: 494}  # rounds that asked only part of a family (08:16: v14 without v15)
DATA = [[8, None, None, None, None, None, None, None], [7, None, None, None, None, None, None, None],
        [2, None, None, None, None, None, None, None], [2, 2, None, None, None, None, None, None],
        [0, 0, 18, None, None, None, None, None], [0, 0, 11, 9, None, None, None, None], [0, 0, 6, 9, 0, None, None, None],
        [0, 0, 1, 6, 0, 2, None, None], [0, 0, 1, 6, 0, 2, 0, 3], [0, 0, 0, 3, 0, 0, 0, 8]]
W, H = 1100, 600
L, R, T, B = 70, 30, 200, 90          # plot margins
YMAX = 24
pw, ph = W - L - R, H - T - B
y = lambda v: T + ph - v / YMAX * ph
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     f'font-family="Inter, Helvetica, Arial, sans-serif">', f'<rect width="{W}" height="{H}" fill="{SURF}"/>',
     f'<text x="{L - 10}" y="40" font-size="24" font-weight="700" fill="{INK}">Red team: confidently wrong answers per round</text>',
     f'<text x="{L - 10}" y="66" font-size="14" fill="{INK2}">Each fix round took the families already asked to 0; each new '
     f'family found the same root cause on a new surface:</text>',
     f'<text x="{L - 10}" y="86" font-size="14" fill="{INK2}">the check verifies the number, not that it answers the storey, '
     f'scope or name that was asked.</text>']
for k, (f, c) in enumerate(zip(FAMS, SER)):  # legend, two columns
    lx, ly = L - 10 + (k % 2) * 520, 112 + (k // 2) * 22
    o.append(f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" rx="2" fill="{c}"/>'
             f'<text x="{lx + 18}" y="{ly}" font-size="13" fill="{INK}">{f}</text>')
for v in range(0, YMAX + 1, 4):  # recessive grid
    o.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>'
             f'<text x="{L - 8}" y="{y(v) + 4:.1f}" font-size="12" fill="{INK2}" text-anchor="end">{v}</text>')
o.append(f'<text x="18" y="{T + ph / 2}" font-size="12" fill="{INK2}" text-anchor="middle" '
         f'transform="rotate(-90 18 {T + ph / 2})">answers wrong at confidence ≥ 0.8</text>')
step = pw / len(ROUNDS)
bw = step * 0.5
for i, (row, (t, c)) in enumerate(zip(DATA, ROUNDS)):
    cx = L + step * (i + 0.5)
    bottom = 0
    for j, v in enumerate(row):
        if not v:
            continue
        y0, y1 = y(bottom), y(bottom + v)
        o.append(f'<rect x="{cx - bw / 2:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{y0 - y1:.1f}" fill="{SER[j]}" '
                 f'stroke="{SURF}" stroke-width="2"/>')
        if v >= 2 and sum(1 for w in row if w) > 1:  # inner labels only where the bar has several segments
            o.append(f'<text x="{cx:.1f}" y="{(y0 + y1) / 2 + 5:.1f}" font-size="13" fill="{INK}" '
                     f'text-anchor="middle">{v}</text>')
        bottom += v
    asked = ASKED.get(i) or sum(n for n, v in zip(SIZES, row) if v is not None)
    o.append(f'<text x="{cx:.1f}" y="{y(bottom) - 8:.1f}" font-size="16" font-weight="700" fill="{INK}" '
             f'text-anchor="middle">{bottom}</text>')
    o.append(f'<text x="{cx:.1f}" y="{T + ph + 22}" font-size="13" fill="{INK}" text-anchor="middle">{t}</text>'
             f'<text x="{cx:.1f}" y="{T + ph + 40}" font-size="12" fill="{INK2}" text-anchor="middle">{c}</text>'
             f'<text x="{cx:.1f}" y="{T + ph + 58}" font-size="11" fill="{INK2}" text-anchor="middle">{asked} Qs asked</text>')
o.append(f'<line x1="{L}" x2="{W - R}" y1="{T + ph}" y2="{T + ph}" stroke="{INK2}" stroke-width="1"/>')
o.append("</svg>")
open("demo/redteam-rounds.svg", "w", encoding="utf-8").write("\n".join(o))
print("demo/redteam-rounds.svg")
