# AbletonMCP — Project Guide

## Architecture

Two-component system communicating via TCP JSON on port 9877:

1. **MCP Server** (`MCP_Server/`) — Python async server using FastMCP. Modular tool architecture with 8 modules under `MCP_Server/tools/`.
2. **Ableton Remote Script** (`AbletonMCP_Remote_Script/__init__.py`) — Runs inside Ableton's Python runtime (Python 2.7+). Socket server that receives commands and executes them via Ableton's Live API.

## Key Constraints

- **Remote Script must stay Python 2.7 compatible**: no f-strings, use `.format()`, `from __future__` imports, `Queue`/`queue` dual import.
- **Remote Script is a single file**: Ableton loads `__init__.py` from the Remote Scripts folder. Cannot be split into multiple files.
- **State-modifying commands must use `schedule_message`**: Ableton's API is not thread-safe. Write commands go through `self.schedule_message(0, callback)` with a Queue for response passing. Read-only commands (get_*) can execute directly on the worker thread.
- **MCP Server tools are async**: All tools use `async def` and `await conn.send_command(...)`.

## Adding New Tools

1. Add the command handler in `AbletonMCP_Remote_Script/__init__.py`:
   - Add handler method (e.g., `_my_new_command`)
   - Register in `self._command_handlers` dict
   - Add to `self._read_commands` or `self._write_commands` set
2. Add the MCP tool in the appropriate `MCP_Server/tools/*_tools.py` module
3. Follow the `register(mcp, get_connection, cache)` pattern

## Tool Module Pattern

```python
def register(mcp: FastMCP, get_connection, cache):
    @mcp.tool()
    async def my_tool(param: int) -> str:
        conn = await get_connection()
        result = await conn.send_command("command_name", {"param": param})
        cache.invalidate_all()  # only for state-modifying commands
        return json.dumps(result, indent=2)
```

## Performance Notes

- Response cache TTLs: session data 2s, browser 60s, playback position 0.5s
- `get_full_session_state` returns everything in 1 call — always prefer this over N+1 queries
- Browser operations are slow in Ableton — aggressive caching is critical
- No `time.sleep()` in the MCP server — all delays removed in favor of async

## Testing

- AI tools (music theory) can be tested without Ableton: pure computation
- Server import test: `python -c "from MCP_Server.server import mcp; print(len(mcp._tool_manager._tools))"`
- Full test requires Ableton running with the Remote Script loaded

## Installation

Run `./install.sh` to install both components, or manually:
- MCP Server: `uv pip install -e .`
- Remote Script: copy `AbletonMCP_Remote_Script/__init__.py` to Ableton's `User Remote Scripts/AbletonMCP/`
