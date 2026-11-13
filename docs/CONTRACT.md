# CONTRACT

> The interface between parts of the system. Solvers, the router, the API and the web demo build against
> this file in parallel. Overnight (13→14 Nov) changes go through S0 (`inbox/S0.md` → DECISION); in the
> day, through a PR labeled `contract` (see "Change the contract" in AGENTS.md). Prefer additive changes.
> Code of record: `stoa/contract.py` (pydantic models). If this file and the code disagree, tell S0.

## Base URLs and ports

| Service | Local | Notes |
|---|---|---|
| Model server (vLLM, OpenAI-compatible) | `http://127.0.0.1:8001/v1` | run by R2; `$LLM_BASE_URL` |
| API (FastAPI, `stoa/api.py`) | `http://127.0.0.1:8100` | run by W4; CORS for `http://localhost:5173` |
| Web dev server (`web/`) | `http://localhost:5173` | W5 |
| Demo | TBD | |

## The solver interface (Python)

```python
from stoa.contract import Answer, Evidence
from stoa.solvers import register
from stoa.solvers.base import BaseSolver

@register("myname")
class MySolver(BaseSolver):
    extensions = (".pdf",)          # optional filter used by the default can_handle
    sources = ("swiss_dwellings",)  # optional filter used by the default can_handle
    def solve(self, path: str, question: str) -> Answer: ...
```

- `path` is **dataset-relative**, exactly as in `questions.jsonl` (`"data/<source>/<file>"`). Open it with
  `stoa.data.abspath(path)`. Sibling formats: `stoa.data.siblings(path)` → `{".dxf": "data/...", ".ifc": ...}`
  (for `ifc_models` plans this includes the parent model under `".ifc"`).
- `can_handle(path, question) -> bool`: cheap check, no heavy I/O.
- `solve(path, question) -> Answer`: never raise for "I don't know"; return `Answer.abstain(name, reason)`
  (value `None`). Exceptions are caught by the eval and counted as abstentions with `error` set.
- Must be thread-safe (the eval calls `solve` from several threads). Cache per drawing.
- Registry: every module under `stoa/solvers/` is imported on first use; a module that fails to import is
  reported (`python -m stoa.eval --list`) but doesn't break other solvers. Constructor kwargs come from
  `--solver-arg key=value`.

## Shared data types (JSON)

### `Answer`
```json
{
  "value": 7,                     // number | string | null (null = abstain)
  "unit": "count",                // "count" | "m2" | "m3" | "m" | "ft2" | ... | null for text
  "confidence": 0.82,             // 0..1
  "evidence": [ /* Evidence */ ],
  "trace": ["parsed: count windows", "dxf layer WINDOW: 7 inserts"],  // short human-readable steps
  "solver": "dxf",
  "assumptions": ["no scale bar; assumed door width 0.9 m"],   // what the answer relies on
  "missing": ["no DXF sibling; counted from raster"],            // what would make it certain
  "cost": {"llm_tokens_in": 0, "llm_tokens_out": 0, "gpu_seconds": 0.0, "api_calls": 0,
           "api_tokens_in": 0, "api_tokens_out": 0, "llm_calls": 0, "wall_seconds": 0.0}
}
```
`Answer` validates on assignment too: `ans.cost = {...}` becomes a `Cost`, and `ans.confidence = 1.2` raises
(the eval records it as an exception, i.e. a refusal; check `errors` in the eval output). `Cost` also behaves
as a read-only mapping of its non-zero fields, so old code doing `{**d, **(ans.cost or {})}` keeps working.

Stoa (13 Nov): refusing is not useful. `value: null` is allowed but counted as a **refusal**; prefer a best
estimate with a low `confidence` plus `assumptions` and `missing`.

Cost: `stoa.contract.record_cost(**fields)` adds to the current question's meter (the eval wraps each
`solve()` in a `CostMeter`). The LLM client (`stoa/llm.py`) calls it after every call, so solvers get
token/API accounting for free; local-server calls set `llm_calls`, tokens and `gpu_seconds` (wall time of
the call is a fine proxy), hosted calls also set `api_calls` and `api_tokens_in/out`. Threads started inside
`solve()` need `contextvars.copy_context().run(...)` to keep the meter. The eval takes the field-wise max of
the meter and `Answer.cost` (no double counting) and fills `wall_seconds` itself.
Units: give the unit you computed in; the eval converts (m2↔ft2, m↔mm/cm/ft/in, m3↔ft3/l). A unit of the
wrong dimension (m for an area question) is wrong. Counts are rounded to the nearest integer before scoring.

### `Evidence`
```json
{
  "file": "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",  // dataset-relative
  "page": 0,                      // 0-based page index for PDFs; null for images and IFC
  "bbox": [x0, y0, x1, y1],       // null for IFC-only evidence; a point is a box with x0==x1, y0==y1
  "bbox_space": "pdf_pt",         // "pdf_pt" | "image_px"; required when bbox is set
  "ifc_guid": null,               // IFC GlobalId for 3D evidence (file = the .ifc)
  "note": "window 3"
}
```
- `pdf_pt`: PDF points in PyMuPDF's page coordinate space (`page.rect`: origin top-left, y down).
  The web viewer must apply the same convention (PDF.js viewport with the page's rotation).
- `image_px`: pixels of the image file as stored on disk (origin top-left, y down).
- Evidence may point to a sibling file (e.g. the DXF-derived box drawn on the PDF that was asked about,
  or GlobalIds in the `.ifc` behind an `ifc_models` plan). Prefer evidence on the asked file.
- One Evidence per counted object for counts; for areas, the room polygon's bbox (or the schedule row).

## Eval CLI (owned by F)

```bash
$JUNCTION_VENV/bin/python -m stoa.eval --solver <name> --split smoke|dev [--limit N] \
    [--source S] [--type T] [--grep REGEX] [--workers N] [--solver-arg k=v] [--handled-only] [--note "..."]
$JUNCTION_VENV/bin/python -m stoa.eval --list        # registered solvers + import errors
```
- Splits (v2) live in `$JUNCTION_SHARED/results/splits/{smoke,dev,test,train,unused,hard}.jsonl`. Grouped
  by drawing (`stoa.data.drawing_group`): sibling formats, floors of one Swiss site, plans and discipline
  models of one IFC project all stay together. Eval splits keep one language per concept (EN or the local
  language; `stoa.data.concept_map`). `test` is sealed (only S0, with `--allow-test`); opening_design is
  dev-only. `unused` = translations and capped-out questions of eval drawings: never train on them. `hard` =
  generated generality checks on dev drawings (`stoa/eval/hard.py`). `hard2` = reasoning kinds that
  questions.jsonl never asks (averages, ratios, percentages, thresholds, complements, unit changes, argmin,
  yes/no; `stoa/eval/hard2.py`, 256 Qs on dev drawings); it adds the scored type `ratio` (dimensionless,
  within 2%). Load in code:
  `stoa.eval.splits.load_split("train")` → `list[Question]` with answers.
- `--limit N` takes the same fixed random subset every run. `--grep REGEX` keeps questions matching the regex
  (case-insensitive), e.g. `--grep 'window|ikkun|fenster|fönster'` for one concept in every language.
- Scoring: count exact (after rounding); area/length/volume within 2% after unit conversion; text/other
  not scored (a rough `text_fuzzy` rate is reported separately). Abstain = wrong, reported as coverage.
- Output: table per source × type (accuracy, coverage, accuracy-when-answered, evidence rate, text~),
  micro accuracy, macro accuracy, **`weighted_acc`** (bucket accuracies weighted by each bucket's share of
  scored questions in the FULL dataset; the team's headline accuracy, S0 D1), refusal rate, cost per question
  (tokens, LLM/API calls, GPU s, wall s, **est. USD/question** with the rates in `stoa/eval/runner.py:RATES`),
  and accuracy per cost tier (`deterministic` / `local` / `api`).
  **Calibration** (`metrics.calibration`; Stoa's "know what you don't know"): ECE (10 bins), Brier, AUROC
  (does confidence rank right above wrong answers; 0.5 = noise), AURC/excess AURC (risk–coverage), and the
  share of answers with confidence ≥ 0.8 plus their accuracy. **Evidence**: `evidence_rate` (any evidence),
  `evidence_2d_rate` (a bbox the UI can draw), `evidence_count_match` (count answers whose located objects,
  i.e. unique IFC GUIDs + boxes without a GUID, equal the answer). One line appended to `$JUNCTION_SHARED/results/leaderboard.jsonl`;
  per-question predictions in `$JUNCTION_SHARED/artifacts/eval/<run-id>.jsonl` (gold, prediction,
  evidence, trace, error) for error analysis.
- Set `AGENT_ID=<your id>` in the environment so the leaderboard line records who ran it.
- `--judge local|nvidia`: grade text/other answers with an LLM judge (`stoa/eval/judge.py`), reported as
  `text_judge` per bucket, never part of accuracy; the judge's cost is not charged to the solver.
- Other tools: `python -m stoa.eval.analyze RUN [--baseline RUN]` (loss tables, examples, calibration),
  `python -m stoa.eval.leaderboard [--split dev]` (latest full run per solver on the current split version),
  `python -m stoa.eval.gates CHEAP_RUN CHALLENGER_RUN` (per-concept gate table from `--split train_gate` runs),
  `python -m stoa.eval.calibration RUN [RUN ...] [--by-source]` (calibration side by side).
  Extra splits: `train_gate` (960 train Qs for choosing gates/thresholds), `cc5k_heldout` (CC5K-pretrained
  models only), `hard` (generality), or any split file path.

## HTTP API (W4 implements `stoa/api.py`, port 8100)

### `POST /ask`
Request: `{"path": "data/...", "question": "How many windows ...?", "solver": "pipeline"}` (`solver`
optional, default `pipeline`). Response `200`: an `Answer` JSON (above). `404` if the file doesn't exist.
Additive fields (D6, 00:33): `"intent"` (the router's parse of the question, `stoa.router.intent.parse(q).to_dict()`),
`"plan"` (only for compound questions: `{"op": "sum"|..., "parts": [...], "sub_questions": [...]}`) and
`"cached"` (bool). Clients must ignore fields they don't know.

### `GET /intent?q=...`
Returns the router's intent parse for a question (debug/demo).

### `GET /file?path=data/...`
Returns the drawing file (PDF, PNG, JPG, SVG, IFC, DXF) with the right content type. Only paths under the
dataset root (reject `..`).

### `GET /files?source=<source>&q=<substring>&limit=<n>`
Response: `{"files": [{"path": "data/...", "source": "...", "ext": ".pdf", "siblings": {".dxf": "..."},
"n_questions": 12, "license": "CC BY 4.0", "credit": "..."}]}`.

### `GET /questions?path=data/...`
Response: `{"questions": [{"question": "...", "type": "count", "unit": "count"}]}` (example questions for
the demo; no answers).

Additional endpoints (e.g. `GET /ifc-index?path=`) are W4's to add; list them here via S0.

## Env vars (names only; values live in `.env` or the shell, never in git)

| Name | Used by | Where to get it |
|---|---|---|
| `STOA_DATA` | all | dataset root (contains `questions.jsonl`, `data/`) |
| `STOA_PREVIEW` | optional | preview dataset root |
| `JUNCTION_SHARED` | eval, agents | shared panel (splits, leaderboard, artifacts) |
| `JUNCTION_VENV` | all | Python env (`$JUNCTION_VENV/bin/python`) |
| `MODEL_DIR` | R2 | model weights |
| `LLM_BASE_URL` | `stoa/llm.py` | local OpenAI-compatible server, default `http://127.0.0.1:8001/v1` |
| `NVIDIA_API_KEY` | `stoa/llm.py` | NVIDIA hosted API (Nemotron); captain's account |
| `AGENT_ID` | eval | optional; recorded in leaderboard lines |
