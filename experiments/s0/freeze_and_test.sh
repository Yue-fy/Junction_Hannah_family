#!/usr/bin/env bash
# S0 (D13): freeze a night commit in its own detached worktree and run the milestone test there, detached from
# the calling session, so `night` stays open for merges while the test runs. From the S0 worktree root:
#   bash experiments/s0/freeze_and_test.sh <name> "S0 sealed test 2" [commit]
# -> worktree /data/User/fangy4/projects/junction-wt/S0-<name>, driver log $JUNCTION_SHARED/logs/S0/<name>-driver.log
# When the driver log ends with "done", remove it: git worktree remove /data/User/fangy4/projects/junction-wt/S0-<name>
set -eu
NAME=${1:?name, e.g. test2}
TAG=${2:-S0 sealed $NAME}
COMMIT=$(git rev-parse --short "${3:-HEAD}")
WT=/data/User/fangy4/projects/junction-wt/S0-$NAME
LOG=$JUNCTION_SHARED/logs/S0/$NAME-driver.log
curl -s 127.0.0.1:8001/v1/models | grep -q '"cc-v2"' || { echo ":8001 does not serve cc-v2 (LoRA); fix the server first" >&2; exit 1; }
git worktree add --detach "$WT" "$COMMIT"
cd "$WT"
setsid nohup bash experiments/s0/run_test.sh "$TAG" > "$LOG" 2>&1 < /dev/null &
echo "started $TAG on $COMMIT in $WT; log $LOG"
