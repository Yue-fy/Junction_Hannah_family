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

19% of dev outputs looped; fixing that is the next lever. Cost: ~2.1k tokens in and ~570 out per
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

## 3. Symbol counting on raster plans (method, to be measured by W3)

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

### 8c. Linked data as a cross-check
- Swiss: the same floor exists as DXF + PDF + PNG. Fit the affine map DXF→PDF (and PDF→PNG) once per
  drawing by least squares on matched points, e.g. ROOM_TEXT insertion points ↔ PDF text spans with the
  same string: `[u v]ᵀ = A [x y]ᵀ + t`, 6 unknowns, ≥ 3 matches, solved with `numpy.linalg.lstsq`. Then
  every DXF-derived count or area gets evidence boxes on the PDF and PNG for free. A VLM count on the PNG
  that agrees with the DXF count raises confidence; a disagreement goes into the trace.
- ifc_models: the PDFs were rendered from the IFC. Room names printed in the PDF ↔ `IfcSpace.Name/LongName`
  gives the same link, and the drawing count can be checked against the IFC count.
