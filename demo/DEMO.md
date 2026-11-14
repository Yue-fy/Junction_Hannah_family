# 3-minute demo script — "Make Blueprints Talk" (Stoa)

Written by agent Q, 14 Nov 04:10. Numbers are from the sealed test run S0 made at 03:21 on night 95f2277 (aggregates
only) and dev runs on the same code. Before the pitch, re-run `demo/check_live.sh` (see the end) and replace any number
that changed. **Every live question below was run through the pipeline tonight (`demo/live_questions.jsonl`), so the
answers are known in advance; the "typed live" variants check that a slightly different wording still works.**

Setup (5 minutes before): API from the `night` worktree root
`$JUNCTION_VENV/bin/python -m uvicorn stoa.api:app --port 8100` (needs :8001 with LoRA cc-v2, check
`curl -s 127.0.0.1:8001/v1/models`), then `cd web && npm run dev` → http://localhost:5173, 1280×720, browser zoom
100 %. The "Demo tour ▸" button (→ / ← keys) walks the same steps. If the API is down, the web app replays recorded
answers (W5's mock), so the demo never shows an error screen.

---

## 0:00–0:25 · The problem (slide 1, no app)
> "A site engineer gets a question: how many doors on the first floor, how big is apartment B, how many WCs are we
> ordering. The answer is in the drawings, but in a 200-sheet set, in five languages, across PDFs, CAD and BIM models.
> Today that is an hour of counting. A chatbot answers in two seconds, but you can't check it, and it is wrong two
> times out of three." (Measured: Qwen3-VL-8B looking at the image: 32 % right on our dev set; NVIDIA's 120B Nemotron
> VL: 33 % on smoke.)

## 0:25–0:45 · The insight (slide 2)
> "Structure first, pixels last. Most drawings are data: CAD layers, IFC models, schedule tables. We read those with
> code, so the answer is exact and comes with the elements we counted. Only when there is nothing to parse — a scanned
> plan — do we use a vision model, and it is a small one we fine-tuned. Every answer carries three things: the value,
> how sure we are, and where it came from."

## 0:45–2:05 · Three live questions (app)

### 1. BIM model, 2D + 3D (≈ 30 s) — `data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf`
Type: **How many doors are shown on the floor plan of '1.korrus'?** → **46** (gold 46), conf ≈ 0.99, 0 model calls.
- Point at: one box per door on the sheet; click "3D": the same 46 doors highlighted in the IFC model by GlobalId; the
  cross-check line "drawing 46 = model 46 ✓".
- Follow-up (shows reasoning, not lookup): **If each door costs 450 euros, what do all the doors on '1.korrus' cost in
  total?** → **20,700 €**. The card shows the agent's three steps: ask "doors on '1.korrus'" → 46 (from the model),
  calc 46 × 450, answer; and the IFC rules computed the same 20,700 independently (cross-check ✓). Say: "The language
  model plans; the numbers come from the model and from code." ⚠ Takes 5–18 s (3 local LLM calls; 18 s at 04:09 on a
  busy GPU) — keep talking while it runs, or use the tour's recorded answer.
- Backup if asked for an area: **What is the net floor area of the room 'KORIDOR (119)' on '1.korrus', in m²?** →
  **63.84 m²** (gold 63.84), the room outline highlighted in 2D and 3D. ⚠ Type this wording; "how big is the corridor
  …" is not parsed as an area question yet (red-team bug 7) and returns a text answer at conf 0.30.

### 2. Vector PDF, another language (≈ 25 s) — `data/swiss_dwellings/site1000_bldg2082_floor9385.pdf`
Type: **Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezeichnet?** → **64** (36 doors + 28
windows; gold 36 and 28).
- Point at: the question is split into two sub-questions, each answered from the CAD layer and boxed on the PDF, the
  sum is done in code. "German in, evidence out; the same works in French, Italian, Finnish, Dutch, Estonian."
- Backup: **How many doors (interior doors and entrance doors together) are drawn on this floor plan?** → **36**.

### 3. Raster scan, the hard case (≈ 25 s) — `data/cubicasa5k/colorful-4539.png` (dev drawing, never trained on)
Type: **Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on?** ("How many bedrooms?") → **3** (gold 3).
- Point at: our fine-tuned 8B vision model counts, a second reader reads the room labels; they agree, so each "MH"
  label is marked and the confidence goes up.
- Optional 10 s if time (tour step 10): `data/cubicasa5k/high_quality_architectural-14797.png`, **How many saunas
  are on this floor plan?** → the model says **0** (gold 1). The card says the label reader disagrees; "Show where"
  marks 'LH' (the sauna). "This is how a person catches our mistake in seconds — the system tells you where to look."

## 2:05–2:35 · The numbers (slide 3)
| | sealed test (2,199 Qs, unseen drawings) | dev |
|---|---:|---:|
| "Just ask a VLM" (Qwen3-VL-8B, image only) | — | 32.0 % micro / 44.1 % weighted |
| Hosted Nemotron 3.5 Super VL 120B, image only | — | 33.2 % micro (smoke, 206 Qs) |
| **Ours** | **87.4 % micro / 79.8 % weighted** | 88.5 % / 81.7 % |
| Ours without the fine-tuned 8B model | 83.9 % / 73.8 % | |

By source on sealed test: Swiss vector plans 98 % areas / 100 % counts; IFC models 97–100 %; scanned apartment plans
(CubiCasa) 70.5 % (a VLM alone: 50 % on dev).
> "When we say we're sure (confidence ≥ 0.8, 78 % of answers), we are right 98 % of the time. Calibration error
> 0.017. Cost: $0.28 per 1,000 questions; 64 % of questions never call a model."

## 2:35–2:55 · Where it breaks, and why (slide 4 — the failure analysis)
> "We tried to break it ourselves."
- **Scanned plans, windows and doors**: 19–35 % exact; both our model and a detector *undercount* dense plans
  (missed symbols grow with density, not with resolution — we tested 2× upscaling: no gain). We show a 90 % range
  ("7 windows, 6–12") instead of pretending.
- **New wordings with an extra operation** ("…excluding apartment A", "…at 450 € each"): our sealed generality set
  drops to 63 %, and derived quantities to 35 % on the code we froze for test 1. Cause: the deterministic solvers
  answered the template they recognised and ignored the extra step. Fix in place: detect the unexplained operation,
  compute it in code or lower the confidence (derived probe 29.5 % → 56.8 %, and 100 % right when confident).
- **Red team** (`redteam/REPORT.md`, 174 adversarial questions built from answers we had right):
  rewording, casing, distractor numbers: 0 of 56 answers changed; typos and prompt injections changed 7, all at
  confidence ≤ 0.42 (flagged); rotated / grayscale / JPEG / half-resolution copies: 30/30; objects that don't exist:
  8/8 "0"; questions a drawing can't answer: all at confidence ≤ 0.40; asking the same 173 questions twice changed 1
  free-text answer. **What broke:** asked about a storey, model or room that doesn't exist (or a real room number with
  the wrong name), the vector and IFC paths answered *something else* at 0.96–0.99 confidence. The IFC solver even
  knew (0.29); the router overwrote it. Our checks verified the number, not that it answered what was asked. That is the same failure as our 7 confident misses on the sealed test — so we know exactly
  why, and the fix is a guard, not more training. (Say "fixed" only if W4/W1's fix is merged and re-run.)

## 2:55–3:00 · Close
> "Answers you can verify in seconds, a confidence you can trust, and an honest list of what we don't know yet."

---

## Pre-flight check (run 30 minutes before; ~2 min)
```
cd <night worktree>
$JUNCTION_VENV/bin/python -m stoa.eval --solver pipeline --split demo/live_questions.jsonl --no-leaderboard --workers 4
```
All rows except `raster-catch-miss` (deliberately wrong: 0 vs gold 1), `ifc-derived` (unscored) and the "how big is
the corridor" row (known bug 7) must be correct. Results from 04:09 (14/16 as expected) are in `demo/LIVE-CHECK.md`.

## Credits to show on the last slide
CubiCasa5K plans (Kalervo et al. 2019, CC BY-NC-SA 4.0, non-commercial), Swiss Dwellings v3.0.0 (Archilyse AG,
CC BY 4.0; drawings rendered by the dataset authors), IFC models each with their own credit per
`data/ifc_models/LICENSE.md`, OpeningDesign drawings (CC BY-SA 4.0 / MIT per file, `data/opening_design/LICENSE.md`).
R1's CubiCasa5K detector weights (CC BY-NC 4.0) only if cc5k=1 is shown. Base model
Qwen3-VL-8B (Apache-2.0); our LoRA trained on our train split only.
