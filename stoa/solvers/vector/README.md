# stoa/solvers/vector — vector drawings (owner: W2)

## `dxf` (swiss_dwellings)
Answers swiss_dwellings questions (asked on .pdf, .png or .dxf) from the sibling DXF, no model, ~0.2 s/question.

```bash
AGENT_ID=W2 $JUNCTION_VENV/bin/python -m stoa.eval --solver dxf --split dev --source swiss_dwellings
```

| split (v2, f43c5369) | count | area | notes |
|---|---|---|---|
| smoke | 100% (40) | 100% (40) | |
| dev | 100% (400) | 97.5% (400) | all area misses overshoot: unnamed numbered rooms |
| hard (swiss) | 100% (150) | 98.3% (120) | compositions, paraphrases, ft², translations |

Pipeline: `qparse.parse` (EN/DE/FR/IT keywords; labels grounded in the floor's own ROOM_TEXT vocabulary) →
`Query(terms, op)` → `floor.load_floor` (rules below) → combine (sum / diff / max / min) → evidence boxes mapped
DXF → PDF points (`pdfmap.fit_transform`, least squares on shared text, rms ≈ 0.05 pt) → PNG px (×png_w/page_w).

Rules (measured on train floors):
- doors = 5-vertex DOOR LWPOLYLINE (leaf); evidence box = leaf ∪ its swing arc.
- windows = WINDOW LWPOLYLINEs / 3; touching boxes clustered, runs of 3 along a wall split into windows.
- bathtub = 69-vertex FIXTURE polyline; shower = 5-vertex; toilet/washbasin = 48-vertex ellipse,
  **washbasin iff a small drain CIRCLE (r < 0.05 m) lies inside it**.
- apartments = "Whg. X"/"App. X" labels; apartment rooms = room label point inside the UNIT_OUTLINE with that label.
- room area = ROOM_OUTLINE polygon containing the number text (innermost polygon); cross-checked against the
  printed "12.05 m²" in the same room (✓/✗ in the evidence note); if they disagree, the printed value wins.
- totals = numbered rooms minus outdoor names (Balkon/Balcon/Loggia/Terrasse/…) and shafts.
  Known limit: the reference sometimes drops numbered rooms *without a name* (train: 96% within 2%); these
  are listed in `assumptions` with the total without them, and confidence drops to 0.8.

Experiments behind the rules: `experiments/w2/` (area_misses.py, unnamed_rooms.py, unnamed_inside.py,
unnamed_rule.py) and R1's `experiments/r1/swiss_area_def/`.
