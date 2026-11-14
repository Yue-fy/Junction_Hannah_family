# `raster` solver: counts, text and measurements on raster drawings

Owner: W3 (overnight 13 → 14 Nov). Solver name `raster`. It handles PNG/JPG/TIF drawings: CubiCasa5K plans,
Swiss Dwellings floors given as PNG, and historical scans (HABS, Finna, Europeana, Wikimedia). Every answer carries
evidence in image pixels (`bbox_space="image_px"`), a confidence measured on held-out or TRAIN data, and
`assumptions`/`missing` when it is an estimate.
Run: `python -m stoa.eval --solver raster --split <split> [--solver-arg twins=0]`. Unit tests: `tests/test_raster.py`.

## What answers what (measured)

| Question kind | Method (module) | Number (split) |
|---|---|---|
| CubiCasa room-label counts (bedrooms MH, WC rooms, balconies PARV, saunas) | one VLM label list per drawing, room codes → classes; 2×2 re-read when the list truncates (`vlm.py`, `classes.py`) | R1's hybrid label policy +13.5 pts on dev; sauna `labels_code` 69% vs labels 62% (TRAIN) |
| CubiCasa sinks / WC seats | rules from room labels: sinks = 1 kitchen + max(1, bathrooms) + WC rooms; WC seats = TRAIN mode given #bedrooms (`gate.json`, `cond_prior.json`) | sinks 69.3% vs prior 59.6%; WC seats 74.6% vs 68.6% (TRAIN 495 drawings) |
| CubiCasa doors / windows / showers | prior (every cheap detector lost to it; see Negative results) | prior: doors 12%, windows 14% |
| Any printed text on a scan or PNG (title block, sheet no., scale, names, notes) | tiled text layer (Qwen3-VL text spotting, ~1100 px tiles at ~2×, overlap merge, disk cache) + one QA call over numbered lines; cited lines become evidence (`textlayer.py`, `textqa.py`) | scan_text 68.8 vs vlm_direct 42.5 (text-judged); cited answers 75% right (54/72); Q's HABS red team 36/36 |
| "How many rooms labelled X" on non-CubiCasa images | exact label match in the text layer, quoted or unquoted (`__init__._text_count`, `apartment.unquoted_label`) | Swiss PNG 36/39 at conf 0.85 |
| Scale of a drawing | number labels of the graphic bar from the text layer, linear fit, then snap to the drawn bar (`scalebar.py`) | Swiss PNG 37/37 within 1% |
| Area of a named room on a PNG with no vector twin | printed area next to the room number, else flood fill × scale (`measure.py`) | held-out 43.3% within 2% vs VLM 36.7%; median error 3.3% vs 10.4% |
| Summed areas (apartment B, all rooms labelled X, whole floor) | unit boundary (red dash-dot, dilated 3-5 px) + printed areas + flood fill for unprinted rooms; numbering gaps make a sum "partial" (`apartment.py`) | 202 twin-less Swiss PNG Qs: 43.6% within 2% vs vlm_direct 0.5%; AUROC 0.844, ECE 0.049 |
| Which apartment is larger / largest | per-unit areas as above, conf by margin (<10%, <5%) | 83/94 vs vlm_direct 46/94; conf ≥ 0.8 12/12 |
| Door count on a PNG plan with no vector twin | swing-arc matched filter at the scale bar's px/m; doors on an apartment boundary counted twice, as the source data does (`doorarcs.py`) | all 100 Swiss dev floors: 12 exact, 31 ±1, 51 ±2 vs the counting LoRA 12 / 27 / 45, one box per door (LoRA none); doubling boundary doors: 12 exact vs 5 without |
| Window count on a PNG plan with no vector twin | wall stretches drawn as 4 thin parallel lines (2 faces + 2 glass) with equal white gaps: per-column/row run scan, lines told apart by ink mass, a mullion splits a run (`windows.py`); 1:100 only. A scale-free pre-scan (`prescan`: the same scan at 50/80/120 px/m, ~0.2 s) runs before the text layer, so a clean plan without such symbols costs no tokens | all 100 Swiss dev floors: 34 exact (74 answered: 46%; 1:200 sheets abstain; the pre-scan changes 0 answers) vs the counting LoRA 10; boxes = the answer on 100%; TRAIN 1:100 recall 0.89 / precision 0.94 |
| Room question on a sheet that shows no floor plan (elevation, section, detail) | sheet-kind veto (`sheet.py`) | low confidence + "this sheet shows no plan" |

Confidence is the measured hit rate of the method, so the pipeline can gate on it. VLM readings of numbers are capped
by kind: sums, superlatives and unprinted numbers ≤ 0.4; a cited label of another room class 0.3 (R1's by-eye
CubiCasa probe: conf ≥ 0.75 went from 2/5 to 5/5 right).

## Methods worth reusing

- **Tile before you read.** A one-shot VLM read of a large or dense sheet truncates or loops (10/20 HABS sheets hit
  max_tokens; Swiss "rooms labelled X" 3/7 one-shot vs 7/7 tiled). Tiles that still truncate are re-read as 2×2
  sub-tiles.
- **Measure from drawn geometry, not from VLM boxes.** VLM boxes for small digits are evenly spaced guesses (a
  scale bar fit with 0.0 px residual was 13% off). Find the drawn bar, wall or arc in pixels and use the text only
  for numbers.
- **Matched filters with a known scale.** Once px/m is known, a door is a quarter ring of radius 0.55-1.35 m.
  Score = ink on the ring − ink just inside and outside it. Reject full circles, and keep a detection only if its
  best radius lies inside the search range (a straight line scores higher as the ring shrinks). Work at full
  resolution: half resolution erased the 1-px arcs (recall 7% vs 91%).
- **Thin-line symbols: classify lines by ink mass, not by min value.** A 1-px line on a slightly tilted wall is
  antialiased over 2 px (black 64+173, grey 238+75), so 'min < 40 = black' misses most windows (recall 0.24 →
  0.69 with mass). Drop coloured overlays first (the red apartment boundary merges with wall faces).
- **Count what the source counts.** The Swiss DXF stores doors on apartment boundaries twice (54/60 TRAIN floors),
  and the gold counts both copies, so an image-only count must add them back.

## Negative results (don't retry without a new idea)

- CubiCasa doors/windows: Qwen3-VL-8B pointing, tiling, direct counts, classical CV arcs, VLM crop verification and a
  conditional prior all lost to the prior on TRAIN. The swing-arc filter does too (7/40 exact vs the prior's 8/40:
  noisy scans, no scale). R1's CubiCasa5K-pretrained detector (`raster_cc5k`, cc5k=1, licence CC BY-NC) is the
  route for those.
- Dimension-line reading (`dimline.py`): 16/126; it needs real tick/arrow detection.
- A walls-only refill for tiny bathroom fills leaks through windows (no gain; reverted).
- Door arcs on Revit-style IFC plan exports (resbim *_plan.png, no scale bar, 40 models, gold = IfcDoor): the door-arc scale fails there (text glyphs at the 12 px floor and grid bubbles outscore the doors; median 14-92 px/m vs ~115 true), best variant 7-8 exact of 40 vs the prior 18. The windows there are not 4-line symbols (the pre-scan finds none: abstain, 0 tokens). The scale-search ceiling (long side / 25) assumes a sheet with margins, not a tight crop. Grid bubbles pass the full-circle test because their centre is found ~3 px off; testing r +-4 px rejects them and drops 0 arcs on 99 Swiss floors (experiments/w3/doorwin/ifc_plan_doors.py, robust_circle_swiss.py). Not wired (freeze).
- Window symbols at 1:200 (~30 px/m): the glass lines render as dark as the faces; dropping the ink test and
  rejecting a 5th / ≥ 6 equally spaced line (stairs) cost 1:100 exact floors or lost on dev (34 → 32). Abstain there.

## Kill switches (`--solver-arg`)

`text=0` (no text-layer QA), `offdomain=0` (old CubiCasa behaviour on every image), `twins=0` (pretend no
DXF/PDF/IFC twin exists, to simulate a PNG-only plan), `doors=0` / `windows=0` (off-domain door / window counts abstain), `prescan=0` (always read the scale bar before the window scan), `gate=cls:method`.

Cost on uploads: scans fail the clean-render gate and CubiCasa-style plans fail the window pre-scan BEFORE the text layer. Q's 30 CubiCasa-style window uploads: 0 tokens, 0.47 s mean (run 20261114-105811-raster-dw_upload_windows-6729).

## Data and experiments

TRAIN-only tuning in `experiments/w3/`. Per-object door/window gold in PNG pixels (from the DXF via
`stoa.solvers.vector.pdfmap`): `experiments/w3/doorwin/gold.py`; window detector eval `windows.py [--show STEM]`;
raster vs LoRA on all dev floors: `upload_set.py --what door|window` + `upload_cmp.py`. Probe sets and caches live in
`$JUNCTION_SHARED/artifacts/W3/`. Drawings: Swiss Dwellings v3.0.0 (CC BY 4.0), CubiCasa5K (CC BY-NC 4.0), HABS
(public domain).
