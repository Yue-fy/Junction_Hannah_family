# Demo pre-flight check

**Latest: run `20261114-083951-pipeline-live_questions-c243` on night c1d6149** (S0 cycle 37 = the pre-merge-#5 heads:
W1 64d1367, W3 2e81496, W4 0319d93, F, R1, R2, W5 b43bdac), via night-Q b1a848c, 08:40 14 Nov: **the same 21 answers,
confidences and box counts as on the test-2 build bb94fe4** (run `…-081638-…-ea8f`, 08:16) and as on 753eccb / dde6347.
Latencies in this run are inflated (2–14 s) because three other evals shared the GPU server; on an idle server they
are the 0.1–5 s of the bb94fe4 run below. Run `web/demo.sh` before going on stage so every tour answer is warm.
New since 753eccb: the fine-tuned model's bedroom and sauna answers carry boxes (3 'MH' labels, 1 sauna label: W4
f889ace room-label regions, $0, no confidence change).
21 rows = the 3-minute script's questions, their "typed live" variants, and every question of W5's 13-step tour
(`web/fixtures/tour.json`; step 13 is the bench, no question).
Re-run before the pitch (from the frozen worktree's root; ~1 min once the scans' text layers are cached):
`$JUNCTION_VENV/bin/python -m stoa.eval --solver pipeline --split demo/live_questions.jsonl --no-leaderboard --workers 4`,
then `python3 $JUNCTION_SHARED/artifacts/Q/live_table.py <run>` renders this table (rows come out in worker order).

Table: bb94fe4 (test-2 build, idle server). c1d6149 gives the same answer / ok / conf / solver / boxes on every row.

| tour step | kind | question | answer | gold | ok | conf | solver | boxes | latency |
|---|---|---|---|---|---|---:|---|---:|---:|
| 1/2 | ifc | What is the net floor area of the room 'KORIDOR (119)' on '1.korrus', in | 63.841 m2 | 63.84 | ✓ | 0.98 | ifc | 2 | 1.7 s |
|  | ifc-live-typed | how big is the corridor KORIDOR (119) on 1.korrus? | 142.242 m2 | 63.84 | ✗ | 0.30 | ifc | 4 | 4.2 s |
| 1/2 | ifc | How many doors are shown on the floor plan of '1.korrus'? | 46 count | 46 | ✓ | 0.98 | ifc | 92 | 1.6 s |
|  | ifc-live-typed | how many doors on the first floor (1.korrus)? | 46 count | 46 | ✓ | 0.98 | ifc | 92 | 1.6 s |
| 5 | ifc-derived | If each door costs 450 euros, what do all the doors on '1.korrus' cost i | 20700.0 EUR | 20700 | — | 0.92 | ifc | 92 | 0.1 s |
| 7/8 | vector | How many doors (interior doors and entrance doors together) are drawn on | 36 count | 36 | ✓ | 0.99 | dxf | 36 | 1.2 s |
|  | vector-live-typed | how many doors are on this plan? | 36 count | 36 | ✓ | 0.99 | dxf | 36 | 2.2 s |
| 7/8 | vector | Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezei | 64 count | 64 | ✓ | 0.98 | compose | 64 | 1.2 s |
| 7/8 | vector | What is the net floor area of apartment B in m², summing all its rooms e | 80.83 m2 | 80.83 | ✓ | 0.90 | dxf | 7 | 0.2 s |
|  | vector-live-typed | How big is apartment B? | 80.83 m2 | 80.83 | ✓ | 0.90 | dxf | 7 | 0.9 s |
| 9 | raster | Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on? | 3 count | 3 | ✓ | 0.92 | vlm_lora | 3 | 1.8 s |
|  | raster-live-typed | How many bedrooms does this apartment have? | 3  | 3 | ✓ | 0.92 | agent | 3 | 5.3 s |
| 9 | raster | How many toilet bowls (WC seats) are drawn on this floor plan? | 2 count | 2 | ✓ | 0.92 | vlm_lora | 2 | 0.9 s |
| 9 | raster | How many saunas are on this floor plan? | 1 count | 1 | ✓ | 0.96 | vlm_lora | 1 | 1.8 s |
| 10 | raster-catch-miss | How many saunas are on this floor plan? | 0 count | 1 | ✗ | 0.82 | vlm_lora | 0 | 0.8 s |
|  | schedule | On sheet A-801 of the Xcel Sports Complex drawings, what is the area of  | 3814.0 ft2 | 3814 | ✓ | 0.85 | schedule | 1 | 3.7 s |
| 3 | ifc-tour3 | How many windows are shown on the floor plan of '1.korrus'? | 55 count | 55 | ✓ | 0.88 | ifc | 110 | 0.0 s |
| 4 | ifc-tour4 | How many doors are there in the model 'Maleva tänav 18 korterelamu (Espl | 211 count | 211 | ✓ | 0.97 | ifc | 422 | 0.0 s |
| 6 | ifc-bench-tour6 | What plumbing fixtures are in this building and their respective counts? | Plumbing fixtures are not listed in the model fa  |  | — | 0.30 | ifc | 1 | 4.2 s |
| 11 | scan-tour11 | What kind of drawing is this (floor plan, elevation, section, site plan) | elevation  | elevation | — | 0.75 | raster | 2 | 0.2 s |
| 12 | scan-tour12 | Mikä on piirustuksen mittakaava? | 1:500  | 1/500 | — | 0.75 | raster | 1 | 2.9 s |

**As expected: 19 of 21.** Everything the 3-minute script types is right (KORIDOR 63.84, doors 46, Swiss doors 36,
German doors+windows 64, apartment B 80.83 also as "How big is apartment B?" (0.90), Finnish bedrooms 3 (now boxed),
450 €/door 20,700 by the IFC rules alone (0 LLM calls, 0.1 s, conf 0.92, 46 doors boxed), schedule 3814 ft²).
Tour steps: windows on '1.korrus' **55** (= IfcWindow contained in the storey; the drawing shows 52, step 3's point),
model-wide doors **211** (dataset gold), HABS sheet **elevation** (0.75), Olympic Stadium scale **1:500** (0.75;
text type, judged by eye).

Not as hoped (unchanged since 04:51):
- `raster-catch-miss` (step 10): 0 saunas at 0.82, gold 1 — **deliberate**: the step shows 'Show where' catching it.
- "how big is the corridor KORIDOR (119) on 1.korrus?" → **142.24 m² at 0.30** (gold 63.84): the unquoted wording
  still sums more than the one room. Type the dataset wording on stage.
- Step 6 (4351_arc, plumbing fixtures, text): the live answer **opens with "Plumbing fixtures are not listed in the
  model facts"** and then lists all four types with the gold counts under "Estimate" (toilets 9, vanity sinks 6,
  urinals 4, kitchen sinks 2 = the dataset's answer), conf 0.30. The recorded tour answer lists only toilets and
  urinals. Either re-record or have the fact card call these families plumbing (W1/W5 told 04:55).
