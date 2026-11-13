# Scorecard (E = agent F, 00:41, 14 Nov)

Integrated `night` (cbd2fe8, all branches at 00:32) on dev v2 (hash f43c5369), hard, and ifc_bench text
(judged by the local LLM). Regenerate:
`python -m stoa.eval.scorecard 20261114-003232-pipeline-dev-98d6 --hard 20261114-003438-pipeline-hard-63f0 --text 20261114-003818-pipeline-dev-79b6`.
The sealed test is run only by S0. Read "cubicasa 61%" as the open problem: symbol counting (windows, doors,
sinks, WC seats); every other source is 98–100% with evidence.

## Scorecard: `pipeline` — 20261114-003232-pipeline-dev-98d6

Baseline: `20261113-235744-prior-dev`. CI = 95% cluster bootstrap over drawings.

| measure | this run | baseline | what it means |
|---|---:|---:|---|
| weighted accuracy | 73.3% | 41.0% | bucket accuracies × full-dataset shares (headline) |
| micro accuracy [95% CI] | 83.4% [80%–86%] | 26.9% [23%–32%] | scored questions as sampled |
| refusals | 0.0% | 0.0% | value = null (Stoa: refusing is not useful) |
| answers with evidence | 64.8% | 0.0% | any file/box/IFC GUID |
| … located on a drawing | 55.0% | 0.0% | a box the UI can highlight |
| counts: located objects = answer | 97.5% of 530 | – | verifiable in seconds |
| answers stating assumptions | 86.0% | 100.0% | Answer.assumptions non-empty |
| answers stating what is missing | 42.3% | 100.0% | Answer.missing non-empty |
| confidence ≥ 0.8: share / accuracy | 67% / 98.1% | 5% / 92.7% | what the user sees as 'sure' |
| calibration error (ECE) | 0.019 | 0.024 | 0 = confidence = accuracy |
| confidence ranks right above wrong (AUROC) | 0.91 | 0.88 | 0.5 = confidence is noise |
| cost per 1,000 questions | $0.41 | $0.00 | LLM tokens, GPU s, API calls priced (runner.RATES) |
| LLM calls per question | 0.22 | 0.00 |  |
| deterministic tier (share / accuracy) | 80% / 86.0% | 100% / 26.9% | no model call at all |
| latency p50 / p95 | 0.176 s / 1.915 s | 0.0 s / 0.001 s |  |
| text answers, LLM-judged | 42.5% of 200 | – | free text (ifc_bench, schedules); judge is lenient ±5 pts |
| generality (hard): translation / paraphrase / composition | 86% / 83% / 65% | – | unseen wordings, languages, units, multi-step |

| source | n | accuracy | conf ≥ 0.8 share / acc | ECE | evidence in 2D | counts verifiable | $/1k |
|---|---:|---:|---:|---:|---:|---:|---:|
| cubicasa5k | 800 | 61.0% | 23% / 91.9% | 0.015 | 5% | 100% | 1.09 |
| ifc_bench | 200 | text 42.5% | – | – | 0% | – | 0.10 |
| ifc_models | 354 | 99.7% | 100% / 99.7% | 0.025 | 93% | 100% | 0.00 |
| opening_design | 61 | 78.3% | 0% / – | 0.259 | 87% | 58% | 0.34 |
| swiss_dwellings | 800 | 98.8% | 100% / 98.8% | 0.011 | 100% | 100% | 0.00 |
