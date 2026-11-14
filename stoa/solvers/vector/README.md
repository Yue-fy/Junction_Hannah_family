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

Reasoning kinds (v5–v10; all deterministic unless noted):
- operators: mean, ratio ("how many times", Faktor, fois, volte, keer, gånger), share in %, threshold counts
  ("rooms over 15 m²", über, plus de, più di, meer dan, mer än), floor total minus an apartment ("not in / ohne /
  sans / senza / niet tot / inte tillhör apartment X"), which-of-two (smaller/larger, kleiner, plus petit, mindre).
- sets: superlatives over rooms ("area of the largest room", "smallest room in apartment B", "la plus grande
  pièce", "la stanza più grande"; unnamed numbered ducts are skipped; a 2% tie lowers confidence to 0.5) and over
  apartments ("which apartment is the largest", "average apartment size", "apartments larger than 60 m²");
  room types inside an apartment ("the kitchen in apartment A", "bathrooms of apartment A"); "how many rooms does
  apartment B have" (numbered indoor rooms); "bedrooms" on plans that only say 'Zimmer/Pièce/Stanza' (assumption
  stated, conf 0.35); "room 1" that is not on the floor → abstain with `missing`.
- **operation check** (local LLM, 3 tokens out; `--solver-arg opcheck=0` turns it off): a question that is not a
  known train template and that the rules read as a plain value/sum/difference is classified into 11 operation
  letters. Agree → rules. Disagree and the parts fit → the rules compute excluding / ratio / share (conf 0.7).
  Otherwise table QA. Template questions make no call.

| split (v10, 1d55527) | result | notes |
|---|---|---|
| dev swiss | count 100% (400), area 97.5% (400) | unchanged since v2 |
| hard2 swiss (120) | 97.1% scored, text 15/15 judged | development split for reasoning |
| hard2q swiss (120) | 91.4% scored (v6: 81.9%) | HELD OUT (D9): aggregates only, no question read |

Weak spots: hard2q floor-minus-apartment 47%, smaller-apartment text 40% (not investigated, D9); "what multiple
of A is B" is read as A/B. How bugs were found: write 20–40 novel questions for one dev floor and look for
confident wrong answers first (W2 cycle 2 found six kinds answered at conf 0.95–0.99 that way).

Experiments behind the rules: `experiments/w2/` (area_misses.py, unnamed_rooms.py, unnamed_inside.py,
unnamed_rule.py) and R1's `experiments/r1/swiss_area_def/`.

Sat 14 Nov additions (cycle 259):
- `floor.Room.net`: the printed room area when the DXF polygon is > 2% off, else the polygon. All totals, rankings and
  table-QA areas use it (the reference follows the printed labels: dev 'all numbered rooms' totals 31 → 34/35).
- Unnamed numbered rooms ≥ 2% of a total → confidence 0.78 (train: apartments 54/69, totals 45/53 right; geometry
  does not tell which ones the reference drops). dxf dev: conf ≥ 0.8 = 768 answers, 100% right.
- `can_handle` reads a sibling `.dxf` anywhere (uploads, hashed copies) when `_swiss_layers` finds the swiss layer
  names in the DXF's layer table; other DXFs are declined.
- `_plan_vs_dxf`: "do this plan and its DXF agree on the number of X?" = DXF-layer count vs the PDF's own vector-path
  count (`pdf_vector`, no LLM) → "yes (36 doors in the DXF = 36 drawn in the PDF)" with both box sets.

## `pdf_vector` (swiss-style vector PDF, NO DXF needed)
Same rules and parser as `dxf`; the floor model comes from the PDF alone (`pdffloor.py`): room polygons = filled
paths stroked grey 0.54 / width 0.37, apartments = red-brown dash-dot strokes, doors = grey-0.27 strokes, texts =
spans, metres from the printed scale ("Massstab 1:200 (A3)"). Styles were mapped to DXF layers on 10 floors
(`experiments/w2/pdf_style_layers.py`). Rooms: 796/797 within 2% of the DXF polygon (`experiments/w2/pdf_rooms.py`).
Fixtures by path shape (black, width 0.51): 47-line chain = WC/basin ellipse, 68-line chain = bathtub, quad = shower,
8 Béziers = circle (drain → washbasin): doors and all fixture kinds equal the DXF counts on 25/25 floors
(`experiments/w2/pdf_symbol_shapes.py`). Windows = touching frame-rectangle + glass-line groups outside every room
polygon, lines / 3: only 19/25 floors exact (overcounts) → confidence 0.5 + assumption.
Dev swiss (`--solver pdf_vector --solver-arg llm=0`): **count 96.5%, area 96.5%** with no DXF (dxf: 100% / 97.5%).
Use: PDF-only drawings, and as an independent second source to cross-check the DXF.

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

Deterministic arithmetic where LLM code flaked: `_assembly_total` ("every N-wide assembly consists of N units" =
Σ k × Count over the k-WIDE rows); a lookup number within 1 ft of a printed feet-inch dimension of its cited rows →
that dimension. Guards: a number copied from the question (room 'Hall (0.1)') ≤ 0.2; notes-only answers ≤ 0.65; a
label echo ≤ 0.2. Non-schedule sheets go to `sheettext.ask` over `pdftext.text_groups` (tags, notes, title block;
a dimension and its '(LABEL)' across the dimension line are one group); sums drop lengths mixed into counts.

Questions about symbols *drawn* on a plan (A-701 restrooms) are not schedule questions: the solver answers with
confidence ≤ 0.15 and says what is missing, so the pipeline escalates.
