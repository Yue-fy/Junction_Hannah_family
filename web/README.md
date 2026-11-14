# web/ — Blueprints Talk demo

Ask a question about a drawing or an IFC model. The answer card shows the value, confidence, cost, the
reasoning steps, assumptions, what is missing, and the evidence list. The evidence is drawn on the 2D
sheet (PDF.js / image) and highlighted in the 3D IFC model (web-ifc + three.js). For `ifc_models` sheets,
both views are linked through IFC GlobalIds: click a room or door on the drawing to see it in 3D, and the
other way round.

## Run

```bash
cd web
npm install
npm run dev          # http://localhost:5173 (Vite, port 5173)
```

- `STOA_DATA` must point at the dataset root (default: the team path in `AGENTS.md`).
- `/api/*` goes to W4's API (`STOA_API_URL`, default `http://127.0.0.1:8100`, see `docs/CONTRACT.md`;
  start it with `$JUNCTION_VENV/bin/python -m uvicorn stoa.api:app --port 8100` from the repo root).
  If that server is down, the dev server answers from a **mock** (`mock/stoaApi.ts`): files and example
  questions come from the dataset, `/ask` replays `fixtures/recorded.json` (live answers recorded with
  `fixtures/record.py`) and then `fixtures/answers.json`. The badge in the top-left says `API live` or `API mock`.
- `/api/kg` (knowledge graph): the API's `GET /kg` if it has one; otherwise the dev server runs W1's
  `stoa.kg.links(path)` itself with `$JUNCTION_VENV/bin/python` from the repo root (`STOA_KG_REPO=<checkout>`
  to use another checkout); if that fails too, it links files by name only (the panel title says "files only").
- `npm run build` type-checks and builds to `dist/`. `npm run preview` serves the build with the same
  `/api` middleware (no separate server needed).

Deep links: `/?file=<dataset-relative path>&q=<question>` opens a file and asks right away, e.g.
`/?file=data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf&q=How many doors are shown on the floor plan of '1.korrus'?`

## Demo script (12 steps, ~2 min; steps 1–3 + 6 + 10 + 12 for a short pitch)

Click **Demo tour ▸** (top left), or press → / ← (when not typing). Each step opens a file, asks one question
and shows a one-line note:

1. Esplanades plan 1.korrus: area of 'KORIDOR (119)' → 63.84 m²; the room outline on the drawing and its
   volume in 3D (same IFC GlobalId).
2. Same sheet: doors on the floor plan → 46 boxes + 46 doors in 3D, banner "drawing 46 = model 46 ✓",
   answered by rules only (cost ≈ €0.00001). Click an evidence row: both views zoom to that door.
3. Same sheet, windows → 55 from the model; the drawing shows 52. The cross-check explains the gap (the plan
   is a cut at floor + 1.2 m; 3 windows lie entirely above/below it) and the matching knowledge-graph pill is
   highlighted ("windows plan 52 · IFC 52 at the cut (55 on storey) ✓").
4. Model-wide doors → 211 with evidence on 5 sheets (chips; click one to open that plan, same answer).
5. A question no template covers, with a number in it ("if each door costs 450 euros, what do all the doors on
   '1.korrus' cost in total?") → 20,700 €. The card says "Understood as: factor 450 EUR per door · not a template: ifc
   read the question itself and computed it in code"; "Why" shows `46 count x 450 = 20700.00 EUR` (green = arithmetic
   done in code), and the 46 doors are the evidence in 2D and 3D. No model call. Same path: "what share of the total
   room area on '1.korrus' does 'KORIDOR (119)' take?" → 7.34 %. Questions no solver can read go to W4's planning
   agent (ask → ask → calc → answer; sub-questions clickable, evidence rows labelled by step).
6. A free-text question about a model (4351_arc.ifc, "what plumbing fixtures are in this building and their counts?"):
   the solver's text cites no elements, so the browser checks it against the loaded IFC model by element name
   (`findNamed` in `src/viewer3d.ts`, no model call). With the 03:29 answer ("Toilet-Domestic-3D: 9, Urinal-Wall-3D: 4")
   the named fixtures turn orange, both counts ✓, and "the model also has Sink Vanity-Round ×6, Sink Kitchen-Double ×2
   … not mentioned ✗" (purple) — exactly what the gold adds. With night 8f02b13's answer ("no plumbing fixtures are
   listed", a fact-card regression, told W1) the card shows "✗ the model has Urinal-Wall-3D ×4, Toilet-Domestic-3D ×9,
   Sink Vanity-Round ×6, Sink Kitchen-Double ×2 of the kind the question asks about" and all 21 in purple.
7. Swiss floor plan: doors counted on the DXF layer, boxed on the PDF (36).
8. Same floor, asked in German, doors and windows together → 64. The card shows "Understood as: count · door +
   window · German" and the plan (sum of 2 sub-questions, each clickable); both parts are cross-checked.
9. CubiCasa scan (colorful-4539), asked in Finnish: bedrooms → 3 from the fine-tuned 8B vision model (LoRA cc-v2);
   W3's raster label reader (one local-VLM call per drawing, shared by all its questions) reads 3 'MH' labels, so the
   pipeline cross-checks "vlm_lora 3 = raster 3 ✓", raises the confidence (86 %) and boxes each counted label.
10. CubiCasa scan (high_quality_architectural-14797): "how many saunas?" → the fine-tuned LoRA says 0 (78 %), the label
   reader read 1, so the card shows "✗ Sources disagree" and no boxes. The tour clicks **Show where · read the room
   labels**: the reader's box lands on "LH 2,7" (löylyhuone = sauna room) — one glance shows the sauna (gold: 1). For
   symbol counts (windows, doors, WC seats, sinks) the same button asks R1's CubiCasa5K detector (`raster_cc5k`, cached,
   no GPU) and the credit line adds its weights' licence (CC BY-NC 4.0); e.g. high_quality_architectural-816 doors:
   answer 7, detector marks 9 (gold 9; that drawing is in CC5K's training list).
11. HAER historical scan (vi0026 sheet 3, Creque Marine Railway, 1977; no questions in the dataset): "what kind
   of drawing is this?" → "elevation" at 70 %, read from the scan's own printed text: W3's text layer
   (`stoa/solvers/raster/textlayer.py`, the local VLM reading the sheet tile by tile) finds 59 texts and the
   scale note (1/4" = 1'-0", 1:48), and the answer cites the title lines "HEAD HOUSE AND RESIDENCE" / "NORTH
   ELEVATION", boxed on the scan (first read ~3 min on a busy GPU, then cached; the card says "first time").
   The tour then clicks **Second opinion · NVIDIA Nemotron**: the hosted Nemotron 3.5 Super VL agrees (time,
   tokens and € shown; its reasoning folded). The
   knowledge-graph strip links the other sheets of the same survey, named from the Library of Congress titles
   ("West Elevation", "South Elevation", "Machinery, North Elevation"). Finna scans link the drawings filed
   under the same address ("drawing 2 of 13").
12. "How well it works": accuracy per source on held-out drawings against "just ask the VLM" and the template
   prior, the hard (generality) split, new question kinds (hard2, plus the clean held-out rewording hard2q as an
   aggregate), cost per 1,000 questions, the share answered by rules alone, and calibration. Read live from the
   stoa.eval leaderboard (`STOA_LEADERBOARD`; pipeline rows from S0's integration runs), else
   `fixtures/bench.json`.

**Show where** (CubiCasa count answers that carry no boxes; `locatorFor` in `src/card.ts`): room counts (bedroom,
kitchen, bathroom, sauna, WC room, balcony) ask the label reader (`raster`) and box the labels it counted; symbol
counts (windows, doors, WC seats, sinks) ask the CubiCasa5K detector (`raster_cc5k`) and box each symbol. The card
adds "✓/✗ <reader> finds N …" next to the pipeline's own cross-check; on ✗ the boxes show the reader's count, and an
assumption says so. Hidden when the pipeline already asked the label reader and it found none.

**Compared candidates** (ranked answers such as "which storey has the most doors?"): when the trace has one value
per candidate and an "argmax/argmin over …" line, the card shows a bar per candidate with the chosen one highlighted.

**Named elements** (free-text answers on an .ifc with no element evidence): element types the text names are
matched in the model by family/type name, highlighted, and their counts checked against the numbers the text gives;
for fixture kinds (sanitary, furniture, lighting), families of that kind that the text leaves out are listed as a ✗
check and under "What would make it certain" (purple in 3D). A kind is checked when the answer names one of its
families or the question asks about it ("plumbing fixtures"; not for questions about rooms/spaces). An assumption
line says the solver did not cite them.

**Second opinion** (any answer from a model tier, or below 80 % confidence, on an image or PDF): one click
asks hosted NVIDIA Nemotron the same question (`POST /ask {solver: "vlm_direct", solver_args: {backend:
"nvidia"}}`) and shows whether it agrees. It is never called automatically outside the tour.

**Cost** on the card uses the eval's rates (`stoa/eval/runner.py`), and local-LLM GPU time is billed from
tokens at the shared server's throughput (as the eval does), not from HTTP latency, which includes queueing.

Also: click any room/door on an IFC sheet to see it in 3D; click an element in 3D to see it on the drawing.

**Knowledge graph** (bottom strip, from `stoa.kg.links`): the files of the same building (IFC model, one plan
per storey, discipline models, the same building in another dataset; swiss PDF/DXF/PNG), then the cross-checks
for the open sheet: elements drawn on this plan vs elements of this storey in the IFC model ("doors plan 46 ·
IFC 46 ✓", "windows plan 52 · IFC 55 ≠"). Swiss floors show the CAD-to-PDF fit, the printed-vs-DXF room areas
and the DXF layer counts (click one to ask it). The "N storeys · M rooms ▾" button opens the room table (IFC
area vs drawn area, or DXF vs printed area): click a row to outline the room on the drawing and frame it in 3D,
"ask" to ask its area.
Historical sources (HABS, Finna, Europeana, Wikimedia) are in the source menu with general example questions.

## Fixtures

`fixtures/make_fixtures.py` computes the demo answers the way a deterministic solver would (PDF text layer,
the IfcConvert `.svg` sibling's GUID groups, IfcOpenShell, DXF layers). It never reads the gold answers. All
five match the dataset answers. Regenerate:

```bash
$JUNCTION_VENV/bin/python web/fixtures/make_fixtures.py
```

**Tour and recorded answers.** The demo tour's steps are in `fixtures/tour.json` (`{file, q, note, bench?,
second?, locate?}`; add a step = add an entry, no code change). `fixtures/record.py` asks the running API every
tour question (plus a few extras, the Nemotron second opinions and the "Show where" readers) and writes
`fixtures/recorded.json`, which the mock replays when the API is down:

```bash
$JUNCTION_VENV/bin/python web/fixtures/record.py --api http://127.0.0.1:8100
```

An entry with `"pinned": true` in `recorded.json` is kept instead of the fresh recording (use it to hold a
known-good answer while a solver regression is fixed, and say why in a `"note"`).

## Coordinates (docs/CONTRACT.md)

- `pdf_pt`: PyMuPDF's **unrotated** page space (origin top-left, y down). On a sheet with `/Rotate 90`,
  `page.rect` is rotated but `search_for`/`get_text` boxes are not; the viewer maps
  `(x, y) → (x + view[0], view[3] − y)` into PDF user space and lets the PDF.js viewport apply the rotation.
- `image_px`: pixels of the stored image.
- `ifc_models` sheet SVG → PDF: `pdf_pt = (svg − viewBox origin) × 72/25.4`.

## Code

| File | What |
|---|---|
| `src/main.ts` | state, file picker, ask flow, view modes (drawing / 3D / side by side), deep links |
| `src/viewer2d.ts` | PDF.js / image rendering, evidence overlay, GUID layer from the sheet SVG, pan/zoom |
| `src/viewer3d.ts` | web-ifc → merged three.js meshes per storey; storey filter, highlight/frame by GlobalId, picking |
| `src/card.ts` | answer card (value, confidence, "understood as" intent + compound plan, cross-check badge, cost tier/time/tokens/€, trace or the agent's reasoning chain, second opinion, evidence) |
| `src/kg.ts` | knowledge-graph strip and drawer (linked files, drawing-vs-model checks, rooms, storeys) |
| `mock/stoaApi.ts` | `/api/*` middleware: forwards to :8100, falls back to the mock (and to `stoa.kg` for `/kg`) |

## Licences

Libraries: three.js (MIT), PDF.js `pdfjs-dist` (Apache-2.0), web-ifc (MPL-2.0, file-level copyleft, used
unmodified from npm, which is compatible with this MIT project), Vite and TypeScript (MIT/Apache-2.0). Drawings
are not in git. The footer shows each file's licence and credit from `data/<source>/LICENSE.md`.
