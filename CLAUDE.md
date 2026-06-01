# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Two independent components communicate over a TCP socket on `localhost:9877`:

```
Claude Code / MCP client
        ↓  MCP protocol
  MCP_Server/server.py       ← Python 3, FastMCP, runs via `uvx ableton-mcp`
        ↓  JSON over TCP (port 9877)
  AbletonMCP_Remote_Script/  ← Python 2.7 (Live 10) or 3.x (Live 11/12), runs inside Ableton
```

**MCP Server** (`MCP_Server/server.py`): FastMCP-based server. Maintains a persistent TCP connection to Ableton via `AbletonConnection`. At startup (lifespan), it connects and validates with `get_session_info`. All MCP tools call `send_command()` which serializes JSON, sends it, and reads the response via `receive_full_response()` (chunked JSON until parseable).

**Remote Script** (`AbletonMCP_Remote_Script/__init__.py`): Ableton MIDI Remote Script. This is where the Live 10 / Live 11+ split matters:

- **Live 11/12** (original): background thread handles socket accept/read loop, calls Live API via `schedule_message()` + queue for write commands.
- **Live 10** (`live10-compatibility` branch): no background threads — all socket I/O and Live API calls happen in `update_display()`, called by Live every ~100ms on the main thread. This sidesteps Python 2.7's GIL starvation that prevents background threads from running reliably inside Live 10's embedded runtime.

### Communication protocol

Commands are JSON objects: `{"type": "command_name", "params": {...}}`.  
Responses: `{"status": "success"|"error", "result": {...}}` or `{"status": "error", "message": "..."}`.  
No framing/length prefix — the receiver accumulates chunks until `json.loads()` succeeds.

## Commands

```bash
# Run the MCP server (requires Ableton running with Remote Script active)
uvx ableton-mcp

# Install dependencies for development
uv sync

# Run the integration test suite (requires Ableton on localhost:9877)
python3 test_ableton_mcp.py

# Kill any zombie MCP server before running tests
kill $(lsof -ti :9877 -s TCP:ESTABLISHED | grep -v $(lsof -ti :9877 -s TCP:LISTEN)) 2>/dev/null
python3 test_ableton_mcp.py
```

## Remote Script installation

Copy `AbletonMCP_Remote_Script/` to Ableton's User Remote Scripts directory:
- macOS: `~/Music/Ableton/User Library/Remote Scripts/AbletonMCP/`

Then in Ableton → Preferences → MIDI: set a Control Surface slot to `AbletonMCP`.

## Live 10 constraints

- `update_display()` is called every ~100ms — all socket operations must be non-blocking (`select()` with `timeout=0`).
- Only one client connection at a time. New connection is only accepted once the current client disconnects.
- Session cache (`self._session_cache`) is reset to `{}` after any write command and rebuilt on the next `update_display()` tick. This ensures `get_session_info` always reflects current state.
- File must declare `# -*- coding: utf-8 -*-` — Live 10's Python 2.7 crashes on any non-ASCII byte (including em dashes in comments) without it.
