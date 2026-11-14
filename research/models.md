# Models for Stoa "Make Blueprints Talk" (owner: R2)

Hardware: 1× RTX PRO 6000 Blackwell 96 GB. Shared server budget ≈ 45 GB (`--gpu-memory-utilization 0.45`).
**Bandwidth is the real constraint tonight:** this machine downloads from Hugging Face at only ~2.5 MB/s total
(Wi-Fi; measured with 8 parallel range requests), i.e. ~2 h per 19 GB. Every download must be chosen carefully.

## TL;DR for the captain (10:45, end of night)
- **Small fine-tuned beats big general.** A LoRA on our own 8B (cc-v2, 2 output tokens per answer) is the night's largest gain on
  SEALED test: CubiCasa +8.8 [+6.0, +11.9], weighted 73.8 → 79.8, at ~$0.02 per 1k questions. A 4× bigger base VLM (Qwen3.6-35B-A3B)
  and hosted Nemotron 3.5 Super VL both count WORSE (35B base: −21 vs cc-v2 on dev CubiCasa; Nemotron: below even the base 8B on smoke).
- **Bigger model only where it measurably helps:** free-text IFC answers (fact cards) on Qwen3.6-35B-A3B (:8002): judged 62.0 vs 54.5,
  hosted Nemotron as independent judge on the disagreements 6 vs 0, +20% GPU-s per question. Everything else stays on the 8B.
- **Hosted Nemotron = visible second opinion** (demo button), not a bulk tier: as planner it ties at 9× cost, as translator 25× slower.
- **Language front end**: translate only what the rules can't read (`should_translate`); held-out languages (nb/hr/el/lt) 78 → 84.5
  in the pipeline (F), 0 dataset questions touched.
- **Files outside our folders (uploads, a hidden set in its own layout)** lose the folder-keyed readers: 800 dev CubiCasa Qs as
  uploads have 47 confident misses vs 24 on the dataset path. Tonight: W4's confidence cap (D23). Day team: file the upload by
  its image-guessed style (`stoa/style.py`, CubiCasa only): 47 → 31, evidence 0 → 32%, 586/588 touched answers = dataset path.
- **Gemini** (key from Sat 10:50): `backend="gemini"` in stoa.llm with the no-abuse rules in code (daily cap, purpose log, rpm);
  for visible steps only. Not yet run live.
- **Cost honesty:** every local call is billed from tokens at measured GPU throughput (not wall time, which includes queueing).
- Negative results are listed under each section and in board/R2.md ("don't repeat").

## Serving now
**If a server dies during the day** (nobody from the night shift is watching after 11:45): restart by hand with
`serving/start.sh` (:8001, loads cc-v2 + cc-v3) and `PORT=8002 GPU_UTIL=0.48 SERVED_NAME=qwen3.6-35b-a3b serving/start.sh qwen36-35b-a3b`
(:8002, optional: answers fall back to :8001), ~2–3 min each. Or let `serving/watchdog.sh` do it (written + dry-run tested 10:58,
**NOT running**: starting a detached restarter was not permitted from the night agent's session) — start it from a terminal with
`setsid nohup serving/watchdog.sh >> $JUNCTION_SHARED/logs/watchdog.log 2>&1 < /dev/null &`. It restarts a port only when its pid
file exists, the pid is dead and /v1/models fails twice (so `serving/stop.sh` is never undone), never kills a live server, max 3
restarts/port, :8002 only without the GPU lock held; `touch $JUNCTION_SHARED/locks/watchdog.off` stops it; exits at 19:00.

| what | value |
|---|---|
| :8002 (since 09:40, D21) | Qwen3.6-35B-A3B-FP8 `qwen3.6-35b-a3b`, util 0.48; ONLY via `llm.text_backend()` (STOA_TEXT_BACKEND=local2), falls back to :8001 |
| hosted Gemini (`backend="gemini"`, 10:38) | `gemini-3-flash-preview` default ($GEMINI_MODEL); per-agent daily cap 200 ($STOA_AGENT), purpose log `logs/gemini_calls.jsonl`, 10 rpm; demo / small probes only (Google no-abuse rule); offline-tested, **not yet run live** |
| :8001 adapters | LoRAs `cc-v2` (CubiCasa counts) and `cc-v3` (+ Swiss PNG), loaded by `serving/start.sh` |
| model | Qwen3-VL-8B-Instruct (bf16), from the text encoder inside Qwen-Image-2.1 (full VLM: vision tower + lm_head; same config as Qwen3-VL-8B-Instruct) |
| URL | http://127.0.0.1:8001/v1, model `default` or `qwen3-vl-8b` |
| context | 32k tokens, KV cache 169k tokens (~5 concurrent full-length requests; dozens of short ones) |
| VRAM | ~42 GB |
| grounding | boxes / points in relative 0..1000 image coordinates (`stoa.llm.parse_boxes` maps them back to pixels) |
| licence | Qwen3-VL is Apache-2.0; this copy came bundled with Qwen-Image-2.1 (qwen-research licence on the bundle). Fine for the hackathon; for anything public re-download the Apache original. |

## Results (vlm_direct = render the page, ask, parse one number)
Cost columns are per question. "dev cc" = dev cubicasa counts (800 q), the bucket that is 68% of the score.
| model / variant | split | micro acc | cost per q | notes |
|---|---|---|---|---|
| Qwen3-VL-8B, CoT (1024 tok) | smoke v0 (246) | 26.2 | 4.5 s, ~600 in / ~400 out | rambles, loops, truncates; parser grabs "1800x2400" |
| Qwen3-VL-8B, **direct answer** (default) | smoke (206) | **37.0** | 0.3–1 s, ~600–1800 in / 3 out | |
| Qwen3-VL-8B, direct answer | dev (2215) | 32.0 (macro 16.0) | ~1 s | = dummy prior 32.0 micro; per template: wins swiss apartments (93 vs 19), rooms-by-label (79 vs 19), swiss room area read from plan (36–59 vs ~0); loses cubicasa fixtures (answers "2" to compound "X and Y" questions — F) |
| Qwen3-VL-8B direct | dev cc | 48.8 | 1.3k in / 2 out | prior: 60.1 |
| + upscale to 2 Mpx | dev cc | 49.8 | 2.1k in | noise |
| + point-then-count (count = #points) | dev cc | 34.1 | 1.3k in / 401 out, p95 91 s | looping point lists; use points only as evidence |
| + self-consistency n=5, T=0.7 | dev cc | 48.9 | 1 request, 10 out | vote share calibrates: 5/5 → 55% acc, 4/5 → 38%, ≤3/5 → ≤20% (routing signal) |
| Nemotron 3.5 Super VL (hosted), direct | smoke (206) | 33.1 | ~4 s, 1 API call | worse than local 8B on every bucket; reasons in the visible answer even with thinking off (`/no_think`, `reasoning_effort` don't stop it) |
| Nemotron, thinking on (4096 tok) | smoke cc (80) | 38.8 (50.0 on answered, 22% unanswered) | ~30 s, 1.9k in / 3.1k out, 1.6 API calls | too slow/costly for bulk; local 8B direct on the same 80: 45.0 |
| (dummy prior, F) | dev | 32.0 | 0 | |

| Qwen3-VL-8B + decompose compound questions | dev cc | 42.6 | 2.2 calls | sinks+basins 56→6, showers+baths 35→5: the 8B over-counts EACH kind; rejected |
| Nemotron, direct prompt, 1024 tok (reasons briefly in the answer) | smoke cc (80) | **50.0** | 8 s, 1.5k in / 313 out, 1.16 API calls, $1.2/1k | best Nemotron mode; local 8B on the same 80: 45.0 (n small) |
| train_gate cc symbols (160: windows, doors, WC, sinks; EN+FI): prior / 8B / 8B+symbol hints / Nemotron | train_gate | 29.4 / 30.6 / 31.9 / 34.4 | Nemotron 13 s, $1.4/1k | windows 5–15%, doors 5–25% for every model: VLMs can't count plan symbols off the shelf |

**LoRA cc-v2 (trained 00:24–01:18) — WINNER on cubicasa counts.** Qwen3-VL-8B + LoRA r16 on TRAIN cubicasa counts,
*excluding every train_gate drawing*. 3,840 drawings as multi-turn image-once samples (EN/FI + paraphrases,
answer-only targets), 54 min, 27 GB, final loss ~0.34. Adapter: `$JUNCTION_SHARED/artifacts/R2/lora/cc-v2`.
Served on :8001 as model `cc-v2` from 01:40 (base unchanged as `default`); solver `vlm_lora`.
| set | LoRA cc-v2 | raster (W3) | pipeline | prior | base 8B | R1 CC5K net |
|---|---|---|---|---|---|---|
| dev cubicasa (800) | **73.9** | 62.5 | 61.8 | 54.1 | 50.4 | (memorised) |
| train_gate cubicasa (480, unseen by LoRA) | **76.7** | | | 51.9 | 45.6 | (memorised) |
| hard cubicasa translations / paraphrases / compositions | **75 / 66** / 9.6 | 67 / 62 / 26.5 | 67 / 60 / 19.3 | | | |
| leak-free for both (200, `cc5k_heldout_notLoRA`) | **79.0** | | | 54.0 | 51.5 | 60.5 |
**Sealed test 1 (S0, frozen 95f2277, 03:21–03:55; aggregates only):** pipeline with the LoRA vs `lora=0`:
cubicasa 61.6 → 70.5, **+8.8 [+6.0, +11.9]** (111 wins / 40 losses), micro 83.9 → 87.4, **weighted 73.8 → 79.8**,
cost $0.19 → $0.28 per 1k, ECE 0.016 → 0.017. About 3/4 of the dev gain (+11.9): symbol concepts transfer, room-label
concepts drop (saunas 93 → 80, bedrooms 90 → 82, separate WC rooms 100 → 90; F). The team's largest gain on sealed data.
Paired: vs raster +11.4 [+8.2, +14.4]; vs CC5K net +18.5 [+11.5, +25.5] (`experiments/r2/paired.py`). Only per-concept loss
vs raster: EN showers+bathtubs 73 vs 84. Compositions must go through the pipeline's compose step (atomic questions).
Cost $0.035/1k (780 tok in, 2 out). Confidence: own map (CONF_MAPS["cc-v2"], fit on train_gate), AUROC 0.885–0.928.
Licence: CubiCasa5K images are CC BY-NC-SA 4.0 → the adapter is non-commercial (same as the CC5K weights).
Scripts: `experiments/r2/lora/{build_data,train_lora,eval_lora.sh}`. Training env: `/data/User/fangy4/envs/junction-train`
(= coder390-vllm packages via a read-only .pth + peft/accelerate).
**LoRA cc-v3 (trained 01:50–02:24) — cubicasa tie, better on unseen raster styles.** cc-v2 continued for 33 min
(lr 5e-5) on `train_v3_mix.jsonl` = TRAIN cubicasa (no train_gate) + swiss PNG twins of TRAIN drawings (4,452 drawings,
2,671 sampled). Adapter: `$JUNCTION_SHARED/artifacts/R2/lora/cc-v3`.
| set | cc-v3 | cc-v2 | base 8B |
|---|---|---|---|
| dev cubicasa (800) | 74.6 | 73.9 | 50.4 |
| train_gate cubicasa (480) | 76.2 | 76.7 | 45.6 |
| hard cubicasa (283: translations, paraphrases, compositions) | 52.6 | 52.7 | |
| cc5k_heldout_notLoRA (200) | 79.5 | 79.0 | 51.5 |
| swiss dev counts on PNG twins (200, EN/DE/FR/IT) | **56.5** | 46.0 | 40.5 |
Paired cc-v3 − cc-v2: dev +0.8 [−1.0, +2.5], train_gate −0.4 [−2.3, +1.5], swiss PNG **+10.5 [+4.4, +16.8]**.
Verdict: more passes over the same cubicasa labels saturate; mixing a second drawing style transfers (+16 over the
base on swiss PNGs, DE windows 0 → 33, WC 62 → 88). cc-v2 stays the cubicasa model (every gate is fitted on it);
cc-v3 is the candidate for count questions on raster plans that are NOT cubicasa (the hidden set's "different" data).
Escalation check (03:50): on the 80 swiss-PNG Qs where cc-v3 is unsure (raw p < 0.9) hosted Nemotron is right 22.5% vs
cc-v3 41.2% ($2.45/1k, 10.5 s/Q) → no Nemotron tier for raster counts. Window errors are spread ±3+ (mode 0), so a
count shift doesn't help either.

Cost accounting: local calls record `gpu_seconds = tokens_in/25k + tokens_out/1k` (amortised throughput measured
at saturation), not HTTP wall time (which includes queueing behind other agents).

**Gemma 4 E4B-it bake-off (03:41, base model, no fine-tuning).** Ungated on HF (Gemma 3 is gated; we have no token),
16 GB bf16, vLLM 0.31 `Gemma4ForConditionalGeneration`, preset `serving/start.sh gemma4-e4b` (image budget
`max_soft_tokens` 1120 = the maximum; the default 280 is too coarse for plans). Same vlm_direct code, raw answer-digit p.
| set | Gemma 4 E4B | Qwen3-VL-8B base |
|---|---|---|
| train_gate cubicasa (480) | 31.7 | 46.2 |
| swiss dev counts on PNG twins (200) | 39.5 | 40.5 |
| smoke micro / weighted (206) | 28.3 / 31.2 | 37.0 / 42.4 |
| tokens in per cubicasa Q | 1,169 (1,100 image) | 770 |
Gemma loses on Finnish room-label reading (kitchens 35 vs 85, saunas 15 vs 50, WC seats 5–15 vs 45–65) and ties on
swiss plans. Not a replacement base.

**Gemma 4 E4B counting LoRA `gemma-cc-v1` (04:00–04:48, `experiments/r2/lora/gemma_lora.sh`):** same TRAIN mix as
cc-v3, 50 min, ~2,700 samples, r16 on the language model only; vLLM 0.31 serves the Gemma4 LoRA directly
(`merge_lora.py` = CPU fallback, not needed).
| set | gemma-cc-v1 | Gemma base | cc-v3 (Qwen 8B) |
|---|---|---|---|
| train_gate cubicasa (480) | **76.5** | 31.7 | 76.2 |
| dev cubicasa (800) | 70.9 | | 74.6 (paired −3.8 [−6.5, −1.1]) |
| cc5k_heldout_notLoRA (200) | 74.5 | | 79.5 |
| swiss PNG dev (200) | 50.5 | 39.5 | 56.5 |
As a cross-check it adds nothing (agree 78% → 85% right; but p-map × agreement AUROC 0.908 vs 0.901 dev, 0.925 vs 0.928
held-out; max-p ensemble 73.6 vs 73.9 dev). Verdict: the Gemma-prize "small fine-tuned model" story (32 → 77% on
unseen drawings in 50 min), optional Gemma-only demo mode; the pipeline keeps cc-v2/cc-v3.

## Agent planner: local 8B vs hosted Nemotron (04:01–04:35)
W4's `agent` solver on derived3 (44 derived-quantity Qs), atomic tools local: local 8B planner 40/44; Nemotron planner on
the 32 it finished 27 vs 32 for local (the 5 misses = empty answers from NVIDIA 429s; tie on the 27 completed), $5.18 vs
$0.56 per 1k, 103 vs 28 s/Q. No Nemotron planner tier. Two concurrent Nemotron jobs triggered sustained 429s.

## Language front end: `stoa.llm.to_english` (04:15)
Sealed hard2r showed the pipeline collapsing on languages nobody wrote rules for (F: Polish cubicasa 21%, Estonian ifc
20%). `lang_guess(q)` (stopwords + diacritics over 20 languages, quoted names ignored; 0 model calls) decides; for a
language outside en/fi/de/fr/it (or `force=True`) ONE local 8B call translates the question to English with quoted
names, numbers/IDs and unit letters masked as `[[n]]` and restored byte-identical (quote marks always restored; a
lost placeholder returns the original with `ok=False`). ~250 tokens in / 40 out, ~0.4 s, cost recorded.
| probe | pipeline as is | translated first | notes |
|---|---|---|---|
| lang4: 12 dev Qs × CS/HU/TR/RO, hand-written (48) | 38/48 (79.2%) | **48/48** | EN originals 12/12; 10 wins / 0 losses; 1 translation rejected (placeholder lost) → original kept |
| hard's 175 non-English Qs (fi/de/fr/it templates; new sv/nl/pl/de wordings) | 152/175 | 146/175 (always) / **152/175** (`should_translate` trigger: fires on 0) | translating what the rules already read loses 7, wins 1 |
Trigger (`should_translate(q, intent)`): non-English AND the intent parser failed (lang '?', no target, or task text).
lang4 with the trigger: 48/48 (fires on 46). So: translate on parse failure only, never by language list.
Known slips of the 8B translator: Czech "záchodové mísy" → "toilet rooms" (once), Swedish "bastur" (saunas) → "bathrooms",
Polish "belek" (beams) → "balconies". Prompt v2 (+ English domain terms, "never add/drop a qualifier") and v3 (+ source-language
hints for ~17 building nouns in pl/et/cs/hu/ro/es/sv/fi/de/nl/da) — concept match with the English base on F's
hardL_open: none 129, v2 139, **v3 141/158**; F's 11 pl/ro ifc trigger questions through the pipeline 10 → **11/11**.
F's held-out hardL (nb/hr/el/lt; v1 prompt): 50.0 → 80.6% (English 90.0), 52 wins / 3 losses. Hosted Nemotron as the
translator: 47/48 on lang4 (8B v1 46, v3 47) at 10 s vs 0.4 s → keep the 8B. Wired by W4 (Pipeline._front_end).
Wiring belongs in the pipeline front (W4). Honest number: sealed hard2r at test 2.

## Qwen3.6-35B-A3B bake-off (08:12–08:31, private :8002, util 0.48 next to :8001; `experiments/r2/hold_8002.sh`)
FP8 MoE (3B active), vLLM 0.31 `Qwen3_5MoeForConditionalGeneration`, 225 s to load, transient OOM warnings while preparing
the FP8 experts (harmless; :8001 unaffected). Text calls ~0.3 s. Harness: `experiments/r2/eval_backend.py --agent local2`
(moves ONLY the agent's planner; atomic solvers and LoRAs stay on :8001) and `probes/concept_backend.py` (translator).
| role | set | Qwen3.6-35B-A3B | Qwen3-VL-8B (now) | verdict |
|---|---|---|---|---|
| agent planner (pipeline, only agent-touched Qs) | 44 Qs (derived3 24, red team 19, hard2 1) | 79.5 | **82.0** | 1 win / 2 losses, +31% tokens, +1.4 s/Q; one new 0.75 confident-wrong |
| translator (`to_english` v3) | hardL_open concept match (232) | 195–200 | **210** | lang4 48 vs 47/48 (tie) |
| base VLM (vlm_direct, no LoRA) | dev cubicasa n200 | 54.0 | 47.5 (base) / **cc-v2 ~75** | +6.5 [−0.5, +13.4] vs base, −21.0 [−27.5, −14.7] vs cc-v2 |
| base VLM | swiss PNG counts dev (200) | 45.0 | 40.5 (base) / **cc-v3 56.5** | +4.5 [−1.6, +10.7] vs base, −11.5 vs cc-v3 |
| base VLM | smoke (184 paired) | | | +0.5 [−6.2, +7.2] vs base |
| **free-text IFC answers** (W1's fact cards; only factcard.py moved, judge = 8B) | dev ifc_bench (200, 3 projects) | **62.0** | 54.5 | 21 W / 6 L; hosted Nemotron re-judging the 27 discordant: 6 vs 0; $0.144 vs $0.18/1k |
Conclusion: like the Nemotron planner (04:01), a stronger planner/translator does not move our numbers; a fine-tuned 8B beats
a 4× bigger base VLM on our counting. :8001 stays Qwen3-VL-8B + cc-v2/cc-v3. EXCEPTION: long free-text answers, where the 35B wins
(above) → `llm.text_backend()` (opt-in via STOA_TEXT_BACKEND=local2, falls back to :8001); permanent :8002 is S0's decision (09:08).

**D21 (09:28): YES. :8002 serves qwen3.6-35b-a3b permanently since 09:40** (`PORT=8002 GPU_UTIL=0.48 SERVED_NAME=qwen3.6-35b-a3b
serving/start.sh qwen36-35b-a3b`, 130 s; GPU 94.6 of 97.9 GB with :8001). Demo/API env sets STOA_TEXT_BACKEND=local2; gates don't.
Cost of one answer (D21 item 4), measured, not assumed:
- Throughput on this GPU, 16 concurrent requests (`experiments/r2/tput.py`): 35B prefill 25.3k tok/s, decode 722 tok/s; 8B at the
  same time (under other agents' load) 14.5k / 856. A3B = ~3B active parameters, so per token the 35B costs about what the 8B does.
- The meter bills local2 at 25k prefill / 700 decode tok/s (8B: 25k / 1k), `stoa.llm.PER_BACKEND_TPS`.
- dev ifc_bench (200 Qs; 0.58 fact-card calls per question): 2.6k tokens in / ~90 out per question either way → **0.235 GPU-s per
  question on the 35B vs 0.196 on the 8B (+20%)**; per fact-card call ≈ 4.5k in / 155 out ≈ 0.40 vs 0.34 GPU-s. Mean latency
  1.9 s vs 4.5 s (the 8B queue is shared with every agent; :8002 is not).

## Language front end, morning fixes (08:35–08:45)
- Conjunction trigger (adec1a2): `should_translate` also fires on a count/area question in a language outside en/fi/de/fr/it whose
  'and' joins words, unless the composer already reads it (2 classes + `compose._TOGETHER`). Q multilingual probe 143 → 146/150
  (compose-cc:sv "toalettstolar och balkonger"), 0 losses; 0 new firings on dev/train_gate/hard/hard2/smoke/hard_nonen. `STOA_TR_CONJ=0` = off.
- Lost placeholders (a699667; F 08:30 hard2r mechanism): the 8B writes `'[1]'` for `'[[1]]'` or drops one → restore reads [n] as [[n]],
  ONE corrective retry when still lost; Estonian function words in lang_guess. Own Estonian room-share probe (hard2 gold) 16/24 → 24/24;
  hardL_open concept 210 → 212/232, not-ok 2 → 0.
- Grouped thousands (2ccace2): Swiss 1'200 / 1 200 masked as one number.
- NEGATIVE: extra slip hints (room codes = rooms, 'Hány … közül' = how many of, băi/banyo = bathtubs): hardL_open 206 vs 212 (hu 45 vs 54).

## lang_guess for terse wordings (09:15–09:35, `experiments/r2/probes/lang_id.py`)
- Problem: a question with no question word was decided by a tie on a shared word ('in', 'de'): 'Nettofläche Whg. B in m², ohne
  Balkon und Loggia?' → en, Spanish 'Número de puertas en este plano?' → fr, Dutch 'Tel de ramen op deze plattegrond.' → fr. Read as
  English or as a covered language, an uncovered-language question never reaches the translator (pipeline `_front_end`).
- v2 scorer: more function/domain words per language (none for hr/nb/el/lt = F's held-out languages), each word weighted
  1/(languages listing it), non-Latin script → '?', å also da/no. Open labelled probes (946 + 46 terse): 892 → 928 right.
- Full v2 measured WORSE in the pipeline (63 open rows whose class changes): 90.2 → 88.5, 0 wins / 1 loss, LLM calls/Q 1.30 → 1.92.
  Mechanism: correct 'fi'/'de'/'it' makes `_front_end` trust the rules (covered language + target found → no translation), so terse
  Finnish ('Laske ikkunat.') lost the translation fallback it got as '?'; de/it now trigger ifc's cross-language LLM check.
- Shipped (163bf61): v2 only for covered → uncovered corrections. 0 changes on the 6,671 open dataset questions; terse same-gold probe
  (Swiss dev counts × nl/sv/pl/es/pt/cs/ro/da/en, written by R2) 89 → 90/92, 5 Spanish answers 0.45 → 0.99, $0.067 → $0.038/1k;
  hardL_open neutral (89.7 vs 89.4, the 3 diffs are rows whose lang_guess did not change = batching noise).

## Noon playbook (model side)
0. One command (09:45): put Stoa's examples in eval-split format (path, question, answer or null, type, meta.kind) and run
   `experiments/r2/noon_models.sh EXAMPLES.jsonl [NEMOTRON_LIMIT=40] [GEMINI_LIMIT=0]` → pipeline vs plain local VLM vs hosted
   Nemotron (1 worker, a fixed N-row sample = the eval's seeded `--limit`, not the first N rows), numbers exact/2%, text by the local
   judge, one per-kind table + cost per run (`compare_runs.py --by kind`; columns are labelled pipeline / local-8B / nemotron /
   gemini via `LABEL=RUN` args). Tested on a 12-row mix (log $JUNCTION_SHARED/logs/R2/noon_models.log) and **re-tested 10:55 on
   night 9b1abd3** (8 rows incl. 2 without gold, Nemotron limit 2: 38 s, exit 0). GEMINI_LIMIT needs $GEMINI_API_KEY in the shell
   that runs it (F's eval hides it only on runs of > 200 questions, counted after --limit). Rows without gold (answer null) are predicted but not
   scored ('-' in the table, 10:30 fix); every question with each model's answer @ confidence goes to
   `$JUNCTION_SHARED/artifacts/R2/noon_side_by_side_<split>.txt`; F's `python -m stoa.eval.review RUN.jsonl` gives a readable review. For an unknown-folder raster, `experiments/r2/style/style.py
   FILE` (PYTHONPATH=.) says which reader family fits (cubicasa5k / swiss_dwellings / ifc_models / scan, p≥0.8 → 96.7% right).
1. New question kinds on rasters/scans: first run `vlm_direct` (8B base, conf=logprob) and `vlm_lora` on Stoa's examples; if the LoRA
   answers a kind it was never trained on, its confidence is NOT calibrated (F 01:28) — keep W4's unseen-wording cap.
2. Hosted Nemotron (`backend=nvidia`, 1 worker, ~4–8 s/Q) is the only model clearly different from ours; use it for visible demo
   steps (Nemotron prize) and as a second opinion on unsure answers, never bulk.
3. To try another open model quickly: `experiments/r2/hold_8002.sh <preset> <name> <minutes>` (GPU lock, private :8002), then
   `experiments/r2/eval_backend.py --agent local2 -- --solver pipeline --split <file>` or `vlm_direct -k backend=local2`.

## Drawing style from image content (09:30–10:25, `stoa/style.py`; training in `experiments/r2/style/`)
- `guess_style(path)` → (cubicasa5k | swiss_dwellings | ifc_models | scan, p): numpy softmax on ~110 cheap features (grey/sat/hue
  histograms, paper tone and texture, edge density and direction, long dark runs, 8×8 thumbnail), image flattened on white first (no
  file-mode / pixel-size cues). Trained on train groups + one upload-like variant each (grayscale / JPEG q40 / crop / downscale ÷3).
- Held-out groups (site / model / building): 92.4%; variants 90–91% (without the augmentation, grayscale or JPEG Swiss plans were 0/308);
  p≥0.8 covers 85% at 96.7%. Residue = CubiCasa ↔ historical scans (CubiCasa contains scanned plans; Wikimedia has CubiCasa-like plans).
- End to end, 40 dev CubiCasa count Qs as unknown-folder files vs filed under the guess: 30 vs 29/40, evidence boxes 0 → 17/40,
  $0.203 → $0.036/1k, ECE 0.100 → 0.044.
- **Dev size (10:16–10:25), Q's upload probe = all 800 dev CubiCasa Qs saved as `<sha>/plan.png`** (source 'unknown'), same code:

  | run | acc | conf≥0.8 (right) | confident misses | evidence | $/1k |
  |---|---|---|---|---|---|
  | style off (today's night) | 74.2 | 567 (91.7%) | 47 | 0% | 0.046 |
  | vlm_lora adapter chosen by style only | 73.2 | 521 (93.5%) | 34 | 0% | 0.046 |
  | **source hook: outside raster → 'cubicasa5k' at p≥0.8** | **75.1** | 478 (93.5%) | **31** | **32.4%** | **0.041** |
  | dataset path (control, Q 09:33) | 75.9 | 450 (94.7%) | 24 | 47.8% | 0.016 |
  | same 800 as JPEG q85 uploads: off → hook | 74.6 → 75.1 | 562 → 477 | 47 → 30 | 0 → 32.0% | 0.043 → 0.040 |

  Swiss PNG dev counts as uploads (200 Qs, 95 images, all guessed Swiss at p≥0.8), filed as 'swiss_dwellings' vs 'unknown':
  56.5 vs 56.0%, confident misses 6 vs 6, evidence 0 vs 0 (no Swiss raster reader with boxes; both answer with vlm_lora),
  $0.099 vs $0.149/1k → **file CubiCasa only**; a Swiss guess buys nothing until a Swiss raster reader exists
  (runs 20261114-103517-pipeline-upload_swiss_png-6dc9 / -c73f; `STYLE_HOOK_CLASSES=cubicasa5k,swiss_dwellings eval_hooked.py`).

  The hook touches 588 Qs (147/200 images): 586 answers identical to the dataset path. The adapter-only variant loses 13 W / 21 L
  (the per-concept gate matters, not the adapter) → dropped. Runtime moved to `stoa/style.py` (+ `stoa/style_weights.json`); the
  hook would go in `stoa/data.py` (F's file; **D23: not tonight — a day-team item**; tonight W4 caps confidence on 'unknown' rasters instead): patch `$JUNCTION_SHARED/artifacts/R2/data_style_hook.patch`, measured with
  `experiments/r2/style/eval_hooked.py`, compared with `experiments/r2/style/upload_compare.py`. False positives at p≥0.8 (held-out
  groups): 12/820 non-CubiCasa images, all historical scans (Wikimedia 10); Swiss/IFC renders 0. First question on a new image runs
  the CC5K detector live (median 0.4 → 1.5 s).

## Candidates surveyed (23:35–23:50, HF hub listing; vLLM 0.31 registry checked)
| model | size | vLLM | why interesting | verdict |
|---|---|---|---|---|
| Qwen3-VL-8B-Instruct | 17.5 GB bf16 | ✅ Qwen3VL | strong grounding (0..1000), OCR, fast | **serving** (already on disk) |
| Qwen3.6-35B-A3B-FP8 | 37.5 GB | ✅ Qwen3_5Moe | newest Qwen (Nov 2026), MoE: only 3B active → cheap per token, likely much stronger | **tested 08:12–09:08: only free-text answers** (see 'Qwen3.6-35B-A3B bake-off') |
| Qwen3.5-9B | 19.3 GB bf16 | ✅ Qwen3_5 | newer than Qwen3-VL-8B, hybrid thinking | download cancelled to give 3.6 the bandwidth |
| Qwen3.6-27B-FP8 | 30.9 GB | ✅ | dense 27B: slower than 35B-A3B | skip |
| Molmo2-8B / 4B | ~17 / ~9 GB | ✅ Molmo2 | trained for pointing + counting (PixMo-Points) → count-by-pointing with evidence | next download candidate if counting stays weak |
| Gemma-4-12B-it | ~24 GB | ✅ Gemma4 | Gemma prize | maybe later; bandwidth. Hosted gemma-3-12b-it 404s and gemma-4-31b-it times out on the NVIDIA API (00:40) |
| Nemotron 3.5 Super VL 120B-A12B | hosted | – | NVIDIA prize; strong; grounding in 0..1000 too | **hosted backend `nvidia`** in stoa.llm (30 RPM shared limiter) |
| Nemotron 3.5 Super VL NVFP4 | ~65 GB | ? | local Nemotron | does not fit next to the shared server; 7 h download |
| Nemotron-Parse v1.2 / 3.5-Parse | small | ? | document parsing (tables, text + boxes) | candidate for schedule tables (opening_design) |
| PaddleOCR-VL 1.6, MinerU2.5-Pro, DeepSeek-OCR-2 | 1–3 GB | mixed | OCR/layout | R1/W3 territory; PDF text layers already cover swiss/ifc_models |
| InternVL3.5-8B/30B-A3B | 17 / 60 GB | ✅ | good docs | not newer than Qwen3.6 |
| GroundingDINO / OWLv2 / Florence-2 | <2 GB | – | open-vocab detectors | symbols on plans are out-of-domain for them |

## Confidence from logprobs (cycle 2, 01:10)
`llm.chat(logprobs=5)` + `llm.answer_prob()` = probability the model gave to its answer's digits (free on vLLM).
vlm_direct maps it through `CONF_MAP` (fit on 1,500 TRAIN Qs with `experiments/r2/fit_conf.py`):
| raw p(digits) | ≤0.49 | ≤0.88 | ≤0.96 | ≤0.991 | ≤0.999 | >0.999 |
|---|---|---|---|---|---|---|
| count accuracy (train) | 12% | 34% | 41% | 48% | 49% | 89% |
Count AUROC 0.78 (cubicasa 0.74, swiss 0.89); ECE 0.02 mapped vs 0.20 for the old constant 0.3. Areas (swiss, 8B reads
them badly: 5% right) AUROC 0.87. The map is model-specific: refit it for a LoRA or another model.
Held-out check: full dev (2,215) ECE 0.024, AUROC 0.869, conf ≥ 0.8 on 14% at 89% right; full hard (711; paraphrases,
translations) ECE 0.054, AUROC 0.868. Accuracy unchanged (dev micro 32.6, hard 25.3); $0.08–0.16 per 1k.

Gate "8B if p ≥ T else baseline" (`experiments/r2/conf_gate.py`), cubicasa: beats the prior (train 55.5 → 58.1 at
T=0.9999, dev 54.1 → 57.4 at T=0.999) but not W3's per-class `raster` (dev 62.5 → 61.6). WC seats are the one concept
where it may add (dev 69 vs 59 EN, 64 vs 55 FI; to be confirmed on TRAIN by W3).

Escalation to hosted Nemotron (`experiments/r2/escalate.py`): on TRAIN cubicasa Qs where the 8B is unsure (raw p < 0.88,
36% of them; 60 sampled) Nemotron 36.7 vs prior 31.7 vs 8B 23.3; $1.57/1k, 11 s. Not worth it for bulk counting.

## Historical scans (no questions in the data)
View-type recognition on finna scans (`experiments/r2/scan_views.py`, weak gold from Finnish title keywords):
8B 68% exact view set on 100 (P 0.79–0.97, R 0.84–1.00 per view), 3.2k tokens/scan; Nemotron 50% on 40 (59% parsed)
vs the 8B's 62.5% on the same 40. The local 8B is enough to type untitled scans for the KG.

## Leak-free symbol comparison (cycle 2)
`$JUNCTION_SHARED/artifacts/R2/cc5k_heldout_notLoRA.jsonl` = R1's cc5k_heldout (original CC5K test list, so the
pretrained CC5K net never saw them) minus drawings in the LoRA's training data minus sealed-test drawings:
200 Qs on 50 drawings (56 dev, 132 train_gate, 12 smoke). ~15 Qs per concept: small, read per-concept numbers as ±12 pts.
| solver | all | windows | doors | WC seats | sinks | showers+baths |
|---|---|---|---|---|---|---|
| prior | 54.0 | 26.7 | 11.1 | 47.1 | 42.9 | 57.1 |
| Qwen3-VL-8B direct | 51.5 | 13.3 | 44.4 | 82.4 | 57.1 | 28.6 |
| R1 CC5K net (plain_over_prior) | 60.5 | 40.0 | 22.2 | 88.2 | 57.1 | 57.1 (prior) |

## Cascade recommendation (from the numbers so far)
1. Deterministic parsers first (DXF 99%, IFC 100%, PDF text layer): free, exact, verifiable. The VLM must never
   override them.
2. Local Qwen3-VL-8B, answer-only prompt, ~1 s and ~1.5k tokens: raster-only questions, and reading printed
   labels/areas. Gate per template against the prior on TRAIN (W4 is calibrating this).
3. Optional free signal: `samples=5` (one request, n=5) → vote share; escalate only when < 1.0 (~20% of questions).
4. Hosted Nemotron (thinking on, ~30 s, ~5k tokens, 1–2 API calls): only for escalated / demo questions. It is
   not more accurate than the local 8B in direct mode, so it should be used as a reasoning verifier
   (e.g. "here is the count and the points; check it"), not as a first-pass counter.
5. Counting LoRAs (status 03:50): cc-v2 replaced step 2 for atomic cubicasa counts (W4's per-concept gate fitted on
   train_gate; pipeline dev weighted 74.0 → 82.1, $0.03/1k, 1 call, 2 output tokens). For raster plans of any other
   style `vlm_lora` uses cc-v3 (+16 over the base 8B on swiss PNGs). Both on :8001 (start.sh loads them by default).
6. Cheap cross-check before any escalation: R1's CC5K detector boxes (cache read, 0 tokens) agree/disagree with the
   LoRA count → confidence + located evidence. Agreement adds little beyond the LoRA's own p (R1 01:56), so use it
   for evidence and for the 'missing' note, not for a second model call.
7. Nemotron (hosted) stays a visible second opinion on low-confidence image answers (W5's button), not a bulk tier.
8. Gemma 4 E4B base is weaker than the 8B (cubicasa 31.7 vs 46.2); its LoRA reaches 76.5 on train_gate (Qwen LoRA 76.7)
   but is 4–5 points lower on dev/held-out and adds nothing as a cross-check → Gemma-prize story / Gemma-only demo mode.
9. Language front end: translate a question with the local 8B ONLY when it is non-English and the rule parser fails
   (`should_translate`); ~0.4 s, ~700 tokens, on 0.03% of dataset questions; held-out languages 50 → 81%.
10. Agent planner: the local 8B; hosted Nemotron as planner ties at 9× the cost.
11. Free-text answers (IFC fact cards): Qwen3.6-35B-A3B on :8002 via `llm.text_backend()` (D21), +20% GPU-s, judged +7.5.
12. Files outside our folders (uploads, a hidden set in new folders): `stoa/style.py` guesses the reader family from the
    image (p≥0.8 → 96.7% right); filing an upload under the guess (stoa/data.py hook; day team, D23) restores the CubiCasa gate, boxes and the
    cheap path: confident misses 47 → 31 on 800 dev Qs as uploads, 586/588 touched answers = the dataset path.
