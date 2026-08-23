#!/bin/zsh
# copy the remote script into Live's user library and hot-reload the handlers.
# only handlers.py reloads live; a change to __init__.py still needs a Live restart.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${ABLETON_REMOTE_SCRIPTS:-$HOME/Music/Ableton/User Library/Remote Scripts}/AbletonMCP"
mkdir -p "$DEST"
changed_init=0
if ! diff -q AbletonMCP_Remote_Script/__init__.py "$DEST/__init__.py" >/dev/null 2>&1; then changed_init=1; fi
cp AbletonMCP_Remote_Script/__init__.py AbletonMCP_Remote_Script/handlers.py "$DEST/"
echo "installed to $DEST"
if [ "$changed_init" = 1 ]; then
  echo "__init__.py changed: restart Live to pick it up"
fi
if nc -z -w1 localhost 9877 2>/dev/null; then
  scripts/abl.py reload | jq -c '{status, version: .result.version, commands: (.result.commands|length), message}'
else
  echo "Live not reachable on :9877 — it will load the new script on next launch"
fi
