# 3-minute demo script — "Make Blueprints Talk" (Stoa)

Written by agent Q, 14 Nov 04:10; updated 05:00 to follow W5's demo tour (`web/fixtures/tour.json`, 13 steps — the
"step N" references below are its numbering); updated 08:20 for **the test-2 build, night bb94fe4** (S0 started
sealed test 2 on it at 08:12). Slide-3 numbers are still test 1 (night 95f2277, aggregates only): replace them with
S0's test-2 aggregates when MORNING.md has them. **Every live question below and every tour question was run through
the pipeline on bb94fe4 at 08:16 (`demo/live_questions.jsonl` → `demo/LIVE-CHECK.md`, 19/21 as expected, the same
21 answers as on dde6347 and 753eccb), so the answers are known in advance; the "typed live" variants check that a
slightly different wording still works.**

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
  total?** → **20,700 €**. On the test-2 build (bb94fe4) the IFC rules read "450 EUR per door" themselves — 46
  doors × 450 in code, 0 model calls, 0.1 s, conf 0.92, 46 doors boxed. Say: "a question no template covers: the
  price comes from the question, the 46 from the model, the multiplication from code — no language model needed."
  Type the price without a thousands separator ("1500 euros", not "1,500"): see the judge list below.
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
- Point at: our fine-tuned 8B vision model counts; it draws no boxes itself, but on the test-2 build the answer
  already carries the three "MH" label boxes from a room-label reader that costs no model call (they agree with
  the count). **"Show where"** still works and marks each counted bedroom.
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
Slide image: `demo/redteam-rounds.png` (SVG next to it; regenerate with `python3 experiments/q/plot_rounds.py` and
headless chromium, numbers from `redteam/REPORT.md`). **Say only this (≈ 20 s, 60 words):**
> "We tried to break it ourselves: 494 adversarial questions — rewordings, nine languages, rotated scans, rooms that
> don't exist, questions no drawing can answer. Every confident mistake had one cause: we checked the number, not
> that it answered what was asked. Each bar is a round of fixes. On the build we're showing, 283 of 290 confident
> answers are right."

Point at the chart: the families already asked go to 0 after each fix; each new family finds the same cause on a
new surface (storeys in everyday words, "whole building" in Swedish, "1,200 euros", two-part questions).

**Backup for questions (don't read out):**
- **What still breaks on the test-2 build (bb94fe4), 12 of 494 at confidence ≥ 0.8:** "how many doors *and how
  many* windows" summed into one number (101 at 0.86; two separate answers were asked, W4); "how many doors on the
  ground floor and how many on the top floor" read as the whole building (W1); "how many floors" counts the
  foundation and roof levels (7, not 5); "the 7th floor" of a 5-storey model answered for the sheet's storey;
  "whole building" asked on a single-floor plan; "1,200 euros" read as 1.2 by the IFC rules; Finnish
  "kellarikerros". Owners have each one; the fixes in W1/W2's unmerged commits (storey heights 1/7 → 5/7, size
  comparisons 7/8 → 8/8) don't touch the 12.
- **What holds** (same 494): rewording, casing, distractor numbers, typos, prompt injection, rotated / grayscale /
  JPEG / half-resolution copies, a plan copied outside our folder, objects that don't exist ("0"), questions no
  drawing answers (all at confidence ≤ 0.40), "which apartment has the largest kitchen", yes/no without a hint.
  One injection obeyed once a VLM saw the question (99 at 0.71) before W4's guard: don't claim "injection-proof".
- **Scanned plans, windows and doors**: 19–35 % exact; both our model and a detector *undercount* dense plans
  (missed symbols grow with density, not resolution; 2× upscaling: no gain). We show a 90 % range ("7 windows,
  6–12") instead of pretending.
- **New wordings with an extra operation** ("…excluding apartment A", "…at 450 € each"): sealed generality set 63 %,
  derived quantities 35 % on the test-1 code. Cause: the rules answered the template they recognised and ignored the
  extra step. Fix in place: detect the unexplained operation, compute it in code or lower the confidence (derived
  probe 29.5 % → 56.8 %, 100 % right when confident). Test 2 measures it on the sealed sets (hard2r, hard3).

### If a judge types their own question (measured 08:16 on the test-2 build bb94fe4, `redteam/REPORT.md` v6–v14)
- Esplanades IFC sheet — safe: "How many rooms / columns are on this floor?" (50 / 37), "How many doors are on the
  ground floor?" (46), "How many windows does the whole building have?" (297, also Finnish "koko rakennuksessa"),
  "How many rooms are there in the building?" (285), "How many more windows than doors are there on this floor?" (9),
  "Which floor has the most doors?" (1.korrus), "Does '1.korrus' have more windows than doors?" (yes).
  **Steer away from:** "how many doors *and how many* windows …" (sums them: 101 at 0.86 — ask one at a time, or say
  "in total"), "… on the ground floor, and how many on the top floor?" (211 twice), "top floor" (picks the roof
  level: 0 doors, flagged 0.42), "how many floors" (7: counts foundation and roof), "1.korrus and 2.korrus together"
  unquoted (42 at 0.68), storey heights (6.7 for a 3.35 m floor-to-floor on this build; fixed on night-W1 8f1c2f8,
  not in test 2), and **prices with a thousands separator**: "€1,500 per door" → 69.0 at 0.92 — type "1500 euros".
  If one of these comes up, open the evidence and say it: "the trace shows what it computed — this is a known
  failure, it's on the failure slide."
- Esplanades rooms are labelled in Estonian; English room words work and the card says which labels it used:
  "How many kitchens are on this floor?" → 10 ('ELUTUBA+KÖÖK'), "How many toilets …?" → 13, "How big is the server
  room?" → 4.26 m². Avoid "laundry room" (PESUKODA isn't mapped; flagged at 0.30).
- Swiss plan — safe: apartments (4), "combined area of apartments A and B" (161.17 m²), "how many square feet is
  apartment B" (870), "by how many m² is B larger than A" (0.49), "Which apartment has the largest kitchen?" (A),
  "Is the kitchen of apartment C larger than that of B?" (no, 7.54 vs 7.59). Avoid "How many doors and how many
  windows …" (64 at 0.98, summed), two-part questions ("how many 'Zimmer' in apartment C and their total area": one
  part answered), "How big is the Küche?" (several kitchens: total at ≤ 0.5 with a per-room list).
- A Finnish judge: "Kuinka monta huonetta tässä kerroksessa on?" 50, "Montako ikkunaa ensimmäisessä kerroksessa on?"
  55, "Paljonko tämän kerroksen ovet maksavat yhteensä, jos yksi ovi maksaa 450 euroa?" 20,700, "Mikä on asunnon B
  pinta-ala?" 80.83, "Onko asunnossa sauna?" yes, "Montako WC-istuinta ja pesuallasta piirustuksessa on yhteensä?" 8.
  Avoid "Mikä on käytävän KORIDOR (119) pinta-ala?" (142 at 0.30), "Montako kerrosta rakennuksessa on?" (7) and
  "Montako ovea pohjapiirroksessa on?" on the Swiss plan (0 at 0.32).
- CubiCasa plan — "How big is this apartment?" gives ≈ 85 m² at confidence 0.05 with "no known scale: estimate" —
  a good moment to show "we know what we don't know". "How many bedrooms and how many bathrooms?" → "3 bedrooms and
  1 bathroom" (agent, 0.58, right). Avoid "How many windows does this apartment have?" (10 at 0.12; gold 8).

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
`ifc-bench-tour6` the fixture list) by eye. Results from 08:16 on the test-2 build bb94fe4 (19/21 as expected,
the same answers as on dde6347 and 753eccb) are in `demo/LIVE-CHECK.md`. Then run `web/demo.sh` to warm the tour.

## Credits to show on the last slide
CubiCasa5K plans (Kalervo et al. 2019, CC BY-NC-SA 4.0, non-commercial), Swiss Dwellings v3.0.0 (Archilyse AG,
CC BY 4.0; drawings rendered by the dataset authors), IFC models each with their own credit per
`data/ifc_models/LICENSE.md`, OpeningDesign drawings (CC BY-SA 4.0 / MIT per file, `data/opening_design/LICENSE.md`).
R1's CubiCasa5K detector weights (CC BY-NC 4.0) only if cc5k=1 is shown. Base model
Qwen3-VL-8B (Apache-2.0); our LoRA trained on our train split only.
