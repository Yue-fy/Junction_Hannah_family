# Scorecard (E = agent F, 01:05, 14 Nov)

Integrated `night` on dev v2 (hash f43c5369): dev/hard = S0 runs on night 2b7935a (00:47–00:52); hard2/hard2p =
night 971b985 (00:58–01:04); ifc_bench text judged on night cbd2fe8 (00:38; re-judged 01:10 with the numeric pre-check). Regenerate:
`python -m stoa.eval.scorecard 20261114-004756-pipeline-dev-fbaf --hard 20261114-005205-pipeline-hard-de9c --text artifacts/eval/20261114-003818-pipeline-dev-79b6.judged.jsonl --gen 20261114-005759-pipeline-hard2-5737 --gen 20261114-010003-pipeline-hard2p-3d40`

- Cost: local-LLM GPU time is billed from tokens (min(reported, estimate)); queueing-inflated latency had made
  it look 10x higher. LLM-cache hits are still billed as free by stoa.llm, so a cold run may cost a bit more.
- hard2 = operators questions.jsonl never asks (average, ratio, %, threshold, excluding, argmin, ft); hard2p =
  the same reworded, HELD OUT (D9). W2 dxf v5 is not in night 971b985 yet.
- The sealed test is run only by S0. Open problems: cubicasa symbol counts (windows, doors, sinks, WC seats) and
  reworded operators (hard2p conf >= 0.8 answers only ~70% right).

## Scorecard: `pipeline` — 20261114-004756-pipeline-dev-fbaf

Baseline: `20261113-235744-prior-dev`. CI = 95% cluster bootstrap over drawings.

| measure | this run | baseline | what it means |
|---|---:|---:|---|
| weighted accuracy | 73.8% | 41.0% | bucket accuracies × full-dataset shares (headline) |
| micro accuracy [95% CI] | 83.6% [80%–86%] | 26.9% [23%–32%] | scored questions as sampled |
| refusals | 0.0% | 0.0% | value = null (Stoa: refusing is not useful) |
| answers with evidence | 65.3% | 0.0% | any file/box/IFC GUID |
| … located on a drawing | 56.2% | 0.0% | a box the UI can highlight |
| counts: located objects = answer | 96.9% of 541 | – | verifiable in seconds |
| answers stating assumptions | 85.9% | 100.0% | Answer.assumptions non-empty |
| answers stating what is missing | 51.3% | 100.0% | Answer.missing non-empty |
| confidence ≥ 0.8: share / accuracy | 53% / 98.5% | 5% / 92.7% | what the user sees as 'sure' |
| calibration error (ECE) | 0.051 | 0.024 | 0 = confidence = accuracy |
| confidence ranks right above wrong (AUROC) | 0.90 | 0.88 | 0.5 = confidence is noise |
| cost per 1,000 questions | $0.05 | $0.00 | LLM tokens, GPU s, API calls priced (runner.RATES) |
| LLM calls per question | 0.23 | 0.00 |  |
| deterministic tier (share / accuracy) | 80% / 86.1% | 100% / 26.9% | no model call at all |
| latency p50 / p95 | 0.284 s / 3.564 s | 0.0 s / 0.001 s |  |
| text answers, LLM-judged | 40.5% of 200 | – | free text (ifc_bench, schedules); judge is lenient ±5 pts |
| generality (hard): translation / paraphrase / composition | 86% / 84% / 65% | – | unseen wordings, languages, units, multi-step |
| generality (hard2): scored / judged text / AUROC / conf ≥ 0.8 acc | 77.8% / 47.8% / 0.51 / 95.8% | – | n=256; operators never seen in questions.jsonl |
| generality (hard2p): scored / judged text / AUROC / conf ≥ 0.8 acc | 56.1% / 56.7% / 0.53 / 69.5% | – | n=256; operators never seen in questions.jsonl |

| source | n | accuracy | conf ≥ 0.8 share / acc | ECE | evidence in 2D | counts verifiable | $/1k |
|---|---:|---:|---:|---:|---:|---:|---:|
| cubicasa5k | 800 | 61.8% | 23% / 91.3% | 0.018 | 6% | 100% | 0.07 |
| ifc_bench | 200 | text 40.5% | – | – | 0% | – | 0.10 |
| ifc_models | 354 | 100.0% | 100% / 100.0% | 0.017 | 98% | 100% | 0.00 |
| opening_design | 61 | 73.9% | 0% / – | 0.267 | 84% | 41% | 0.44 |
| swiss_dwellings | 800 | 98.8% | 66% / 100.0% | 0.105 | 100% | 100% | 0.01 |
