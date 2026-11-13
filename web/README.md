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

## Demo script (30 s)

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
5. A question no template covers ("what share of the total room area on '1.korrus' does 'KORIDOR (119)'
   take?") → 7.34 %. The card's **Reasoning** section shows W4's agent chain: ask (total area, 870.29 m², ifc)
   → ask (KORIDOR, 63.84 m², ifc) → calc `63.841 ÷ 870.288 × 100` → answer. Sub-questions are clickable, each
   evidence row says which step it came from, and the cross-check is labelled "step 2".
6. Swiss floor plan: doors counted on the DXF layer, boxed on the PDF (36).
7. Same floor, asked in German, doors and windows together → 64. The card shows "Understood as: count · door +
   window · German" and the plan (sum of 2 sub-questions, each clickable); both parts are cross-checked.
8. CubiCasa scan (colorful-4539), asked in Finnish: bedrooms → 3, each counted 'MH' label boxed on the image
   (W3's raster label reader, one local-VLM call per drawing, shared by all its questions).
9. HABS historical scan (no questions in the dataset): "what kind of drawing is this?" → the local VLM says
   "site plan" at 20 %, and the tour clicks **Second opinion · NVIDIA Nemotron**: the hosted Nemotron 3.5 Super
   VL agrees (time, tokens and € shown; its reasoning folded).
10. "How well it works": accuracy per source on held-out drawings against "just ask the VLM" and the template
   prior, the hard (generality) split, new question kinds (hard2, plus the clean held-out rewording hard2q as an
   aggregate), cost per 1,000 questions, the share answered by rules alone, and calibration. Read live from the
   stoa.eval leaderboard (`STOA_LEADERBOARD`; pipeline rows from S0's integration runs), else
   `fixtures/bench.json`.

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
