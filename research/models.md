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

**LoRA in progress (00:13–01:13):** Qwen3-VL-8B + LoRA r16 on TRAIN cubicasa counts (4,366 drawings, multi-turn
image-once samples, EN/FI + paraphrases, answer-only targets). Adapter: `$JUNCTION_SHARED/artifacts/R2/lora/cc-v1`.
Scripts: `experiments/r2/lora/{build_data,train_lora}.py`. Training env: `/data/User/fangy4/envs/junction-train`
(= coder390-vllm packages via a read-only .pth + peft/accelerate).

## Candidates surveyed (23:35–23:50, HF hub listing; vLLM 0.31 registry checked)
| model | size | vLLM | why interesting | verdict |
|---|---|---|---|---|
| Qwen3-VL-8B-Instruct | 17.5 GB bf16 | ✅ Qwen3VL | strong grounding (0..1000), OCR, fast | **serving** (already on disk) |
| Qwen3.6-35B-A3B-FP8 | 37.5 GB | ✅ Qwen3_5Moe | newest Qwen (Nov 2026), MoE: only 3B active → cheap per token, likely much stronger | **downloading** (~4 h at 2.5 MB/s); bake-off when it lands |
| Qwen3.5-9B | 19.3 GB bf16 | ✅ Qwen3_5 | newer than Qwen3-VL-8B, hybrid thinking | download cancelled to give 3.6 the bandwidth |
| Qwen3.6-27B-FP8 | 30.9 GB | ✅ | dense 27B: slower than 35B-A3B | skip |
| Molmo2-8B / 4B | ~17 / ~9 GB | ✅ Molmo2 | trained for pointing + counting (PixMo-Points) → count-by-pointing with evidence | next download candidate if counting stays weak |
| Gemma-4-12B-it | ~24 GB | ✅ Gemma4 | Gemma prize | maybe later; bandwidth |
| Nemotron 3.5 Super VL 120B-A12B | hosted | – | NVIDIA prize; strong; grounding in 0..1000 too | **hosted backend `nvidia`** in stoa.llm (30 RPM shared limiter) |
| Nemotron 3.5 Super VL NVFP4 | ~65 GB | ? | local Nemotron | does not fit next to the shared server; 7 h download |
| Nemotron-Parse v1.2 / 3.5-Parse | small | ? | document parsing (tables, text + boxes) | candidate for schedule tables (opening_design) |
| PaddleOCR-VL 1.6, MinerU2.5-Pro, DeepSeek-OCR-2 | 1–3 GB | mixed | OCR/layout | R1/W3 territory; PDF text layers already cover swiss/ifc_models |
| InternVL3.5-8B/30B-A3B | 17 / 60 GB | ✅ | good docs | not newer than Qwen3.6 |
| GroundingDINO / OWLv2 / Florence-2 | <2 GB | – | open-vocab detectors | symbols on plans are out-of-domain for them |

## Cascade recommendation (from the numbers so far)
1. Deterministic parsers first (DXF 99%, IFC 100%, PDF text layer): free, exact, verifiable. The VLM must never
   override them.
2. Local Qwen3-VL-8B, answer-only prompt, ~1 s and ~1.5k tokens: raster-only questions, and reading printed
   labels/areas. Gate per template against the prior on TRAIN (W4 is calibrating this).
3. Optional free signal: `samples=5` (one request, n=5) → vote share; escalate only when < 1.0 (~20% of questions).
4. Hosted Nemotron (thinking on, ~30 s, ~5k tokens, 1–2 API calls): only for escalated / demo questions. It is
   not more accurate than the local 8B in direct mode, so it should be used as a reasoning verifier
   (e.g. "here is the count and the points; check it"), not as a first-pass counter.
5. If the counting LoRA wins on dev cc, it replaces step 2 for raster counts (same server, `model="cc-v1"`).
