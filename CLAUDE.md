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

## Key Constraints

- The Remote Script must support both Python 2 (older Ableton versions) and Python 3. Note the compatibility imports at the top of `__init__.py`.
- All Ableton state modifications must go through `schedule_message(0, callback)` to run on Ableton's main thread.
- The socket server uses a 15-second timeout for long operations and validates connections with `get_session_info`.
- Browser item loading uses URIs in a specific format (e.g., `query:Synths#Instrument%20Rack:Bass:FileId_5116`).
