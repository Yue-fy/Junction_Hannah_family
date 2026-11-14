# Error analysis (E = agent F)

Updated 03:30, 14 Nov 2026 (sections newest first). Regenerate the tables with
`/data/User/fangy4/envs/junction/bin/python -m stoa.eval.analyze <run_id> --baseline <dummy run_id> --top 20`.
For paired significance use `python3 experiments/r1/stats/compare.py RUN_A RUN_B --by template` (cluster CI).

Run analysed: `20261113-235024-vlm_direct-dev` (R2's baseline: Qwen3-VL-8B local, image only, direct
answer) vs `20261113-234812-dummy-dev` (template prior), both on dev v2 (hash f43c5369; 2,215 Qs,
2,000 scored, 320 drawings).

| run | micro (95% cluster CI) | weighted_acc | refusals | evidence |
|---|---|---:|---:|---:|
| dummy (prior) | 26.1% | 40.4% | 0 | 0% |
| vlm_direct | 32.0% (28.0–36.5) | 44.1% | 200 (all IFC) | 0% |

## LATEST (03:30): gate of the test-1 code, cc5k=1 leak-free, where dev points are left

Context: every agent was stopped by the org spend limit 01:58–03:10, so there was no 02:40 freeze. At 03:12 F gated
W4 c1b294c (trust on unseen wordings, from F's 01:44 held-out mechanisms) + W4 3d21bee (cc5k gate path) + R1 eb03604
(CC5K crosscheck) as a scratch merge (d764334 = night 609e41c + night-W4 8d7f23a + night-R1 6072523). S0 froze the same
code (+ R1 f13db8f count ranges, W5 web) as 95f2277 and started sealed test 1 at 03:21.

### Gate (pipeline, cc5k=0; paired cluster CI from experiments/r1/stats/compare.py)
| split | 609e41c | d764334 | paired | calibration |
|---|---:|---:|---|---|
| dev (weighted / micro) | 81.7 / 88.5 | 81.7 / 88.5 | +0.0 [−0.1, +0.1] | ECE 0.020 → 0.019 |
| hard (micro) | 84.7 | 84.5 | −0.3 [−0.8, +0.0] n.s. (2 cubicasa LoRA re-reads at conf ≤ 0.16) | **ECE 0.036 → 0.075** |
| hard2 (micro) | 92.1 | 92.1 | identical | ECE 0.133 both |
| **hard2q held-out (scored)** | 75.7 | **79.9** | **+5.9 [+0.7, +11.3] \*** (all swiss: 11 wins / 3 losses) | conf≥0.8 precision 88.0 → 92.7% |

- Held-out gain is entirely swiss area (64.4 → 82.2 of 45); cubicasa (42.0) and ifc (100) unchanged; judged text 68.7
  unchanged. F's 01:44 simulation predicted ≈81.5.
- The 0.5 confidence cap on non-template wordings: on `hard` it lowers 77 cubicasa paraphrase answers from 0.86 to 0.50
  while they are 79% right (under-confident → ECE doubles); on held-out hard2q the 15 capped answers are 33% right (0.80 →
  0.50, still over-confident). Direction right, trigger too broad. Suggested to W4: cap when the parse leaves unexplained
  structure (second concept, numbers, comparison words); otherwise scale by ~0.9 (fit on `hard`, check on `hard2`).

### cc5k=1 on leak-free data (R2's cc5k_heldout_notLoRA: 200 Qs, 50 drawings unseen by CC5K net AND LoRA)
| concept | n | cc5k=0 | cc5k=1 | answers with boxes 0 → 1 |
|---|---:|---:|---:|---|
| windows | 15 | 5 | 6 | 0 → 15 (all answered by raster_cc5k) |
| doors | 18 | 6 | 7 | 0 → 5 |
| WC seats | 32 | 28 | 28 | 10 → 16 |
| sinks | 14 | 11 | 11 | 8 → 12 |
| showers/baths | 14 | 8 | 8 | 0 → 0 |
| rooms etc. | 107 | 100 | 100 | 22 → 22 |
| **all** | 200 | **79.0** | **80.0** (+1.0 [−2.0, +4.0]) | **20% → 35%** |

cc5k=1 costs no accuracy on unseen drawings and adds located evidence on the worst bucket. Dev/test numbers with it on
stay labelled "inflated" (D8), but for windows the inflation is small: on dev the detector scores 36% on drawings in
CC5K's own train list vs 41% on the 17 that are not.

### Where dev points are left (night 609e41c; `stoa.eval.analyze 20261114-015159-pipeline-dev-272e`)
Weighted 81.7: cubicasa counts are **18.0 of the 18.3** weighted points lost (73.4% right). By concept (EN + FI):

| concept | w-pts lost | right | dominant error |
|---|---:|---|---|
| windows | 7.4 | 19% / 20% | under-count (gold mean 9.7; LoRA 8.5; detector 7.4) |
| doors | 3.2 | 38% / 28% | ±1–3 both ways |
| sinks | 2.5 | 73% / 66% | off-by-one under (19 vs 8 over) |
| WC seats | 2.2 | 72% / 81% | off-by-one under (13 vs 5 over, EN) |
| showers + baths | 1.5 | 84% / 74% | off-by-one under |
| saunas, bedrooms, bathrooms | 0.75 | 81–88% | — |
| swiss area | 0.10 | 97.5% | near misses 2–15% |

Windows, two counters (experiments/F/window_combo.py, dev, by CC5K list stratum): on the 91 drawings in CC5K's train list
LoRA 22%, detector 36%, max 26%, min 32%, rounded mean 24%, oracle-of-two 48%; agreement 18/91 at 50% right. No
combination of the two beats the detector alone, so the next window gain needs a better counter, not an ensemble.
Doors: LoRA 31–44%, detector 22–67% (n ≤ 45), no stable winner (R1 saw the sign flip across sets too).

### NEGATIVE: the detector's window undercount is not a resolution problem (03:45)
Leak-free cc5k_heldout (340 drawings outside CC5K's train list; fit/check halves by path hash; CPU; R1's model code used
read-only; `experiments/F/cc5k_scale_probe.py`, `cc5k_scale_score.py`, data in `$JUNCTION_SHARED/artifacts/F/cc5k_scale/`).
The miss grows with window density (long side / √gold < 200 px: 6% exact, 45% of windows missed; ≥ 400 px: 46% exact,
no bias), so two fixes were tried. Splitting long boxes (by median box length or wall thickness): never beats raw.
Upscaling ×1.5 / ×2 × morphology kernel 0/3/5/7: ×1.5 shrinks the windows bias (−2.8 → −2.1 per drawing) but exact
accuracy does not move (FROZEN 28.3 / 31.4 fit/check; best ×1.5 k=3 33.3 / 28.6); ×2 is worse on every symbol (check:
windows 18.6, WC 41.1, sinks 38.1). R1's FROZEN settings stand; the missed windows are styles, not pixels.

### `hard` on the test-1 code (run 20261114-031744-pipeline-hard-bb4a), by kind
| kind / source | n | acc | mean conf | share of wrong |
|---|---:|---:|---:|---:|
| composition / cubicasa | 83 | 38.6 | 0.27 | 48% |
| paraphrase / cubicasa | 100 | 70.0 | 0.45 | 28% |
| translation / cubicasa | 100 | 76.0 | 0.73 | 22% |
| swiss (all kinds) | 270 | 99.3 | 0.96 | 2% |
| ifc (all kinds) | 135 | 100 | 0.96 | 0% |

Paraphrases and translations generalise at the dev template level (73.4%); compositions are bounded by the atomic
counters (two counts both right). The paraphrase confidence (0.45 at 70% right) is the 0.5 unseen-wording cap (told W4).

## Earlier (01:45): night fdb0ecc: where the points are now, LoRA routing worth +8, held-out mechanisms

### Dev (S0's run 20261114-012630-pipeline-dev-878d): weighted 74.0%, micro 84.0%
Of the 26 weighted points still lost, ~25.6 are cubicasa counts (62.0%, 800 Qs). Swiss area 98%, swiss count / ifc
100%, opening_design count 81% (n=37). Cubicasa losses by concept (EN+FI), ranked by weighted points lost:
windows 7.9 (17% / 10% right; undercounts), doors 3.6 (12% / 40%), sinks 4.5 (44% / 48%; off-by-one under), WC seats
3.9 (58% / 55%; off-by-one under), showers+baths 1.5, saunas 1.4, bedrooms 0.6, storeys 1.0.

### LoRA routing simulation (experiments/F/lora_route_sim.py, gate table experiments/F/lora_gate_cc-v2.json)
Per-concept choice and confidence fitted on **train_gate** (pipeline 20261114-013211-pipeline-train_gate-8bc9 vs LoRA
20261114-012403-vlm_direct-train_gate-ee1b), then applied to dev. No model calls: stored predictions are merged.

| policy (dev) | weighted | micro | cubicasa | ECE | AUROC | conf≥0.8 share / acc | $/1k |
|---|---:|---:|---:|---:|---:|---:|---:|
| pipeline (fdb0ecc) | 74.0% | 84.0% | 62.0% | 0.011 | 0.922 | 72% / 97.2% | 0.055 |
| LoRA for every cubicasa count (own conf) | 82.1% | 88.7% | 73.9% | 0.164 | 0.923 | 60% / 98.8% | 0.062 |
| per concept (train_gate), conf = train_gate hit rate | 82.1% | 88.8% | 74.0% | 0.015 | 0.912 | 82% / 96.7% | 0.060 |
| + agree/disagree confidence | **82.1%** | **88.8%** | 74.0% | **0.012** | 0.915 | 79% / 97.6% | 0.060 |

Paired vs the pipeline (drawing-cluster bootstrap): ALL +4.8 [+3.4, +6.3] *, cubicasa +12.0 [+9.1, +14.9] * (126 wins,
30 losses). LoRA for wc, sink, door, window, bathroom, bedroom, balcony, sauna, storey, wc_room; pipeline for
shower_bathtub and kitchen (ties on train_gate). Use it only on ATOMIC questions (compose splits compounds; on whole
compounds the LoRA scores 9.6% and its own confidence is inverted, see the 01:29 section).

Overfitting check of the current cubicasa path: pipeline on train_gate cubicasa (480 Qs on 461 drawings nobody tuned
on) 64.8% vs dev 62.0%: no dev overfitting.

### Held-out (aggregates only, D10): raw_first fixed trust, not accuracy
| run (night fdb0ecc unless noted) | hard2q (clean) | hard2p (partly seen) |
|---|---:|---:|
| pipeline, scored | 70.4% (474e3e4: 69.3) | 78.3% |
| pipeline, judged text | 62.7% | 64.2% |
| pipeline AUROC / conf≥0.8 right | 0.73 / 90.6% (474e3e4: 0.50 / 77.2%) | 0.78 / 91.5% |
| pipeline by source: cubicasa / swiss / ifc (scored) | 38.0 / 76.2 / 100 | 38.0 / 90.5 / 100 |
| dxf alone, swiss scored | 81.9% | 97.1% |
| ifc alone, ifc scored | 100% | 100% |

dxf on hard2p (whose wordings were quoted to W2 at 00:57) 97.1% vs clean hard2q 81.9%: a 15-point "seen wording"
gap, the clearest overfitting signal tonight. ifc shows no gap (W1's fixes were general).

Mechanisms on hard2q (counts only; messages to owners contain no wordings):
1. **Canonical override** (W4), 6/45 swiss area, both held-out sets (hard2p 7): dxf answers as asked, right, but caps
   conf at 0.3 because it saw an operator word; the pipeline's modifiers() saw none, asks the canonical form (operator
   dropped), gets 0.98 "train hit rate", the KG cross-check ✓ confirms the wrong quantity → canonical wins. Pipeline
   never beats dxf on swiss on either held-out set (0 questions). Fix: union of operator detectors; a canonical answer
   never outranks a disagreeing raw answer; a ✓ only proves arithmetic.
2. **Unrecognised ratio phrasing** (W2), 11/45 swiss ratio, one English phrasing, parsed as a sum of two apartments at
   conf 0.6–0.9. Fix: dictionary-wide ratio family in all languages; no default sum at ≥0.6 without a sum cue.
3. **Count question typed as text** (W4), 14/50 cubicasa: no gate, no compose, base VLM at conf 0.2 (3/14 right).
4. **Compound question read as atomic** (W4), 11/50 cubicasa, language outside the dataset: prior '1' at the template
   hit rate 0.60 (3/11 right). Fix: ≥2 concept stems → multi; template hit rates only for template wordings.

### Cost depends on questions per drawing
Cubicasa dev (4.0 Qs/drawing) $0.073/1k vs train_gate (1.04 Qs/drawing) $0.37/1k for the same pipeline (0.38 vs 0.99
LLM calls/Q): the raster label call is made once per drawing. The eval now prints billed GPU seconds next to raw.

## Earlier (01:29): LoRA cc-v2 overfitting watch: the biggest cubicasa gain, with routing rules

R2's LoRA cc-v2 (Qwen3-VL-8B, trained on TRAIN cubicasa counts; train_gate drawings excluded), served on a private
:8002 and asked via `vlm_direct model=cc-v2`:

| split (cubicasa) | LoRA cc-v2 | integrated pipeline | note |
|---|---:|---:|---|
| dev (800) | **73.9%** | 61.8% (2b7935a) | +12.1 [+9.0, +15.2] cluster CI; ≈ +8 weighted pts |
| train_gate (480, unseen drawings) | 76.7% | – | no memorisation gap |
| hard: translation / paraphrase / composition | 75.0 / 65.0 / 9.6% | 66 / 58 / 23% (cbd2fe8) | compositions asked directly |
| hard2q (clean held-out) | 26% scored, 68% text | 52% (scored + text) | LoRA conf ≥ 0.8 → 15.8% right (inverted) |

Per concept on dev (LoRA / pipeline): windows 21/14, doors 35/26, WC seats 76/57, sinks 71/46, storeys 99/88,
saunas 93/71, bedrooms 90/71, WC rooms 100/88, balconies 91/83, bathrooms 91/88, kitchens 100/100, showers+baths
77/78.
**Rules:** route only atomic, known concepts (after compose/canonical; not showers+baths) to the LoRA; take the
confidence from the per-concept train_gate hit rate, never from the LoRA; paraphrases cost ~9 points, so canonicalise
for this VLM path (but ask dxf/ifc the original question).

## Earlier (01:15): clean held-out `hard2q`, judge numeric check

- **hard2p is contaminated for dxf/ifc**: my messages quoted its wordings, and dxf v6 then reached 97% on it.
  `hard2q` (third wording: Italian/Dutch/Swedish + new English; same drawings and answers) is the clean held-out
  set. Aggregates only; never quote its questions.

| | hard2 (dev) | hard2p | hard2q (clean) |
|---|---:|---:|---:|
| dxf v6 (W2 e539b77), swiss, scored | 97.1% | 97.1% (contaminated) | **81.9%** (conf ≥ 0.8: 84.9% right) |
| ifc (W1 532d61d), scored | 100% | 88.2% | **100%** |
| pipeline, scored / judged text | 77.8% / 47.8% (971b985) | 56.1% / 56.7% (971b985) | **69.3% / 64.2%** (474e3e4) |
| pipeline: conf ≥ 0.8 accuracy | 95.8% | 69.5% | 77.2% |

  Pipeline per source on hard2q: swiss 74.2% (dxf alone 81.9% scored), ifc 91.7% (ifc alone 100%), cubicasa 52%.
  The pipeline layer (canonicalisation + gate confidence) still loses points vs its own solvers on new wordings.
- **Judge:** a deterministic numeric check now decides when the reference holds exactly one number (2%, units
  converted; unit-less integers exact). ifc_bench text for the pipeline is 40.5% (was 42.5% with the lenient LLM).

## Earlier (01:05): held-out rewording (hard2p), cost billing, format swap

- **hard2p** = hard2 reworded (other English phrasing, German/French/Finnish; same drawings and answers; HELD OUT, D9).
  Integrated pipeline night 971b985: hard2 69.9% → hard2p **56.2%** (scored + judged text). Answers at conf ≥ 0.8
  are 95.8% right on hard2 but **69.5%** on hard2p. By source: cubicasa 61→51, ifc 89→64, swiss 72→58 (de/fr 47%).
  W2's dxf v5 (built while looking at hard2 failures): hard2 97.1% vs hard2p 63.8%. Threshold counts fail on
  "exceed"/"über", German ratios ("Um welchen Faktor") and "ohne Wohnung". Operators are keyword-matched.
  → An operator-word detector over synonym families in all dataset languages. If an operator word is present
  and no rule consumed it: defer to the agent and cap the confidence.
- **Cost billing:** raster timed local VLM calls by HTTP latency (queueing behind LoRA training: 30.9 s for a ~0.27 s
  call), which was 95% of the pipeline's cost. The eval now bills local-LLM GPU time as min(reported, token estimate):
  pipeline dev $0.41 → $0.04–0.05 per 1k questions. stoa.llm still bills cache hits as free (asked R2).
- **Format swap** (same dev questions on the sibling PNG/DXF/SVG): 99.6% of 250; evidence follows the asked file.
- **hard2 text answers** (night 971b985): "Which is smaller, apartment B or H?" is still canonicalised to an area
  question and answered with a number (swiss text 0/15 judged; dxf alone 15/15).

## Earlier (00:47): `hard2`: novel reasoning kinds expose confidently wrong answers

Stoa says the hidden test is "harder and different". `hard2` (256 Qs on dev drawings, answers from ground truth
only) asks what questions.jsonl never asks: averages, ratios, percentages, thresholds, complements ("not in
apartment A"), ft/ft², argmin and yes/no. Runs: pipeline `20261114-004439-pipeline-hard2-945f` (night cbd2fe8),
`dxf` alone `20261114-004625-dxf-hard2-eb26`, `ifc` alone `20261114-004657-ifc-hard2-8ead`.

| | pipeline | dxf alone (swiss) | ifc alone (ifc) |
|---|---:|---:|---:|
| scored accuracy | 35.4% (swiss 29.5%, ifc 26%, cubicasa 54%) | **47.6%** | 26.5% |
| text, LLM-judged | swiss 0%, ifc 0%, cubicasa 64% | **86.7%** | 0% |
| AUROC (confidence ranks right above wrong) | **0.32** (worse than chance) | 0.50 | 0.22 |
| conf ≥ 0.8: share / accuracy | 66% / **24%** | 31% / 49% | 94% / 28% |

**Mechanism 1 (pipeline, W4): canonicalisation rewrites a novel question into the nearest template, then the
train hit rate of that template (0.976) replaces the solver's confidence.**
"How many times larger is apartment B than apartment A?" → canonical "How many apartments …?" → 2 at 0.976
(dxf alone: 1.07 ✓ at 0.45). "What share of the floor … does apartment C take up, in percent?" → apartment C
area 43.71 m² at 0.976. "Average net floor area of rooms 1.77 and 1.78" → 0.0 m² at 0.976 (dxf alone 14.7 ✓).
dxf alone per recipe: apartment ratio 93%, smaller apartment 87% (judged), room sum in ft² 100%, threshold
60%, average 33%, doors per apartment 33%, share in % 7%, floor minus apartment 7% (conf 0.91: ignores "not").
→ Fix: ask the solver the ORIGINAL question first; canonicalise only for languages/wordings it can't parse
(or when it abstains); and use conf = min(train hit rate, solver's own confidence). The solver knows when it
fell back to table QA (0.45–0.6).

**Mechanism 2 (ifc, W1): the parser maps unknown operators onto a known quantity at full confidence.**
"Average net floor area per room on 'Attic'" → the storey total (212.4 vs 26.5) at 0.95; "What percentage of
the floor area of '0' does room X take up?" → the room's m² at 0.97; "How many of rooms A, B, C, D are larger
than 5 m²?" → wrong at 0.97. Unit conversion works (walls in feet 100%).
→ Fix: an operator guard. If the question contains average/mean/per, percent/percentage/share, ratio/"times",
"more/less than N", "excluding/not", and the parser has no rule for it, cap the confidence (≤ 0.3) and
put the operator in `missing`, or hand the question to the LLM fact-card path with the operator spelled out.

**What works:** unit changes (ft², ft) 100% via dxf/ifc; cubicasa compositions decompose correctly (wet rooms,
toilets + showers; accuracy limited by the counts); "more bedrooms than bathrooms?" 96% judged.
Caveat: share-in-% golds use the dataset's "total net floor area of all numbered indoor rooms" as the
denominator; dxf gave 100.8% once, so the apartment and floor-total definitions may not nest. Check before
treating that recipe as solver error.

## Earlier (00:32): pipeline gate v1, calibration, hard compositions, label→fixture

Runs: `20261114-002746-pipeline-dev` (W4 gate v1, night-W4 279b5ec) vs `20261114-000718-pipeline-dev`;
`20261114-003003-pipeline-hard`. Paired with `experiments/r1/stats/compare.py` (cluster CI).

**1. Gate v1 = +0.5 points (n.s.).** micro 81.3 → 81.8 [−0.2, +1.2]; weighted 72.2 → 73.1; cubicasa
59.4 → 60.8 [−0.2, +3.1]; cost $1.35 → $0.54 per 1k questions. The loss table is unchanged in shape:
windows (EN 17%, FI 10%; 7.9 w-pts), doors (EN 12%, FI 44%; 3.6 w-pts; the EN/FI gap is drawing mix, both
go to vlm_direct), WC seats (55–58%; 3.9 w-pts, prior answers 1 where gold is 2), sinks (44–48%; 4.5 w-pts,
prior 2 where gold is 3). Errors are undercounts (median pred/gold 0.5).

**2. Calibration is good and now measured on every run.** `python -m stoa.eval.calibration RUN...` and
a `calibration: ...` line in every eval report (also in the leaderboard JSON and viewer).

| run | ECE | Brier | AUROC | answers with conf ≥ 0.8 | their accuracy |
|---|---:|---:|---:|---:|---:|
| pipeline dev 00:07 | 0.043 | 0.083 | 0.93 | 61% | 99.1% |
| pipeline dev gate v1 | **0.015** | **0.078** | 0.92 | 67% | 97.9% |
| pipeline hard gate v1 | 0.032 | 0.071 | 0.95 | 65% | 98.9% |
| raster v2 dev (cubicasa only, 00:30) | 0.038 | 0.169 | 0.81 | 23% | 88.1% |
| vlm_direct dev (constant 0.3) | 0.021 | 0.218 | **0.50** | 0% | – |

Gate v1 moved storeys (vlm_direct) and bathrooms (prior) into the 0.8–0.9 band, where they are ~85–90%
right: honest, so high-confidence accuracy dips a little while ECE improves 3×. Cubicasa reliability bins
are on the diagonal (conf 0.13/0.21/0.54/0.60/0.76/0.88/0.94 → acc 0.14/0.26/0.53/0.57/0.75/0.88/0.91).
For the demo/judges: "when the pipeline says ≥ 0.8 (two thirds of answers), it is right 98% of the time."
Confidently wrong (conf ≥ 0.8) on dev: 28 of 1,339: storeys via vlm_direct 13, Swiss area totals via dxf 10
(all 2–16% too high, see W2), bathrooms via prior 4, and **1 IFC regression**: Polish "Ile schodów … w
modelu «…»" was canonicalised to "on the floor plan of …", so `ifc` counted stairs on the plan's storey
(0) instead of the model (3) at conf 0.975 (W1 had reported the "w modelu" scope bug to W4).

**3. Routing gaps.** opening_design: all 61 dev questions go to vlm_direct (18.9%) although W2's `schedule`
solver scores 78.3% on them (00:30, 2d39b54) → route opening_design to `schedule`. The ifc regression above.

**4. Hard compositions on cubicasa fail for one reason: their parts.** "Windows − doors", "doors + windows"
are 0–18% because the sub-answers are vlm_direct's typical guesses (window 10, door 10 → "0 more"). The
decomposition itself works (swiss and ifc compositions 99–100%). Bedrooms + bathrooms 47% (bathroom
over by 1). Nothing to fix in the composer; it inherits the symbol counting gap.

**5. Experiment F-label2fixture (negative/weak).** Can room-label counts (R1's one VLM call per drawing)
predict fixtures? On TRAIN gold (4,366 drawings) the relations are strong: sinks = kitchens + bathrooms +
WC rooms 81% (mode 60%), showers+baths = bathrooms 85% (81%), WC seats = WC rooms + bathrooms 72% (69%).
With PREDICTED labels (R1 cache; kitchens fixed at 1 because the reader over-counts kitchens 12/51 on
train): dev sinks 64.3% vs prior 57.1% (+7.1, CI [−1.4, +15.7], 25 wins / 15 losses, 140 drawings; train
+3.3 on 60), WC seats −5.7, showers+baths −3.1. So: only sinks, positive but not significant; nearly free
when the label call is already made for room questions. Code: `experiments/F/label2fixture/`.

## Previous: integrated pipeline on dev (00:22) — where the remaining points are

Run `20261114-000718-pipeline-dev` (S0's integrated night): micro **81.3%** (95% cluster CI 77.0–85.0), weighted_acc
**72.2%**, evidence on 1,318/2,215 answers, $0.00135/question. Solved: Swiss counts 100%, Swiss areas 98%, IFC 100%.
**Left: cubicasa (59%, ≈27.8 w-pts lost) and opening_design (11–19%, dev-only, 46 Qs).** Swiss areas: 8 near
misses, all 2–16% too high (the R1 overshoot: lifts/stairs/unnamed rooms).

cubicasa per concept (pipeline final answer vs each component, from the traces):

| concept | n | pipeline | prior | raster | vlm_direct | one of raster/VLM right | w-pts lost |
|---|---:|---:|---:|---:|---:|---:|---:|
| windows | 108 | 11% | 14% | 14% | 11% | 19% | **8.1** |
| sinks | 98 | 46% | 46% | 46% | 52% | 55% | **4.5** |
| WC seats | 107 | 57% | 57% | 57% | - | - | **3.9** |
| doors | 57 | 26% | 18% | 18% | 26% | 39% | **3.6** |
| floors | 96 | 75% | 75% | 75% | (not called; 86–92% elsewhere) | - | 2.0 |
| showers+baths | 83 | 78% | 78% | 78% | - | - | 1.5 |
| saunas | 58 | 71% | 62% | 71% | 71% | **93%** | 1.4 |
| WC rooms | 40 | 75% | 42% | 75% | 35% | **88%** | 0.9 |
| bedrooms | 41 | 78% | 37% | 78% | 71% | **88%** | 0.8 |
| balconies / bathrooms / kitchens | 112 | 74–100% | | | | | 0.9 |

Errors are now mostly **undercounts** (off-by-one under 145, undercount 139; median pred/gold 0.50).

Recommendations (owner, expected gain):
1. **Windows + doors = 11.7 w-pts, and no current method beats ~26%.** This is a capability gap, not routing:
   symbol counting by pointing on upscaled tiles, a LoRA counter (R2, running), or a classical detector for
   wall-gap window symbols. W3 / R1 / R2. Even 50% on windows would add ~4 w-pts.
2. **Floors → VLM** (vlm_direct 92% vs prior 72% on train_gate; 86% vs 75% on dev). The pipeline answers floors
   from the prior. W4, ≈ +1.0 w-pts, nearly free.
3. **Arbitration when raster ≠ VLM:** for saunas, WC rooms and bedrooms, one of them is right 88–93% of the time
   vs 71–78% now. vlm_direct's confidence is a constant 0.3, so comparing raw confidences across solvers picks
   by accident (e.g. windows: raster 4 @0.13 vs VLM 2 @0.30 → VLM). Use per-concept accuracies from
   `results/gates/vlm_direct_vs_prior.json` (train) as the confidence, or a targeted verification prompt. W4/W3,
   ≈ +1.5 w-pts.
4. The pipeline trace says "no train gate for this kind of question" for Finnish cubicasa templates. Check the
   router's template keys (use `stoa.data.template_of`, and pool translations with `concept_map`). W4.
5. opening_design (dev-only): schedule solver (W2's NEXT); 46 scored Qs at 11–19% today.

---

## Where the weighted points go (vlm_direct, dev)

weighted_acc lost per bucket = (1 − bucket accuracy) × full-data share:

| bucket | full-data share | vlm_direct acc | w-pts lost | who can win them back |
|---|---:|---:|---:|---|
| cubicasa symbol counts (windows, doors, sinks, WC seats, showers+baths) | 67.8% × 453/800 | 36% (prior 43%) | **24.7** | W3 (+R2) |
| swiss counts | 20.3% | 46% | **11.0** | W2: R1's DXF rules are exact on 200–1000 floors |
| cubicasa room-label counts (saunas, kitchens, bedrooms, bathrooms, WC rooms, balconies, floors) | 67.8% × 347/800 | 68% (prior 68%) | **9.4** | W3: read the room labels |
| swiss areas | 9.5% | 12% | **8.4** | W2: DXF polygons (S0 592/594) |
| ifc_models area / count / volume / length | 2.4% | 0–6% | 2.3 | W1: answer from the IFC |

## Top 3 loss buckets and hypotheses

1. **cubicasa symbol counts: 24.7 w-pts.** The VLM does not count. It answers **"2"** to most fixture
   questions whatever the drawing shows: WC seats 73/107, sinks 82/98, showers+bathtubs 67/83, bathrooms
   21/34, WC rooms 21/40. Showers+bathtubs drop from 78% (prior "1") to 24% because the model answers
   "2", which suggests it counts the two nouns in the question. Windows (12%) and doors (26%) are
   undercounted (median pred/gold 0.8; often "2" for 8+). Images are small (median 765 px; the run used
   250–1,400 image tokens), so symbols are a few pixels wide.
   *Fix to test:* point-then-count (one point or box per object = evidence; count = number of points)
   on an upscaled (2–3×) and tiled image. Ask one class at a time, e.g. "showers" and "bathtubs"
   separately, then sum. Gate per concept against the prior using a TRAIN sample (D4). Expected: windows
   and doors are the big prize (11.6 w-pts at ~15% today).
2. **swiss counts: 11.0 w-pts.** Doors 0% (pred/gold ≈ 0.1–0.4; floors have ~30 doors), windows 0–5%,
   washbasins 25%. The PDF/PNG is a whole building. *Fix:* R1's DXF rules (doors = 5-vertex DOOR
   LWPOLYLINEs 1000/1000, windows = WINDOW LWPOLYLINEs/3 200/200, bathtubs = 69-vertex FIXTURE, showers =
   5-vertex FIXTURE, rooms labelled X = ROOM_TEXT 1213/1213, apartments = "Whg./App." labels 200/200) →
   W2. Expected ≈ +10 w-pts.
3. **swiss areas: 8.4 w-pts.** VLM areas are mostly too low (pred/gold median 0.52); apartment-A area
   gets 0/30 (prior 7/30). *Fix:* DXF ROOM_OUTLINE polygons containing the room-number text (S0: 592/594
   rooms; R1: floor total 91%, apartment 96.4%); the printed "16.78 m²" text when present (27% of floors)
   as a cross-check → W2. Expected ≈ +8 w-pts.

Also:
- **Room-label counts (9.4 w-pts):** the VLM beats the prior on bedrooms (71% vs 37%) but loses on
  bathrooms (35% vs 88%), balconies (22% vs 52%) and WC rooms. These are text-reading tasks (R1 23:39):
  list the room labels (KH, KPH, PH, PESUH, SH, WC, MH, S, PARV…) with boxes, then count by class.
- **Confidence is constant (0.3)**, so nothing can be calibrated or gated. Every solver should emit a
  confidence that varies (e.g. agreement of two methods, prior hit rate, number of evidence items) (D4).
- **No evidence on any answer.** Stoa scores verifiability; point-then-count gives evidence for free.
- **Cost:** vlm_direct ≈ 0.5 GPU-s and ~400–1,500 input tokens per question (/bin/bash.0003 at our rates). The DXF
  and IFC paths are deterministic and ~free, so take them first (cascade).
- cubicasa drawings often say "Piirros ohjeellinen, ei mittakaavassa" ("indicative drawing, not to
  scale"). If the hidden set asks for areas on such plans, state the scale assumption (Stoa point 3).

## Gating prior vs VLM, chosen on TRAIN (added 00:19)

`train_gate` = 960 train questions (20 per cubicasa template, Swiss and train IFC projects; one language per
concept). Gate per concept (EN + translations pooled): use vlm_direct only if it beats the prior by >10 points
and by ≥2 questions on train_gate. Table: `results/gates/vlm_direct_vs_prior.json` (`python -m stoa.eval.gates`).
VLM chosen for: bedrooms, floors, Swiss apartments, rooms labelled X, Swiss WCs, IFC stairs. Prior kept for:
showers+bathtubs, bathrooms, WC rooms, balconies, kitchens, WC seats, saunas, windows, doors.

Applied offline to the existing dev runs (an honest estimate, because the gates never saw dev):

| | dev micro | weighted_acc | cubicasa | swiss count |
|---|---:|---:|---:|---:|
| prior | 26.9% | 41.0% | 54.1% | 18.2% |
| vlm_direct | 32.0% | 44.1% | 49.8% | 45.8% |
| **gated (train-chosen)** | **34.8%** | **48.6%** | **57.2%** | 41.5% |

→ W4 should gate from this file now. Swiss counts drop under gating only because doors/windows/washbasins
fall back to the prior at n=6; the DXF solver (W2) replaces both there anyway.

## Generality: the `hard` split (added 00:02)

`hard` = 711 Qs on dev drawings: real translations (the other-language twin), rule paraphrases (EN/SV/DE,
unit changes) and compositions computed from known answers (`stoa/eval/hard.py`).

| kind | n | prior | vlm_direct (`20261113-235933-vlm_direct-hard`) |
|---|---:|---:|---:|
| translation | 250 | 31.2% | 35.2% |
| paraphrase | 250 | 23.6% | 26.8% |
| composition | 211 | 3.7% | 9.6% |

Findings:
1. **Compositions break both** (VLM 9.6%): doors+windows totals 0%, room A + room B 0–15%, room A − room B 0%,
   apartment A+B 0%, largest of 3 rooms 0%. The only wins are yes/no sauna (59%) and bedrooms+bathrooms (29%).
   → **W4: decompose questions.** Split "doors and windows in total" or "how many more X than Y" into
   sub-questions, answer each with the cheapest exact solver (DXF/IFC/text), do the arithmetic in code, and
   keep the union of the evidence. That generalises to the harder hidden set at near-zero cost, and the
   trace shows the reasoning (Stoa scores reasoning).
2. **Unit trap:** Swiss room area asked in m² gets 57% (paraphrase); the same room asked in **ft²** gets 14%
   (floor total in ft² 0%). → Compute in the drawing's native unit, convert in code, and set `Answer.unit` to
   what the question asked for (the eval converts anyway, but the model doesn't).
3. **Language sensitivity:** Swedish rewordings collapse where English works: saunas EN 80% → SV 0%,
   balconies EN 60% → SV 0%. German saunas 80%. Real dataset twins: swiss translation 39% (EN-only paraphrase
   room-area 57%). → Parse every question into a language-neutral intent (W4) before solving, and add
   SV/DE/FR/IT/ET/NL/DA/ES synonyms to the parser.
4. ifc_models stays at ~0% on every kind: nothing works on rendered PDFs without the IFC (W1).

---

## 20261113-235024-vlm_direct-dev (baseline: 20261113-234812-dummy-dev)

- scored questions: 2000 on 320 drawings; micro accuracy **32.0%** (95% cluster CI 28.0–36.5); weighted_acc **44.1%**
- refusals: 200/2215; exceptions: 0; mean cost $0.00000/question; evidence on 0/2215 answers
- baseline (dummy) on the same questions: 26.1%

### Where points are lost (ranked by weighted_acc points lost)

| # | bucket | template | n | acc | baseline acc | lost | % of lost Qs | w-pts lost | main error types |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | cubicasa5k/count | how many windows are shown on this floor plan? | 58 | 12% | 17% | 51 | 3.8% | 4.32 | undercount 37, off-by-one under 7, overcount 4 |
| 2 | cubicasa5k/count | kuinka monta ikkunaa pohjapiirustuksessa on? | 50 | 12% | 10% | 44 | 3.2% | 3.73 | undercount 39, off-by-one under 3, overcount 1 |
| 3 | cubicasa5k/count | kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty … | 46 | 15% | 74% | 39 | 2.9% | 3.30 | off-by-one over 33, off-by-one under 4, overcount 2 |
| 4 | cubicasa5k/count | how many doors are shown on this floor plan? count doorways fitted wi… | 32 | 12% | 22% | 28 | 2.1% | 2.37 | undercount 15, overcount 5, off-by-one over 5 |
| 5 | cubicasa5k/count | kuinka monta pesu- ja tiskiallasta (keittiö ja kylpytilat yhteensä; k… | 50 | 48% | 48% | 26 | 1.9% | 2.20 | off-by-one under 14, undercount 12 |
| 6 | cubicasa5k/count | how many toilet bowls (wc seats) are drawn on this floor plan? | 65 | 60% | 58% | 26 | 1.9% | 2.20 | off-by-one over 18, off-by-one under 6, overcount 2 |
| 7 | cubicasa5k/count | how many showers and bathtubs are drawn on this floor plan in total? | 37 | 35% | 84% | 24 | 1.8% | 2.03 | off-by-one over 21, undercount 1, overcount 1 |
| 8 | cubicasa5k/count | how many sinks and wash basins (kitchen and bathroom combined; a doub… | 48 | 56% | 44% | 21 | 1.5% | 1.78 | off-by-one under 15, off-by-one over 3, undercount 2 |
| 9 | cubicasa5k/count | kuinka monta wc-istuinta pohjapiirustukseen on piirretty? | 42 | 57% | 55% | 18 | 1.3% | 1.52 | off-by-one over 16, overcount 1, off-by-one under 1 |
| 10 | swiss_dwellings/count | how many doors (interior doors and entrance doors together) are drawn… | 28 | 0% | 0% | 28 | 2.1% | 1.42 | undercount 26, overcount 1, off-by-one over 1 |
| 11 | swiss_dwellings/count | how many washbasins are drawn on this floor plan? | 32 | 25% | 28% | 24 | 1.8% | 1.22 | overcount 9, undercount 8, off-by-one under 5 |
| 12 | cubicasa5k/count | kuinka monta erillistä wc-tilaa pohjapiirustuksessa on? | 22 | 36% | 36% | 14 | 1.0% | 1.19 | off-by-one over 9, overcount 5 |
| 13 | cubicasa5k/count | kuinka monta ovea pohjapiirustuksessa on? laske oviaukot, joissa on o… | 25 | 44% | 12% | 14 | 1.0% | 1.19 | undercount 9, off-by-one under 3, off-by-one over 2 |
| 14 | swiss_dwellings/area | what is the net floor area of room <N> (<Q>) in m²? | 67 | 36% | 1% | 43 | 3.2% | 1.02 | too high 21, too low 12, near miss (2-15%) 10 |
| 15 | cubicasa5k/count | how many balconies (parveke, including glazed balconies) are on this … | 14 | 14% | 64% | 12 | 0.9% | 1.02 | off-by-one over 9, overcount 3 |
| 16 | swiss_dwellings/count | how many windows are drawn on this floor plan? | 21 | 5% | 5% | 20 | 1.5% | 1.01 | undercount 18, off-by-one under 1, overcount 1 |
| 17 | swiss_dwellings/area | what is the total net area in m² of all rooms labelled <Q> on this fl… | 44 | 7% | 0% | 41 | 3.0% | 0.98 | too low 35, too high 3, near miss (2-15%) 3 |
| 18 | swiss_dwellings/count | wie viele fenster sind auf diesem grundriss eingezeichnet? | 19 | 0% | 0% | 19 | 1.4% | 0.96 | undercount 11, overcount 6, off-by-one under 1 |
| 19 | cubicasa5k/count | how many bathrooms or washrooms (e.g. kh, kph, ph, pesuh, sh) are on … | 16 | 31% | 75% | 11 | 0.8% | 0.93 | off-by-one over 10, overcount 1 |
| 20 | cubicasa5k/count | how many separate wc rooms (toilet rooms marked wc) are on this floor… | 18 | 39% | 50% | 11 | 0.8% | 0.93 | overcount 6, off-by-one over 5 |

### Error types per bucket

| bucket | n | acc | error types (count) | pred/gold ratio p10/p50/p90 (wrong numeric) |
|---|---:|---:|---|---|
| cubicasa5k/count | 800 | 50% | off-by-one over 185, undercount 116, off-by-one under 64, overcount 37 | 0.33 / 0.80 / 2.00 |
| ifc_models/area | 259 | 0% | too high 194, too low 42, near miss (2-15%) 22 | 0.56 / 1.94 / 4.65 |
| ifc_models/count | 64 | 6% | undercount 52, overcount 5, off-by-one over 3 | 0.00 / 0.32 / 1.67 |
| ifc_models/length | 9 | 0% | too low 9 | 0.27 / 0.36 / 0.54 |
| ifc_models/volume | 22 | 0% | too low 15, too high 7 | 0.00 / 0.00 / 13.57 |
| opening_design/area | 9 | 11% | too low 6, too high 2 | 0.01 / 0.25 / 10.76 |
| opening_design/count | 37 | 19% | undercount 25, overcount 3, off-by-one over 1, off-by-one under 1 | 0.07 / 0.22 / 2.00 |
| swiss_dwellings/area | 400 | 12% | too low 272, too high 48, near miss (2-15%) 33 | 0.26 / 0.52 / 1.29 |
| swiss_dwellings/count | 400 | 46% | undercount 121, off-by-one under 37, overcount 36, off-by-one over 23 | 0.39 / 0.71 / 1.75 |

### Failing examples (top templates)

**1. cubicasa5k/count — how many windows are shown on this floor plan?** (51/58 wrong)

- `high_quality-8683.png`: How many windows are shown on this floor plan? — gold **3**, pred **2** count (off-by-one under; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 1178->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=1178 tok_out=2 gpu_s=0.29 api_calls=0
- `high_quality_architectural-3505.png`: How many windows are shown on this floor plan? — gold **16**, pred **10** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.4s tok 1445->3 ⟶ raw: 10 ⟶ cost: calls=1 tok_in=1445 tok_out=3 gpu_s=0.41 api_calls=0
- `high_quality_architectural-7694.png`: How many windows are shown on this floor plan? — gold **15**, pred **4** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.5s tok 788->2 ⟶ raw: 4 ⟶ cost: calls=1 tok_in=788 tok_out=2 gpu_s=0.49 api_calls=0

**2. cubicasa5k/count — kuinka monta ikkunaa pohjapiirustuksessa on?** (44/50 wrong)

- `colorful-13820.png`: Kuinka monta ikkunaa pohjapiirustuksessa on? — gold **9**, pred **0** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.4s tok 782->2 ⟶ raw: 0 ⟶ cost: calls=1 tok_in=782 tok_out=2 gpu_s=0.38 api_calls=0
- `high_quality_architectural-9862.png`: Kuinka monta ikkunaa pohjapiirustuksessa on? — gold **6**, pred **4** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 558->2 ⟶ raw: 4 ⟶ cost: calls=1 tok_in=558 tok_out=2 gpu_s=0.32 api_calls=0
- `high_quality-14359.png`: Kuinka monta ikkunaa pohjapiirustuksessa on? — gold **8**, pred **2** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 414->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=414 tok_out=2 gpu_s=0.31 api_calls=0

**3. cubicasa5k/count — kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä?** (39/46 wrong)

- `high_quality_architectural-9648.png`: Kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä? — gold **0**, pred **2** count (overcount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.6s tok 585->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=585 tok_out=2 gpu_s=0.59 api_calls=0
- `high_quality_architectural-11880.png`: Kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä? — gold **1**, pred **2** count (off-by-one over; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.2s tok 791->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=791 tok_out=2 gpu_s=0.17 api_calls=0
- `high_quality-10241.png`: Kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä? — gold **1**, pred **2** count (off-by-one over; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 816->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=816 tok_out=2 gpu_s=0.34 api_calls=0

**4. cubicasa5k/count — how many doors are shown on this floor plan? count doorways fitted with a door; open door…** (28/32 wrong)

- `high_quality_architectural-13772.png`: How many doors are shown on this floor plan? Count doorways fitted with a door; open door… — gold **13**, pred **10** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.5s tok 1231->3 ⟶ raw: 10 ⟶ cost: calls=1 tok_in=1231 tok_out=3 gpu_s=0.48 api_calls=0
- `colorful-3133.png`: How many doors are shown on this floor plan? Count doorways fitted with a door; open door… — gold **7**, pred **5** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 1263->2 ⟶ raw: 5 ⟶ cost: calls=1 tok_in=1263 tok_out=2 gpu_s=0.33 api_calls=0
- `high_quality_architectural-5046.png`: How many doors are shown on this floor plan? Count doorways fitted with a door; open door… — gold **23**, pred **12** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.4s tok 1479->3 ⟶ raw: 12 ⟶ cost: calls=1 tok_in=1479 tok_out=3 gpu_s=0.42 api_calls=0

**5. cubicasa5k/count — kuinka monta pesu- ja tiskiallasta (keittiö ja kylpytilat yhteensä; kaksoisallas lasketaa…** (26/50 wrong)

- `high_quality_architectural-1215.png`: Kuinka monta pesu- ja tiskiallasta (keittiö ja kylpytilat yhteensä; kaksoisallas lasketaa… — gold **4**, pred **2** count (undercount; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 401->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=401 tok_out=2 gpu_s=0.29 api_calls=0
- `colorful-8235.png`: Kuinka monta pesu- ja tiskiallasta (keittiö ja kylpytilat yhteensä; kaksoisallas lasketaa… — gold **3**, pred **2** count (off-by-one under; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.2s tok 419->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=419 tok_out=2 gpu_s=0.17 api_calls=0
- `high_quality_architectural-11885.png`: Kuinka monta pesu- ja tiskiallasta (keittiö ja kylpytilat yhteensä; kaksoisallas lasketaa… — gold **3**, pred **2** count (off-by-one under; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.2s tok 761->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=761 tok_out=2 gpu_s=0.22 api_calls=0

**6. cubicasa5k/count — how many toilet bowls (wc seats) are drawn on this floor plan?** (26/65 wrong)

- `colorful-3159.png`: How many toilet bowls (WC seats) are drawn on this floor plan? — gold **1**, pred **2** count (off-by-one over; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 934->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=934 tok_out=2 gpu_s=0.26 api_calls=0
- `high_quality_architectural-9540.png`: How many toilet bowls (WC seats) are drawn on this floor plan? — gold **1**, pred **2** count (off-by-one over; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.1s tok 163->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=163 tok_out=2 gpu_s=0.11 api_calls=0
- `high_quality_architectural-3876.png`: How many toilet bowls (WC seats) are drawn on this floor plan? — gold **3**, pred **2** count (off-by-one under; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.2s tok 702->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=702 tok_out=2 gpu_s=0.21 api_calls=0

**7. cubicasa5k/count — how many showers and bathtubs are drawn on this floor plan in total?** (24/37 wrong)

- `high_quality_architectural-12531.png`: How many showers and bathtubs are drawn on this floor plan in total? — gold **1**, pred **2** count (off-by-one over; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.2s tok 938->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=938 tok_out=2 gpu_s=0.19 api_calls=0
- `high_quality_architectural-1988.png`: How many showers and bathtubs are drawn on this floor plan in total? — gold **1**, pred **2** count (off-by-one over; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.2s tok 578->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=578 tok_out=2 gpu_s=0.17 api_calls=0
- `high_quality_architectural-9862.png`: How many showers and bathtubs are drawn on this floor plan in total? — gold **1**, pred **2** count (off-by-one over; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 554->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=554 tok_out=2 gpu_s=0.32 api_calls=0

**8. cubicasa5k/count — how many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts …** (21/48 wrong)

- `high_quality_architectural-7669.png`: How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts … — gold **3**, pred **2** count (off-by-one under; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.3s tok 257->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=257 tok_out=2 gpu_s=0.29 api_calls=0
- `high_quality_architectural-3505.png`: How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts … — gold **3**, pred **2** count (off-by-one under; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.4s tok 1465->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=1465 tok_out=2 gpu_s=0.39 api_calls=0
- `high_quality_architectural-7777.png`: How many sinks and wash basins (kitchen and bathroom combined; a double-bowl sink counts … — gold **3**, pred **2** count (off-by-one under; evidence 0; conf 0.3) — trace: local:qwen3-vl-8b 0.2s tok 322->2 ⟶ raw: 2 ⟶ cost: calls=1 tok_in=322 tok_out=2 gpu_s=0.21 api_calls=0

### Templates where the baseline beats this run (dev oracle; choose any gating on TRAIN, not here)

Best-of-two per template would add 101 correct answers (5.0 pts micro).

| bucket | template | n | this run | baseline |
|---|---|---:|---:|---:|
| cubicasa5k/count | kuinka monta suihkua ja kylpyammetta pohjapiirustukseen on piirretty yhteensä? | 46 | 7 | 34 |
| cubicasa5k/count | how many showers and bathtubs are drawn on this floor plan in total? | 37 | 13 | 31 |
| cubicasa5k/count | kuinka monta kylpy- tai pesuhuonetta (esim. kh, kph, ph, pesuh, sh) pohjapiirus… | 18 | 7 | 18 |
| swiss_dwellings/area | what is the net floor area of apartment a in m², summing all its rooms except b… | 30 | 0 | 7 |
| cubicasa5k/count | how many bathrooms or washrooms (e.g. kh, kph, ph, pesuh, sh) are on this floor… | 16 | 5 | 12 |
| cubicasa5k/count | how many balconies (parveke, including glazed balconies) are on this floor plan? | 14 | 2 | 9 |
| cubicasa5k/count | how many windows are shown on this floor plan? | 58 | 7 | 10 |
| cubicasa5k/count | how many kitchens (including kitchenettes, open kitchens and utility kitchens) … | 24 | 21 | 24 |
| cubicasa5k/count | how many doors are shown on this floor plan? count doorways fitted with a door;… | 32 | 4 | 7 |
| swiss_dwellings/area | what is the net floor area of apartment c in m², summing all its rooms except b… | 12 | 0 | 2 |
| ifc_models/area | wat is de netto vloeroppervlakte van de ruimte <Q> op <Q>, in m²? | 116 | 1 | 3 |
| cubicasa5k/count | how many separate wc rooms (toilet rooms marked wc) are on this floor plan? | 18 | 7 | 9 |

### Calibration (accuracy per confidence bin)

| confidence | n | accuracy |
|---|---:|---:|
| 0.2–0.3 | 3 | 0% |
| 0.3–0.4 | 1997 | 32% |

