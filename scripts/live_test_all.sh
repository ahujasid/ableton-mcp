#!/usr/bin/env bash
# Run every live test in order against an EMPTY Live set and summarise.
# Each test refuses a non-empty set on its own and cleans up after itself.
# usage: scripts/live_test_all.sh
set -u
cd "$(dirname "$0")/.."
mkdir -p /tmp/claude
status=0
for t in live_test.py live_test_mixer.py live_test_devices.py live_test_transport.py; do
  log="/tmp/claude/ableton-${t%.py}.log"
  echo "##### $t (log: $log)"
  timeout 600 python3 "scripts/$t" > "$log" 2>&1
  rc=$?
  grep -E "^\s+FAIL|passed, .* failed|REFUSING|stale" "$log"
  [ $rc -eq 0 ] || status=1
  [ $rc -eq 2 ] && { echo "stopped: the set is not empty or the script is stale"; exit 2; }
done
exit $status
