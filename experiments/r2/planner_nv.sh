#!/usr/bin/env bash
# Planner bake-off: W4's `agent` solver with the local 8B planner vs hosted Nemotron as planner (atomic tools stay local).
# Usage: experiments/r2/planner_nv.sh <split.jsonl> [more splits...]   Owner: R2.
set -uo pipefail
S=${JUNCTION_SHARED:-/home/fangy4/work/projects/junction-shared}
J=${JUNCTION_VENV:-/data/User/fangy4/envs/junction}/bin/python
cd "$(dirname "$0")/../.."
for sp in "$@"; do
  echo "[$(date +%H:%M)] local planner: $sp"
  "$J" -m stoa.eval --solver agent --solver-arg backend=local --split "$sp" --workers 4 \
    --note "R2 planner bake-off: agent, 8B planner (local)" 2>&1 | grep -v "it/s" | tail -12 &
  echo "[$(date +%H:%M)] nemotron planner: $sp"
  "$J" -m stoa.eval --solver agent --solver-arg backend=nvidia --split "$sp" --workers 2 \
    --note "R2 planner bake-off: agent, Nemotron 3.5 Super planner (nvidia)" 2>&1 | grep -v "it/s" | tail -12
  wait
done
echo "[$(date +%H:%M)] done"
