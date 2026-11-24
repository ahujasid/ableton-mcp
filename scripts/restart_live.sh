#!/usr/bin/env bash
# Restart Ableton Live so it loads a freshly deployed Remote Script.
#
# Only for unattended development: refuses unless the open set is an EMPTY set
# (scripts/live_harness.py --guard), because the restart is a hard kill
# (ableton-kill) and anything unsaved is lost. Live then starts on its default
# template, which is an empty set. Waits for the Remote Script's port 9877 and
# prints the loaded script version.
#
# A hard kill leaves Live's crash marker (Preferences/CrashDetection.cfg =
# "Running"), and the next start then stops on "Live unexpectedly quit ...
# recover your work?", which nothing can answer unattended. After a guarded
# kill the marker is moved to ~/programs/ableton-mcp-crash-markers/ so Live
# starts straight on its default (empty) template.
#
# usage: scripts/restart_live.sh [--unresponsive-ok]
#   --unresponsive-ok  kill a Live whose Remote Script isn't answering (so the
#                      set can't be checked). Only after checking by other means
#                      (e.g. Live's log) that it holds nothing but an empty set.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PORT=9877
LOG="$HOME/.wine-ableton/drive_c/users/jeremy/AppData/Roaming/Ableton"
MARKERS="$HOME/programs/ableton-mcp-crash-markers"

listening() { ss -ltn "sport = :$PORT" | grep -q LISTEN; }
live_running() { pgrep -f 'Ableton Live 12.*\.exe' >/dev/null; }

answering=no
if listening; then
  echo "== guard: is the open set empty?"
  set +e
  timeout 90 python3 "$REPO/scripts/live_harness.py" --guard > /tmp/claude/restart-guard.log 2>&1
  rc=$?
  set -e
  tail -3 /tmp/claude/restart-guard.log
  if [ $rc -eq 0 ]; then
    answering=yes
  elif [ $rc -eq 2 ]; then
    echo "REFUSING: the open set is not empty" >&2
    exit 2
  fi
fi
if [ $answering = yes ]; then
  :
elif live_running; then
  if [ "${1:-}" != "--unresponsive-ok" ]; then
    echo "REFUSING: Live is running but its Remote Script is not answering, so the open set" >&2
    echo "can't be checked. Pass --unresponsive-ok only if you know it holds an empty set." >&2
    exit 2
  fi
  echo "== Live is running but not answering; --unresponsive-ok given"
else
  echo "== Live is not running"
fi

echo "== killing Live"
ableton-kill || true
for _ in $(seq 1 20); do listening || break; sleep 0.5; done

mkdir -p "$MARKERS"
stamp=$(date +%Y%m%d-%H%M%S)
for prefs in "$LOG"/Live*/Preferences; do
  # CrashDetection.cfg says "Running"; CrashRecoveryInfo.cfg lists what to recover.
  for f in CrashDetection.cfg CrashRecoveryInfo.cfg; do
    if [ -f "$prefs/$f" ]; then
      mv "$prefs/$f" "$MARKERS/$f.$(basename "$(dirname "$prefs")" | tr ' ' _).$stamp"
      echo "   moved $f aside (Live had only the empty set open)"
    fi
  done
done

echo "== launching Live"
setsid -f "$HOME/.local/bin/ableton-live" >/dev/null 2>&1 < /dev/null

for i in $(seq 1 240); do
  if listening; then echo "   port $PORT up after ${i}s"; break; fi
  sleep 1
done
listening || { echo "Live did not open port $PORT within 240 s" >&2; exit 1; }
sleep 5  # let the set finish loading before anyone writes

newest=$(find "$LOG" -name Log.txt -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
grep -o "script v[0-9.]*" "$newest" | tail -1
