# Methods (R1): what works, with numbers

Owner: R1. Each section gives the method, the math, a measured number when there is one, and the code path.
Numbers come from `questions.jsonl` (all 127,044 questions) unless a split is named.

## 0. Where the questions are

| Bucket | Questions | Share | Owner | Route |
|---|---|---|---|---|
| cubicasa5k counts, symbols (windows, doors, WC seats, sinks, showers+tubs, storeys) | ~54,100 | 43% | W3 | raster symbol counting |
| cubicasa5k counts, room labels (sauna, kitchen, bedroom MH, bathroom KH, WC room, balcony PARV) | 31,430 | 25% | W3 | OCR of room text, then count |
| swiss_dwellings counts (doors, windows, fixtures, apartments, rooms by label) | 25,568 | 20% | W2 | DXF layers |
| swiss_dwellings areas (total, per apartment, per room, per label) | 12,016 | 9% | W2 | DXF polygons |
| ifc_models (area 2,218 / count 642 / volume 138 / length 64) | 3,062 | 2.4% | W1 | ifcopenshell |
| ifc_bench (free text) | 820 | 0.6% | W1 | ifcopenshell + LLM |
| opening_design (schedules) | 64 | 0.05% | W2 | PDF text |

Every cubicasa question is asked twice (English and Finnish) on the same image with the same answer, and
Swiss questions come in EN/DE/FR/IT. One structured intent per (drawing, question) can be cached and
answered once. Check that the router really maps both languages to the same intent.

## 1. Prior baseline per template (measured)

`experiments/r1/priors/priors.py`. Answering every count with the most common answer for its template:

| Template (cubicasa) | Mode | Accuracy |
|---|---|---|
| kitchens | 1 | 95.8% |
| bathrooms/washrooms | 1 | 88.6% |
| storeys | 1 | 79.9% |
| showers + bathtubs | 1 | 76.2% |
| WC seats | 1 | 60.4% |
| saunas | 1 | 56.9% |
| separate WC rooms | 0 | 55.6% |
| sinks + wash basins | 2 | 51.0% |
| balconies | 0 | 51.0% |
| bedrooms | 1 | 31.1% |
| windows | 4 | 13.6% |
| doors | 6 | 11.6% |
| **all cubicasa counts** | | **55.3%** |
| all swiss counts | | 22.9% |

Consequences:
- A solver's headline accuracy is meaningless without this floor. Report it per template.
- Combining a noisy detector count `k` with the prior is Bayes: `P(n | k) ∝ P(k | n) · P(n | template)`.
  With a detector that is right with probability `a` and otherwise off by ±1, the posterior picks the
  prior mode over the detector only when `P(mode)/P(k) > a/(1−a)·…`. In practice, fit `P(k|n)` as a
  confusion matrix on the train split (cheap, it's a few hundred cells) and take the argmax of the posterior.
- Abstention fallback: return the prior mode with low confidence, never "no answer". Scoring has no
  penalty for a wrong answer beyond losing the point.

## 2. Room-label counting on Finnish plans (measured: +13.5 pts on dev)

`experiments/r1/room_labels/{run,policy}.py`. One Qwen3-VL-8B call per drawing (image upscaled 2×, max side
2400) with a grounded prompt: "Locate every room name or room code printed as text inside the rooms…
Output a JSON list [{"bbox_2d", "text"}]". The prompt gives NO example codes: v1 listed codes and the
model echoed them back on some plans. Labels are split on `+ / , -`, trailing digits are stripped
(`MH1`→`MH`), codes are mapped to classes, and duplicates (same text, IoU > 0.3) are dropped. If one
text repeats > 6×, the output looped, and we fall back to the prior.

Per-template policy chosen on 60 train drawings (574 Qs), then frozen and scored once on dev (251 Qs,
140 drawings):

| Template | Policy | Prior (dev) | Policy (dev) |
|---|---|---|---|
| bedroom | labels | 36.6% | **78.0%** |
| WC room | labels | 42.5% | **75.0%** |
| balcony | labels | 52.2% | **73.9%** |
| sauna | labels | 62.1% | 60.3% (no gain: the one-letter `S` is missed) |
| kitchen | prior "1" | 100% | 100% (labels: 52.7%, because `K` + `TK` double-count) |
| bathroom | max(1, labels) | 88.2% | 88.2% |
| **all** | | 65.7% | **79.3%**, paired delta +13.5, 95% CI [+7.2, +19.6] (cluster bootstrap) |

19% of dev outputs looped. Retrying them with vLLM `repetition_penalty=1.15` (`retry_loops.py`) fixes 26 of 28, and dev rises to **82.1%** (+16.3 vs the prior, 95% CI [+9.4, +22.8]; WC rooms 85.0%, balconies 87.0%). For saunas, use the prior: labels are neutral on dev. Cost: ~2.1k tokens in and ~570 out per
drawing, and one call answers all 12 room-type questions (EN+FI).

About 25% of all questions (37% of cubicasa) count rooms by type. Finnish plans print the room code
inside the room: `MH` (bedroom), `OH` (living room), `K`/`KK`/`TK` (kitchen, kitchenette, open kitchen),
`KH`/`PH`/`PESUH`/`KPH` (bathroom/washroom), `WC`, `S`/`SAUNA` (sauna), `PARV`/`LASITETTU PARV.` (balcony),
`ET` (hall), `VH`/`VAR` (storage), `KHH` (utility room), `AK`/`TUPAK` (alcove, farmhouse kitchen).
Pipeline: OCR all text with boxes (or ask the VLM to list every room label with a box), normalise,
map to class, count. The evidence is the text box: a human checks it in one glance.
On the images the codes are often lowercase (`kt`, `oh`, `mh`, `wc`, `et`, `khh`, `var`) and only ~8 px
tall at native resolution (e.g. `colorful-1012.png`), and some plans also print room areas (`8,1 m²`).
Upscale 2–3× before OCR.
Caveats: `MH` can carry a digit (`MH1`, `MH2`). Some kitchens are a niche without a label (`K` missing),
which is why the "always 1" prior is so strong. Saunas are sometimes only drawn as a bench symbol.

## 3a. Symbol counting with the pretrained CubiCasa5K model (measured: +15 to +30 pts, leak-safe)

The CubiCasa5K multi-task network (Kalervo et al., SCIA 2019; public weights `model_best_val_loss_var.pkl`,
CC BY-NC 4.0) segments 12 room classes and 11 icon classes, including Window, Door, Toilet, Sink and
Bathtub, exactly the symbols we lose points on. We wrote our own copy of the network
(`experiments/r1/cc5k_model/net.py`, same parameter names) and load the checkpoint with
`torch.load(weights_only=True)`. We don't run the upstream code. Inference takes ~0.8 s of CPU per drawing and
no GPU or LLM.

Count = number of 8-connected components of `icons == class` with area ≥ `min_frac·H·W`, after an optional
k×k morphological opening. Evidence = one box per component.

**Leak safety (D3).** The model was trained on the original CubiCasa5K *train* list, which holds 84% of
our drawings, including most of dev, train_gate and test. So it is tuned only on drawings in the original
**val** list (371 drawings, not in our sealed test) and reported only on the original **test** list
(`cc5k_heldout`, 365 drawings). Numbers on dev or train_gate would be inflated by memorisation.

Settings frozen on val: windows (2e-4, k=5), doors (2e-4, k=0), WC seats (2e-4, k=5), sinks (2e-5, k=5).

| Template | Prior (test) | CC5K model (test) | Paired gain, cluster CI (cc5k_heldout, eval tool) |
|---|---|---|---|
| windows | 13.9% | **34.0%** | +14.6 [+6.2, +23.1] |
| doors | 9.8% | **40.2%** | +29.9 [+21.3, +39.4] |
| WC seats | 55.0% | **75.5%** | +29.1 [+18.9, +39.4] |
| sinks | 45.7% | **60.1%** | +22.0 [+11.8, +31.5] |
| showers + bathtubs | 73.9% | 10.1% | the model has no shower class → keep the prior |
| all cubicasa questions in cc5k_heldout | 51.2% | **59.5%** | **+8.4 [+6.4, +10.3]** |

(The left two columns count one gold per drawing; the CI column uses the eval tool's question rows. Prior
row: `artifacts/eval/20261114-005001-prior-cc5k_heldout-14c7.jsonl`; model rows:
`artifacts/R1/cc5k_preds/plain_over_prior.jsonl`.)

By style (test, model vs prior): windows colorful 47/15, high_quality 46/29, architectural 28/10; doors 57/8,
66/17, 29/8; WC seats 82/69, 86/68, 71/49; sinks 62/63 (no gain on colorful), 73/56, 57/39. Scanned
architectural sheets are the hardest. Small images are not worse than large ones (windows by long side:
<700 px 49%, ≥1500 px 35%), so upscaling is not the fix.

Calibration: `confidence = P(gold == count | template, count bucket)` fit on val (Laplace-smoothed;
`calib.py`, `calib_plain.json`). ECE on test is 0.03–0.09. A gate "prior if it is more often right in this bucket"
never fires except for sinks with 0, 1 or ≥6, where it changes nothing on test. Within ±1 coverage on test:
windows 57%, doors 68%, WC seats 95%, sinks 86%. These are the intervals to state when unsure.

Inside the full pipeline (`pipeline` on cc5k_heldout, night cbd2fe8: 61.8%), swapping in the model's
counts for the 4 symbol templates gives 68.8%: **+7.1 [+5.1, +9.0]**. Doors: pipeline (VLM) 23.6% → 38.6%.
(`artifacts/eval/20261114-005010-pipeline-cc5k_heldout-5645.jsonl` vs `artifacts/R1/cc5k_preds/plain_over_pipeline.jsonl`.)

Tried and not adopted:
- 4-rotation TTA (4× CPU): test windows 35.3 (+1.3), doors 37.1 (−3.1), WC 77.9 (+2.4), sinks 63.1 (+3.0).
  All within noise, so we keep plain inference because it is 4× cheaper.
- An opening kernel relative to image size: no change (windows 33.4, WC 75.7, sinks 59.5).
- Splitting long window components into several windows by a typical window length: always worse
  (windows val 40% → ≤ 39%). The −4 tail (18% of val drawings) is missed windows, not merged ones.
- A per-class probability threshold instead of argmax (P(window) ≥ τ, τ = 0.15–0.45; 227 val drawings):
  never better (windows 44.1% argmax vs 43.6%). The missed windows are not near-misses in probability.

**Memorisation check (D3).** Accuracy on drawings from the model's original *train* list is about the
same as on held-out *test* drawings of the same style, so there is little memorisation:

| Style (n train / test) | Windows | Doors | WC seats | Sinks |
|---|---|---|---|---|
| colorful (153 / 66) | 41 / 45 | 51 / 55 | 76 / 83 | 56 / 62 |
| high_quality (785 / 59) | 51 / 47 | 54 / 64 | 86 / 85 | 66 / 72 |
| architectural (2153 / 258) | 28 / 28 | 36 / 29 | 76 / 72 | 54 / 56 |

On 127 of our dev drawings (all in the CC5K train list): windows 37, doors 45, WC 79, sinks 60. Dev numbers
for this model should be within a few points of the leak-safe ones.

**Out-of-domain check (ResBIM).** Sixty Revit plans from `data/ifc_models/resbim-N_plan.png` (7572×4189), with the
paired IFC's IfcWindow/IfcDoor counts as ground truth (`resbim_check.py`):

| Preprocessing | Windows exact | Doors exact |
|---|---|---|
| whole image → 2000 px long side | **77%** (12/15 on plans whose count isn't the common 4) | 0% (always under) |
| crop to ink box → 1000 px | 65% | 12% |
| crop → 1500 / 2000 px | 55% / 33% | 2% / 0% |

Windows transfer to an unseen style; doors don't (Revit draws thin swing arcs). `predict.py` now resizes
images whose long side is over 3000 px to 2000 px and maps the boxes back to original pixels.

**Room segmentation as a cross-check (Stoa point 4).** Room-type regions = components of room class
(Bed Room 5, Bath 6, Kitchen 3, Outdoor 1) ≥ min_frac·H·W (val-chosen: 1.2e-2, 1.2e-2, 1.6e-2, 2.4e-2;
`config.ROOMS_FROZEN`). On cc5k_heldout the pipeline's answer is right 92–96% of the time when it agrees
with this count, and much less often when it doesn't:

| Template | Agree (n) | Pipeline acc. when agree | when disagree | Segmentation alone (test) |
|---|---|---|---|---|
| balconies | 60/108 | 92% | 65% | 68% (val 70%) |
| bedrooms | 63/126 | 75% | 37% | **67%** vs pipeline 56% |
| bathrooms | 57/96 | 96% | 82% | 65% (prior ~92%) |
| kitchens | 111/126 | 96% | 80% | 88% (prior ~94%) |

`adapter.cross_check(path, concept, value)` returns the line in D4/W5 badge format, e.g.
`cross-check: label reading 3 = CC5K room segmentation 3 ✓`.

Live use: `experiments/r1/cc5k_model/predict.py IMG.png` prints `{counts: {windows|doors|wc_seats|sinks:
{count, confidence, boxes}}}`. It needs torch (CPU is enough; `/data/User/fangy4/envs/junction-train`
has it, but `$JUNCTION_VENV` does not).

## 3. Symbol counting on raster plans (measured: Qwen3-VL-8B pointing does NOT work)

Measured with Qwen3-VL-8B (`experiments/r1/symbol_points/`), exact match vs the per-template prior:

| Setting | Split | Windows | Doors | WC seats | Sinks | Showers+tubs |
|---|---|---|---|---|---|---|
| prior | train (40 drawings) | 12.5% | 6.7% | 70.0% | 47.5% | 54.1% |
| full image 2×, one class per prompt | train | 5.0% | 10.0% (loops) | **87.5%** | 15.0% | 43.2% |
| same, frozen | dev (107) | – | – | 65.4% vs 57.0% (+8.4, CI [−2.8, +19.6]) | – | – |
| 2×2 tiles, 1280 px each | train_gate (14/16) | 0.0% (0.63×) | 25.0% vs 6.2% | – | – | – |
| 3×3 tiles, 1024 px each | train_gate | 7.1% (1.74×) | 25.0% (0.72×) | – | – | – |
| 2×2 tiles, frozen | dev (57) | – | 10.5% vs 17.5% | – | – | – |

The door gain on train_gate (n=16) did not replicate on dev. Tiled counts are unbiased on average
(pred/gold 0.97) but much too noisy for exact match. This is consistent with AECV-Bench: frontier VLMs
score ≤ 0.39 on doors. What's left to try: exemplar counters (GeCo2/CountGD), classical CV for door arcs
and window symbols, or a bigger VLM. The original recipe below is kept for reference.

Recommended order (cheapest first):
1. VLM pointing: ask for one point per instance (Molmo / Qwen-VL grounding), then count the points.
   Points are evidence, and counting points beats asking for a number (VLMs' numeric counts saturate
   and drift above ~6 objects).
2. Upscale before asking: median cubicasa image is ~700×700 px and symbols are ~10–20 px. Feed 2× or
   tile into 2×2 with 20% overlap, so each symbol is at least ~32 px in model input.
3. Tiling de-duplication: merge points closer than `r` across tiles, with `r` ≈ half the symbol size
   (≈ 0.5 × median door width in px). Overlap must exceed the symbol size so no symbol is cut in both tiles.
4. Self-consistency: sample m=5 point sets, cluster points (DBSCAN with eps=r, min_samples=⌈m/2⌉), and keep
   clusters seen in a majority. This is a vote per object, not per count, so it keeps the evidence.
5. Verify: crop 64×64 around each point and ask "is this a <class> symbol? yes/no". This removes false
   positives cheaply.
6. Combine with the prior (section 1) when the vote is split.

## 4. Swiss net floor area from DXF (measured)

`experiments/r1/swiss_area_def/test_total.py` (stdlib DXF reader, no ezdxf needed).
Rule: label each `ROOM_OUTLINE` LWPOLYLINE by the `ROOM_TEXT` points inside it (point-in-polygon).
A room counts if it carries a room-number text (`^[A-Z]{0,2}\d+(\.\d+)*$`, e.g. `7.01`, `U2.18`) and its
name is not an outdoor space (`Balkon, Balcon, Balcone, Loggia, Terrasse, Terrazza, Sitzplatz, Garten…`).
Area is the shoelace area in DXF units (metres; `$INSUNITS = 6`).

| Rule | Within 2% (400 floors) |
|---|---|
| all ROOM_OUTLINE polygons | 16.2% |
| numbered polygons | 22.8% |
| numbered, not outdoor | **91.0%** |
| numbered, not outdoor, not lift/shaft | 89.0% |
| not outdoor (numbered or not) | 73.5% |

Same rule, other English templates (first 300 floors, within 2%;
`experiments/r1/swiss_area_def/test_apartment.py`):

| Template | Rule | Within 2% |
|---|---|---|
| net floor area of room N ('Name') | the polygon containing number text N | 99.0% (594/600) |
| total net area of all rooms labelled 'Name' | sum of polygons containing that name text | 100% (291/291) |
| net floor area of apartment X | numbered, non-outdoor rooms whose label lies inside the UNIT_OUTLINE that contains `Whg. X` / `App. X` | 96.4% (530/550) |

Negative result: treating untexted polygons inside a room as holes and subtracting them changes the
total from 91.0% to 92.0% and per-room from 99.2% to 98.8%, which is noise (`test_holes.py`).

Counts, exact match, DXF only (`test_counts.py`, `test_doors2.py`, `test_fixtures.py`, `test_wc_basin.py`):

| Template | Rule | Exact |
|---|---|---|
| doors | number of 5-vertex DOOR LWPOLYLINEs (arcs: 56.7%; double doors have 2 arcs) | 1000/1000 |
| windows | WINDOW LWPOLYLINEs / 3 | 200/200 |
| apartments | ROOM_TEXT matching `^(Whg|App)\.` (UNIT_OUTLINE polygons: 89%) | 200/200 |
| rooms labelled X | ROOM_TEXT == X | 1213/1213 |
| bathtubs | 69-vertex FIXTURE LWPOLYLINEs | 258/258 |
| showers | 5-vertex FIXTURE LWPOLYLINEs | 96/96 |
| toilets / washbasins | 48-vertex FIXTURE ellipses; one with a FIXTURE CIRCLE (drain) inside it is a washbasin, otherwise a toilet. Found by rendering the fixtures; size, aspect ratio and adjacent rectangles all fail (~5%). | 1000/1000 each |

All 36 misses of the total rule overshoot by 2–6%. Residual causes: numbered rooms with no name, and Lift/stairs that are
excluded on some floors but not others. This matches SIA 416 logic, where net floor area is usable
area + circulation + services, and shafts (`Schächte`) and outdoor areas sit outside it.

## 5. Areas from measurements: why the definition matters more than the pixels

- The tolerance is 2% relative. Area scales with the square of the length scale, so the drawing scale
  must be right to within ~1%: `δA/A ≈ 2·δs/s`.
- Net and gross differ by much more than 2%: a 4 m × 4 m room measured to wall centrelines instead of
  inner faces (0.1 m half-wall on each side) gives `(4.2² − 4²)/4² = 10.25%` too much. Always check which
  boundary the reference uses (inner face = net) before fitting anything.
- Fit the scale from all dimension strings at once by least squares. With pixel lengths `ℓᵢ` and written
  lengths `dᵢ`, `s* = Σ ℓᵢ dᵢ / Σ ℓᵢ²`. Use the median of `dᵢ/ℓᵢ` or RANSAC to reject misread strings.

## 6. Statistics for the team

- dev has ~2,000 questions. At accuracy p ≈ 0.5, the standard error is `√(p(1−p)/n) ≈ 1.1` points, so a
  95% CI is ±2.2 points. On a smoke set of 200 it's ±7 points: never claim a gain from smoke alone.
- Comparing two solvers on the SAME questions: use McNemar on the discordant pairs (b = A right, B wrong;
  c = A wrong, B right). `χ² = (|b − c| − 1)² / (b + c)`; with b + c < 25 use the exact binomial test.
  This is much more sensitive than comparing two CIs.
- Per-template reporting is required (section 1). A pooled number hides a solver that only learned "1".

## 7. Verifiability ideas that next year's frontier models won't make obsolete

- Cross-modal agreement as confidence: Swiss floors exist as DXF + PDF + PNG; ifc_models plans exist as
  IFC + PDF. Answer through two independent routes; agreement → high confidence, disagreement → show both
  with evidence. This also produces a calibrated confidence for free.
- Evidence = the exact primitives summed or counted (polygons, points, IFC GlobalIds), so the UI can
  highlight them and a human can verify in seconds.

## 8. Stoa's feedback (23:40): generality, cost, calibrated estimates, linked data

Stoa says the hidden test is harder and different, and that they score reasoning, interface and cost.
Template rules (sections 2 and 4) are fast paths. Each needs a general fallback.

### 8a. Calibrated estimate instead of refusal (measured)
`experiments/r1/door_scale/door_scale.py`. When a drawing has no scale, take the median door-leaf width
as 0.857 m. Swiss DXF ground truth (789 floors, 25,120 door arcs):

| Area error | Share of floors |
|---|---|
| ≤ 2% | 11.7% |
| ≤ 5% | 28.9% |
| ≤ 10% | 53.4% |
| ≤ 20% | 84.9% |

Median area error is 9.2%. This is a usable estimate, not an exact answer. Return it with
`assumptions=["no scale found; assumed median door leaf 0.86 m"]`, an 80% interval of ±17% on area, and
`missing=["scale bar or dimension strings"]`. The same pattern works for counts: return the posterior mode
from the prior (section 1) with its probability as the confidence, e.g. "1 kitchen (96% of similar plans
have exactly one)".

### 8b. Cost-aware cascade (to be measured once W4's pipeline reports cost)
Stage k answers if its confidence ≥ τ_k, otherwise it escalates:
deterministic geometry (DXF/IFC/PDF text, ~0 cost) → OCR/CV → small local VLM → hosted Nemotron.
Expected cost = Σ_k P(reach k) · cost_k. Pick τ_k from the risk–coverage curve of stage k on dev
(`experiments/r1/stats/compare.py RUN`): the smallest τ at which accuracy-when-answered ≥ the next stage's
accuracy on the same questions. Escalating only then can't lower accuracy, and it cuts cost.

### 8d. Calibrated count ranges from two counters (measured)
`experiments/r1/count_interval/interval.py`; live in `stoa/solvers/raster_cc5k/crosscheck.py` (`interval()`, and
`check()` adds it to LoRA answers). Stoa wants "a best estimate with a calibrated confidence" instead of a refusal.
For a count, the natural form is an integer range that holds the true count with a stated probability.

Two independent counters answer every cubicasa count: the LoRA (L) and the CubiCasa5K detector (C). Rule:
`[min(L, C) − lo, max(L, C) + hi]`, with margins per group (openings = windows, doors; fixtures = WC seats, sinks;
rooms) × (agree | disagree). The margins are split-conformal: on the calibration run, take the narrowest (lo, hi)
whose coverage is at least ⌈(n+1)(1−α)⌉/n. That is the finite-sample level that guarantees ≥ 1−α on
exchangeable new drawings. Calibration run: the LoRA on train_gate (320 answers; it never trained there).

| 90% nominal | lo, hi when agree | lo, hi when disagree | dev coverage (width) | leak-free-for-both coverage (width) |
|---|---|---|---|---|
| fixtures, rooms | 0, 0 | 0, 0 (the two counts' range) | 87–100% (1.1–1.8) | 88–100% (1.3–1.7) |
| windows, doors | 1, 4 | 1, 5 | windows 89% (9.4), doors 100% (9.2) | 100% (8.9), 100% (8.1) |
| all | | | **93% (3.9)**; through `check()` on dev run feec: 91.9% (4.3) | **97% (3.2)** |

Compared with the same margins around the single arbitrated answer (`point`: dev 90%, width 4.3) and relative
margins (`rel`: 92%, 4.1), the two-counter range is both narrower and better covered. It also needs no extra model
call. At 80% nominal: dev 89% (3.2), leak-free 92% (2.6). Window ranges are wide (about 9 values) because both
counters miss windows on large plans (dev residuals up to +28). That is the honest answer, and it shows where the
method is weak.

How to use it: show `7 windows (90%: 6–12)`. A comparison ("more bedrooms than bathrooms?") is sure only when the
two ranges don't overlap. A sum of two counts has the range [lo₁+lo₂, hi₁+hi₂], which covers the true sum at
least 1−2α of the time (union bound). The ranges were fitted for LoRA answers only, so other solvers get none.

**Detector alone (leak-safe).** When the pipeline sends a count to `raster_cc5k` first (windows on cc5k=1), no
second counter exists. Then the range is `[C − lo, C + hi]`, with margins per class × count bucket. The margins are
fitted on the original CC5K **val** list and checked on the original **test** list
(`experiments/r1/count_interval/det_interval.py`, D8-clean). raster_cc5k's answers carry it automatically
("interval90: [lo, hi]").

| 90% nominal | test coverage | mean width | margins (bucket: −lo/+hi) |
|---|---|---|---|
| windows (n 368) | 89.7% | 10.2 | ≤4: −1/+3, ≤8: −3/+5, >8: −3/+13 |
| doors (264) | 93.2% | 10.7 | ≤4: −1/+9, ≤8: −2/+9, >8: −3/+5 |
| WC seats (367) | 91.3% | 2.0 | ≤1: −0/+1, >1: −1/+0 |
| sinks (363) | 92.8% | 3.5 | ≤2: −0/+2, >2: −2/+1 |

With a second independent counter, the fixture ranges are narrower at the same coverage: 1.4–1.7 values wide
instead of 2.0–3.5. That is the measurable value of linking two sources (Stoa point 4).

### 8c. Linked data as a cross-check
- Swiss (measured, `experiments/r1/link_dxf_pdf/fit_affine.py`): DXF → PDF is one affine map per floor,
  fitted by least squares on room numbers that occur once in both the DXF `ROOM_TEXT` and the PDF words
  (PyMuPDF): `[u v] = [x y 1]·A`. It fits **1,036/1,040 floors with RMSE 0.04 pt (max 0.08 pt)**; the other 4
  have fewer than 3 unique numbers. The PDFs are A3 at 1:100 (859) or 1:200 (177), and the PNG is the page at
  150 dpi (px = pt × 150/72). Every DXF-derived count or area therefore gets exact evidence boxes on the PDF
  and PNG. A VLM count on the PNG that agrees with the DXF count raises confidence; a disagreement goes
  into the trace.
- ifc_models: the PDFs were rendered from the IFC. Room names printed in the PDF ↔ `IfcSpace.Name/LongName`
  gives the same link, and the drawing count can be checked against the IFC count.
