#!/usr/bin/env bash
# AbletonMCP Installer
# Installs both the MCP Server and the Ableton Remote Script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE_SCRIPT_SRC="$SCRIPT_DIR/AbletonMCP_Remote_Script/__init__.py"

echo "=== AbletonMCP Installer ==="
echo ""

# --- Step 1: Install the MCP Server ---
echo "[1/2] Installing MCP Server..."
if command -v uv &>/dev/null; then
    uv pip install --system -e "$SCRIPT_DIR" 2>/dev/null || uv pip install -e "$SCRIPT_DIR"
    echo "  MCP Server installed via uv."
elif command -v pip3 &>/dev/null; then
    pip3 install -e "$SCRIPT_DIR"
    echo "  MCP Server installed via pip3."
else
    echo "  ERROR: Neither uv nor pip3 found. Install uv first: brew install uv"
    exit 1
fi

# --- Step 2: Install the Remote Script into Ableton ---
echo ""
echo "[2/2] Installing Ableton Remote Script..."

# Find all Ableton User Remote Scripts directories
DIRS=()
while IFS= read -r -d '' dir; do
    DIRS+=("$dir")
done < <(find "$HOME/Library/Preferences/Ableton" -type d -name "User Remote Scripts" -print0 2>/dev/null)

# Also check Application bundle
while IFS= read -r -d '' dir; do
    DIRS+=("$dir")
done < <(find /Applications -maxdepth 2 -type d -name "MIDI Remote Scripts" -path "*/Ableton*" -print0 2>/dev/null)

if [ ${#DIRS[@]} -eq 0 ]; then
    echo "  No Ableton installation found."
    echo "  Please manually copy AbletonMCP_Remote_Script/__init__.py"
    echo "  to your Ableton MIDI Remote Scripts/AbletonMCP/ folder."
    exit 1
fi

echo "  Found Ableton installations:"
for i in "${!DIRS[@]}"; do
    echo "    [$((i+1))] ${DIRS[$i]}"
done

# If only one, use it. Otherwise ask.
if [ ${#DIRS[@]} -eq 1 ]; then
    CHOSEN="${DIRS[0]}"
    echo ""
    echo "  Using: $CHOSEN"
else
    echo ""
    read -rp "  Which one? [1-${#DIRS[@]}, or 'a' for all]: " choice
    if [ "$choice" = "a" ]; then
        for dir in "${DIRS[@]}"; do
            TARGET="$dir/AbletonMCP"
            mkdir -p "$TARGET"
            cp "$REMOTE_SCRIPT_SRC" "$TARGET/__init__.py"
            echo "  Installed to: $TARGET"
        done
        echo ""
        echo "=== Done! ==="
        echo "Restart Ableton and select 'AbletonMCP' in Settings > Link, Tempo & MIDI > Control Surface."
        exit 0
    else
        idx=$((choice - 1))
        CHOSEN="${DIRS[$idx]}"
    fi
fi

TARGET="$CHOSEN/AbletonMCP"
mkdir -p "$TARGET"
cp "$REMOTE_SCRIPT_SRC" "$TARGET/__init__.py"
echo "  Installed to: $TARGET"

echo ""
echo "=== Done! ==="
echo ""
echo "Next steps:"
echo "  1. Restart Ableton Live"
echo "  2. Go to Settings > Link, Tempo & MIDI"
echo "  3. Set Control Surface to 'AbletonMCP'"
echo "  4. Set Input and Output to 'None'"
echo ""
echo "MCP client config (Claude Desktop / Cursor):"
echo '  { "mcpServers": { "AbletonMCP": { "command": "ableton-mcp" } } }'
