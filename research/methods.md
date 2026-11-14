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

- 2× upscaling with the maps KEPT at 2× (`dense2x.py`; `infer.py --scale 2 --keep-res`, so neighbouring symbols
  don't merge again on the way back to 1×), for all 688 val+test plans ≤ 1500 px, min_frac × kernel grid on val.
  Always-2×: windows val 40.1 → 34.7, test 33.9 → 32.5; doors val 46.3 → 40.6, test 39.6 → 36.0. The best gated
  rule from val (2× only on small, dense plans) gives test windows +0.5 [−2.1, +3.4] and doors +1.1 [−1.4, +3.6],
  which is selection noise (800 rules tried). The worst misses, such as 29 windows on a 785×355 plan, are not
  caused by low resolution.

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

**Second unseen style: swiss PNG twins** (A3 at 150 dpi, gold from the DXF; 145 plans in R2's count splits;
`swiss_png_check.py`). Windows: 26% exact, 43% within ±1, against the LoRA's 12% and the base VLM's 8% on the same
dev questions. Sinks: 34% (LoRA 46%). WC seats: 7%. Doors: 0%, because the model finds about 3% of them. Across both
unseen styles, the detector transfers for windows only.

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

**Current raster methods with measured numbers: see `stoa/solvers/raster/README.md` (W3, night-W3 1150bbd)** — not
duplicated here. Two facts from W3 (09:36) that matter for any raster door count: (1) the swing-arc matched filter
(`doorarcs.py`) counts doors on clean Swiss PNG renders (arc recall ~0.9 / precision ~0.95; twin-less dev doors 2/15
exact vs vlm_direct 0/15) but is NEGATIVE on CubiCasa scans (7/40 vs the prior's 8/40), so the CC5K detector (§3a)
stays the CubiCasa door route; (2) the Swiss DXF door gold double-counts doors on apartment boundaries (54/60 TRAIN
floors), so any image-only door count on Swiss plans is low by ~1–10 against that gold.

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

**Yes/no threshold questions ("at least two toilets?").** The answer comes from one count, but its confidence
should come from whether the second counter is on the same side of N. LoRA + CC5K, pooled over N = 1..10, fitted
on train_gate (`threshold_side.py`, `crosscheck.threshold_confidence()`):

| group | same side: conf (dev right) | straddling N: conf (dev right) |
|---|---|---|
| openings (windows, doors) | 0.94 (95%, n 1124) | 0.53 (59%, n 249) |
| fixtures (WC, sinks) | 0.97 (96%, n 562) | 0.68 (69%, n 121) |
| rooms | 0.97 (98%, n 302) | 0.80 (90%, n 40) |

The pipeline today gives "at least two WC seats?" 0.82 whether the answer is right or wrong (hard2: 0.82 vs 0.79).

### 8e. Area on a raster plan with no scale: printed areas first, then door widths (measured)
Stoa's own example of "a best estimate, not a refusal" is a plan with no scale ("assumed standard door width 0.9 m").
Today the pipeline sends a cubicasa area question to the base VLM. It reads a printed area correctly, but at
confidence 0.32 and with no evidence. With nothing printed, it guesses (74 m², conf 0.05) with no assumptions.

**Ground truth without dataset labels.** Many cubicasa plans print areas: a room's ("MH 13.0 m²") or the
apartment's ("3h+k+s 85 m2"). One local VLM call per plan reads them with boxes (`find_areas.py`). 178 of 380 TRAIN plans print at least one
(55% of high_quality_architectural, 18% of colorful). A printed room area inside one CC5K room region gives that plan's true
px/m (median over ≥ 2 consistent rooms); a printed apartment total over all interior regions gives it too. Rule: any
area ≥ 40 m² or "NhK…" text is a total (no room is that big; several apartment totals are summed).

**Estimators, 2-fold cross-fit by plan** (`raster_scale.py`; constant and band fitted on one half, errors on the other):

| estimator (px/m) | constant | area error p50 | within 10% / 20% | 80% band (true = est ×) | band coverage |
|---|---|---|---|---|---|
| **median CC5K door opening** | 0.80 m | **16.5%** | 31% / 55% | [0.70, 1.49] | 79% |
| median wall thickness | 0.18 m | 32.0% | 14% / 32% | [0.49, 1.98] | 79% |
| door × wall (geometric mean) | | 21.2% | 27% / 46% | [0.67, 1.70] | 76% |
| one px/m for all plans | 51.9 px/m | 47.3% | 8% / 22% | [0.26, 2.20] | 73% |

(153 plans with a usable true scale: 44 room-level, 109 total-level. A q40, inter-quartile mean or aspect-filtered
door width is no better: 16.4–19.6%.) **"Nothing printed" end-to-end** (`masked_eval.py`): on 120 plans whose
printed total we know, every printed area is whited out and the question "What is the total floor area of this
apartment?" goes to the base VLM, which is the pipeline's path today:

| answer | error p50 | within 2% | within 10% | within 20% |
|---|---|---|---|---|
| base VLM on the masked plan (today) | 34.8% | 5% | 25% | 33% |
| door scale (cross-fit) | 18.1% | 7% | 33% | 53% |
| **door scale shrunk to the typical apartment (cross-fit)** | **13.4%** | 8% | 40% | **62%** |

Shrunk door estimate vs the VLM, within 20%: **+28.3 pts [+17.5, +39.2]** (paired bootstrap, n = 120).

The implied door opening (median, IQR) is 0.78 m (0.73–0.85) from apartment totals and 0.85 m (0.82–0.92) from
rooms: Finnish 8M–9M interior doors, so the constant is physical, not just fitted. Wall thickness and a "typical plan resolution" are much worse: plan resolutions vary 3–4× (true px/m
p10–p90 35–103).

**Shrinkage helps the apartment total.** A log-blend of the door estimate with the typical training apartment
(70.5 m²), weighted by the two error variances (no grid search), lowers the cross-fit median error from 16.7% to
12.7% (108 plans; weight 0.55 on the door estimate). The helper uses the blend for whole-apartment areas and states it in `assumptions`.

**Single rooms are harder.** A room's area from its CC5K region has a median error of 21% (349 printed rooms on
73 plans; bedrooms 15%, baths 17%, storage 14%, living rooms and kitchens 34%, because open kitchens merge). Regions
are fragments or merges of the printed room. Rooms get their own constant (0.86 m; regions are smaller than printed
net areas). Their 80% band covers 81%, so it is honest but wide (true = est × [0.71, 2.57]): always show it.

**Scale-free questions** (`relative.py`, 45 plans with ≥ 3 printed rooms, 1,129 pairs): "is A bigger than B?" from
region pixels is right 84% (87% when the sizes differ by ≥ 25%); "which room is largest?" 60%; an area ratio A/B errs
by 19.5% (median). The ratio error is about the room-area error (21%), so for single rooms the limit is the
segmentation, not the scale.

**Within the 2% scoring tolerance:** 7–8% of plans (VLM 5%). A door-derived area is an honest estimate, not a scored answer.
The value is in the interval, the assumptions and the evidence (doors measured, regions summed).

**Use** (`experiments/r1/raster_scale/scale.py`, CC5K caches, no torch; D8: cc5k=1 path; CC BY-NC):
1. `printed_areas(path)` (one VLM call): if the asked room or apartment prints its area, answer that number, with
   the text box as evidence and the CC5K region class under it. Cross-check it with step 2: inside the band → ✓.
2. Otherwise `estimate_area(path, "apartment" | "kitchen" | …)` → value, `interval80`, confidence = P(within 2%),
   assumptions ("no scale printed; assumed the median door opening is 0.80 m, 7 doors measured", shrinkage), missing
   ("a scale bar, dimension strings or printed room areas"), door boxes and region boxes as evidence.
Plans outside the cache run the CC5K model once on CPU (~3 s, `predict.py` with `CC5K_SAVE_MAPS`). Doors do not
transfer to other raster styles (swiss PNG 3%, Revit 0–12%), so this is for cubicasa-style plans only.
Leak note (D8): the CC5K maps on our TRAIN plans are from a model that saw most of them in pretraining; the truth is
printed text, not CC5K labels. Error on the few plans from CC5K's own val/test lists: CC5K-test plans 11.0% (n 13), val 18.3% (n 6), train 17.0% (n 133): no sign of inflation.

### 8g. Scale of a historical scan, two ways (exploratory, small n)
HABS scans were resized to ≤ 3000 px, so the DPI is lost and a printed "1/4" = 1'-0"" alone gives no px/ft.
`experiments/r1/scan_scale/scan_scale.py` (CPU, W3's cached text layer) gets px/ft twice: (A) the scale note ×
the standard sheet size found from the aspect ratio (24 × 36 in → 1.5, 19 × 24 in → 1.263; px per paper inch = long
side / 36 or 24), and (B) a graphic scale bar (tick labels in one row next to FEET/METERS: least squares, or one
merged OCR item "0 10 20 30 60 90 ft." spanning the bar). On 16 bars on 11 HABS sheets the two agree within 10% half
the time (median gap 8.7%; 5.6% on the 9 sheets with one scale note); bars run a few % below the note estimate
(scans include some margin). Failures: a junk label row, a ×2 mismatch, metric bars on multi-scale sheets. Use it
as "≈ 42 ft (scale bar and 1/4" note agree within 5%)" with that agreement as the confidence, never as exact.
Coverage: 50/148 scans have a known sheet aspect, 77 a scale note, 19 a usable bar.

### 8f. What the cubicasa second reader is worth (measured; cost cascade, 8b)
The pipeline runs raster (VLM label reader) as a second opinion on every LoRA count and moves the confidence by
agreement. That made cubicasa ~20× more expensive (S0 03:56: $0.02 → $0.42 per 1k). The values never change, so
the reader can only help through confidence and evidence. `experiments/r1/cost_gate/second_reader.py RUN [--boot]`
replays a run: today's confidence (the key's train hit rate, moved by agreement) vs vlm_lora's own per-question
confidence (answer-digit probability mapped on train_gate, already in the trace, free).

| split (LoRA answers) | own conf: ECE / AUROC / Brier | after cross-check | conf ≥ 0.8: own vs today |
|---|---|---|---|
| dev bb98 (662) | 0.022 / **0.899** / **0.112** | 0.035 / 0.881 / 0.122 | 60% @ 93.5% vs 47% @ 94.5% |
| leak-free cc5k_heldout_notLoRA 7ec6 (152) | 0.051 / **0.941** / **0.076** | 0.067 / 0.861 / 0.102 | 72% @ 98% vs 66% @ 95% |
| hard 8d9d (141) | 0.079 / 0.824 / 0.133 | 0.076 / 0.828 / 0.135 | 72% @ 92% vs 55% @ 92% |

Drawing-cluster bootstrap on dev: the cross-check makes Brier worse by +0.009 [+0.0005, +0.018], and AUROC
−0.018 [−0.039, +0.002]. Per kind, agreement helps only windows (AUROC 0.55 → 0.64); it hurts sinks, storeys,
saunas, bedrooms and bathrooms. The reader's real value is evidence: it gives the only boxes on 159 of 662 LoRA
answers (labels of bedrooms, saunas, WC rooms, balconies; kitchens for sinks; bedrooms for WC seats), and none for
windows, doors, storeys or bathrooms. So use the LoRA's own confidence, and call the reader only to attach
evidence for label kinds, or lazily on "Show where". Gating it by confidence band saves little, because the read is
per drawing and 64–97% of drawings have at least one question in any useful band.

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

### 8h. Room graph of a raster plan: per-room questions with evidence (measured without dataset labels)
Why: a harder test can ask per-room questions the dataset never asks ("how many windows does the kitchen
have?", "which rooms open onto the hall?", "is the WC next to a bedroom?", "area of the largest bedroom?").
On CubiCasa-style rasters there is no twin and no IFC, so the plan itself must become a small graph
(the in-drawing part of agenda item 1, linking: printed labels ↔ segmented regions ↔ symbols).

Method (`experiments/r1/room_graph/graph.py`, cache-only, ~0.3 s per plan on CPU, no LLM): rooms = connected
components of each CC5K room class (min size 2e-3 of the image for baths/WCs, 5e-3 balconies, the frozen
1.2e-2 for bedrooms, 3e-3 otherwise); a region with a sauna bench is a sauna (CC5K has no sauna class).
Icons use the FROZEN counting settings, so per-room counts sum to the drawing-level detector counts.
Fixtures go to the room under them; a window goes to the interior room its wall ring (one wall thickness,
measured from the wall map) touches most, and is 'exterior' if the ring also touches background/outdoor; a door
links the two rooms its ring touches most, or one room + 'outside'; regions touching directly (no wall) are
`open_to` (open-plan kitchen ↔ living); regions within 1.5 wall thicknesses are `wall_to`. Areas come from the
door scale (8e, room constant, 80% band). Printed labels (cached VLM label read) name the regions; two labels of
the same kind in one region are flagged `merged` (a thin partition the segmentation missed).
`graph_text(g)` is a one-line-per-room summary for an agent tool or an answer card.

Validation without dataset labels (`validate.py`; artifacts/R1/room_graph/validate.json):
| Check | n | Result |
|---|---:|---:|
| Printed label ↔ region class (172 plans, VLM-read labels, independent of CC5K) | 1,117 labels | **92.1%** |
| … bedroom (MH) / living (OH) / kitchen (K) / balcony (PARVEKE) | 169 / 119 / 144 / 60 | 97.0 / 95.8 / 93.1 / 98.3% |
| … bath+WC (KH/PH/WC) / sauna / entry (ET/TK) / storage (VH/VAR) | 169 / 44 / 156 / 106 | 90.5 / 84.1 / 87.8 / 87.7% |
| Bedroom named MH has ≥ 1 window (Finnish habitable rooms need one) | 155 | 91.6% |
| Bath/WC named KH/PH/WC has a toilet or sink | 155 | 84.5% |
| Kitchen named K/KEITTIÖ has a sink; sauna has a bench | 139 / 43 | 84.9 / 86.0% |
| Named interior room has a door or open link | 835 | 95.3% |
| Random 400 cached plans: doors linking two sides / windows assigned to a room | 3,045 / 2,852 | 94.1 / 97.0% |
| … share of interior rooms reachable from outside (doors + open links) | 400 plans | mean 81%; all rooms 43% |
| … plan has a door to outside or a balcony | 400 | 95.8% |
First run (before two fixes): bath labels 63.5% (49 of 167 fell on no region: the room-count size threshold
dropped small WCs) and sauna 6.8% (CC5K calls saunas 'undefined').
Eye check of two overlays (high_quality_architectural-7607 and -3919): every detected door links the right rooms,
every detected window is in the right room, entrance and balcony doors found; failures: two bedrooms merged into one
region (flagged by the two MH labels), a washroom 'PS' called sauna because a bench icon touched it.
Limits: the 8% of bedrooms with no window are missed windows (the detector's known window recall); disconnected
graphs come from undetected doors; D8 (pretrained CC5K) → cc5k=1 path only; areas carry the door-scale band (8e).
New drawings: room_graph(path) runs the CC5K model once (torch env subprocess, CC5K_PYTHON) when no cached map
exists and saves rooms + icons to artifacts/R1/cc5k_seg_live/; an uncached copy of -7607 gave the identical graph
in 4.7 s. Maps are keyed by file stem, so two different plans with the same file name would collide.
How to use: answer a per-room question from the graph with the region box + icon boxes as evidence, and quote the
room's label; if the region is `merged`, say so and answer for the region ("these two bedrooms have 2 windows").

### 8i. Room graph vs the VLM and the pipeline on per-room questions (by-eye probe, leak-free plans)
Why: 8h validated the graph's internals; this measures whether it answers the per-room questions a harder test
may ask, against what the team ships today. Gold was written BY EYE (zoomed crops for every door/fixture call)
before any method ran, on dev plans from CubiCasa5K's official TEST list (so D8 leak-free).
Set v1 (development: 29 Qs, 8 plans) was used to find and fix failures; set v2 (confirmation: 14 Qs, 3 new plans)
was written after the fixes were frozen. Files: `experiments/r1/room_graph/probe/probe_v1.jsonl`, `probe_v2.jsonl`
(gold + how verified), `run.py answer|score`. Kinds: which room the sauna / walk-in closet / balcony / porch is
entered from; windows or doors of a named room; rooms with a toilet; rooms off the hall; largest room; summed
printed areas; total area.

Method "graph": `graph_text(room_graph(path, printed=True))` + the question → local Qwen3-VL-8B as a TEXT model
(no image), system prompt with a Finnish room-code glossary, JSON answer. ~1.4–1.6k tokens in / 60 out per
question + one cached VLM call per plan that reads printed areas (8e) + CC5K on CPU (cached, or ~3–10 s live).

| Method | v1 (dev, 29) | v2 (confirm, 14) | counts v2 | areas v2 | text v2 |
|---|---:|---:|---:|---:|---:|
| pipeline (night dde6347, default) | 17 | 6 | 1/4 | 1/3 | 4/7 |
| vlm_direct (base VLM, image) | 19 | 6 | 1/4 | 1/3 | 4/7 |
| VLM + image + my glossary/JSON prompt | 21 | 9 | 1/4 | 1/3 | 7/7 |
| **room graph + 8B text LLM (final code)** | **25** | **11** | **3/4** | **2/3** | 6/7 |
Paired (exact McNemar): v2 graph vs pipeline 5 right-only vs 0 (p = 0.062), vs vlm_direct 5 vs 0 (p = 0.062);
v1 vs pipeline 10 vs 2 (p = 0.039). Small n: the direction is consistent on both sets, the size is not pinned down.
Where it wins: windows/doors of ONE room (VLMs answer the whole plan's count or guess 2), "through which room is the
sauna entered" (6 such questions over v1+v2: pipeline 1/6, vlm_direct 1/6, graph 6/6; the VLM paths answer 'living
room' / 'master bedroom' from layout priors), sums of printed room areas.
Fixes made on v1 (generic, all listed as known failures in 8h before the probe): (1) the printed label's room kind
overrides the CC5K class when they disagree ('H' segmented as undefined → bedroom; CC5K class kept as
`cls_cc5k`); (2) printed areas attached to rooms (`printed=True`; also numbers inside labels such as
'MAKUUHUONE 13,1', which the area reader misses because there is no unit); (3) a region holding two printed room
areas is flagged `merged`; (4) the text says printed areas are exact and estimates ±50%. v1 went 22 → 25.
Remaining failures (v2): plan text rotated 90° → no printed areas or labels read → the LLM sums rough estimates
(37.5 asked, 44.5 answered; fix: retry the area reader on the rotated image when it finds nothing); LLM arithmetic
slips (12.5 + 12.0 → 24.0; route sums through a calculator, as W4's agent does); a toilet count of 3 for 2 by every
method (a shower read as a toilet); 'porch entered from' → entry (the porch door was not linked to the living room).
PITFALL found on the way (pipeline, not the graph): per-room counts get whole-plan answers. "How many windows does the
living room have?" → raster_cc5k's drawing count 3 (gold 1); "windows of the two bedrooms in total" → compose
parses windows + bedrooms = 6; "doors of the kitchen" → agent 2; "rooms that contain a toilet seat" → WC-room count 1
at conf 0.75. Confidence was ≤ 0.48 on all but the last, so calibration mostly held; the scope was lost.
How to use: an agent tool `room_graph(path)` → graph_text for cubicasa-style rasters whenever the question names a
room or a relation (of the kitchen / entered from / next to / opens onto / largest room / area of the bedrooms).
**Update (same cycle): wire-ready `solve()` and a third, untouched set.** `experiments/r1/room_graph/answer.py`
`solve(path, question) -> stoa.contract.Answer` (value, unit, provisional confidence, evidence = boxes of the rooms
used + the windows / doors / fixtures the question is about, image_px; trace; assumptions; missing). Changes after
v1/v2: the LLM lists the numbers to add and Python adds them, only when its own value is within 10% of the sum (an
arithmetic slip; a bigger gap = another basis such as a printed apartment total, kept); KHH is a utility room, not a
bath (my naming map had it wrong); the area reader, when it finds no area with a unit, also tries unit-less numbers
and the image turned 90° each way and keeps the orientation with the most areas (tie → turned), items flagged
`unitless` (conf 0.6 instead of 0.85). Scoring made stricter for every method: an answer naming a different room that
shares the type word ('bathroom (KHH)' when the sauna opens to PH) is wrong — this moved graph v2 from 11 to 10.
| Set | solve() | pipeline | vlm_direct |
|---|---:|---:|---:|
| v1 (dev, 29) | 23 | 17 | 19 |
| v2 (used to debug solve(), 14) | 11 | 6 | 6 |
| **v3 (untouched confirmation, 11 Qs / 3 new plans)** | **8** | 4 | 4 |
| all 54 Qs / 14 plans | **42 (78%)** | 27 (50%) | 29 (54%) |
v3: 4 vs 0 discordant (p = 0.125). All 54: vs pipeline 18 vs 3 (McNemar p = 0.0015), **+27.8 pts, 95% plan-cluster
bootstrap [+15.4, +41.4]**; vs vlm_direct 16 vs 3 (p = 0.004). v1/v2 were used for development, so the pooled gain is
optimistic; v3 alone agrees in direction. Cost per question: one local 8B text call (~1.5k tokens in) + the plan's
area reads (1 cached VLM call, 3 when nothing with a unit is printed) + CC5K on CPU; $0 hosted.
v3 misses (all methods): the balcony door of a bedroom that also opens to the living room (all say living room); a
closet entered from the hall (solve says bedroom); upper-floor bedroom areas on a two-storey sheet (graph has no
floor split: 25.0 for 36.5).
**Final version (night-R1, this commit):** prompt asks for the label quoted in the graph (no invented codes: it wrote
'bathroom (KPH)' where the plan prints PH) and internal ids are stripped from text answers ('(R9)' → the room's
label or nothing). Same cached LLM calls otherwise. Scores: v1 24/29, v2 12/14, v3 7/11 (ed6489a had 8/11 on v3:
one balcony answer flipped from living room to bedroom, LLM wobble) → **43/54 (80%) vs pipeline 27/54, +29.6 pts
[+18.5, +40.7], McNemar 19 vs 3 p = 0.0009; vs vlm_direct 17 vs 3 p = 0.003**; v3 alone 3 vs 0 (p = 0.25).
Read: a robust direction over 14 plans, a size between ~+15 and +40 points; v3 is too small to confirm on its own.
NEGATIVE (same cycle): splitting a sheet into its separate drawings (two floors side by side; components of the
dilated footprint ≥ 15%: 6007 and 4828 split 52/48 and 57/43, single plans 99–100%) and prefixing each room line
with [A]/[B] + "the ground floor normally has the entrance and kitchen" fixed no probe answer and broke 2 on the one
two-storey v3 plan (4828, whose segmentation also merges TYÖH + KHH + LH into one region). Kept in the graph dict
(`parts`, `room['part']`), off in graph_text (show_parts=False). Per-floor questions need a floor label reader
('1 KRS' / '2 KRS', 'upper floor') and better segmentation first; n = 2 plans is too few to tune on.

### 8j. Routing per-room questions to the room graph inside the pipeline (untouched probe v4 + live pipeline run)
Why: 8i showed the room graph answers per-room questions the pipeline answers at whole-plan scope; this decides
WHICH questions to hand it and measures the change inside the real pipeline (night 528cadd), not by simulation.
**Trigger** `experiments/r1/room_graph/route.py` `per_room(question, path)` → `{fire, fire_any, area, kind, why}`:
regexes for a room as owner ("windows of the kitchen", "does the bathroom have"), relations (entered from, opens
onto, next to, share a wall, "A and B adjacent", reachable without), locate ("which room has the bathtub", "where's
the toilet"), superlatives ("largest bedroom"), plus a few fi/de/fr/sv/it forms (not translated by the front end).
"number of balconies in this drawing" / "(kitchen and bathroom combined)" stay whole-plan. Raster files only.
False fires (`route_eval.py`): **0 raster-gated fires on all 127,044 dataset questions and on smoke / dev / hard /
hard2 / hardL_open / cc5k_heldout / train_gate** (text-only fires exist on swiss / ifc wordings, gated out by file
type), so wiring it cannot move any existing score. Recall: route_probe.txt (written before the trigger ran) 25/26 →
26/26 after fixes; route_probe2.txt (untouched, 42 fresh wordings) **19/24 recall, 0/18 false** before its own fixes
(24/24, 0/18 after).
**Untouched probe v4** (`probe/probe_v4.jsonl`, committed 3949e0e BEFORE any solver ran): 24 by-eye Qs on 6 fresh
plans from CubiCasa5K's official test list that are in neither our train nor test split (2 are two-storey sheets);
15 ask for printed room areas, 9 are relations / per-room counts.
| v4 (untouched) | relations + per-room counts (9) | printed room areas (15) | all 24 |
|---|---:|---:|---:|
| pipeline (night 528cadd) | 2 | 8 | 10 |
| vlm_direct | 3 | 8 | 11 |
| room_graph solve() alone | **8** | 2 | 10 |
| **pipeline + route (areas excluded)** | **8** | 8 | **16** |
So the room graph wins scope and relations but LOSES printed-area questions (2/13 when routed): its area reader's
VLM boxes put printed numbers into the wrong regions (1264: eight '1.5' values attached to the hall; 9976 two-storey:
most printed areas unattached), while the pipeline's VLM reads "HUONE 22 11,5" next to the label directly. Hence
**fire = room-scoped AND not an area question** (`AREA_Q`: area/size/how big/m²/fläche/pinta-ala/superficie…).
**Live run** (`pipeline_rg.py` registers `pipeline_rg` = Pipeline + the route; standard `stoa.eval`, leaderboard
lines `pipeline_rg-probe_v*`): all 78 by-eye probe Qs / 20 plans: **54/78 vs pipeline 37/78, +21.8 pts [+8.2,
+35.1] (plan-cluster bootstrap), McNemar 22 vs 5 p = 0.0015**; untouched v4 alone 16 vs 10 (6 vs 0, p = 0.031).
Evidence on 7.7% → 67.9% of answers; cost $0.077 → $0.228 per 1k (one more local 8B call, ~1.5k tokens; $0 hosted);
per-room counts now attach only the counted windows/doors (each note names its room) so "located items = answer".
The 5 lost: 3 real (v1 dev: bathroom doors 1 vs 2; 'largest room' → bedroom; balcony accessed from 'entry'), 2
pipeline run-to-run noise on questions the route does not touch.
**PITFALL found:** the hook must sit in `Pipeline.solve` after the language front end and BEFORE `decompose()`: the
composer splits "How many windows do the two bedrooms have in total?" into "windows on this plan" + "bedrooms" = 6
(gold 2), so a hook in `_solve_atomic` never sees the room scope (2 probe Qs lost that way in the first live run).
Limits: n = 78 by-eye Qs on 20 plans written by one person; confidence is still a rule (capped at 0.75 in the
wrapper). Next for areas: attach printed areas from an OCR text layer (W3's) instead of VLM boxes.
**Addendum (same cycle): OCR text layer as the graph's source, and an area cross-check.** W3's tiled text layer
(`stoa.solvers.raster.textlayer`, VLM text spotting per 1100 px tile) gives tile-accurate boxes for every label and
printed number (1264: OLOHUONE 17,0 / KEITTIÖ 14,5 / HUONE 11,5 / LH 3,0 all in the right regions, where the
whole-image reader had put eight '1.5' values in the hall). `room_graph(..., textlayer=True)` /
`solve(..., textlayer=True)` (env `R1_RG_TEXTLAYER=1`) takes labels and printed areas from it, so plans without a
cached label read (hidden test plans) get labels too. solve() with it: relations / per-room counts 45/53 vs 43/53
(noise), routed area questions 9/18 vs pipeline 7/18 vs old solve 5/18; all area questions 10/23 vs pipeline 11/23 —
a tie, so areas still stay with the pipeline. But the two disagree informatively: **when the pipeline's area and the
text-layer graph's area agree (2%), the pipeline was right 6/6; when they disagree, 5/17.** `pipeline_rg
area_xcheck=1` (`area_crosscheck()`): room-scoped area question → pipeline answers → graph cross-check; agree → the
graph's room box (+ printed value) as evidence and conf ≥ 0.75, disagree → conf ≤ 0.3 and "the room graph reads X m²"
in `missing`; the value never changes. Live on all 78: area answers right 11/23 both ways, **evidence 0 → 6, conf ≥
0.7 on 6 (6 right), area AUROC 0.51 → 0.88** (all Qs 0.69 → 0.74). Cost $0.228 → $0.523 per 1k on this mix (one
text layer per plan, ~3–7k tokens in, up to 5k out; local). n = 6 agreements: the direction is clear, the 0.75 is a
guess. `xcheck_eval.py` reproduces the table. Text-layer PITFALL: 9 of 20 CubiCasa tiles hit the 2,500-token cap
and 1841 came back with 3 items (a loop), so dense plans lose labels at the end of the list.
NEGATIVE (exploratory, same cycle): per-floor questions on two-storey sheets cannot lean on printed floor titles —
the OCR text layer finds one on 1 of 4 two-storey probe sheets ('1 KRS' on 6007; none on 4828, 5046, 9976). A floor
split needs layout cues (entrance door, stair position, which part holds the kitchen), not text. Latency note for the
demo: a cold text layer took 6–165 s per plan with the GPU saturated (1–2 tiles, up to 2,500 tokens out per tile).
**Addendum (cycle 244): the combined build.** night-W4 4d4187f (per_room route before the composer) merged with
night-W3 ac981b3 (text mode for CubiCasa non-count Qs) and night-R1: 54/78 overall, but area 9/23 with 15 at conf ≥
0.7 and only 6 right (9 confident-wrong: room_graph's in-atomic area fallback '19.5 m²' / 'bedroom' @ 0.70, W3 text
mode's wrong printed number for 'largest bedroom' / 'sauna' / sums @ 0.75). Applying `area_crosscheck` offline
(`xcheck_sim.py`, graph values from the logged traces, plus a new cap for non-numeric answers to area questions):
conf ≥ 0.7 on 4 (all right), area AUROC 0.56 → 0.76, accuracy unchanged. W3's text mode and my text-layer graph read
the same OCR layer, so their agreement is not fully independent; still 4/4 agreements were right here.

### 8k. Questions ABOUT the links: a project knowledge graph that answers, not only cross-checks (measured)
Stoa point 4 says linking data earns points; Q's red team (v17, KNOWLEDGE 08:47) showed the obvious follow-up
questions a judge asks after seeing "drawing 46 = model 46 ✓" all fail: "do the plan and the model agree on the
windows of '1.korrus'?" → a bare 55, "how many windows are in the model but not drawn?" → 297 @ 0.98 (whole model),
"how many floor plan sheets?" → 1, "which sheet shows the server room?" → "no sheet information".
Method (`experiments/r1/kg_qa/kgqa.py`, read-only over W1's `stoa.kg.project_graph`): the project graph becomes
numbered fact rows — F = files (plan / section / elevation sheets with their storey, model, discipline models, same
building in ifc_bench), S = storeys (elevation, plan sheet or NONE, model door/window/room counts), C = W1's
cut-plane comparison per storey (model, cut by the 1.2 m plane, drawn on the sheet's SVG twin, drawn from other
storeys; "UNKNOWN" when the twin tags no such class), R = rooms (name, storey, area, plan, pdf_pt box; only rooms
sharing a token with the question are shown). Sheet counts / 'is there a section' are answered in Python with no
model call; everything else is ONE local text call returning {op, rows, a, b} (count_rows, lookup_storey /
lookup_sheet, agree, diff, greater, list_storeys, exists, none) and Python computes the value from the cited rows
(W2's 'point at rows' method). Yes/no questions never get a diff (op is coerced). Agree answers carry the reason:
"no (IFC model 55 windows on '1.korrus', plan draws 52; the other 3 lie entirely above/below the plan's 1.2 m section
plane, so the drawing is consistent with the model)". Evidence = the room's box on its sheet, or the sheet files.
Trigger `is_link_question()` (en/de/fi/fr/sv/it/nl forms: plan-vs-model agreement words, 'how many <sheet noun>',
'which <sheet noun> shows', storeys without a plan / without rooms, 'another dataset', 'on which floor is <room>'):
**0 fires on all 127,044 dataset questions and on every open split** (dev, hard, hard2, hardL, smoke, train,
train_gate, unused, cc5k_heldout); recall 20/21 on the fresh probe, 8/8 on v17's link rows.
Probe (`probe_kg.jsonl`, 21 Qs on 6 non-test IFC projects in EN/DE/FI/FR; gold from file names, the IFC index and
the SVG twins' data-guid counts, independent of stoa.kg; committed 798069f before any run). Wrapper `pipeline_kg`
(Pipeline + kg_qa when the trigger fires on ifc_models/ifc_bench; no value → the normal pipeline):
| probe | pipeline | pipeline_kg | conf ≥ 0.8 (pipeline → kg) | tokens/Q |
|---|---|---|---|---|
| fresh probe_kg (21) | 4/21 | **20/21** (16 won / 0 lost, McNemar p < 0.0001) | 4 @ 0 right → 17 @ 17 right | 4,332 → 1,970 |
| Q v17 (9, used while building) | 2/9 | **9/9** (7 / 0) | 2 @ 1 right → 9 @ 9 right | 3,325 → 2,223 |
Runs: 20261114-085547-pipeline-probe_kg-f75d / -090314-pipeline_kg-probe_kg-6ea6; -085617-pipeline-v17-0ec1 /
-090327-pipeline_kg-v17-1eeb (pipeline = merge-tree archive of W4 4d4187f + W3 ac981b3 + R1; pipeline_kg = night-R1).
stoa.eval leaves text answers unscored, so `compare.py` scores with the probe's regexes. Honest limits: one author
wrote both the probe and the system (wording bias; the trigger is a regex list), n is small, IFC only (Swiss
PDF↔DXF↔PNG and raster↔IFC links are not covered), and the one miss is "does the 'UG2' plan show doors the model
does not assign to 'UG2'?" (drawn_other). Note the gdynia/warmond plan twins tag only IfcSpace: there the C rows
say UNKNOWN and kg_qa answers with conf 0.2 + a 'missing' line instead of claiming agreement.
**Robustness on wordings R1 did not write (same cycle).** The local LLM rewrote each of the 29 link questions 3× in
English and once in each of fi/de/fr/it/sv/nl/et/es (318 rows, gold unchanged, `probe_para.jsonl`, committed before
scoring; `paraphrase.py`). The first regex trigger caught only 48% (fi 7%, it 10%). Broadened with language-general
signals — a model word AND a plan/drawing word in one question (0 of 127,044 dataset Qs have both), a drawing-set
phrase, 'which drawing/sheet/feuillet/foglio/ritning/hoja', plural storeys + a negation + a room word — tuned on half
A (by original question) and tested on half B: **trigger recall on held-out B 42/153 → 126/153 (+ the to_english
front end for sv/nl/et/es: 133/153), still 0 false fires on 128,535 dataset + open-split Qs; kg_qa right on B 114/153
(75%) with 106/115 confident answers right.** Then four general fixes after looking at errors on both halves
(in-sample from here): room retrieval by name-token prefix ('Serverraum' ↔ SERVER) and all rooms when nothing matches
(≤80 rooms), the specific sheet kind beats the generic 'plan' word ('plans de coupe'), yes/no detection without a
count cue + 'all/every/aligned' → agree, deterministic storey lists: **258/318 = 81% right, conf ≥ 0.8 on 244 with
232 right (95%)**; by language en 91%, fr 97%, de/es/sv 90%, nl 83%, it 62%, et 59%, fi 50% (fi/et/it misses are
mostly the trigger on poor machine translations: 'kerrosluokka', 'paperi'). Fresh probe_kg after the broadening:
20/21 again (kg21 now fires and is answered 'no' @ 0.8: the drawn-from-another-storey case stays the known miss);
v17 9/9. Runs -091809-pipeline_kg-probe_kg-624b, -091829-pipeline_kg-v17-2f7f.

**8j addendum (cycle 244): per_room trigger on wordings R1 did not write.** The local LLM rewrote the 78 probe
questions 3× in English + once in fi/de/sv/fr/it/nl/es (780 rows, `probe/probe_para.jsonl`, committed before scoring;
`para_route.py make|score`, trigger as asked, then after the to_english front end for uncovered languages). Recall
on the 73 originals that fire: non-area `fire` 68% overall (en 80%, de 58%, fr 57%, it 58%, nl 25%). Added
language-general forms — compound room-noun suffixes (Technik*zimmer*, utility*kamer*), per-room counts with
'hat/ha/heeft/tiene/a + det + room', 'y a-t-il dans / ci sono nella / zijn er in / hay en', relation question words in
6 languages ('van welk vertrek', 'par quelles pièces', 'da quale stanza', 'desde qué habitación', 'from what room'),
per-room area forms, AREA_Q in 8 languages — tuned on half A (by original question): **held-out half B non-area fire
65% → 78% (A 71% → 87%), still 0 text fires on 85,514 dataset CubiCasa questions** (route_eval.py; other sources stay
behind the raster + cubicasa gate). End to end on 40 routed non-English half-B paraphrases: room_graph 33/40 vs 36/40
for the same questions in English (4 lost / 1 won: balcony/terrace access, the known relation failure); conf ≥ 0.7 on
30 (25 right). Since W4's pipeline imports `experiments.r1.room_graph.route.per_room`, this lands with the merge.
**8k addendum: before/after on current night (31397eb + R1, W1's in-ifc link answers included) and Q's v20.**
| probe | night pipeline | pipeline_kg | conf ≥ 0.8 (night → kg) |
|---|---|---|---|
| fresh probe_kg (21) | 9/21 | **21/21** (12 won / 0 lost, p = 0.0005) | 7 @ 3 right → 20 @ 20 right |
| Q v17 (9) | 7/9 | 9/9 | 5 @ 5 → 9 @ 9 |
| Q v20 (19, Q's own new wordings/models) | 6/19 | **19/19** (13 won / 0 lost) | 6 @ 4 → 18 @ 18 |
Runs 20261114-092552-pipeline-{probe_kg-4e8a,v17-2f04,v20-c62a} vs -092552-pipeline_kg-{probe_kg-0902,v17-6ebe,v20-5fb5}.
v20 caveat: its first run on b44392a was 12/19; the trigger broadening was done before I saw v20, but the sheet
formatter fix (3 confident misses where the text said 'no plan sheet' while the evidence was the sheet) came from
it. Night's 4 confident-wrong answers on probe_kg all come from ifc as asked (sheets in total → 4 @ 0.85; FR 'même
nombre de portes' → 18 @ 0.97; 'more windows on DG1 than the plan shows' → 'no (36 = 36)' @ 0.89; 'storeys with no
rooms' → a room name @ 0.90), so kg_qa must run BEFORE ifc on a link question, not as a fallback after it.

### 8l. Link questions: comparatives, two-part questions, storey roles, 'this sheet' (measured, cycle 21)
Q's v23 round and W1's c8_cmp probe found four ways kg_qa (routed FIRST for link questions since W4 1b831ed) was
confidently wrong. All four are about reading the QUESTION, not the graph, so the fixes are deterministic and the
LLM's role stays "cite the rows":
1. **Comparatives have a direction.** "Does this plan show fewer windows than the IFC model has on the same storey?"
   was answered with the 'agree?' polarity ("no: 55 vs 52"), because 'same' (in 'the same storey') matched the
   agree words. Now: 'more/fewer … than' in en/de/fi/fr/sv/it/nl/es/et → subject = the side (plan/drawn/here vs
   model/IFC/BIM) named before 'than' (or, if neither, the opposite of the side after it) → yes iff subject {>,<}
   other, Python on the cited C row. 'the same storey/floor/Geschoss …' is removed before the agree test.
2. **Two-part questions** ("Which storey does this sheet show, and does its door count match the model?";
   "Are some BIM windows missing on this sheet, and if so how many?") split on ', and/und/ja/et/och/e/en/y' + a
   question word; each part is solved alone (the second one sees the full question with "answer ONLY its last
   part"), answers joined with '; ', confidence = min; one part unanswered → the other at ≤ 0.5 + missing.
3. **'this sheet' pins its storey.** When the question says this plan/sheet/drawing/here and names no other storey,
   a C row of another storey is swapped for the same element's C row of the sheet's own storey ('windows in the 3D
   model that this sheet does not draw' had cited 2.korrus 60 vs 53; right by luck).
4. **Storey ROLE words** (W1's PITFALL 09:36) use W1's `parse._GROUND_Q / _GROUND_NAME / ground_reference` (+ a
   basement rule: a storey named KG/UG/Keller/basement, else the first storey below −1 m with rooms) and add a hint
   row "[H1] 'ground floor' = storey 'EG'"; a 'which sheet' lookup that cites another storey is redirected.
Guards: when the LLM cites no C row on a yes/no plan-vs-model question, the storey (quoted / role / this sheet's) +
the element word pick the row; 'Can you tell me how many …' is a count, not a yes/no; a 'how many' question is never
answered by a storey/sheet lookup (c8: 'How many walls are there on the ground floor?' → 'EG' @ 0.85 standalone);
sheet enumerations 'plans, sections and elevations' keep the plans; two-storey differences ('How many more doors on
'1.korrus' than on '5.korrus'?') subtract the two storeys' model counts (was model − drawn of one row = 0).
New trigger rule 'model vs drawn' ('… than are drawn here'): **0 fires on 128,535 dataset questions** (trigger_eval.py).

| probe (pipeline end to end, same code before/after) | before | after | conf ≥ 0.8 wrong |
|---|---|---|---|
| Q v23 (21, Q's wordings) | 18/21 | **21/21** | 3 → 0 |
| R1 r1v5 (15, gold committed 8368fe2 before any run) | 11/15 | **15/15** | 3 → 0 |
| W1 c8_cmp (22, W1's comparatives; base = W1's own run) | 19/22 | **22/22** | 3 → 0 |
| pooled | 48/58 | **58/58** (10 W / 0 L, McNemar p ≈ 0.002) | 9 → 0 |
Standalone kg_qa: probe_kg 21/21 (kg21 'doors the model does not assign to UG2' now right), v17 9/9, v20 19/19;
318 LLM paraphrases in 9 languages 258 → **272/318**, conf ≥ 0.8 244 @ 232 right → **247 @ 246 right** (the one left:
Dutch 'hoogteplannen'). Cost: +8% tokens/Q on link questions (two-part questions make 2 calls). dev/hard/hard2 are
unchanged by construction (the trigger fires on none of their questions). Runs: artifacts/eval/20261114-102506-…-
probe_v23q-5ac3 → -103309-…-e4e5; -102517-…-probe_r1v5-b5eb → -103327-…-0369; -102051-…-c8_cmp-05db → -103343-…-9092;
score with `python experiments/r1/kg_qa/compare.py PROBE A B`. Code: experiments/r1/kg_qa/kgqa.py (night-R1 a07af69).
Honest caveat: v23's three misses were seen before the fix (in-sample); r1v5 and c8 are the out-of-sample evidence,
and c8 was written by W1 for the same bug class, so the classes are known, the wordings were not.
Still open: Swiss PDF↔DXF↔PNG and CubiCasa link questions ('Is there an IFC model for this plan?', 'do this plan and
its DXF agree on doors?') — facts() returns [] for non-IFC files, so kg_qa abstains and the pipeline answers (right
on v23 at 0.30–0.45). Finnish/Italian/Estonian trigger recall 54–79% on paraphrases.

### 8m. Estimate, don't refuse: out-of-drawing questions (measured end to end; NOT wired, a post-noon option)
Stoa point 3. Q's audit (KNOWLEDGE 09:16): the pipeline answers rent / occupants / price / construction cost /
U-value / construction year / energy questions with the string "unknown" @ 0.25. `experiments/r1/estimate/
estimate.py`: `kind_of(question)` (en/fi/sv/de/fr/it/nl/et/es; questions that STATE their own rate are not ours —
those are derived quantities) and `solve(path, question)` = a quantity the drawing DOES hold (dwelling area from DXF
rooms / IFC spaces / CubiCasa room graph; bedroom count) × a published reference rate for the dataset's country,
with the rate's range as the interval, assumptions and 'what would settle it' in `missing`, evidence = the rooms
summed, confidence ≤ 0.2 by construction, 0 LLM calls. `pipeline_est.py` = Pipeline + this route (CubiCasa/Swiss:
estimate first; IFC/sheets/scans: pipeline first, estimate only when that gives None / not a number / < 0.3 without
evidence; text-judged sources get a sentence "Not recorded in the model; estimate ~ …").
End to end on probe_e2e.jsonl (107 rows, Q-style; runs artifacts/eval/20261114-103519-pipeline-probe_e2e-65ce vs
-103949-pipeline_est-probe_e2e-d933, `python experiments/r1/estimate/compare.py A.jsonl B.jsonl`):
| 101 out-of-drawing rows | pipeline | pipeline_est |
|---|---|---|
| bare 'unknown' / None | 16 | **0** |
| a number or a flagged estimate | 55 | **100** |
| answers at conf ≥ 0.5 (should be few: nothing is read) | 20 | 11 |
| LLM calls / tokens / wall | 328 / 787k / 1021 s | **180 / 492k / 254 s** |
The 6 'states its own rate' rows: 0 values changed. Trigger: **1 fire on 127,044 dataset questions** (ifc_bench
duplex_mep 'What is the predicted annual energy consumption?', gold 'This information is not available in the BIM
model.' — the IFC route answers first, the estimate only as the sentence fallback) and 0 on 1,491 open-split rows.
No accuracy number exists for these (no gold); what it buys is Stoa's 'no bare refusal' + cost. Wiring = ~10 lines
in Pipeline._solve_question after the link route (W4); deliberately not before the 11:10 freeze (D22: no new
subsystems). Decide after the noon reveal if Stoa's hidden kinds include out-of-drawing questions.
**8l addendum (10:58, night-R1 c1bcf5c): uploads, file existence, Q v27.** (a) A renamed/uploaded sheet next to its
model ('A101.pdf', F's hashed copies) was no plan node in stoa.kg (it globs '{model stem}_*.pdf'), so kg_qa had no C
rows; facts() now adds one with W1's plan_storey (title, else GUID tags) + W1's _cut_compare → Q v26_hash 4 W / 0 L,
kg_qa answers 28 link Qs instead of 2 (runs -103316-…-531d → -103800-…-989b). (b) 'Is there an IFC / 3D / DXF model
for this drawing?' on files with no project graph → yes/no from the linked files (r1v6_files 6/6 @ 0.85 standalone;
no pipeline effect yet: _link_question admits only IFC sources). (c) Q v27 (Q's wordings, Q's scorer): comparatives
9/9 held; imperative second parts ('… and say how many …') split; 'how many X does the model have there' read from
the storey's C row; 'fewer doors drawn here than the model' and it/es/sv/nl/et 'not drawn' fire → 2 W / 0 L
(-103938-…-b9d0 → -105146-…-58c1). Every trigger change re-checked: 0 / 128,535 dataset questions.

### 8n. Integration check on night b656826 + a noon triage kit (cycle 22, 11:05-11:15)
**Link probes on the merged build** (night b656826 = every agent's final answer-changing head; pipeline end to end):
| probe | base (cycle 21 run) | night b656826 | conf ≥ 0.8 right | tokens/Q |
|---|---|---|---|---|
| R1 r1v5 (15) | 15/15 | **15/15** | 15/15 | 3214 → 3212 |
| Q v23 (21) | 21/21 | **21/21** | 18 → **21** | 4087 → **2353** |
| R1 probe_kg (21) | 20/21 (09:31 run) | **21/21** | 17 → **20** | 2983 → **1829** |
| R1 r1v6_files (6) | 6/6 (standalone) | **6/6** | 0 → **6** (evidence 0 → 6) | 9434 → **0** |
| W1 c8_cmp (22) | 22/22 | **22/22** | 18 → **22** | 2460 → 2162 |
| Q v27 (23; base run had 14 rows) | 14/14 | **23/23** | 20/20 | 3664 → 2239 |
| W4 file_exists (14) | 14/14 | **14/14** | 12/12 | 190 → 190 |
| **total** | | **122/122, 0 wrong at ≥ 0.8** | | |
W4's GlobalId check (W1 plan_vs_model, 0 LLM) raises the share of answers at ≥ 0.8 (it agrees with kg_qa → ✓) and
cuts tokens on v23q/probe_kg by ~40%. W4's file-subject gate makes 'Is there an IFC model for this drawing?' cost
0 tokens. Runs: artifacts/eval/20261114-110451-…-probe_r1v5-ee65, -110519-…-probe_v23q-1a9c, -110540-…-probe_kg-d67d,
-110605-…-probe_r1v6_files-f489, -110606-…-c8_cmp-5370, -110624-…-v27-1865, -110641-…-file_exists-399f.
Scorer fix: experiments/r1/kg_qa/run.py correct() now reads Q's `meta.items` (every regex must match). Before the fix
it marked 3 right v27 two-part answers as wrong.

**Noon triage** (experiments/r1/noon/, README there): `triage.py EXAMPLES.jsonl` = for each question, with 0 LLM
calls and in ~10 s, the source, W4's intent parse, train-template hit, compose plan, R1's triggers (link / room /
estimate), the nearest train+dev question (TF-IDF over words + char 4-grams; test is never read) and where a fix
would go (stoa/router/README.md §3). NEW = nearest < 0.5 and no train template. Calibrated (`calibrate.py`): NEW on
dev 14%, hard 33%, hard2 77%, Q's red team 70%.
**Negative result: novelty does not predict failure** (`triage_vs_run.py RUN`, Q's rescore for text rows):
| split (run) | NEW acc | seen acc | what does predict it |
|---|---|---|---|
| Q red team (snap12, 973 scored) | 95.4% (453) | 78.3% (520) | CubiCasa seen 68.7%, 'unknown' (uploads) 72.4% |
| hard (c43 gate, 688) | 87.3% (157) | 84.9% (531) | CubiCasa 63.9-68.8%, Swiss/IFC 99-100% |
| hard2 (c43 gate, 189) | 97.4% (116) | 83.6% (73) | CubiCasa seen 76.0% |
The team has worked on these rows all night (they are in-sample for the fixes), and the weak part is a source, not
a wording: CubiCasa raster counts. So NEW tells you where to write probes, and it must not become a confidence cap.
Small-sample rule for Stoa's examples (exact McNemar): a fix needs ≥ 6 W / 0 L (p = 0.031) or 8 W / 1 L (p = 0.039);
15/20 right = 75% [53, 89] Wilson. Write 5-10 rewordings per example (Q's redteam/from_examples.py) so that a fix
can be tested at all.
**8m re-check on night b656826 (11:13):** pipeline_est on probe_e2e (run -111321-pipeline_est-probe_e2e-7c2c vs
-103949-…-d933): out-of-drawing rows 0 'unknown'/None, 100/101 a number or flagged estimate, conf ≥ 0.5 on 10 (11),
177 LLM calls (180), 477k tokens (492k); the 6 rate-stated rows: 0 values changed. So the post-noon option still runs
unchanged on the final build. Gap found with triage: kind_of misses renovation costs ('What would it cost to repaint
all walls on this floor?'). That is a derived quantity (wall area × a rate), so it belongs in the agent, not the estimate.

### 8o. Repaint cost as an estimate kind (cycle 23, 11:20-11:30; NOT wired, same post-noon option as 8m)
Correction to the 8m note above: a repaint question is derived (wall area × rate) only when it STATES the rate
("… at 12 €/m²"; `_STATED` keeps those out, so the composer/agent answers them exactly). Without a rate, the rate is
out-of-drawing like a rent rate, so it belongs in the estimate route next to rent/price.
- `experiments/r1/estimate/estimate.py` kind `repaint`: a cost/price word within 60 characters of a paint word, 9
  languages (en/de/fi/fr/it/sv/nl/es/et), placed before `construction_cost`.
- Value = floor area (the same `dwelling()` read as rent: IfcSpace sums per storey, DXF room polygons, CubiCasa room
  graph; else a typical dwelling) × painted surface per floor m² × a painter rate per m².
  Wall surface per floor m²: for square rooms of a m², 2.6 m high, ~12% openings, 4·2.6·√a·0.88 / a = 9.15/√a, which is
  2.9 at 10 m², 2.4 at 15, 2.0 at 20 and 1.8 at 25 → 2.4 (range 1.8–3.2), now 2.6 (1.6–4.0) after the IFC check below. Tiled wet rooms are left out. 'ceilings' adds
  1.0 × floor area. If no surface is named, walls only (stated as an assumption).
  Rates (labour + paint, 2 coats) are **rules of thumb, not cited statistics**, and they are labelled "assumed": FI 15
  (10–25) EUR/m², CH 30 (20–45) CHF, US 30 (15–55) USD, EU 15 (8–30) EUR. Rounded to 100, conf 0.1, and `missing`
  says what would settle it (a quote or a stated rate, plus the real wall areas).
- Checks: 0 repaint fires on 141,343 questions (all 127,044 dataset questions + open splits + W4/F derived sets + Q's
  red team; the only fire is the old energy one). 11/11 positive and 5/5 negative wordings in
  `experiments/r1/estimate/probe_repaint.txt`. Those wordings are IN-SAMPLE (I wrote them together with the regex).
  One drawing per source gives sensible values (CubiCasa 106 m² → 3,800 EUR; Swiss 304 m² floor → 21,900 CHF walls,
  31,000 walls + ceilings; IFC storey 325 m² → 11,700 EUR; HABS/finna without an area → a typical dwelling, wide range).
- IFC check (11:23, `experiments/r1/estimate/wall_factor_ifc.py`, W1's ifc solver, 11 ifc_models projects in 150 s):
  R = total wall net side area (one face) / total IfcSpace area: median 1.91, IQR 1.23–2.80. Range over projects 0.59
  (gym hall) to 4.45 (warmond). Residential: duplex 2.06, fzk-haus 1.10, smiley-west 1.83, esplanades 1.91. Painted
  surface ≈ 1.5 R (interior walls are painted on both faces, exterior walls on one) → median 2.9, IQR 1.8–4.2. Several
  wall sums are the solver's fallback at conf 0.41. **WALL_PER_FLOOR is now 2.6 (1.6–4.0)** (was 2.4 (1.8–3.2)): between
  the geometry and the IFC median, with the range widened to the measured IQR. n = 11, mostly non-residential, so
  this is a sanity check, not a fit.
- Done (cycle 24, bf5de18): on an `.ifc` path with whole-model scope, repaint now uses the model's net wall side area
  (W1's ifc solver, 'total net side area of all walls', accepted at conf ≥ 0.3, 0 LLM) × FACES_PER_SIDE 1.5 (1.2–1.9),
  + ceilings = floor area when asked; the floor-area factor stays the fallback. Coverage over one file per IFC project
  (345 files, 200 s): measured on 11 (gdynia, vitoria, warmond, clinic, duplex, esplanades, gymzaal, molio, fzk-haus,
  institute, smiley-west); the other 334 (324 resbim + barlad, frigento, chesapeake, …) have neither walls nor IfcSpace
  areas the solver reads, so they get the typical-dwelling fallback (90 m², 3,500 EUR, range 600–19,400). Esplanades:
  8,227 m² one face → 12,341 m² painted (the floor factor gave 11,190) → 185,100 EUR (79,000–469,000), conf 0.1.
  Known limits: 'on this floor' on an `.ifc` path is still the whole model (dwelling() already did that for floor area,
  and the assumption text says 'the whole model'); a per-storey wall sum needs W1's ifc storey filter. No gold exists, so
  this is a sanity check, not an accuracy claim.
