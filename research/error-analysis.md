# Error analysis (E = agent F)

Updated 10:45, 14 Nov 2026 (sections newest first). Regenerate the tables with
`/data/User/fangy4/envs/junction/bin/python -m stoa.eval.analyze <run_id> --baseline <dummy run_id> --top 20`.
For paired significance use `python3 experiments/r1/stats/compare.py RUN_A RUN_B --by template` (cluster CI).

Run analysed: `20261113-235024-vlm_direct-dev` (R2's baseline: Qwen3-VL-8B local, image only, direct
answer) vs `20261113-234812-dummy-dev` (template prior), both on dev v2 (hash f43c5369; 2,215 Qs,
2,000 scored, 320 drawings).

| run | micro (95% cluster CI) | weighted_acc | refusals | evidence |
|---|---|---:|---:|---:|
| dummy (prior) | 26.1% | 40.4% | 0 | 0% |
| vlm_direct | 32.0% (28.0–36.5) | 44.1% | 200 (all IFC) | 0% |

## LATEST (10:45, cycle 227): end-of-night state — the same-gold suite, and what is still confidently wrong

**One command for the whole OPEN probe suite** (18 probes, 10,062 rows, ~8 min with 3 streams):
`PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/F/probe_suite.py run --tag X` then
`python3 experiments/F/probe_suite.py compare $JUNCTION_SHARED/artifacts/F/probe_suite/X.json` (default base = night
1a4e2af; lists every lost row). Use it on any change made after Stoa's noon reveal.

Night 7a78559 → 1a4e2af (S0 cycles 40–41), paired on 9,410 common rows: **60 won / 8 lost, confident-wrong 67 → 65**.
All 8 losses are low-confidence flips (≤ 0.61: LoRA counts, an agent sum, a Swedish doors-minus-windows compose).
Wins: W1 6f1edf1 sheets with meaningless names know their storey (this_plan_nh 86.5 → 100, 44 W), apt_wording_scope_nh
95.6 → 100. New probe `whole_top` (+ hashed `_nh`; 326 rows each; `experiments/F/whole_top_probe.py`): 'whole building',
'across all floors', 'entire model', nl/de/fr building words, 'top floor' / 'uppermost storey' / 'oberstes Geschoss' on
models and other-storey sheets: all 100%, 0 confident-wrong; the one miss family is **"How many N are in this building?"
asked on a plan sheet → that sheet's storey (3/18, max conf 0.68)** (W1 told).

**The 65 confident-wrong suite rows (conf ≥ 0.8) are 4 known causes, all also wrong in the dataset wording:**
| cause | rows | owner | note |
|---|---:|---|---|
| two Swiss apartments dxf reads 3% high (site171 floor1442 A, site790 floor7704 B) | 29 | W2 | every wording |
| CubiCasa LoRA fixture counts (WC, sinks, saunas, bathrooms) at the concept gate's 0.82–0.86 | 25 | R2 | model limit; calibrated per concept |
| CubiCasa compose bedrooms + bathrooms | 6 | W4/R2 | parts from the LoRA |
| Swiss dxf totals 2–3% high / site753 apartments +16% | 5 | W2 | see below |

**Dev at S0's c40 gate (run 20261114-095337-pipeline-dev-07a7): 35 confident-wrong = 26 CubiCasa LoRA + 9 Swiss dxf
areas, every one of the 9 ABOVE gold (+2.2 … +16.4%).** site753_bldg1637_floor7293: apartment A 79.03 @0.9 vs 67.88; the
gap is exactly room 5.04, an unlabeled numbered room (11.14 m², no name, no printed area) that the gold leaves out.
`experiments/F/unlabeled_rooms.py`: on 1,497 train apartment questions an apartment that contains an unlabeled numbered
room ≥ 4 m² is right 34/50 (68%) vs 1407/1447 (97.2%) otherwise; dropping the room is worse (11/50) → a confidence CAP
(≈ 0.65 + an assumption line), not a rule (W2 told 10:40). NEGATIVE: a dxf-vs-pdf_vector disagreement check is no
detector: they disagree (> 2%) on 10 of 400 dev Swiss area Qs and dxf is right on 7 of the 9 confident ones
(run 20261114-102530-pdf_vector-dev-a2aa); the other 7 confident-wrongs have both readers agreeing.

**Addendum 11:03 — night 9b1abd3 (S0 cycle 43 round 1): confident-wrong 68 → 33 at the same accuracy.**

| night | suite acc | answers at conf ≥ 0.8 | precision there | confident-wrong |
|---|---:|---:|---:|---:|
| 1a4e2af (c41) | 92.2 | 7,900 (72.5%) | 99.08% | 73 |
| 6025963 (c42 r2) | 92.5 | 7,953 (73.0%) | 99.14% | 68 |
| 9b1abd3 (c43 r1) | 92.6 | 7,808 (71.7%) | 99.58% | 33 |
| b656826 (c43 r2, freeze) | 92.9 | 7,896 (72.5%) | 99.59% | 32 |

(10,894 paired OPEN rows, 19 probes.) The drop is W2 fd50ee3 (unnamed numbered rooms ≥ 2% of a total → 0.78, from the
unlabeled-room finding above): the two Swiss apartments wrong in every wording lose their 0.9. What is left at ≥ 0.8 is
almost all CubiCasa LoRA / compose counts, calibrated per concept (WC 0.82 tier: 79% on cc5k_heldout).

**Addendum 10:55 — night 6025963 (S0 cycle 42 round 2) vs 1a4e2af, 19 probes / 10,894 paired rows: 51 won / 13 lost,
confident-wrong 73 → 68, every loss at conf ≤ 0.65.** W1 7fa37ed: "How many N are in this building?" on a sheet = whole
model (whole_top 95.4 → 100); W2 e461199: DXF twins outside data/swiss_dwellings/ read (neutral_path cw 15 → 13). One dxf
parse loss: "Welche Wohnfläche hat die Wohnung A (ohne Balkon)?" → area_label(Balkon) (an exclusion read as the target;
W2 told). New `unit_probe` (832 rows: square feet / sq ft / cm² / mm / cm / feet): answers come back in the unit asked and
strict = converted = the m² control (IFC 100%, Swiss 98.3%). Eval: runs > 200 Qs hide the Gemini key (`--allow-gemini`);
`--split human` reads agent H's expert questions.

Files outside the dataset: documented in `docs/CONTRACT.md` ("Files outside the dataset"): what `source_of` /
`siblings` / `dataset_rel` infer, the measured cost per layout, and the recommended layout for Stoa's files
(`<ROOT>/data/<source>/<name>.<ext>`, twins under one stem, the IFC model next to its sheets).

## Earlier (09:50, cycle 226): the same files outside our dataset folders (Stoa's noon files, demo uploads)

Every test we run uses dataset paths (`data/<source>/<file>`). Stoa's files and a visitor's upload won't sit there,
and several routes read the path: `source_of()` takes the source from the folder name, `siblings()` finds same-stem
twins, IFC sheets find their model by file-name prefix, caches/gates are keyed by dataset-relative paths.
**Neutral-path probe** (`experiments/F/neutral_path_probe.py`, OPEN: 168 dev questions, the same bytes hard-linked
under `/data/User/fangy4/stoa-neutral/`, 5 kinds of path; report `python3 experiments/F/neutral_compare.py RUN`):

| variant (meta.wording) | what it is | before (2b1a) | after 749e5c3 (3cb0) | LLM calls / Q |
|---|---|---:|---:|---:|
| dataset | control | 91.1 | 91.1 | 0.35 |
| twins_name | neutral folder, original names, all twins (dxf/png/svg/.ifc) | 66.7 | **90.5** | 0.71 |
| twins_hash | same, hashed names ("A101.pdf") | 66.1 | **89.9** | 0.68 |
| srcdir_lone | the file alone in `.../data/<source>/`, hashed | 65.5 | 66.1 | 0.36 |
| lone_hash | the file alone, hashed (a single upload) | 66.7 | 66.1 | 1.63 |

Per source (after the fix):
- **ifc_models sheets (43 Qs)**: with the model in the folder 100% (before: **0–21%**: source 'unknown' → no model
  sibling, no `ifc` route, `ifc.can_handle` False → vlm_direct guesses at ≤0.32, pdf_text echoing the room number
  '(0.1)' as an area at 0.65–0.75). Fix in `stoa/data.py` (F-owned): an outside sheet whose model sits next to it
  (prefix name, or the ONLY .ifc in a project folder that isn't laid out as data/ifc_models/) is source 'ifc_models'.
  A sheet without its model: 0/43 (prior at ≤0.23 or vlm_direct; calibrated except the pdf_text echo, W2 told).
- **Swiss (60 Qs)**: areas 93.3 → 100 (pdf_vector answers; it is right on two floors where dxf's room total is 2.2% high
  at 0.9–0.975); counts 100 → 90 (dxf declines a DXF twin outside data/swiss_dwellings/: DE/FR windows). W2 told.
- **CubiCasa (56 Qs)**: 76.8% in every variant; vlm_lora answers all (raster_cc5k and the prior gate drop out),
  tokens 630 → 1,056–1,521 per Q. **Schedules** (9 Qs) and **ifc_bench free text on an outside .ifc** (14 Qs, judged):
  unchanged (one schedule LLM flake 379 → 235 @0.85 in 1 of 10 identical runs).

**Sheets named without their storey** (`experiments/F/this_plan_probe.py` + `experiments/F/neutralize.py --mode hash`:
163 dev sheet questions that name the sheet's own storey, re-asked "on this floor plan" / "on this floor"):
dataset names 163/163; hashed names counts 1/19, volumes 0/12, lengths 0/3, area totals −11 (room-by-name areas
fine), all at 0.475–0.485: "no storey named or implied (not a plan file); whole model". The sheet states its storey
in its own text ("— Floor plan: 0") and through its room labels. W1 told. Runs -093821-…-this_plan-5fca vs
-093834-…-this_plan_nh-92ec.

`experiments/F/neutralize.py IN OUT --mode hash|name|lone` re-asks any open probe on neutral copies (same qids);
pair with `kind_compare.py`. Use it on any new route before trusting it on Stoa's files.

## Earlier (08:55, cycle 225): same-gold wording probes in 8 languages: where a judge's own wording breaks us

All probes are OPEN (dev drawings / open hard + hard2 bases; quote and fix freely). Each re-asks a dataset question in
the words a judge might type, with the SAME gold; most carry the dataset wording of the same base as a control
(`experiments/F/add_controls.py`), so `python3 experiments/F/control_compare.py PROBE RUN` isolates the wording effect.
Code: night c1d6149 (S0 cycle 37 merges incl. W4 0319d93 apartment normalisation). Generators:
`experiments/F/apt_wording_probe.py [N] [--ml|--cc|--ifc|--ml2]`, `experiments/F/comp_ml_probe.py`.

| probe (artifacts/F/…) | rows | acc | vs control | confident-wrong (≥0.8) | where it breaks |
|---|---:|---:|---|---:|---|
| apt_wording (EN: Swiss/IFC/CubiCasa) | 1711 | 89.3 | Swiss 82.5 → **94.5** after W4 0319d93 (152 won / 0 lost) | 123 → 39 (Swiss) | "including the apartment entrance doors" 0/28 @0.98; plural "areas" 0/30; CubiCasa "this apartment" windows 3/30; IFC unquoted room names |
| apt_wording_ml (Swiss apartments DE/FR/IT) | 880 | 66.8 | — | 84 | **Wohneinheit / logement → floor total @0.96–0.98 (77)**; 'wie viele Quadratmeter / combien de mètres carrés / quanti metri quadrati' → balcony count 0/120; 'ohne Balkon und Loggia' / 'balcons exclus' → balcony area |
| apt_wording_ml2 (Swiss rooms/labels/fixtures DE/FR/IT) | 934 | **100** | = control | 0 | none |
| apt_wording_ifc (IFC rooms/counts in 7 languages) | 348 | **100** | = control | 0 | none (quoted names) |
| apt_wording_cc (CubiCasa casual FI/EN) | 1080 | 73.2 | 71.8 vs 75.8 | 18 | composer: "sinks … kitchen and bathroom together" → sink+kitchen+bathroom (0/30); FI '…keittiössä ja kylpyhuoneessa yhteensä' → kitchen+bathroom @0.92; 'Laske ikkunat.' → text |
| comp_ml (Swiss hard/hard2 compositions DE/FR/IT) | 780 | 93.3* | 537/585 vs control 573/585; all 36 losses in two buckets | 36 | **FR 'de plus que' summed (compose.py 'plus' = +) 23/23 @0.976; IT 'Di quanti m² … più grande del …' → max (room name) 13/13 @0.99** |
| comp_ml_cc (CubiCasa hard/hard2 count compositions FI/SV) | 399 | 45.4 | FI = control (7/7 recipes); SV 42.1 vs 51.9 | 2 | **SV 'våtrum (badrum, separata toaletter och bastur)' → 'sauna' via LoRA @0.75 (0/25); 'sovrum och badrum … sammanlagt' → 'bedroom'** (no sv sum cues; front end skips because a target was found) |
| apt_wording_syn (Swiss fixture synonyms EN) | 660 | 99.1 | 98.8 vs 100 | 0 | 'tubs' 36/40, 'loos' 36/38 (vlm_direct ≤0.34, calibrated) |
| apt_wording_typo (quick typing: lower-case ids, misspellings, decimal comma) | 534 | 78.6 | **72.8 vs 98.6** | 2 | 'room 5,11' 2/30; 'apartment d' 12/30; 'apartmnet' 14/30; 'appartment' 19/30; 'sq m' 11/30 (all ≤0.6: accuracy, not calibration) |
| apt_wording_scope (IFC storey by role: 'ground floor' / 'basement', plan sheets) | 114 | 100 | = control | 0 | none (sheet implies the storey) |
| apt_wording_scope_model (same, asked on the .ifc model path; night 31397eb) | 114 | 95.6 | 109/114 | 5 | **smiley-west 'on the ground floor' / 'at ground level' → whole model (walls 281 vs EG 81 @0.97; slabs 522 vs 105 m³ @0.95)**; '0', '00 Begane grond', basement → KG/-1/Basement fine (W1 told) |

\* first run had a probe bug (sanitary item list always 'bathtubs'; English bases vary bathtubs/showers): 15 false
losses, fixed; clean re-run 20261114-084910-pipeline-comp_ml-a0c6 = the baseline (all 36 confident-wrong are the FR
'de plus que' and IT 'di quanti m²' rows; ECE 0.218, AUROC 0.40: right DE/FR/IT compositions sit under the unseen cap).

Runs: 20261114-083551-pipeline-apt_wording-93e0, -083721-…-apt_wording_ml-7b6c, -084334-…-apt_wording_ml2-1f56,
-084147-…-apt_wording_ifc-f27a, -084051-…-apt_wording_cc-1bc6, -084910-…-comp_ml-a0c6, -085023-…-comp_ml_cc-4f34, -090345-…-apt_wording_syn-1d9e (62754aa), -090539-…-apt_wording_typo-6f1b (62754aa); plural mini-probe -083814-…-areas_plural-e14a.

**Reading.** Per-entity atomic questions are wording- and language-robust everywhere we looked (Swiss rooms/labels/
fixtures in DE/FR/IT, IFC in 7 languages, CubiCasa casual FI/EN: 100% / 100% / = control). The failures are all in
**the small set of words that change scope or operator**, and they fail confidently:
1. *Dwelling nouns outside the normaliser* (Wohneinheit, Einheit, logement, alloggio, "units") lose the apartment
   scope → whole-floor sum at 0.96–0.98. The cross-check that should catch it compares the floor total with itself.
   Fix asked of W4: the nouns + a whole-floor safety net (dwelling id in the question, floor-total trace → cap ≤0.5).
2. *Operator words that are also other words*: French 'plus' (= more) → '+'; plural 'areas' → not an area; 'including
   the apartment entrance doors' → '+ apartments'; Italian 'di quanti m² … più grande' → 'which is larger'.
3. *Locations read as terms*: "sinks in the kitchen and bathroom" → sinks + kitchens + bathrooms.
4. *Intent says area, the solver says count*: 'wie viele Quadratmeter …' (intent right, dxf counts balconies). A kind
   mismatch between intent and answer should trigger the canonical re-ask instead of returning the count.

**Round-2 merges (night 62754aa, 09:00), paired per wording vs c1d6149:** English 89.3 → 91.4% (confident-wrong
43 → 13: 'Sum the floor areas …' 0 → 30/30, 'including the apartment entrance doors' still 0/28 but capped, 28 → 0
confident); Swedish 'våtrum' 0 → 16/25; DE/FR/IT apartments 66.8 → 67.0 (77 Wohneinheit/logement confident-wrong left),
compositions 93.3 = (36 left), CubiCasa casual 73.2 → 72.9 (sinks composer 10 left). Runs 20261114-085553-pipeline-
{apt_wording-a614, apt_wording_ml-4942, comp_ml-1e99, comp_ml_cc-b8c5, apt_wording_cc-8fe9} = baselines for the next fixes.

**Round-3 (night 31397eb = S0 4fb47c9 + R1, 09:10), paired per wording vs 62754aa — the wording gaps close:**

| probe | 62754aa | 31397eb | confident-wrong | won / lost |
|---|---:|---:|---|---|
| apt_wording (EN) | 91.4 | **92.7** | 13 → 10 | 28 / 6 (IFC unquoted names 3 → 8/8; CubiCasa 'this apartment' windows 7 → 15/30) |
| apt_wording_ml (DE/FR/IT apartments) | 67.0 | **92.0** | 84 → 12 | 224 / 4 |
| comp_ml (Swiss compositions DE/FR/IT) | 93.3 | **97.9** | 37 → 1 | 36 / 0 |
| comp_ml_cc (CubiCasa FI/SV compositions) | 50.4 | 53.1 | 4 → 4 | 21 / 10 (SV now = control) |
| apt_wording_cc (CubiCasa casual) | 72.9 | 74.4 | 28 → 11 | 23 / 6 (sinks composer 0 → 17/30) |
| apt_wording_syn / _typo | 99.1 / 78.7 | 98.9 / 77.9 | 0 / 3 | single low-conf flips |

All 7 probes: 6,044 rows, 86.8%, confident-wrong 168 → 41. 32 of the 41 are two Swiss apartments wrong by ~3% in
EVERY wording incl. the dataset's (site171_bldg350_floor1442 A 123.1 vs 119.14; site790_bldg1731_floor7704 B 105.78
vs 102.63: a dxf/data issue, W2 told); only one is wording-specific. Runs 20261114-090750-pipeline-{apt_wording-b90c,
apt_wording_ml-7528, comp_ml-e57e, comp_ml_cc-eaff, apt_wording_cc-f375, apt_wording_syn-0308, apt_wording_typo-85c3}.
Still open (low confidence, accuracy only): quick typing (lower-case ids, misspelt 'apartment', 'room 5,11', 'sq m').

**Held-out check of W4's 'both readings' (2b954b5)** on hardL (nb/hr/el/lt; F/S0 only, aggregates): 85.3 → 84.9%
(paired −0.5 [−3.2, +2.3], 4 vs 3), ECE 0.179 → 0.085, conf ≥ 0.8 on 23% → 60% of answers at 99.3% right, AUROC
0.925 → 0.932, $0.12 → $0.15 per 1k. hardL_open 87.0 → 87.7, ECE 0.134 → 0.084, 36% → 61% @ 99.4%. My offline
simulation (08:20) predicted ECE 0.132 and 54%: the wired rule does better. Runs -085405-…-hardL-5270 / -085553-…-hardL-4adb.

Owners told (inbox 08:40–08:52): W4 (1, 2-plus/areas, 3, 4, CubiCasa 'Laske'), W2 (2-incl/areas/di quanti, the
Quadratmeter parse, exclusions read as targets, alloggio table-QA). Re-run commands for each are in board/F.md NEXT.

## Earlier (08:20, cycle 224): the wired language front end on held-out languages; "both readings" fixes its underconfidence; one English confident-wrong

Context: all agents were stopped by the org spend limit 05:20–08:10, so night is still bb94fe4 (S0 cycle 19) and
sealed test 2 started only at 08:12 (S0). S0's last gate on bb94fe4: dev 89.9 / 83.6 w, hard 84.7, hard2 92.1,
ifc dev 100, $0.036/1k (logs/S0/c19-*.log). The dev loss table is unchanged from 04:55 (cubicasa window/door
counts still 37% / 33% of the 165 such dev questions; dev run 20261114-051705-pipeline-dev-f35a).

**1. The pipeline's language front end, measured as wired (night bb94fe4), paired on the same items.**
hardL v2 = 58 dev/hard2 bases (39 atomic, 19 compositions) in 4 held-out languages (nb/hr/el/lt; F/S0 only,
aggregates) and 4 open ones (cs/hu/tr/ro). English base 93.1% on the same items.

| split | front end on | translate=0 | paired on − off (drawing-cluster 95% CI) | conf ≥ 0.8 (on / off) |
|---|---:|---:|---|---|
| hardL held-out (232) | **84.5** | 78.0 | **+6.5 [+1.7, +11.6]**, 20 won / 5 lost | 22% @ 100% / 41% @ 99.0% |
| hardL_open (232 non-en) | 84.5 | 76.7 | +7.8 [+0.9, +15.4], 25 / 7 | 25% @ 100% / 42% @ 96.9% |

Runs: held-out 20261114-081146-pipeline-hardL-4273 (on) / -081245-…-hardL-b5d8 (off); open -081146-…-hardL_open-aa12 /
-081246-…-hardL_open-d162. By language (held-out, on): nb 86.2, hr 87.9, lt 82.8, el 81.0. By source (on vs off):
cubicasa 56.9 vs 37.5, swiss 95.7 = 95.7, ifc 98.5 vs 97.1.
- translate=0 is no longer "no translation": W2's dxf translates inside itself and W1's ifc cross-checks a translated
  reading, so swiss/ifc are already ~96–98% without the pipeline front end (the 04:45 "as is" baseline was 50.0).
  The pipeline front end now earns its points on **cubicasa** (+19 points held-out), where the VLM reads the
  question.
- Caveat: LT/HR appear in W4's lang4b probe (R2 declined to tune on it; R2's glossary has general da/no nouns for
  beam/column). Greek is the cleanest language here and it is the lowest (81.0).

**2. The front end is underconfident, and it demotes right answers.** Translated answers are capped at 0.9, or 0.75
with extra structure. The 0.7 bin is 96% right on held-out (109/114) and 91% on open (101/111), and on Swiss
plans the ≥ 0.8 bin falls from 69 answers (front end off, all right) to 25 (front end on): the cap throws away
confidence that the rules solver earned on the original wording. ECE 0.173 held-out.
**"Both readings" rule** (offline from the two stored runs; `experiments/F/both_readings_sim.py ON OFF [--det-only]`):
for a question the front end translated, also answer the original (translate=0). If the two answers agree,
confidence = max(both); if they disagree, take the more confident one, capped at 0.5.

| | acc | ECE | conf ≥ 0.8 | confident-wrong |
|---|---:|---:|---|---:|
| open, current | 84.5 | 0.145 | 25% @ 100% | 0 |
| open, both readings (rule designed here) | 84.9 | 0.114 | 56% @ 97.7% | 3 (2 = bug in §3, 1 = probe defect) |
| held-out, current | 84.5 | 0.173 | 22% @ 100% | 0 |
| held-out, both readings | 84.9 | 0.132 | 54% @ 99.2% | 1 (cubicasa) |
| held-out, both readings, lift only for rules solvers (`--det-only`)* | 84.9 | 0.134 | 53% @ 100% | 0 |

\*`--det-only` was chosen after seeing the held-out cubicasa row (ECE worse when a VLM answer is lifted; the
open set showed the same direction), so its held-out row is slightly optimistic. Cost: one more pipeline pass,
only on questions the front end translates (0 of 2,199 on sealed test; 75/256 on hard2r). The two readings share
the memoised translation inside dxf/ifc, so they are not independent; agreement still separates right from wrong
here: held-out, 89.8% of agreeing answers are right; on disagreement the translated reading is right 56% (20/36) and the original only 14% (5/36), (open: 90.0%; 60% vs 17%). Always taking the translated answer on disagreement (`--dis-pick translated`) is no better than the more confident one (acc 84.5 vs 84.9, ECE 0.135 vs 0.132 held-out), so keep the simple rule.

**3. An English confident-wrong found through the Turkish rows (W4, intent.py).** "What is the net floor area of
B apartment in m², excluding balconies…?" → `_APT` (case-insensitive) takes 'in' from "apartment in m²" →
apartment 'IN' → dxf sums the whole floor: **321.76 m² @ 0.95** (gold 63.07; "apartment B" wording → 63.07 @ 0.965).
Fix: in the area branch, require the id to be upper case or a digit in the original text (the count branch
already does this), accept "<Letter> apartment|flat|unit", and add 'flat' (currently "area of flat A" parses as area/unknown).

**4. Other translated-question mechanisms (open set, en base right → translated wrong, 20 rows):**
- compose adds a fixture to a room sum (6 rows, all at 0.75): translated "bathrooms or **toilets** (KH, KPH, PH…)"
  → parts bathroom + **wc (toilet bowls)** + wc_room + sauna → 2 instead of 1. With 'rooms' as the head noun, only
  room kinds should be summed, and "X or Y (codes)" names one class.
- count answered with an area (1, 0.67): hu "How many rooms (spaces) … on the '-1' floor" → 54.406 m². The
  fraction guard only fires when unit == count; a how-many question answered in m² should be capped too.
- translation slips (6, all ≤ 0.63): cs 'Kolik van' (bathtubs) → "How many are shown" (inside dxf), hu
  'Hány … közül' (how many of) → "Which of", 'washrooms' → 'toilets', 'showers and bathtubs' → 'showers and
  bathrooms' (ro 'băi', tr 'banyo' are ambiguous).
- Probe defects (mine): the hosted Romanian translations contain non-words ('arulate', 'aritate', 'bați',
  'număruând', 'sediiile'), and one ro composition dropped "average" (gold 13.81 = average, the question as written
  asks the sum 27.63 → the pipeline is right). The ro numbers are slightly pessimistic.

**5. English wording probe on the commonest Swiss kinds (open; 08:22): apartment references are the weak spot.**
`experiments/F/apt_wording_probe.py` → `$JUNCTION_SHARED/artifacts/F/apt_wording.jsonl`: 30 dev Swiss bases per kind,
each re-asked in natural English wordings with the same gold (810 rows). Run 20261114-082232-pipeline-apt_wording-6bcb
(night bb94fe4): 76.9% overall, conf ≥ 0.8 on 66% of answers but only 83.8% of those right.

| kind (dev template) | wordings | right | confident-wrong (≥ 0.8) |
|---|---:|---:|---:|
| apartment net area ("apartment X") | 10 | **143/300 (47.7%)** | **87** |
| room area by number ("room 1.02 ('Wohnen')") | 8 | 240/240 | 0 |
| count of rooms by label | 5 | 150/150 | 0 |
| total area by label | 4 | 90/120 | 0 |

Apartment wordings: flat X / unit X / "How big is flat X?" / "How many square meters is apartment X?" 29/30 each;
"the X apartment" 3/30, "X apartment in m²" 5/30, "apartment-X" 0/30 (30 confident-wrong), "apt. X" 6/30,
"apartment 'X'" 0/30 (quoted letter read as a storey → abstain → VLM 2.2 m² @ 0.32), "Apartment X: … balconies
excluded?" 11/30 (dxf reads the exclusion as the target: balcony area). Mechanism of all 87: no apartment filter
(neither the router intent nor dxf's own parse) → dxf area_total = whole floor (e.g. 128.23 vs 28.34) @ 0.95.
Fix (W4/W2, sent 08:28): normalise apartment references to "apartment X" before parsing, plus a safety net:
a question that names an apartment but gets a whole-floor answer → conf ≤ 0.3 + missing "which apartment".
Imperative "Sum the floor areas of the rooms named 'X'." → task text → count 5 @ 0.30 (0/30, calibrated).
Extended at 08:25 with Swiss counts (1264 rows; run 20261114-082449-pipeline-apt_wording-1a8e): doors / bathtubs /
apartments / windows in 3–4 plain judge wordings each 100%; washbasins 88/90 ("bathroom sinks": agent 2 @ 0.9 although
its own trace says "cross-check: agent 2 ≠ dxf 4" → W4); **"How many doors does this floor have, including the
apartment entrance doors?" 0/28, all @ 0.98**: dxf parses count(door) + count(apartment) = 20 + 2 (a qualifier read
as a second class; the LLM operation check agrees → W2). apt re-run 139/300 (vs 143: VLM/agent run-to-run noise).
Why it matters: S0's gates only use dataset wordings ("apartment X"), so this never showed on dev/hard; the
hard split's paraphrases were generated by templates that keep "apartment X".

**5b. The same probe on IFC and CubiCasa (08:31).** IFC (135 rows on dev models; run 20261114-083112-pipeline-apt_wording-1356):
92.6%, conf ≥ 0.8 100% right; per-storey counts/totals/wall side area/slab volume 100%; only unquoted room names
("What is the area of Living (414B-19-001-002) on 1. Level?") 3/8 at 0.3 → W1 (substring match of the storey's
IfcSpace names). CubiCasa (312 rows; run 20261114-083158-pipeline-apt_wording-2f99), vs the dataset wording on the same
drawings (dev run f35a): rewordings that keep the structure reproduce the dataset accuracy exactly (same solver); any
wording with **"this apartment"** goes to the general agent: windows 3/30 (15/30), toilets 18/30 with 3 wrong at
≥ 0.8 (22/30), bedrooms 15/19 (16/19). → W4: on a one-dwelling plan an unlettered apartment scope is the drawing.
Across sources, "apartment" handling is the one wording weakness (Swiss §5 and here).

**6. Sealed hard3 on the test-2 code (bb94fe4): 34.6 → 62.2; what is left (aggregates; mechanisms only).**
Run 20261114-081621-pipeline-hard3-d242 (S0) vs 20261114-035756-pipeline-hard3-55fd (test-1 code). By recipe:
swiss growth/fixtures/split-bill 35/35, heating-year 11/12, carpet-ft2 9/12 (0 → 9), ifc cleaning-hours 8/8 (0 → 8);
left: **ifc wall surface 0/9, all 9 at 0.95** (the confident-wrongs that drive the hard3 conf ≥ 0.8 bin to 73%),
ifc flooring-waste 4/8, swiss occupancy 8/11 (**10 in test 1**), cubicasa per-sauna/per-room derived kinds 13/48 (low conf).
- Wall surface: ifc's as-asked reading was unsure (0.30, correctly); the pipeline's canonical-form retry ("total
  net side area of all walls on <storey>") drops the number the question states (an assumed wall height) and
  answers at 0.95 from the train hit rate, ignoring its own cross-check (−60.6%). → W4: unused-number guard at the
  canonical retry; cross-check disagreement > 5% caps conf.
- Occupancy regression: the agent concludes "floor(6.873) → 6 count", then `_finish` restores 6.873 (rule meant
  for "5.908 days → 6") and the fraction guard caps 0.3. → W4: never un-round when unit == count.
- Flooring waste (4, Italian): language guessed 'fr', the waste percentage read as a share → agent, 0.3.

**7. Sealed hard2r on test-2 code: 63.0 → 80.4 (aggregates).** Run 20261114-081509-pipeline-hard2r-dd4e vs -035900-…-6f03.
Scored (189): left = cubicasa wc+showers 12/25 and wet-rooms 15/25 (perception, low conf), swiss rooms-above-threshold
7/15 (4 in test 1; "how many of rooms … larger than N m²" parsed as an AREA question → dxf area differences at ≤ 0.3 →
agent), ifc room-share-% 4/8 (Estonian: "translation lost a name or number; used the original" → vlm_direct guess at
0.27). Gains since test 1: swiss apartment-ratio 8 → 15, doors-per-apartment 9 → 15, ifc 14 → 30 of 36. Text (67,
judged): 60 right; two-wc-yes-no has 5 wrong at ≥ 0.8. Underconfidence (S0): 42% of answers at ≥ 0.8, 98.7% right —
same picture as hardL §2, so "both readings" applies here too.

## Earlier (04:55, cycle 62): language is the biggest held-out gap, and a translate-first front end closes most of it

### 1. hardL: the same known-gold questions in 8 languages nobody tuned on (stoa/eval/hardl.py)
Base = dev questions with gold (v0: 20 atomic; cubicasa 7, ifc 9, swiss 4; the 20 hard2 compositions are still
being translated: hosted API 429s). Translations by hosted Nemotron 3.5 VL (not the local Qwen that a front end uses),
quoted names and numbers checked verbatim. `hardL_open` (cs/hu/tr/ro + the 60 English bases) is open; `hardL`
(nb/hr/el/lt) is held out (F/S0, aggregates). None of these languages is in hard2r (es/et/pl) or hard3. Paired on the
same items with `experiments/F/hardl_paired.py EN_RUN RUN`. Night 15c0b04, `lora_conf=own`, 4 workers.

| run | English (same items) | as is | translate-first (simulated) | paired W/L | conf≥0.8 right | confident-wrong |
|---|---:|---:|---:|---:|---:|---:|
| open cs/hu/tr/ro (n 80) | 90.0 | 52.5 | **86.2** | 27 / 0 | 90.3 → 100% | 3 → 0 |
| held-out nb/hr/el/lt (n 78) | 89.7 | 53.8 | **79.5** | 20 / 0 | 75.9 → 95.7% | 7 → 2 |
| held-out by source: cubicasa / ifc / swiss | 71 / 100 / 100 | 32 / 68 / 62.5 | 54 / 91 / 100 | | | |

Simulation = R2's `should_translate` trigger (non-English and the intent parser failed) → `to_english(force=True)`,
English kept only if it re-parses (`experiments/F/lang_frontend_sim.py`). Per held-out language: nb 80 → 90 (rules
already read 6 of 20), el 50 → 85, hr 45 → 75, lt 39 → 67. Remaining held-out misses: translation drift (the 8B
model added an 'external' the source did not say → ifc filtered walls at ≥0.8) and trigger-fired-but-no-reparse
(original kept; ifc answered a count with a non-integer at ≥0.8). Guards suggested to W4. Runs:
20261114-042948-…-hardL_open-80c7, -043124-…-hardL_open_fe-e0f4, -043021-…-hardL-dbd0, -043140-…-hardL_fe-df5f.

**v1 (04:50, current night cc1ca5b; 40 bases = 33 dev atomic + 7 hard2 compositions; 13 compositions still untranslated
because of hosted-API 429s):**

| run | English (same items) | as is | translate-first (simulated) | paired vs as is | conf≥0.8 right | confident-wrong |
|---|---:|---:|---:|---:|---:|---:|
| open cs/hu/tr/ro (n 158) | 89.9 | 48.7 | **82.9** | +34.2 [+21.5, +46.8], 56 W / 2 L | 65.3 → 97.1% | 17 → 3 |
| held-out nb/hr/el/lt (n 160) | 90.0 | 50.0 | **80.6** | +30.6 [+20.0, +41.2], 52 W / 3 L | 66.0 → 96.9% | 16 → 3 |
| held-out compositions only (n 28) | 71.4 | 35.7 | 64.3 | | | |

(CI = bootstrap over base questions.) As is, swiss gives 10 of the 16 held-out confident-wrong answers (dxf reads a
foreign operator wrongly at high confidence), ifc 5. After translation: el 90, hr 82.5, nb 80, lt 70. Cubicasa's
remaining gap vs English is mostly concept-noun slips in the 8B translation (4 of 5 v0 losses changed the intent
target) → R2: a domain glossary in the to_english prompt.

**Side effect on our own data:** the trigger fires on 11 dataset questions (Polish/Romanian ifc_models questions on
the BIM-Speed Gdynia/Barlad models; the ifc solver reads them already, dev 4/4 @ 0.97) and on 0 of hard's 175
non-English questions. Translating them lost 1 ('belek' = beams → 'balconies'). A 'solve both, on disagreement take
the more confident at ≤ 0.5' rule recovers it but shrinks the held-out ≥0.8 bin 46 → 28 at equal accuracy (v0), so
plain translate-first + glossary is the recommendation.

### 2. Held-out hard2q on night 15c0b04 (aggregates)
Round 2 (night cc1ca5b, lora_conf=own default): 80.4%, ≥0.8 50.8% @ 92.7% = neutral (run 0103).
W4's 0.75 cap: ≥0.8 bin 50.8% @ 92.7% (0980: 55.6% @ 86.7%), accuracy 79.9 (=). `lora_conf=own` vs `gate`:
cubicasa ECE 0.107 vs 0.162, AUROC 0.669 vs 0.632 → default own. Last confident-wrong bucket: swiss
floor-minus-apartment 7/15 wrong, all at 0.90–0.96: dxf returns the excluded apartment's area when the exclusion is a
fronted phrase, and the KG ✓ checks the apartment polygons, so nothing lowers confidence (W2: parse; W4: guard).

### 3. IFC areas on unseen models (artifacts/F/ifc_area_probe.jsonl, `experiments/F/ifc_probe.py write_area`)
137 Qs on 13 ifc_bench models with IfcSpaces: 78/78 Qto-gold answers right, 0 errors, 0 None; 32 right answers at 0.7
only because Qto ≠ shape by > 2% (W1). With the count probe (301/301), IFC geometry generalises; wording does not.

### 4. Paths outside the dataset (Q 04:13, fixed 62b0d1e)
`dataset_rel` cut any absolute path containing data/<source>/ and looked it up under $STOA_DATA → missing file →
prior at 0.8. Now only a true copy (same relative path and size) is cut; others keep their path and get the source
from the folder name; `ifc_model_for` looks next to a foreign plan.

## Earlier (03:30): gate of the test-1 code, cc5k=1 leak-free, where dev points are left

Context: every agent was stopped by the org spend limit 01:58–03:10, so there was no 02:40 freeze. At 03:12 F gated
W4 c1b294c (trust on unseen wordings, from F's 01:44 held-out mechanisms) + W4 3d21bee (cc5k gate path) + R1 eb03604
(CC5K crosscheck) as a scratch merge (d764334 = night 609e41c + night-W4 8d7f23a + night-R1 6072523). S0 froze the same
code (+ R1 f13db8f count ranges, W5 web) as 95f2277 and started sealed test 1 at 03:21.

### Sealed test 1 vs dev (S0's run 20261114-032105-pipeline-test-9709 on 95f2277, cc5k=0; aggregates only)
| | dev (same code) | expected on test from dev buckets | **test 1** |
|---|---:|---:|---:|
| micro | 88.5 | 88.8 | **87.4** |
| weighted | 81.7 | 81.7 | **79.8** |
| ECE / conf≥0.8 share @ precision | 0.019 / 78% @ 98.0 | | 0.017 / 78% @ 97.9 |

- The −1.9 weighted gap is cubicasa (70.5 vs 73.4; ≈1 SE). Swiss transfers. IFC: all 7 misses in ONE of the 3 test
  models (bsc-molio, 7/197; the model is wholly in test, so inspecting it is S0's call).
- Cubicasa by concept (diagnostic only, never tune on it): symbol counts transfer (windows 19 → 21, doors 33 → 35,
  WC 76 → 79, sinks 69 → 65); room-label concepts drop (saunas 93 → 80, bedrooms 90 → 82, separate WC rooms
  100 → 90; together 94 → 84 on ~140 Qs each). R2: no checkpoint/temperature search on dev; on train_gate (never
  used for selection) these concepts are 90.0% (120 Qs), so dev was ~4 pts lucky and test is ~1.5 SE below train_gate.
- LoRA ablation on sealed test (lora=0 e96f vs 9709): cubicasa +8.8 [+6.0, +11.9] (dev +11.9), weighted 73.8 → 79.8.
- cc5k=1 on sealed test (32c9, inflated label): accuracy flat (79.9 weighted); cubicasa answers with boxes 17% → 39%.
- Judged ifc_bench text: dev 55.0% (after W1's dev tuning), test 57.8%: transfers.

### Sealed generality on the test-1 code (aggregates only, D12/D15)
| split | what it is | micro | conf≥0.8: share @ precision | AUROC |
|---|---|---:|---|---:|
| hard2 | reasoning kinds, developed on | 92.1 | 50% @ 100 | 0.83 |
| hard2p | reworded, partly seen | 85.2 | 48% @ 98.9 | 0.88 |
| hard2q | third wording, worn | 79.9 | 51% @ 92.7 | 0.79 |
| **hard2r** | sealed fresh draw, 4th wording (ES/ET/PL + new EN) | **63.0** | 37% @ 84.1 | 0.73 |
| **hard3** | sealed derived quantities (price/rate/constant/% in the question) | **34.6** | 24% @ **0.0** | **0.33** |

- hard2r by wording: new English ≈ 80% (cubicasa 84.6, ifc 71.4, swiss 79.2; no confident-wrong); unseen languages
  collapse (cubicasa Polish 20.8%, ifc Estonian 20.0% with 5 confident-wrong, swiss Spanish 70.2% with 6). Fresh draws
  65.3 vs redrawn instances 55.6, so it is not instance difficulty. Fix family: translate-first front end for
  languages the rules don't cover (develop on OTHER unseen languages, not ES/ET/PL).
- hard3: 30% of all questions are answered with the BASE quantity (operation not applied, mean conf 0.72); all 37
  answers at conf ≥ 0.8 are wrong, from dxf (19) and ifc (18). Fix family: a number in the question that the solver
  did not consume (W4's intent.extra_structure) must cap deterministic answers and route to the composer/agent.

### New sealed split `hard3` (derived quantities; stoa/eval/hard3.py, wordings in $JUNCTION_SHARED/sealed/F/)
156 Qs on dev drawings: 15 recipes (occupancy limit, yearly heating cost, % growth, ft² carpet price, proportional
bill split, fixture costs; smoke detectors = bedrooms + storeys, sauna stove kW, cleaning minutes, bedrooms per WC
seat, balcony planters; flooring + waste %, cleaning hours, door/window hardware cost, wall surface = length × height),
8 languages. Different recipes and wordings from W4's dev probe (artifacts/W4/derived*.jsonl), which W4 tuned on.
Rules as hard2r: only F and S0, milestones, aggregates only. Dummy floor 6.4%; test-1 code 34.6% (run 55fd).

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

