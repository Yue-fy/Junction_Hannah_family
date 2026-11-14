# 3-minute demo script — "Make Blueprints Talk" (Stoa)

Written by agent Q, 14 Nov 04:10; updated 05:00 to follow W5's demo tour (`web/fixtures/tour.json`, 13 steps — the
"step N" references below are its numbering); updated 08:20 for **the test-2 build, night bb94fe4** (S0 started
sealed test 2 on it at 08:12). Slide 3 has the test-2 aggregates (S0, 08:26). **Every live question below and every tour question was run through
the pipeline on bb94fe4 at 08:16 and again on night c1d6149 at 08:40 and 62754aa at 08:46 (`demo/live_questions.jsonl` →
`demo/LIVE-CHECK.md`, 19/21 as expected, the same 21 answers on both and as on dde6347 and 753eccb), so the answers are known in advance; the "typed live" variants check that a
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
Sealed test 2 = S0's run b391 on the test-2 build bb94fe4 (08:12, aggregates only, `logs/S0/scorecard-test2.md`).
| | sealed test 2 (2,199 Qs, unseen drawings) | dev |
|---|---:|---:|
| "Just ask a VLM" (Qwen3-VL-8B, image only) | — | 32.0 % micro / 44.1 % weighted |
| Hosted Nemotron 3.5 Super VL 120B, image only | — | 33.2 % micro (smoke, 206 Qs) |
| **Ours** | **87.7 % micro / 79.7 % weighted** | 89.8 % / 83.4 % |
| Ours without the fine-tuned 8B model (test-1 code) | 83.9 % / 73.8 % | |
| **New wordings of the same kinds** (sealed, nobody tuned on it) | **80.4 %** (test 1: 63.0) | |
| **Derived quantities: prices, rates, shares** (sealed) | **62.2 %** (test 1: 34.6) | |

By source on sealed test 2: Swiss vector plans 99.0 %, IFC models 100 % (397/397), scanned apartment plans
(CubiCasa) 70.4 % (a VLM alone: 50 % on dev).
> "When we say we're sure — 79 % of answers — we are right 98 % of the time; calibration error 0.02. Cost: 3 cents
> per 1,000 questions, ten times less than this morning, because 56 % of questions never call a model. And the
> failure analysis paid off: on wordings nobody had seen, 63 → 80 %." (Tour step 13 shows W5's bench snapshot:
> check that it shows the test-2 numbers, or say these.)

## 2:35–2:55 · Where it breaks, and why (slide 4 — the failure analysis)
Slide image: `demo/redteam-rounds.png` (SVG next to it; regenerate with `python3 experiments/q/plot_rounds.py` and
headless chromium, numbers from `redteam/REPORT.md`). **Say only this (≈ 22 s, 65 words):**
> "We tried to break it ourselves: over a thousand adversarial questions — rewordings, nine languages, rotated scans,
> rooms that don't exist, renamed files, a judge's own upload. Every confident mistake had one cause: we checked the
> number, not that it answered what was asked. Each bar is a round of fixes; the tall ones on the right are this
> morning's new attacks. On the first 600, all 397 confident answers are right — and it never just refuses."
(The bars from 09:28 on count only the newest families — uploads, links, lists, rankings, renamed files, relative
storeys — on builds where every older family is at 0: 14 / 12 / 19 / 18, then 10 and 5 with the 10:47 / 10:54 owner
heads, 6 on b656826, **5 on the final night 637a6df: all five are CubiCasa uploads without the style (bug 26)**. Redraw after the final
build: `python3 experiments/q/bar_count.py MAIN_RUN [V27_RUN] --v26 V26_RUN` gives the bar.)
(Numbers by stage build — say the line for the build on stage: **the final night 637a6df (11:13):
"… all 397 confident answers are right, and no confident answer to a trick question"** (run
`…-111324-…-all-637a6df-538a`; 432 of 432 on v1–v20); b656826: "… all 398"; pre-merge #11: "… all 396"; pre-merge #10: "… all 398"; night 6025963: "… all 402" (`…-103834-…-all-6025963-f05a`);
41188a4: "… all 379"; **7a78559 (09:50): "… all 378"** (run `…-094023-…-all-7a78559-2466`; 413 of 413 on
v1–v20); 0ffd81b: "… all 364" (run `…-092751-…-all-0ffd81b-ba15`); be57171 / 31397eb: "609 … all 360"; bb94fe4 (test 2):
"494 … 283 of 290"; c1d6149: "564 … 338 of 339"; 62754aa: "609 … 337 of 339". "Never just refuses": 0 of 647
answers on be57171 are a bare refusal, and every wrong one carries an assumption or a "missing" line — see backup.)

Point at the chart: the families already asked go to 0 after each fix; each new family finds the same cause on a
new surface (storeys in everyday words, "whole building" in Swedish, "1,200 euros", two-part questions).

**Backup for questions (don't read out):**
- **Newest (09:05, night be57171, 609 questions v1–v18): 360 of 360 confident scored answers right; 3 false
  premises still answered confidently ("whole building" on a single-floor plan). The two newest families (v19 list
  answers, v20 plan↔model link wordings, 38 questions, the chart's last bar) found 6 more confident misses**, e.g.
  "Which living rooms are smaller than 30 m²?" → every room < 30 m², "How many of the model's windows does this
  drawing not show?" → 297. Same root cause, new surface.
- **"We know what we don't know" (Stoa's point 3), measured on all 622 answers of be57171:** 0 bare refusals (5
  "unknown" text answers to questions no drawing answers: rent, construction year, U-value, cost, occupants); every
  answer below confidence 0.3 says what is missing (35/35); all 33 wrong answers carry an assumption or a "missing"
  line. Honest caveat: 108 of those lines are process notes ("no located evidence from this solver"), not what the
  building's documents lack.
- **Newest (08:45, pre-merge #6 = night 62754aa + the 08:41 heads): 3 of 564 at confidence ≥ 0.8 — all three are
  "whole building" asked on a single-floor plan — and 350 of 350 confident scored answers right.**
- **Latest merged (08:37, night c1d6149): 4 of 564 at confidence ≥ 0.8, and 338 of 339 confident scored answers right** (`redteam/REPORT.md` "Pre-merge check #5"; the chart's last bar). Left:
  "whole building" asked on a single-floor Swiss plan (answers the floor, ×3) and a Finnish two-number question
  answered with one number.
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

### If a judge types their own question (measured 10:38 on night 6025963, run `…-103834-…-all-6025963-f05a` + v27 `…-103938-…-v27-b9d0`; `redteam/REPORT.md` v6–v27)
On older builds more of these break: see the git history of this file (08:20 and 08:37 versions).
- **Esplanades IFC sheet — safe:** "How many rooms / columns are on this floor?" (50 / 37), "How many doors are on the
  ground floor?" (46, 0.98), "How many windows does the whole building have?" (297; also Finnish "koko
  rakennuksessa", Italian "in tutto l'edificio"), "How many more windows than doors are there on this floor?" (9),
  "Which floor has the most / the fewest doors?" (1.korrus / 5.korrus, 0.89), "Does '1.korrus' have more windows than
  doors?" (yes), "How many doors and how many windows are on '1.korrus'?" ("door: 46; window: 55"), "What is the
  floor-to-floor height between '1.korrus' and '2.korrus'?" (3.35 m), "How high above the ground floor is the top
  floor?" (13.4 m, 0.85), prices of any format ("If each door costs €1,500 …" 69,000).
  **New and worth typing (Stoa: linking earns points):** "Do the floor plan and the IFC model agree on the number of
  windows on '1.korrus'?" → "no: the model has 55, the plan draws 52 (3 lie wholly above/below the cut plane)" at 0.85
  with the 3 GUIDs; the same with doors → "yes: both 46"; "How many floor plan sheets are there for this building?" (5).
  **Lists:** "Which rooms on '1.korrus' are larger than 50 m²?" → 4 rooms with their areas at 0.92 (also "under 4 m²",
  "between 20 and 25 m²", in Estonian/German), and since 0ffd81b with a room type ("Which ELUTUBA+KÖÖK rooms are
  smaller than 25 m²?" → 6-1), "Which floors have more than 55 rooms?" (2.–4.korrus), "On which floors is there a
  MAGAMISTUBA?" (2.–5.korrus). **Links, since 0ffd81b:** "Which sheet shows the server room?" → plan-01-1-korrus (0.85),
  "Does this drawing show every window that the model has?" → "no: 52 of 55", "How many windows on '1.korrus' are in
  the model but not drawn on this plan?" → 3 (0.80), "On which floor is the laundry room (PESUKODA)?" → 1.korrus (0.85),
  in French/Spanish/Swedish too ("Le plan et la maquette IFC ont-ils le même nombre de portes … ?" → yes).
  Right but shown as unsure (fine to type, the card says why): "How many floors does this building have?" (5, 0.60),
  "How many doors are on the top floor?" (39, 0.53), "1.korrus and 2.korrus together" (88, 0.63).
  **Since 6025963 also safe:** comparative link questions in five languages ("Does this plan show fewer windows than
  the IFC model has?" → yes 52 < 55; "Does the IFC model contain more windows … than this drawing shows?" → yes; "How
  many more windows does the model have than this plan shows?" → 3), "Which sheet shows the ground floor?" (smiley:
  plan-02-eg), "Which storey does this sheet show, and does its door count match?" (both halves), rankings that name a
  tie ("Which floor has the most rooms?" → "2.korrus and 3.korrus and 4.korrus (tie, 60 each)" at 0.56), "the three
  largest rooms on '1.korrus'" (0.90), "the total area of the three largest rooms" (232.88 m²), "top floor" (5.korrus).
  **On the 11:15 build (pre-merge #11) also right:** "How many doors are on the floor above this one?" (42), "… the
  floor below this one?" (0 — the foundation), "Which floor has no MAGAMISTUBA?" (1.korrus), "Which floor has the
  biggest room?" (1.korrus), "Quale piano ha il maggior numero di porte?" (frigento: Piano 1). **Steer away from:**
  nothing new from tonight's families on 637a6df ("the storey directly above this one" → 60; "How many windows does
  the floor with the most doors have?" is capped, no longer 297 at 0.95). Also "How big is the laundry room?" (870 at 0.30) and "the same area as room X" (returns X's area). If one
  of these comes up, open the evidence and say it: "the trace shows what it computed — this is a known failure, it's
  on the failure slide."
- Esplanades rooms are labelled in Estonian; English room words work and the card says which labels it used:
  "How many kitchens are on this floor?" → 10 ('ELUTUBA+KÖÖK'), "How many toilets …?" → 13, "How big is the server
  room?" → 4.26 m². Typed without quotes, "how big is the corridor KORIDOR (119) on 1.korrus?" is now right (63.84 at
  0.95) but goes through the agent (11 s): type the dataset wording on stage.
- **Swiss plan — safe:** apartments (4), "combined area of apartments A and B" (161.17 m²), "how many square feet is
  apartment B" (870), "by how many m² is B larger than A" (0.49), "Which apartment has the largest kitchen?" (A),
  "Is apartment A's kitchen bigger than apartment B's?" (yes, 0.87), "How many doors and how many windows are drawn
  on this floor plan?" ("door: 36; window: 28", 0.99 — now also in German, French, Italian and Finnish), "… in total?"
  (64). "How many doors are there in the whole building?" → 36 at 0.50 with "only floor 9385 of building 2082 is drawn"
  (fine to show: it says what it can't know). **Avoid:** two-part area questions ("how many 'Zimmer' in apartment C
  and their total area"), "How big is the Küche?" (several kitchens: total at 0.50 with a per-room list), prices
  written "1,200 euros" on this plan (right about half the time, at 0.45).
- **A Finnish judge:** "Kuinka monta huonetta tässä kerroksessa on?" 50, "Montako ikkunaa ensimmäisessä kerroksessa
  on?" 55, "Montako kerrosta rakennuksessa on?" 5 (0.60), "Paljonko tämän kerroksen ovet maksavat yhteensä, jos yksi
  ovi maksaa 450 euroa?" 20,700, "Mikä on asunnon B pinta-ala?" 80.83, "Onko asunnossa sauna?" yes, "Montako
  WC-istuinta ja pesuallasta piirustuksessa on yhteensä?" 8, "Montako ovea ja montako ikkunaa kerroksessa '2.korrus'
  on?" ("door: 42; window: 60", 0.53). "Mikä on käytävän KORIDOR (119) pinta-ala?" is now right (63.84) but at 0.29.
  Avoid "Montako ovea pohjapiirroksessa on?" on the Swiss plan (0 at 0.32).
- **CubiCasa plan:** "How big is this apartment?" gives an estimate at low confidence (0.05–0.40) with "no known
  scale" — a good moment to show "we know what we don't know". "How many bedrooms and how many bathrooms?" →
  "bedroom: 3; bathroom: 1" (0.92). Avoid "How many windows does this apartment have?" (11 at 0.30; gold 8).
- **"＋ Your own drawing" (upload; red-team v22 + all 800 CubiCasa dev questions):** for an apartment plan image, tick
  the style "Nordic apartment plan" — then every answer is the dataset path's (64/64 identical); without it the
  answers are about as accurate but twice as often confidently wrong (24 → 46 of 800; bug 26). An .ifc uploaded alone
  answers like ours (7/7). A plan sheet uploaded WITHOUT its .ifc gets only the vision path (0/5, low confidence):
  ask the judge to drop the .ifc too.

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
