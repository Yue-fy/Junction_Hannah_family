# Router and pipeline: a playbook for new question kinds

`stoa/pipeline.py` (solver `pipeline`) is the team's one entry point. `stoa/router/` holds its parts: the question
parser (`intent.py`), compound questions (`compose.py`), the general agent (`agent.py`), per-question LLM budget
(`budget.py`), gates (`gating.py` + `gating.json`), priors (`prior.py`), canonical rewrites (`canonical.py`) and the
gate calibrator (`calibrate.py`). This page is for whoever adapts the pipeline to Stoa's new question kinds after the
noon reveal. The overnight agents stop at 11:45.

## 1. Measure before changing anything

```bash
# Stoa's examples as rows {"path": "data/...", "question": "...", "answer": "..."}; "answer" is optional (unscored)
$JUNCTION_VENV/bin/python -m stoa.eval --solver pipeline --split /path/to/stoa_examples.jsonl --no-leaderboard
# one question with its full trace, evidence and cost
$JUNCTION_VENV/bin/python experiments/w4/ask.py data/ifc_models/<sheet>.pdf "How big is room 119?" [k=v ...]
# where the points go / two runs side by side
$JUNCTION_VENV/bin/python -m stoa.eval.analyze <run_id> --baseline <run_id>
$JUNCTION_VENV/bin/python experiments/r2/compare_runs.py <run_a> <run_b> --show
```

Write the gold answers before the first run, and add 5 to 10 rewordings of each kind of your own (other
languages, typos, the way a customer would ask). A fix that only covers Stoa's exact sentences will not hold on the
hidden set.

## 2. Read the trace: which step answered

`Pipeline.solve` → `_solve_question` runs these steps in order. The first trace line tells you which step answered.

| Order | Step (code) | Trace starts with | Fires when |
|---|---|---|---|
| 0 | file check | `the file could not be opened` | path not found: prior at conf <= 0.05 |
| 1 | normalisers `normalise_numbers/refs/scope`, `name_sheet` | `question normalised (...)` (added at the end) | Swiss apostrophes, 'apt. D', 'this flat' on CubiCasa, ... |
| 2 | `_link_question` | `route: link question (<why>)` | R1's `is_link_question` fires: plan vs model, sheet sets, 'Is there an IFC model for this plan?' |
| 3 | `_front_end` (translation), then step 2 again | `language front end: ...` | not English: the local LLM translates; answers are capped at `translate_cap` unless both readings agree |
| 4 | `_per_room` (cc5k=1, CubiCasa) | `route: ... room graph (R1)` | room-scoped questions on a raster |
| 5 | `compose.decompose` → `_solve_composed` | `compound question → <op> over N parts` | sum / diff / argmax / list / yes-no comparisons of simpler questions |
| 6 | `_solve_atomic`: parse | `intent: <task> <target> [scope]` | always |
| 6a | `_raw_deterministic` | `<solver> (question as asked): ...` | a deterministic solver in the route (dxf, ifc, schedule, pdf_vector) reads the question itself; kept when conf >= 0.45 |
| 6b | `_run_agent` (`agent.py`) | `general agent first: <why>` / `agent: ...` | operators (average, share, difference, thresholds), unknown classes, or a solver flagged an operation it did not apply |
| 6c | template cascade (gate → solvers in `route()` order) | `gate (train n=...)`, `<solver>: ...` | known question kinds |
| 6d | `_kg_crosscheck` | `cross-check: ... ✓ / ✗` | the KG has the same quantity from another file |
| 6e | `_prior_answer` | `prior[...]` | nothing else answered (never a bare refusal) |
| 7 | exit caps in `_solve_question` | `... confidence capped at ...` | count answer to a non-count question, size answer to 'how many', fractions, echoes, a ✗ cross-check |
| 8 | `_shape_guard` (in `solve`) | `answer shape check: ...` | which-floor/room/sheet answered by a number, yes/no answered by a number, how-many answered by yes/no → 0.3 |

## 3. Where to put a fix for a new kind

- **A wording the parser misreads** (wrong task, target or scope in the `intent:` line): `intent.py` (rules, every
  language) or a normaliser in `pipeline.py`. Run the parse over `questions.jsonl` before and after and count the
  changes. Tonight's rule was 0 changes on the dataset unless the change is the point.
- **A question about files, links or the drawing set**: R1's `experiments/r1/kg_qa` (trigger and reader) and the
  gate at the top of `_link_question`. On drawings without a project graph only file-subject questions are admitted
  (`_FILE_SUBJECT`).
- **A new operator over things we can already read** (top-k, 'except', 'per storey'): `compose.py` when it splits
  into simple questions; else the agent (`agent.py` tools: ask, table, rows, find_text, look, calc, answer).
- **A new quantity on one file type**: the owning solver (ifc = W1, dxf = W2, raster = W3, schedule / pdf_vector,
  see docs/TEAM.md). The pipeline asks it as asked first (step 6a), so a fix there needs no router change.
- **Confident but wrong shape or scope**: add an exit check (step 7 or 8). Cap the confidence and say why in
  `missing`. Don't change the value.

## 4. Rules that held tonight

1. **Narrow triggers.** Before running anything, count how many dataset and open-split questions a new route
   catches (`questions.jsonl` + `$JUNCTION_SHARED/results/splits/*.jsonl`). A route that should fire on 0 of them
   leaves dev/hard/hard2 unchanged by construction, so you only need to measure the new probe.
2. **Paired runs with an off switch.** Each step has a solver arg (`--solver-arg links=0`, `pvm=0`, `agent=0`,
   `compose=0`, `cc5k=0`, `lora=0`, `both_readings=0`, `translate=0`; full list in the `pipeline.py` docstring). Run the
   same rows with it on and off, and compare per row, not only the totals.
3. **A new reader checks, it does not overrule.** When two readers disagree, cap the confidence (LINK_DISAGREE 0.6,
   XCHECK_CAP 0.7, SHAPE_CAP 0.3) and name the other answer in `missing`. Don't flip a confident answer.
4. **Cost is scored.** Read tokens, calls and p95 off the eval footer. A solver that abstains after an expensive
   read (text layer, OCR, a VLM call) costs that read on every question routed to it first.
5. **Imports under threads.** The eval runs 6 worker threads. Load a solver module through the registry
   (`self._get(name)`) before a guarded `from stoa.solvers.X import f`. A bare guarded import from several threads
   at once met a half-initialised module and silently returned None.
6. **Gemini** (`stoa.llm.chat(..., backend="gemini", purpose=...)`): never inside bulk evals. The eval hides the key
   for runs over 200 rows unless `--allow-gemini` is set. The pipeline doesn't call Gemini.

## 5. Known gaps (11:00)

- R1's link trigger misses Italian 'Quante finestre del modello IFC non sono disegnate in questa pianta?' (55 @0.875,
  gold 3), and W1's `plan_vs_model` has no Italian.
- dxf's rule parser misses Italian '(senza balconi)' / 'alloggio X'. A pipeline normaliser made it worse (24 → 16).
- Raster-first for window counts on 'unknown'-source uploads helps Swiss-style PNGs but costs ×7.8 tokens on
  CubiCasa-style ones until raster's style check runs before its text layer (W3 4c0ebff did this for scans).
  The one-line route change is in board/W4.md.
- CubiCasa window counts stay weak (~15% exact even with the LoRA).
