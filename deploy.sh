#!/bin/bash
# Deploy AbletonMCP handler changes and hot-reload

set -e

SRC="$(dirname "$0")/AbletonMCP_Remote_Script"
APP_DEST="/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/AbletonMCP"
CLI="$(dirname "$0")/ableton-cli.py"

echo "Syncing to App-Resources..."
rsync -a --delete "$SRC/" "$APP_DEST/"
find "$APP_DEST" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Sync to every installed Live version's User Remote Scripts (auto-covers updates)
for live_pref in "$HOME/Library/Preferences/Ableton/Live "*; do
    [ -d "$live_pref/User Remote Scripts" ] || continue
    user_dest="$live_pref/User Remote Scripts/AbletonMCP"
    echo "Syncing to $user_dest"
    rsync -a --delete "$SRC/" "$user_dest/"
    find "$user_dest" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
done
echo "Cleared __pycache__."

# Hot-reload via socket
echo "Sending reload_handlers..."
python3 "$CLI" reload_handlers

echo "Done."
