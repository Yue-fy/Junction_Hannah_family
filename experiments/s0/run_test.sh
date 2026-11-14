#!/usr/bin/env bash
# S0 milestone run on a FROZEN night commit (D7/D8/D10). Run from the worktree root:
#   bash experiments/s0/run_test.sh "S0 sealed test 1"
# Runs, all on the same commit and logged to the leaderboard:
#   test  cc5k=0  (clean headline)          test  default (cc5k=1 if the pipeline knows it; labelled inflated, D8)
#   dev, hard, hard2 (development), hard2q (held-out, aggregates only, D10), hard2p ("partly seen"),
#   hard2r (sealed fresh draw, D12)
# then the scorecard of the clean test run. Writes logs to $JUNCTION_SHARED/logs/S0/test-<tag>-*.log.
set -u
TAG="${1:-S0 sealed test}"
P="$JUNCTION_VENV/bin/python"
L="$JUNCTION_SHARED/logs/S0"; mkdir -p "$L"
C=$(git rev-parse --short HEAD)
STAMP=$(date +%H%M)
export AGENT_ID=S0
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then echo "worktree not clean; commit first" >&2; exit 1; fi
# cc5k=0/1 only differ when raster_cc5k is registered AND the pipeline finds its cc5k_heldout gate (D8).
HAS_CC5K=$("$P" -c "from stoa.pipeline import GATING_CC5K; from stoa.solvers import available; print(int(GATING_CC5K.exists() and 'raster_cc5k' in available()))" 2>/dev/null || echo 0)
HAS_LORA=$(grep -c "lora: int" stoa/pipeline.py || true)

run() {  # name split extra-args...
  local name=$1 split=$2; shift 2
  echo "[$(date +%H:%M)] $name ($split) ..."
  "$P" -m stoa.eval --solver pipeline --split "$split" --workers 8 --note "$TAG @ $C: $name" "$@" \
    > "$L/test-$STAMP-$name.log" 2>&1
  tr '\r' '\n' < "$L/test-$STAMP-$name.log" | grep -E "OVERALL|weighted_acc|calibration|cost/question|predictions:|Traceback"
}

run test-cc5k0 test --allow-test --solver-arg cc5k=0 --judge local   # clean headline (D8, D11)
if [ "$HAS_LORA" -gt 0 ]; then
  run test-lora0 test --allow-test --solver-arg cc5k=0 --solver-arg lora=0   # ablation: without R2's counting LoRA
fi
if [ "$HAS_CC5K" = "1" ]; then
  run test-cc5k1 test --allow-test --solver-arg cc5k=1   # labelled INFLATED (CC5K pretraining saw these images)
else
  echo "cc5k=1 is a no-op at $C (raster_cc5k gate not found by the pipeline): skipped"
fi
run dev dev
run hard hard
run hard2 hard2
run hard2q hard2q   # held out: aggregates only, never quote wordings (D10)
run hard2p hard2p   # partly seen
run hard2r hard2r --judge local   # D12: sealed fresh draw (F), milestones only, aggregates only
run hard3 hard3 --judge local    # D15: sealed derived quantities (F), milestones only, aggregates only
pred() { tr '\r' '\n' < "$L/test-$STAMP-$1.log" | sed -n 's/^predictions: //p' | tail -1; }
CLEAN=$(pred test-cc5k0)
DEV=$(pred dev)
echo "scorecard: test=$CLEAN dev=$DEV"
"$P" -m stoa.eval.scorecard "$CLEAN" --hard "$(pred hard)" --gen "$(pred hard2)" --gen "$(pred hard2q)" --gen "$(pred hard2r)" --gen "$(pred hard3)" --out "$L/scorecard-$STAMP.md" 2>&1 | tail -40
echo "done $C; scorecard in $L/scorecard-$STAMP.md"
