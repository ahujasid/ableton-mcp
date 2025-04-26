#!/bin/zsh

# Simple script to copy the development remote script to the Ableton App Bundle.
# !!! WARNING !!!
# This targets the script folder INSIDE the Ableton .app bundle.
# This is NOT the standard location and has drawbacks:
#   1. Requires sudo privileges to run.
#   2. The script WILL BE OVERWRITTEN when Ableton Live is updated.
# We are using this location primarily because it matches the original setup video
# and has proven more reliable than the User Library path during testing.
# Consider switching to the User Library path for long-term use if possible:
# User Library Path: $HOME/Library/Preferences/Ableton/Live X.Y.Z/User Remote Scripts/AbletonMCP

# --- Configuration ---
# Source file in this repository
# NOTE: Path is relative to the *project root*, assuming the script is run from there.
SOURCE_SCRIPT="AbletonMCP_Remote_Script/__init__.py"

# Destination directory inside the Ableton App Bundle
# Default Ableton path (change if necessary or use ABLETON_APP_PATH env var)
DEFAULT_ABLETON_APP_PATH="/Applications/Ableton Live 12 Trial.app"

# Use environment variable if set, otherwise use default
DEST_APP_BUNDLE="${ABLETON_APP_PATH:-$DEFAULT_ABLETON_APP_PATH}"

# Construct the final destination directory
DEST_DIR="$DEST_APP_BUNDLE/Contents/App-Resources/MIDI Remote Scripts/AbletonMCP"

# --- Script Logic ---

echo "Using Ableton App Path: $DEST_APP_BUNDLE"
echo "Target MIDI Script Directory: $DEST_DIR"
echo "Attempting to copy remote script to App Bundle (requires sudo)..."

# Check if source file exists
if [ ! -f "$SOURCE_SCRIPT" ]; then
  echo "Error: Source script not found at '$SOURCE_SCRIPT'"
  echo "Please run this script from the root of the ableton-mcp repository."
  exit 1
fi

# Check if Ableton App Bundle exists
if [ ! -d "$DEST_APP_BUNDLE" ]; then
  echo "Error: Ableton application bundle not found at '$DEST_APP_BUNDLE'"
  echo "Hint: You can set the ABLETON_APP_PATH environment variable."
  echo "Example: ABLETON_APP_PATH=\"/Applications/Ableton Live 11 Suite.app\" ./update_remote_script_macos.sh"
  exit 1
fi

# Check if destination directory exists, create if not (using sudo)
if [ ! -d "$DEST_DIR" ]; then
  echo "Destination directory not found. Creating '$DEST_DIR' (using sudo)..."
  sudo mkdir -p "$DEST_DIR"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to create destination directory. Check sudo permissions."
    exit 1
  fi
else
  echo "Destination directory found: '$DEST_DIR'"
fi

# Perform the copy (using sudo)
echo "Copying '$SOURCE_SCRIPT' to '$DEST_DIR/' (using sudo)"
sudo cp "$SOURCE_SCRIPT" "$DEST_DIR/"

# Check if copy was successful
if [ $? -eq 0 ]; then
  # Set ownership, just in case (might not be strictly necessary but good practice)
  echo "Setting ownership (using sudo)..."
  sudo chown -R root:wheel "$DEST_DIR"
  
  echo "Success! Remote script updated in App Bundle."
  echo "Please RESTART Ableton Live for the changes to take effect."
else
  echo "Error: Failed to copy the script. Check sudo permissions or paths."
  exit 1
fi

exit 0 