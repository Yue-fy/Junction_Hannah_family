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

**Before a demo, one command:** `web/demo.sh` (from anywhere). It uses the API at `STOA_API_URL` (default :8100)
or starts one from this checkout, checks the local model server (`LLM_BASE_URL`; IFC/Swiss/schedule steps need no
model), starts Vite on :5173 if needed, and asks every tour question once so the presenter's answers come from the
API cache (`DEMO_WARM=0` skips that; `fixtures/recorded.json` is not changed). Then open http://localhost:5173.

- `STOA_DATA` must point at the dataset root (default: the team path in `AGENTS.md`).
- `/api/*` goes to W4's API (`STOA_API_URL`, default `http://127.0.0.1:8100`, see `docs/CONTRACT.md`;
  start it with `$JUNCTION_VENV/bin/python -m uvicorn stoa.api:app --port 8100` from the repo root).
  If that server is down, the dev server answers from a **mock** (`mock/stoaApi.ts`): files and example
  questions come from the dataset, `/ask` replays `fixtures/recorded.json` (live answers recorded with
  `fixtures/record.py`) and then `fixtures/answers.json`. The badge in the top-left says `API live` or `API mock`.
- `/api/kg` (knowledge graph): the API's `GET /kg` if it has one; otherwise the dev server runs W1's
  `stoa.kg.links(path)` itself with `$JUNCTION_VENV/bin/python` from the repo root (`STOA_KG_REPO=<checkout>`
  to use another checkout); if that fails too, it links files by name only (the panel title says "files only").
- Hosted second opinions (NVIDIA Nemotron) are rate-limited and can hang for minutes: the dev server waits
  `STOA_HOSTED_TIMEOUT_S` (default 45) seconds, then shows that model's answer from `fixtures/recorded.json`, marked
  "⟲ recorded HH:MM · hosted API busy right now" (or "hosted model busy" when there is no recording). The API keeps
  the call running and caches it, so the next click is live.
- `npm run build` type-checks and builds to `dist/`. `npm run preview` serves the build with the same
  `/api` middleware (no separate server needed).

**Your own drawing (upload).** "＋ Your own drawing" under the file list, or drop a file anywhere on the page: PDF,
PNG, JPG or IFC, up to 200 MB. The dev server saves it outside the repo and the dataset (`STOA_UPLOADS`, default
`<tmp>/stoa-uploads/<sha256[:12]>/<name>`) and the browser knows it as `upload/<id>/<name>`. The API only accepts
dataset paths, so questions about an upload run the same pipeline in the dev server's process with the shared venv
(`server/ask_upload.py`, one Python process per question, ~0.3 s to load; answers cached per question until the dev
server restarts). Such a file has no template, no CAD/IFC twin and no cached reading, so it shows what the hidden
set's "different" drawings get: e.g. a Swiss plan PDF alone → 36 doors with 36 boxes (pdf_vector, 3 s), apartment B
80.83 m² with its 7 rooms boxed; an IFC-Bench model alone → 5 doors, 2 storeys (ifc rules, GUIDs highlighted in
3D, 0 LLM calls); a Swiss PNG alone → apartments 4 (LoRA), apartment B 77.79 m² at 0.5 with the room labels and
the unit outline boxed. Needs the Python env (no mock answers for uploads). The example chips switch to general
questions (floor-plan ones for drawings, model ones for IFC).

Deep links: `/?file=<dataset-relative path>&q=<question>` opens a file and asks right away, e.g.
`/?file=data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf&q=How many doors are shown on the floor plan of '1.korrus'?`

## Demo script (14 steps, ~2 min; steps 1–3 + 6 + 10 + 13 + 14 for a short pitch)

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
   '1.korrus' cost in total?") → 20,700 €. Since night 753eccb the IFC rules read "each door costs 450 €" as a
   factor themselves ("Understood as: cost + given · factor 450 EUR per door"), count 46 doors and multiply in
   code: conf 0.92, 0 LLM calls, ~20 ms, all 46 doors boxed. Questions the rules cannot read go to W4's planning
   agent (ASK → CALC → ANSWER, numbers from tools only; "Reasoning · N steps" on the card). Same family: "what
   share of the total room area on '1.korrus' does 'KORIDOR (119)' take?" → 7.34 %.
6. A free-text question about a model (4351_arc.ifc, "what plumbing fixtures are in this building and their counts?"):
   a local model answers from facts extracted from the IFC; the browser then counts every type the text names in the
   loaded model (`findNamed` in `src/viewer3d.ts`, no model call). The card leads with that table ("Counted in the IFC
   model · 4 types": Toilet-Domestic-3D 9, Sink Vanity-Round 6, Urinal-Wall-3D 4, Sink Kitchen-Double 2, total 21,
   each ✓ vs the answer) and the 21 fixtures turn orange in 3D; the LLM's own wording folds when every count matches
   (its confidence is labelled "before the check"). Same-kind fixtures an answer leaves out are listed ✗ and shown purple.
7. Swiss floor plan: doors counted on the DXF layer, boxed on the PDF (36).
8. Same floor, asked in German, doors and windows together → 64. The card shows "Understood as: count · door +
   window · German" and the plan (sum of 2 sub-questions, each clickable); both parts are cross-checked.
9. CubiCasa scan (colorful-4539), asked in Finnish: bedrooms → 3 from the fine-tuned 8B vision model (LoRA cc-v2),
   92 %. Since night bb94fe4 (W4 f889ace) the pipeline attaches R1's room-segmentation regions for room-label counts
   when their number equals the answer (cached pretrained CubiCasa5K map, ~0.1 s, no LLM): the 3 'MH' bedrooms are
   outlined and the card shows "✓ Cross-checked: 3 bedroom regions in the room segmentation (pretrained CubiCasa5K)
   = the answer".
10. Same plan, **Rooms & doors** (no question): R1's room graph (`experiments/r1/room_graph/graph.py`, read by the
   middleware's `GET /api/rooms` from the cached CC5K segmentation; offline from `fixtures/rooms.json`): every room
   tinted by kind with its English kind + ~m² under the printed code, every door as a link room → door → room
   (dashed: open-plan links, dotted: to the outside). The legend names the best-connected room ("hall 'ET' leads to
   6 rooms") and lights its links; hover any room for its links, windows and the 80 % area band. Areas: no scale
   printed, so the scale comes from the measured door widths (assumption in the legend).
11. CubiCasa scan (high_quality_architectural-14797): "how many saunas?" → the fine-tuned LoRA says 0 (82 %) with no
   boxes; the card already shows "✗ Sources disagree: 1 sauna region in the room segmentation; the answer says 0".
   The tour clicks **Show where**: the label reader's box lands on "LH 2,7" (löylyhuone = sauna room) and adds
   "✗ label reader (raster) finds 1 sauna label (answer 0)" — two independent readers against the answer (gold: 1).
   For symbol counts (windows, doors, WC seats, sinks) the same button asks R1's CubiCasa5K detector (`raster_cc5k`,
   cached, no GPU) and the credit line adds its weights' licence (CC BY-NC 4.0).
12. HAER historical scan (vi0026 sheet 3, Creque Marine Railway, 1977; no questions in the dataset): "what kind
   of drawing is this?" → "elevation" at 75 %, read from the scan's own printed text: W3's text layer
   (`stoa/solvers/raster/textlayer.py`, the local VLM reading the sheet tile by tile) finds the texts and the
   scale note (1/4" = 1'-0", 1:48), and the answer cites the title lines "HEAD HOUSE AND RESIDENCE" / "NORTH
   ELEVATION", boxed on the scan (first read minutes on a busy GPU, then cached; the card says "first time").
   The tour then clicks **Second opinion · NVIDIA Nemotron**: the hosted Nemotron 3.5 Super VL agrees (time,
   tokens and € shown; its reasoning folded). The knowledge-graph strip links the other sheets of the same survey.
13. Finna scan of the Helsinki Olympic Stadium site plan (Lindegren & Jäntti, Architecture & Design Museum, CC BY
   4.0), asked in Finnish: "Mikä on piirustuksen mittakaava?" → 1:500 (0.75), read from the hand-lettered note
   "ASEMAPIIRROS M.K. 1/500", which is boxed (the language front end translates the question first).
14. "How well it works": every pipeline number from ONE commit (the sealed test's commit when dev also ran on it;
   now bb94fe4 = test 2): accuracy per source on held-out drawings against "just ask the VLM" and the template
   prior, the hard split, new question kinds (hard2, hard2r) and derived quantities (hard3), cost per 1,000
   questions, the share answered by rules alone, calibration, and the blue **Overnight, on sealed data** line
   (previous sealed test → this one: test 87.4 → 87.7 % at €0.24 → €0.02 per 1k, p95 35 s → 1.9 s, hard2r
   63.0 → 80.4 %, hard3 34.6 → 62.2 %). Read live from the stoa.eval leaderboard (`STOA_LEADERBOARD`), else
   `fixtures/bench.json`.

Card details worth pointing at: yes/no answers show their basis ("apartment B 80.83 m² > apartment A 80.34 m²",
"55 windows > 46 doors"); multi-part answers ("how many rooms … and what is their total area?") show one row per part.

**Show where** (CubiCasa count answers that carry no boxes; `locatorFor` in `src/card.ts`): room counts (bedroom,
kitchen, bathroom, sauna, WC room, balcony) ask the label reader (`raster`) and box the labels it counted; symbol
counts (windows, doors, WC seats, sinks) ask the CubiCasa5K detector (`raster_cc5k`) and box each symbol. The card
adds "✓/✗ <reader> finds N …" next to the pipeline's own cross-check; on ✗ the boxes show the reader's count, and an
assumption says so. Hidden when the pipeline already asked the label reader and it found none.

**Show where · room graph** (CubiCasa answers without evidence whose question names a room: "where is the kitchen?",
"which room is the sauna entered from?"; `locatorFor` in `src/card.ts`, `locateRooms` in `src/main.ts`): boxes the
rooms the question names (printed code such as '(OH)' first, else every region of that kind; EN/FI/SV/DE room words)
from R1's room graph, no model call. A ✓/✗ line only with a verdict: the answer names a marked room, a door of the
marked room leads to the room the answer names (that room is boxed too), or a count equals the number of rooms.

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
| `mock/stoaApi.ts` | `/api/*` middleware: forwards to :8100, falls back to the mock (and to `stoa.kg` for `/kg`); uploads (`POST /api/upload`, `upload/...` paths) |
| `server/ask_upload.py` | answers a question about an uploaded file (absolute path outside the dataset) the way the API's POST /ask does |

## Licences

Libraries: three.js (MIT), PDF.js `pdfjs-dist` (Apache-2.0), web-ifc (MPL-2.0, file-level copyleft, used
unmodified from npm, which is compatible with this MIT project), Vite and TypeScript (MIT/Apache-2.0). Drawings
are not in git. The footer shows each file's licence and credit from `data/<source>/LICENSE.md`.
