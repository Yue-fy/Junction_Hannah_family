# Noon kit: Stoa's example questions, from first look to a measured fix

The overnight agents stop at 11:45; Stoa shows its example questions at 12:00. This page lists the tools in the
order to use them. Every step except 3 is 0 LLM calls.

## 1. Write the gold before any run
Rows `{"path": "data/...", "question": "...", "answer": ..., "unit": ..., "type": ...}` (answer optional). Write the
gold by eye from the drawing, and commit it before any run. Afterwards a fix can't quietly move the target.

## 2. Triage (0 LLM, ~10 s): which route catches each question?
```bash
$JUNCTION_VENV/bin/python experiments/r1/noon/triage.py EXAMPLES.jsonl --out triage.jsonl
```
For each question it prints the source, W4's parse (task / target / scope), whether its template occurs in train,
the compose plan, and whether R1's triggers fire (link → kg_qa + W1 plan_vs_model; room graph; out-of-drawing
estimate, not wired). It also prints the most similar train/dev question and where a fix would go. **NEW** means the
nearest train/dev question has cosine < 0.5 and the template is not in train: a wording nobody tuned for, so write
5-10 rewordings of it (other languages, typos, casual phrasings). Q's `redteam/from_examples.py` makes
those variants automatically.
- Calibration (`calibrate.py`, nearest TRAIN question, 400 rows per split): flagged NEW = dev 14%, hard 33%,
  hard2 77%, Q's red team 70%.
- **NEW does not mean wrong** (`triage_vs_run.py RUN.jsonl`). Accuracy NEW vs seen is 95.4 vs 78.3% on Q's red team
  (973 rows, snap12), 87.3 vs 84.9% on hard (688), 97.4 vs 83.6% on hard2 (189). The SOURCE predicts failure:
  CubiCasa counts are 64-77% right in every split, Swiss and IFC 94-100%, new or not. Don't turn NEW into a
  confidence cap.

## 3. Run and read
```bash
$JUNCTION_VENV/bin/python -m stoa.eval --solver pipeline --split EXAMPLES.jsonl --no-leaderboard
experiments/r2/noon_models.sh EXAMPLES.jsonl          # pipeline vs local 8B vs Nemotron (vs Gemini, <= 40 calls)
```
The first trace line names the step that answered (table in `stoa/router/README.md` section 2). Section 3 there
says where each kind of fix goes. Link questions: `python experiments/r1/kg_qa/compare.py PROBE RUN_A RUN_B`. It
scores yes/no, accept_re and Q's per-item regexes, which stoa.eval leaves unscored.

## 4. Is a fix real? (few examples → small-sample statistics)
Paired runs (same rows, fix off/on). Exact two-sided McNemar on the rows that changed:

| wins / losses | 4 / 0 | 5 / 0 | 6 / 0 | 7 / 1 | 8 / 1 | 9 / 2 | 10 / 2 |
|---|---|---|---|---|---|---|---|
| p | 0.125 | 0.062 | **0.031** | 0.070 | **0.039** | 0.065 | **0.039** |

So on Stoa's examples alone a fix needs **≥ 6 wins with 0 losses** before it counts as more than luck. That is
the reason to write rewordings (step 2): 3 examples × 5 rewordings is a testable probe, 3 examples are not.
Accuracy on n questions (Wilson 95%): 8/10 = 80% [49, 94]; 15/20 = 75% [53, 89]; 18/20 = 90% [70, 97];
25/30 = 83% [66, 93]. A 10-point difference between two systems on 20 questions is noise.
For dev-sized runs: `python3 experiments/r1/stats/compare.py RUN_A RUN_B` (cluster bootstrap by drawing + McNemar).

## 5. Narrow triggers (tonight's rule)
Before you wire a new route, count how many dataset and open-split questions it fires on (as
`experiments/r1/kg_qa/trigger_eval.py` does). A route that fires on 0 of them leaves dev/hard/hard2 unchanged by
construction, so only the new probe needs measuring.
