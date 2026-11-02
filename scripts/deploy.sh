#!/usr/bin/env bash
# Install this checkout as the live ableton-mcp: the MCP server as an editable
# uv tool (edits take effect when the server restarts) and the Remote Script
# into Live's User Library (takes effect when Live restarts).
#
# Refuses unless the two Remote Script copies match and the unit tests pass.
# The installer backs the previous Remote Script up to __init__.py.bak.
# Back to upstream: uv tool install --force ableton-mcp==1.4.5 && ableton-mcp-install-script --target ...
#
# usage: scripts/deploy.sh            (ABLETON_REMOTE_SCRIPTS overrides the target dir)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ABLETON_REMOTE_SCRIPTS:-$HOME/Documents/Ableton/User Library/Remote Scripts}"
cd "$REPO"

if ! cmp -s AbletonMCP_Remote_Script/__init__.py MCP_Server/bundled_ableton_remote_script/AbletonMCP_init.py; then
    echo "Remote Script copies differ. Run: cp AbletonMCP_Remote_Script/__init__.py MCP_Server/bundled_ableton_remote_script/AbletonMCP_init.py" >&2
    exit 1
fi
python3 -m py_compile AbletonMCP_Remote_Script/__init__.py

echo "== unit tests"
uv run --frozen --with pytest pytest -q

echo "== MCP server (editable uv tool from $REPO, $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD))"
uv tool install --quiet --editable --force "$REPO"

echo "== Remote Script -> $TARGET/AbletonMCP"
ableton-mcp-install-script --target "$TARGET"
# Live's embedded Python kept running a stale __pycache__/*.pyc after the source changed
# (2026-11-01: 1.8.0 source, 1.7.1 bytecode loaded). Drop it so Live compiles the new file.
if [ -d "$TARGET/AbletonMCP/__pycache__" ]; then
  rm -rf "$TARGET/AbletonMCP/__pycache__"
  echo "   removed stale __pycache__"
fi

ver=$(sed -n 's/^SCRIPT_VERSION = "\(.*\)"/\1/p' AbletonMCP_Remote_Script/__init__.py)
cat <<EOF

Deployed Remote Script $ver. To load it:
  1. Live: restart it (Live reads Remote Scripts only at startup), open an EMPTY set for live tests.
  2. Claude Code: /mcp -> ableton -> Reconnect (or restart the session) to pick up new tools.
  3. Check: get_remote_script_info shows script_version $ver; then python3 scripts/live_test.py
EOF
