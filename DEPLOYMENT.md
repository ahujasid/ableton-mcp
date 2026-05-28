# AbletonMCP Deployment Guide (Mac White)

## Architecture

```
production/ableton-mcp/
  AbletonMCP_Remote_Script/   # Source code (canonical)
    __init__.py               # Main control surface + socket server
    handlers/                 # Command handlers (devices, clips, mixer, etc.)
  MCP_Server/                 # MCP server (connects Claude to the socket)
    server.py                 # FastMCP server entry point
    connection.py             # Socket client for Ableton
    tools/                    # MCP tool definitions
```

## Deployment Paths

The Remote Script must be deployed to where Ableton actually loads it from.

### Primary (App Bundle) - Ableton loads from here:
```
/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/AbletonMCP/
```

### Secondary (User Prefs) - also works but app bundle takes priority:
```
~/Library/Preferences/Ableton/Live 12.3.5/User Remote Scripts/AbletonMCP/
```

**Important:** If both exist, Ableton uses the app bundle version. Check the log at
`~/Library/Preferences/Ableton/Live 12.3.5/Log.txt` to confirm which path is active.

## Deploying Updates

### Quick deploy (copy source to both targets):
```bash
# From repo root
SRC="production/ableton-mcp/AbletonMCP_Remote_Script"
APP="/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts/AbletonMCP"
USR="$HOME/Library/Preferences/Ableton/Live 12.3.5/User Remote Scripts/AbletonMCP"

cp -R "$SRC/"* "$APP/"
cp -R "$SRC/"* "$USR/"
```

### Reloading in Ableton

The `__init__.py` includes an `importlib.reload()` call that force-reloads all handler
submodules when the control surface initializes. This means:

- **Handler changes** (files in `handlers/`): Toggle the control surface off and back on
  in Preferences > Link, Tempo & MIDI. No full restart needed.
- **`__init__.py` changes**: Requires a full Ableton quit (Cmd+Q) and relaunch.
  Python caches the top-level module and toggling won't reload it.

### Why toggling sometimes doesn't work

Ableton's Python runtime caches imported modules in `sys.modules`. When you toggle
the control surface off/on, it calls `create_instance()` again which re-runs `__init__.py`,
but any `from . import handlers` uses the cached version. The `importlib.reload()` call
we added forces fresh imports of handler submodules, solving this for handler changes.

## MCP Server Setup

The MCP server is configured in `.mcp.json` at the repo root:
```json
{
  "mcpServers": {
    "ableton": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/macwhite/Music/MacWhite/production/ableton-mcp", "ableton-mcp-macwhite"]
    }
  }
}
```

The server connects to the Remote Script on `localhost:9877`.

## CLI Tool

For direct testing without the MCP layer:
```bash
uv run python3 production/ableton-mcp/ableton-cli.py get_session_info
uv run python3 production/ableton-mcp/ableton-cli.py get_chain_devices --params '{"track_index": 7, "device_index": 2}'
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Connection refused" | Remote Script not loaded | Enable AbletonMCP in Preferences > Link, Tempo & MIDI |
| "Unknown command: X" | Old handler code cached | Toggle control surface off/on (or full restart) |
| "Unknown command: X" after toggle | Change was in `__init__.py` | Full Ableton restart required |
| "Timeout waiting for response" | Ableton busy or socket dead | Restart both MCP server and Ableton |
| Log shows wrong path | App bundle vs user prefs conflict | Deploy to both; app bundle takes priority |

## Checking Logs

```bash
tail -f "$HOME/Library/Preferences/Ableton/Live 12.3.5/Log.txt" | grep AbletonMCP
```
