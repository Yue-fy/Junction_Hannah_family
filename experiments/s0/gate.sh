#!/usr/bin/env bash
# S0 merge gate (cycle 17): snapshot <commit> in its own detached worktree, run ifc (ifc_models dev) and pipeline
# hard2/hard/dev there, detached, so `night` stays open. From the S0 worktree root:
#   bash experiments/s0/gate.sh <tag> [commit]      e.g. bash experiments/s0/gate.sh c18
# -> logs $JUNCTION_SHARED/logs/S0/<tag>-{ifc-dev,hard2,hard,dev}.log, done marker <tag>-gate.done (~10 min).
# Compare: python3 experiments/r1/stats/compare.py OLD.jsonl NEW.jsonl --by source
# Afterwards: git worktree remove /data/User/fangy4/projects/junction-wt/S0-gate-<tag>
set -eu
TAG=${1:?tag}
C=$(git rev-parse --short "${2:-HEAD}")
WT=/data/User/fangy4/projects/junction-wt/S0-gate-$TAG
L=$JUNCTION_SHARED/logs/S0
PY=$JUNCTION_VENV/bin/python
git worktree add --detach "$WT" "$C" >/dev/null
cd "$WT"
N="S0 $TAG gate night $C"
setsid nohup bash -c "
export AGENT_ID=S0
$PY -m stoa.eval --solver ifc --split dev --source ifc_models --workers 4 --note '$N ifc' > $L/$TAG-ifc-dev.log 2>&1 &
$PY -m stoa.eval --solver pipeline --split hard2 --workers 6 --note '$N' > $L/$TAG-hard2.log 2>&1
$PY -m stoa.eval --solver pipeline --split hard --workers 6 --note '$N' > $L/$TAG-hard.log 2>&1
$PY -m stoa.eval --solver pipeline --split dev --workers 8 --note '$N' > $L/$TAG-dev.log 2>&1
wait; echo DONE > $L/$TAG-gate.done" > "$L/$TAG-gate-driver.log" 2>&1 < /dev/null &
echo "gate $TAG on $C started in $WT"
