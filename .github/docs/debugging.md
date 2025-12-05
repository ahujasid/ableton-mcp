# Debugging

How to troubleshoot issues with the Ableton MCP.

## Checking Ableton's Log File

Check Ableton's log file for Remote Script output:

**Windows (PowerShell):**
```powershell
Get-Content "$env:APPDATA\Ableton\Live *\Preferences\Log.txt" -Tail 50 | Select-String "AbletonMCP"
```

**macOS (bash):**
```bash
tail -50 ~/Library/Preferences/Ableton/Live*/Log.txt | grep AbletonMCP
```

**Linux (bash):**
```bash
tail -50 ~/.ableton/Live*/Preferences/Log.txt | grep AbletonMCP
```

## VS Code MCP Tool Cache

VS Code caches MCP tool configurations in multiple locations. If new tools aren't appearing or old tools persist:

### Clear Copilot's MCP Cache

**Windows (PowerShell):**
```powershell
Remove-Item "$env:APPDATA\Code\User\globalStorage\github.copilot\mcp.json" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:APPDATA\Code\User\globalStorage\github.copilot-chat\toolEmbeddingsCache.bin" -Force -ErrorAction SilentlyContinue
```

**macOS (bash):**
```bash
rm -f ~/Library/Application\ Support/Code/User/globalStorage/github.copilot/mcp.json
rm -f ~/Library/Application\ Support/Code/User/globalStorage/github.copilot-chat/toolEmbeddingsCache.bin
```

**Linux (bash):**
```bash
rm -f ~/.config/Code/User/globalStorage/github.copilot/mcp.json
rm -f ~/.config/Code/User/globalStorage/github.copilot-chat/toolEmbeddingsCache.bin
```

Then fully quit VS Code (check Task Manager/Activity Monitor) and restart.

## Adding Debug Output

Use `self.log_message("message")` in the Remote Script to add debug output:

```python
def _my_handler(self, command):
    self.log_message(f"AbletonMCP: Processing command with params: {command}")
    try:
        # ... implementation
        self.log_message("AbletonMCP: Command succeeded")
        return {"status": "success"}
    except Exception as e:
        self.log_message(f"AbletonMCP: Error - {str(e)}")
        return {"status": "error", "message": str(e)}
```

## Common Issues

| Issue | Solution |
|-------|----------|
| Tool not appearing | Ensure `@mcp.tool()` decorator is present |
| Changes not taking effect | Toggle Control Surface off/on in Ableton Preferences |
| Old code running | Clear UV cache: `uv cache clean ableton-mcp` |
| Socket connection failed | Restart both Ableton and VS Code |
| Effect loads to track not chain | Use `move_device()` after `load_item()` |
| Can't create chains | Use `insert_chain()` not `chains.append()` |

## VS Code Reload

After making MCP server changes, reload VS Code:
- `Ctrl+Shift+P` / `Cmd+Shift+P` → "Developer: Reload Window"
