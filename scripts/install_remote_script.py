#!/usr/bin/env python3
"""Install the AbletonMCP Remote Script to Ableton Live's User Library."""

import shutil
import sys
from pathlib import Path

# ANSI color codes for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def get_ableton_remote_scripts_dir() -> Path:
    """Get the Ableton Live Remote Scripts directory for the current platform."""
    if sys.platform == "darwin":
        # macOS: ~/Music/Ableton/User Library/Remote Scripts/
        return Path.home() / "Music" / "Ableton" / "User Library" / "Remote Scripts"
    elif sys.platform == "win32":
        # Windows: ~\Documents\Ableton\User Library\Remote Scripts\
        return Path.home() / "Documents" / "Ableton" / "User Library" / "Remote Scripts"
    else:
        print(f"{YELLOW}Warning: Unsupported platform '{sys.platform}'.{RESET}")
        print("Please manually copy the AbletonMCP_Remote_Script folder to your")
        print("Ableton Live User Library/Remote Scripts directory.")
        sys.exit(1)


def get_source_dir() -> Path:
    """Get the source AbletonMCP_Remote_Script directory."""
    # Try relative to this script first (installed package)
    script_dir = Path(__file__).parent.parent
    source = script_dir / "AbletonMCP_Remote_Script"
    if source.exists():
        return source

    # Try current working directory (development)
    cwd_source = Path.cwd() / "AbletonMCP_Remote_Script"
    if cwd_source.exists():
        return cwd_source

    print(f"{YELLOW}Error: Could not find AbletonMCP_Remote_Script directory.{RESET}")
    print("Please run this command from the ableton-mcp project root.")
    sys.exit(1)


def install_remote_script() -> None:
    """Copy the Remote Script to Ableton's User Library."""
    source_dir = get_source_dir()
    target_base = get_ableton_remote_scripts_dir()
    target_dir = target_base / "AbletonMCP"

    print(f"{BOLD}AbletonMCP Remote Script Installer{RESET}\n")

    # Create User Library/Remote Scripts if it doesn't exist
    if not target_base.exists():
        print(f"Creating directory: {target_base}")
        target_base.mkdir(parents=True, exist_ok=True)

    # Check if already installed
    if target_dir.exists():
        print(f"{YELLOW}Existing installation found at:{RESET}")
        print(f"  {target_dir}\n")
        print("Updating to latest version...")
        shutil.rmtree(target_dir)
    else:
        print("Installing AbletonMCP Remote Script...")

    # Copy the Remote Script
    shutil.copytree(source_dir, target_dir)

    print(f"\n{GREEN}Successfully installed to:{RESET}")
    print(f"  {target_dir}\n")

    # Print setup instructions
    print(f"{BOLD}Next steps to complete setup in Ableton Live:{RESET}\n")
    print(f"  1. {BLUE}Restart Ableton Live{RESET} if it's currently running\n")
    print(f"  2. Open {BLUE}Preferences{RESET} (Cmd+, on macOS, Ctrl+, on Windows)\n")
    print(f"  3. Go to the {BLUE}Link, Tempo & MIDI{RESET} tab\n")
    print(f"  4. Under {BLUE}Control Surface{RESET}, select an empty slot and choose:")
    print(f"     {GREEN}AbletonMCP{RESET}\n")
    print(f"  5. Leave Input and Output set to {BLUE}None{RESET}\n")
    print("  6. Close Preferences - the Remote Script is now active!\n")
    print(f"{BOLD}Verify the connection:{RESET}")
    print(f"  Run: {BLUE}uv run ableton-mcp{RESET}")
    print("  You should see a successful connection message.\n")


def main() -> None:
    """Entry point for the install command."""
    try:
        install_remote_script()
    except PermissionError as e:
        print(f"{YELLOW}Permission denied: {e}{RESET}")
        print("Try running with appropriate permissions.")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"{YELLOW}File not found: {e}{RESET}")
        print("Please ensure the AbletonMCP_Remote_Script directory exists.")
        sys.exit(1)
    except OSError as e:
        print(f"{YELLOW}File system error: {e}{RESET}")
        print("Check disk space and file system permissions.")
        sys.exit(1)
    except Exception as e:
        print(f"{YELLOW}Installation failed: {e}{RESET}")
        print("Please report this issue with the full error message.")
        sys.exit(1)


if __name__ == "__main__":
    main()
