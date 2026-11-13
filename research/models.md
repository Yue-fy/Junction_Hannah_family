# Models for Stoa "Make Blueprints Talk" (owner: R2)

Hardware: 1× RTX PRO 6000 Blackwell 96 GB. Shared server budget ≈ 45 GB (`--gpu-memory-utilization 0.45`).
**Bandwidth is the real constraint tonight:** this machine downloads from Hugging Face at only ~2.5 MB/s total
(Wi-Fi; measured with 8 parallel range requests), i.e. ~2 h per 19 GB. Every download must be chosen carefully.

## Serving now
| what | value |
|---|---|
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

**LoRA in progress (00:24–01:25): cc-v2.** Qwen3-VL-8B + LoRA r16 on TRAIN cubicasa counts, *excluding every
train_gate drawing* (train_gate ⊂ train is used for gating; cc-v1 had seen it and was stopped after 10 min).
3,905 drawings as multi-turn image-once samples (34.7k Q/A turns, EN/FI + paraphrases, answer-only targets),
~0.94 s/sample, 27 GB. Adapter: `$JUNCTION_SHARED/artifacts/R2/lora/cc-v2`.
Scripts: `experiments/r2/lora/{build_data,train_lora,eval_lora.sh}`. Training env: `/data/User/fangy4/envs/junction-train`
(= coder390-vllm packages via a read-only .pth + peft/accelerate).

Cost accounting: local calls record `gpu_seconds = tokens_in/25k + tokens_out/1k` (amortised throughput measured
at saturation), not HTTP wall time (which includes queueing behind other agents).

## Candidates surveyed (23:35–23:50, HF hub listing; vLLM 0.31 registry checked)
| model | size | vLLM | why interesting | verdict |
|---|---|---|---|---|
| Qwen3-VL-8B-Instruct | 17.5 GB bf16 | ✅ Qwen3VL | strong grounding (0..1000), OCR, fast | **serving** (already on disk) |
| Qwen3.6-35B-A3B-FP8 | 37.5 GB | ✅ Qwen3_5Moe | newest Qwen (Nov 2026), MoE: only 3B active → cheap per token, likely much stronger | **downloading** (~4 h at 2.5 MB/s); bake-off when it lands |
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
5. If the counting LoRA wins on dev cc and on train_gate per concept, it replaces step 2 for those concepts
   (same server with LoRA enabled, `model="cc-v2"`).
