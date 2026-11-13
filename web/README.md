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
  questions come from the dataset, `/ask` returns the precomputed fixtures in `fixtures/answers.json`. The
  badge in the top-left says `API live` or `API mock`.
- `npm run build` type-checks and builds to `dist/`. `npm run preview` serves the build with the same
  `/api` middleware (no separate server needed).

Deep links: `/?file=<dataset-relative path>&q=<question>` opens a file and asks right away, e.g.
`/?file=data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf&q=How many doors are shown on the floor plan of '1.korrus'?`

## Demo script (30 s)

Click **Demo tour ▸** (top left). Each click opens a file, asks one question and shows a one-line note:

1. Esplanades plan 1.korrus: area of 'KORIDOR (119)' → 63.84 m²; the room outline on the drawing and its
   volume in 3D (same IFC GlobalId).
2. Same sheet: doors on the floor plan → 46 boxes + 46 doors in 3D, banner "drawing 46 = model 46 ✓",
   answered by rules only (cost ≈ €0.00001). Click an evidence row: both views zoom to that door.
3. Model-wide doors → 211 with evidence on 5 sheets (chips; click one to open that plan, same answer).
4. Swiss floor plan: doors counted on the DXF layer, boxed on the PDF (36).
5. HABS historical scan (no questions in the dataset): "what kind of drawing is this?" → the cascade escalates
   to the local VLM (strip shows "rules › **local model**"), low confidence and what is missing.

Also: click any room/door on an IFC sheet to see it in 3D; click an element in 3D to see it on the drawing.
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
| `src/card.ts` | answer card (value, confidence, cross-check badge, cost tier/time/tokens/€, trace, evidence) |
| `mock/stoaApi.ts` | `/api/*` middleware: forwards to :8100, falls back to the mock |

## Licences

Libraries: three.js (MIT), PDF.js `pdfjs-dist` (Apache-2.0), web-ifc (MPL-2.0, file-level copyleft, used
unmodified from npm, which is compatible with this MIT project), Vite and TypeScript (MIT/Apache-2.0). Drawings
are not in git. The footer shows each file's licence and credit from `data/<source>/LICENSE.md`.
