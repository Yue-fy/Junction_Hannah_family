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

Beyond the templates (all deterministic unless noted):
- per-apartment scope: "How many windows in apartment B?" → objects inside / touching (doors, windows ±0.3 m)
  the UNIT_OUTLINE that holds "Whg. B"; "rooms labelled X in apartment C" likewise.
- "including balconies" → outdoor rooms included; "gross area" → apartment outline area, confidence 0.25, with
  the missing wall data stated (the DXF has no gross area). Careful: Swiss German "wie gross" = "how large".
- cross-checks (linked data): label/apartment counts vs. the PDF text layer (each DXF TEXT is one PDF span;
  187/187 agree on dev), room areas vs. the printed "m²" label. ✓/✗ goes to the trace; ✗ lowers confidence.
- **table-QA fallback** (local LLM, `tableqa.py`): when `qparse.covered()` says the rules miss part of the
  question (which/average/yes-no/with-without/…; 0 false flags on 31k swiss questions), the floor becomes
  three tables (rooms, objects, apartments), the LLM writes pandas, we run it in a restricted namespace and
  the rooms it used become evidence. Typed-in numbers are rejected and retried. Derived-gold check:
  `experiments/w2/fallback_eval.py` → 24/24 (avg area per label, which apartment is larger, is there an X).

Experiments behind the rules: `experiments/w2/` (area_misses.py, unnamed_rooms.py, unnamed_inside.py,
unnamed_rule.py) and R1's `experiments/r1/swiss_area_def/`.

## `schedule` (opening_design and other vector PDF sheets with tables)

```bash
AGENT_ID=W2 $JUNCTION_VENV/bin/python -m stoa.eval --solver schedule --split dev --source opening_design
# --solver-arg backend=nvidia  -> hosted Nemotron 120B instead of local Qwen3-VL-8B
```
`pdftables.py` rebuilds tables from the text layer (PyMuPDF `find_tables` finds nothing on these rotated sheets
and takes 46–75 s): words → visual space (rotation_matrix) → rows by y → cells by x-gap → tables = runs of rows
whose key cell starts at the same x → columns by x-centre clusters → header from the rows above (data-like rows
pulled back into the table) → fragments of one schedule merged. Legends/notes (short rows) become a `notes`
table. `tableqa.ask` then writes pandas over them; evidence = boxes of the rows used (pdf_pt in PyMuPDF word space,
i.e. unrotated page space).

| run (dev, 61 Qs, 46 scored) | scored acc | notes |
|---|---|---|
| v0 | 67.4% | model types numbers it "read"; Count column is text |
| v2 local Qwen3-VL-8B | 78.3% | literal answers rejected, quantity columns typed, retry on empty result |
| v3 backend=nvidia | 82.6% | +2 questions, similar est. cost; not adopted as default |
| v4 local (+notes table) | 76.1% | two-part / "what does F4 mean" text answers improve; counts within noise |

Questions about symbols *drawn* on a plan (A-701 restrooms) are not schedule questions: the solver answers with
confidence ≤ 0.15 and says what is missing, so the pipeline escalates.
