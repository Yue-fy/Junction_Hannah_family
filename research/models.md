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
| model | style | split | micro acc | macro acc | latency mean | tokens in/out per q | notes |
|---|---|---|---|---|---|---|---|
| Qwen3-VL-8B local | CoT, 1024 max tok | smoke | 26.2 | 13.0 | 4.5 s | ~600/~400 | rambles, loops, truncates (finish=length); parse picks dimension text like "1800x2400" |
| Qwen3-VL-8B local | direct (answer only) | smoke | **32.9** | **28.4** | 0.32 s | ~600/3 | 8× fewer output tokens, better accuracy |
| (dummy floor, F) | template mode | smoke | 31.6 | – | – | 0 | the floor to beat |

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

## Cascade recommendation (draft, to be measured)
1. Deterministic parsers first (DXF / IFC / PDF text layer): free and exact.
2. Local VLM, direct answer (0.3 s, ~600 tokens) for raster-only questions.
3. Escalate to hosted Nemotron only when the local answer is low-confidence (e.g. self-consistency disagreement
   across 2 tiles/resolutions, or a count above ~15 on a dense plan).
