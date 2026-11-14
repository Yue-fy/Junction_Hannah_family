# 3-minute demo script — "Make Blueprints Talk" (Stoa)

Written by agent Q, 14 Nov 04:10; updated 05:00 to follow W5's demo tour (`web/fixtures/tour.json`, 13 steps — the
"step N" references below are its numbering). Numbers are from the sealed test run S0 made at 03:21 on night 95f2277
(aggregates only) and dev runs on the same code. Before the pitch, re-run the pre-flight (see the end) and replace any
number that changed. **Every live question below and every tour question was run through the pipeline on night
dde6347 at 04:51 (`demo/live_questions.jsonl` → `demo/LIVE-CHECK.md`, 19/21 as expected), so the answers are known in
advance; the "typed live" variants check that a slightly different wording still works.**

Setup (5 minutes before): API from the `night` worktree root
`$JUNCTION_VENV/bin/python -m uvicorn stoa.api:app --port 8100` (needs :8001 with LoRA cc-v2, check
`curl -s 127.0.0.1:8001/v1/models`), then `cd web && npm run dev` → http://localhost:5173, 1280×720, browser zoom
100 %. Run `web/demo.sh` once before going on stage: it warms every tour answer. The "Demo tour ▸" button (→ / ← keys)
walks the 13 steps; the 3-minute pitch uses steps 2, 5, 8, 9, 10 and 13 (1, 3, 4, 6, 7, 11, 12 are for questions
afterwards). If the API is down, the web app replays recorded answers (W5's mock), so the demo never shows an error
screen.

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

### 1. BIM model, 2D + 3D (≈ 30 s, tour steps 2 and 5) — `data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf`
Type: **How many doors are shown on the floor plan of '1.korrus'?** → **46** (gold 46), conf ≈ 0.99, 0 model calls.
- Point at: one box per door on the sheet; click "3D": the same 46 doors highlighted in the IFC model by GlobalId; the
  cross-check line "drawing 46 = model 46 ✓".
- Follow-up (shows reasoning, not lookup): **If each door costs 450 euros, what do all the doors on '1.korrus' cost in
  total?** → **20,700 €**. The card shows the agent's three steps: ask "doors on '1.korrus'" → 46 (from the model),
  calc 46 × 450, answer; and the IFC rules computed the same 20,700 independently (cross-check ✓). Say: "The language
  model plans; the numbers come from the model and from code." ⚠ Takes 5–18 s (7.5 s at 04:51 on dde6347; 18 s at
  04:09 on a busy GPU) — keep talking while it runs, or use the tour's recorded answer.
- Backup if asked for an area (step 1): **What is the net floor area of the room 'KORIDOR (119)' on '1.korrus', in m²?**
  → **63.84 m²** (gold 63.84), the room outline highlighted in 2D and 3D. ⚠ Type this wording; the unquoted "how big is
  the corridor KORIDOR (119) on 1.korrus?" returns 142.24 m² at conf 0.30 (flagged, but wrong).
- If asked about windows (step 3): 55 in the model, 52 visible on the cut plane; the card explains the 3.
- Don't type a storey as "the ground floor" / "im Erdgeschoss" on another storey's sheet: red-team bug 13 (the sheet's
  storey is answered, confidently) — unless W1's fix is in the frozen build.

### 2. Vector PDF, another language (≈ 25 s, tour step 8; step 7 is the backup) — `data/swiss_dwellings/site1000_bldg2082_floor9385.pdf`
Type: **Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezeichnet?** → **64** (36 doors + 28
windows; gold 36 and 28).
- Point at: the question is split into two sub-questions, each answered from the CAD layer and boxed on the PDF, the
  sum is done in code. "German in, evidence out; the same works in French, Italian, Finnish, Dutch, Estonian."
- Backup: **How many doors (interior doors and entrance doors together) are drawn on this floor plan?** → **36**.

### 3. Raster scan, the hard case (≈ 25 s, tour steps 9–10) — `data/cubicasa5k/colorful-4539.png` (dev drawing, never trained on)
Type: **Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on?** ("How many bedrooms?") → **3** (gold 3, conf 0.92,
0.5 s).
- Point at: our fine-tuned 8B vision model counts; to keep cost low it draws no boxes itself. Click **"Show where"**:
  a second reader finds the three "MH" labels, they agree (✓), and each counted bedroom is marked.
- Step 10, 10 s: `data/cubicasa5k/high_quality_architectural-14797.png`, **How many saunas are on this floor plan?** →
  the model says **0** at 0.82 (gold 1). "Show where": the label reader finds 'LH' (löylyhuone, the sauna), the card
  turns the disagreement into a ✗ and marks the label. "This is how a person catches our mistake in seconds — the
  system tells you where to look."
- If a judge asks about historical drawings (Stoa cares): step 12, the Helsinki Olympic Stadium site plan (Finna,
  CC BY 4.0), asked in Finnish **Mikä on piirustuksen mittakaava?** → **1:500**, boxed on the hand-lettered
  'ASEMAPIIRROS M.K. 1/500' (3 s, local model only); step 11, a 1977 HAER sheet → "elevation" from its printed title.

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
> 0.017. Cost: €0.24 per 1,000 questions; 64 % of questions never call a model." (Tour step 13 shows the same bench;
> replace with the test-2 numbers if S0 publishes them before the pitch.)

## 2:35–2:55 · Where it breaks, and why (slide 4 — the failure analysis)
> "We tried to break it ourselves."
- **Scanned plans, windows and doors**: 19–35 % exact; both our model and a detector *undercount* dense plans
  (missed symbols grow with density, not with resolution — we tested 2× upscaling: no gain). We show a 90 % range
  ("7 windows, 6–12") instead of pretending.
- **New wordings with an extra operation** ("…excluding apartment A", "…at 450 € each"): our sealed generality set
  drops to 63 %, and derived quantities to 35 % on the code we froze for test 1. Cause: the deterministic solvers
  answered the template they recognised and ignored the extra step. Fix in place: detect the unexplained operation,
  compute it in code or lower the confidence (derived probe 29.5 % → 56.8 %, and 100 % right when confident).
- **Red team** (`redteam/REPORT.md`, 418 adversarial questions; the first 205 built from answers we had right):
  rewording, casing, distractor numbers: 0 of 56 answers changed; typos and prompt injections changed 7, all at
  confidence ≤ 0.42 (flagged) — but one injection obeyed once a VLM saw the question (99 at 0.71), so don't claim
  "injection-proof"; rotated / grayscale / JPEG / half-resolution copies: 30/30; objects that don't exist:
  8/8 "0"; questions a drawing can't answer: all at confidence ≤ 0.40; asking the same 173 questions twice changed 1
  free-text answer. **What broke:** asked about a storey, model or room that doesn't exist (or a real room number with
  the wrong name), the vector and IFC paths answered *something else* at 0.96–0.99 confidence. The IFC solver even
  knew (0.29); the router overwrote it. Our checks verified the number, not that it answered what was asked.
  **Then we fixed it the general way** — keep the solver's own doubt, check that every quoted name resolves, never
  trust an answer that just repeats a number from the question: confident answers to such questions went from 7 of
  24 to **0 of 24**, and every scored answer we gave at ≥ 0.8 confidence on those 283 questions was right (190/190).
  (Verified 04:46 on night dde6347; say "fixed" only if that code is in the frozen test-2 build — check
  `git merge-base --is-ancestor dde6347 <test-2 commit>`.) **And then we broke it again**: asked the way people talk —
  "how many doors are in the basement?", "im Erdgeschoss?", "in the whole building" in Swedish — the IFC path answered
  the storey of the sheet on screen, confidently (12 of 20 storey rows, 12 of 12 SV/FR/IT/ET "whole building" rows).
  Same root cause, a new surface: the check verifies the number, not that it is about the place that was asked.
  **One round later** (night 753eccb, 05:00): a cross-language reading (as asked + translated, compared) fixed "whole
  building" in 5 of 6 languages and half the storey words; 20 of 418 red-team answers are still confidently wrong
  ("basement", Italian, ambiguous room names). Say the latest numbers; check they are in the test-2 build.

### If a judge types their own question (measured 04:55 on dde6347, `redteam/REPORT.md` v6)
- Esplanades IFC sheet — safe: "How many rooms / columns are on this floor?" (50 / 37), "How many doors are on the
  ground floor?" (46), "How many windows does the whole building have?" (297), "How many more windows than doors are
  there on this floor?" (9). Steer away from: storeys in everyday words on another sheet ("the basement", "im
  Erdgeschoss"), "top floor" (picks the roof level), "how many floors" (says 7: counts foundation and roof), Finnish
  "koko rakennuksessa" (answers this storey), floor-to-floor height. If one of these comes up, open the evidence and
  say it: "the cross-check shows which storey it used — this is our known failure, on the failure slide."
- Swiss plan — safe: apartments (4), "combined area of apartments A and B" (161.17 m²), "how many square feet is
  apartment B" (870), "by how many m² is B larger than A" (0.49). Avoid "How big is the Küche?" on floors with several
  kitchens (sums them, bug 14).
- CubiCasa plan — "How big is this apartment?" gives ≈ 84 m² at confidence 0.05 with "no known scale: estimate" —
  a good moment to show "we know what we don't know".

## 2:55–3:00 · Close
> "Answers you can verify in seconds, a confidence you can trust, and an honest list of what we don't know yet."

---

## Pre-flight check (run 30 minutes before; ~2 min)
```
cd <night worktree>
$JUNCTION_VENV/bin/python -m stoa.eval --solver pipeline --split demo/live_questions.jsonl --no-leaderboard --workers 4
```
All rows except `raster-catch-miss` (deliberately wrong: 0 vs gold 1) and the unquoted "how big is the corridor" row
must be correct; read the text rows (`ifc-derived` 20,700, `scan-tour11` elevation, `scan-tour12` 1:500,
`ifc-bench-tour6` the fixture list) by eye. Results from 04:51 on dde6347 (19/21 as expected) are in
`demo/LIVE-CHECK.md`. Then run `web/demo.sh` to warm the tour.

## Credits to show on the last slide
CubiCasa5K plans (Kalervo et al. 2019, CC BY-NC-SA 4.0, non-commercial), Swiss Dwellings v3.0.0 (Archilyse AG,
CC BY 4.0; drawings rendered by the dataset authors), IFC models each with their own credit per
`data/ifc_models/LICENSE.md`, OpeningDesign drawings (CC BY-SA 4.0 / MIT per file, `data/opening_design/LICENSE.md`).
R1's CubiCasa5K detector weights (CC BY-NC 4.0) only if cc5k=1 is shown. Base model
Qwen3-VL-8B (Apache-2.0); our LoRA trained on our train split only.
