#!/bin/bash
# Deploy AbletonMCP handler changes and hot-reload

set -e

SRC="$(dirname "$0")/AbletonMCP_Remote_Script"
APP_DEST="/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/AbletonMCP"
USER_DEST="$HOME/Library/Preferences/Ableton/Live 12.3.5/User Remote Scripts/AbletonMCP"
CLI="$(dirname "$0")/ableton-cli.py"

echo "Syncing to App-Resources..."
rsync -a --delete "$SRC/" "$APP_DEST/"

echo "Syncing to User Remote Scripts..."
rsync -a --delete "$SRC/" "$USER_DEST/"

# Clear __pycache__
find "$APP_DEST" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find "$USER_DEST" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
echo "Cleared __pycache__."

# Hot-reload via socket
echo "Sending reload_handlers..."
python3 "$CLI" reload_handlers

echo "Done."
