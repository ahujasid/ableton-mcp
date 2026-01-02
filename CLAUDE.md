# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AbletonMCP connects Ableton Live to Claude AI through the Model Context Protocol (MCP). It enables AI-assisted music production by allowing Claude to control Ableton Live sessions directly.

## Architecture

The system has two independent components that communicate via TCP socket:

1. **MCP Server** (`MCP_Server/server.py`): Python server implementing MCP protocol using FastMCP. Connects to Claude Desktop/Cursor and forwards commands to Ableton. Runs as a standalone process via `uvx ableton-mcp`.

2. **Ableton Remote Script** (`AbletonMCP_Remote_Script/__init__.py`): MIDI Remote Script loaded into Ableton Live. Creates a TCP socket server on port 9877 to receive and execute commands within Ableton's Python runtime.

**Communication Flow:**
```
Claude AI <-> MCP Server <-> TCP Socket (port 9877) <-> Ableton Remote Script <-> Ableton Live
```

Commands are JSON objects with `type` and `params` fields. Responses contain `status` and `result` or `message`. State-modifying commands (create_midi_track, add_notes_to_clip, etc.) are scheduled on Ableton's main thread via `schedule_message`.

## Development Commands

```bash
# Install dependencies
uv sync

# Run MCP server locally (requires Ableton with Remote Script running)
uv run ableton-mcp

# Install via uvx (recommended for end users)
uvx ableton-mcp
```

## Installing the Remote Script

The Remote Script must be installed into Ableton's MIDI Remote Scripts folder with the name `AbletonMCP`:

```bash
# macOS
cp -r AbletonMCP_Remote_Script "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/AbletonMCP"

# Or use the install script
python install.py
```

After installation:
1. Restart Ableton Live (or go to Preferences → Link/Tempo/MIDI)
2. Select "AbletonMCP" as the Control Surface
3. No Input/Output MIDI ports are required

**Important**: The folder must be named `AbletonMCP` (not `AbletonMCP_Remote_Script`) for Ableton to recognize it correctly.

## Development Workflow

When modifying the Remote Script during development:

1. Make changes to `AbletonMCP_Remote_Script/__init__.py`
2. Run linter: `uv run ruff check AbletonMCP_Remote_Script/__init__.py`
3. Reinstall: `cp -r AbletonMCP_Remote_Script "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/AbletonMCP"`
4. **Wait for user confirmation** that Ableton has reloaded the control surface before testing MCP commands

The Remote Script reloads automatically when the file changes, but the reload causes a brief connection reset. Always wait for the user to confirm the reload is complete before attempting any MCP operations.

## Key Constraints

- The Remote Script must support both Python 2 (older Ableton versions) and Python 3. Note the compatibility imports at the top of `__init__.py`.
- All Ableton state modifications must go through `schedule_message(0, callback)` to run on Ableton's main thread.
- The socket server uses a 15-second timeout for long operations and validates connections with `get_session_info`.
- Browser item loading uses URIs in a specific format (e.g., `query:Synths#Instrument%20Rack:Bass:FileId_5116`).

## Documentation Resources

- **Ableton Live 12 Manual**: Use Context7 library `/websites/ableton_en_live-manual_12` for official Ableton documentation
- **Live Object Model (LOM)**: Use Context7 library `/websites/cycling74_apiref_lom` for the Python API reference when building Remote Scripts
- **Official LOM Docs**: For specific function lookups, use WebFetch with `https://docs.cycling74.com/apiref/lom/{class}/#{function}` (e.g., `https://docs.cycling74.com/apiref/lom/song/#set_or_delete_cue` for Song.set_or_delete_cue)
