# Running the MCP Server from Local Directory

When making changes to the MCP server code, you need to ensure the local version runs instead of the cached package.

## Steps to Run Local MCP Server

### 1. Clear UV cache

```bash
uv cache clean ableton-mcp
```

### 2. Update MCP configuration

**Windows:** `%APPDATA%\Code\User\mcp.json`  
**macOS:** `~/Library/Application Support/Code/User/mcp.json`  
**Linux:** `~/.config/Code/User/mcp.json`

```json
{
  "servers": {
    "AbletonMCP": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ableton-mcp", "python", "-m", "MCP_Server.server"],
      "type": "stdio"
    }
  }
}
```

This uses `uv run` to execute the server directly from the local directory.

### 3. After making code changes

Copy Remote Script to Ableton's Remote Scripts folder:

**Windows (PowerShell):**
```powershell
Copy-Item ".\AbletonMCP_Remote_Script\__init__.py" -Destination "$env:USERPROFILE\Documents\Ableton\User Library\Remote Scripts\AbletonMCP\__init__.py" -Force
```

**macOS/Linux (bash):**
```bash
cp ./AbletonMCP_Remote_Script/__init__.py ~/Music/Ableton/User\ Library/Remote\ Scripts/AbletonMCP/__init__.py
```

Then reload:
- **Option A:** Restart Ableton Live
- **Option B (faster):** Toggle Control Surface off and on in Ableton Preferences → Link/Tempo/MIDI (set to "None", then back to "AbletonMCP")
- Reload VS Code window (`Ctrl+Shift+P` / `Cmd+Shift+P` → "Developer: Reload Window")

### 4. Clear Python cache if needed

**Windows (PowerShell):**
```powershell
Get-ChildItem -Path "." -Include __pycache__,*.pyc -Recurse -Force | Remove-Item -Force -Recurse
```

**macOS/Linux (bash):**
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find . -name "*.pyc" -delete
```

## Why This Works

- `uvx ableton-mcp` runs the cached/installed package
- `uv run --directory <path>` runs from the specified local directory
- The `--directory` flag ensures dependencies are resolved from that location
- Clearing the UV cache prevents old versions from being used
