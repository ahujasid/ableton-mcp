# Ableton MCP → CLI Conversion Plan

## Current Architecture

```
Claude AI → MCP Server (FastMCP/stdio) → TCP Socket (:9877) → Ableton Remote Script → Ableton Live
```

The MCP server is a thin wrapper: each tool calls `ableton.send_command("command_name", params)` over a TCP socket to the Ableton Remote Script. There are ~40 tools across 10 modules (session, tracks, clips, mixer, devices, browser, scenes, arrangement, audio, midi).

---

## Goal

Create a CLI that lets users (and AI agents) call Ableton commands directly from the terminal:

```bash
# Direct tool calls
ableton-cli call get_session_info
ableton-cli call set_tempo '{"tempo": 120}'
ableton-cli call create_midi_track '{"index": -1}'

# Discovery
ableton-cli list                          # all tools
ableton-cli info set_tempo                # tool schema/help
ableton-cli grep "track"                  # search tools

# Interactive
ableton-cli chat                          # LLM-powered chat mode
```

---

## Approach: Two-Layer Architecture

### Layer 1 — Direct CLI (Click + AbletonConnection)

Build a Python CLI using Click that talks directly to Ableton's TCP socket. This reuses the existing `AbletonConnection` class and bypasses MCP protocol overhead entirely.

**Why this is the right core:**
- All 40 MCP tools are thin wrappers around `send_command(type, params)`
- No need for MCP client/server ceremony for direct CLI use
- Single process, minimal latency
- Full reuse of `connection.py`

### Layer 2 — MCP-compatible mode (optional)

Also support `mcp_servers.json` config so the CLI can act as an MCP client to *any* MCP server (not just Ableton). This follows the philschmid/mcp-cli pattern.

---

## Implementation Plan

### Phase 1: Core CLI Framework

**New files:**
- `cli/__init__.py`
- `cli/main.py` — Click entry point with command groups
- `cli/commands/call.py` — Execute tools with JSON args
- `cli/commands/list.py` — List available tools
- `cli/commands/info.py` — Show tool schema/help
- `cli/commands/grep.py` — Search tools by pattern

**Tool Registry:**
Create a declarative tool registry that maps tool names to their command type, parameters schema, and description. This replaces the `@mcp.tool()` decorators with data that both the MCP server and CLI can consume.

```python
# cli/registry.py
TOOLS = {
    "get_session_info": {
        "command": "get_session_info",
        "description": "Get detailed information about the current Ableton session",
        "params": {}
    },
    "set_tempo": {
        "command": "set_tempo",
        "description": "Set the tempo of the Ableton session",
        "params": {
            "tempo": {"type": "float", "required": True, "help": "BPM value"}
        }
    },
    "create_midi_track": {
        "command": "create_midi_track",
        "description": "Create a new MIDI track",
        "params": {
            "index": {"type": "int", "required": False, "default": -1, "help": "Track index (-1 = end)"}
        }
    },
    # ... all 40+ tools
}
```

**Core commands:**

```bash
# List all tools (grouped by module)
ableton-cli list
ableton-cli list --json              # JSON output for scripting

# Tool info
ableton-cli info create_clip         # shows params, types, defaults

# Search
ableton-cli grep "clip"              # glob/regex search across tool names + descriptions

# Call a tool
ableton-cli call get_session_info
ableton-cli call set_tempo '{"tempo": 128}'
echo '{"tempo": 128}' | ableton-cli call set_tempo   # stdin support
ableton-cli call create_clip --track-index 0 --clip-index 0 --length 8  # named args alternative
```

**Connection management:**

```bash
ableton-cli --host localhost --port 9877 call get_session_info   # override defaults
```

### Phase 2: Shared Tool Registry (DRY refactor)

Refactor the existing MCP tools to consume the same registry so tool definitions are maintained in one place:

```
cli/registry.py          ← single source of truth for all tools
├── cli/commands/call.py  ← CLI reads registry, calls send_command()
└── MCP_Server/tools/*.py ← MCP tools read registry, register with FastMCP
```

This means adding/changing a tool only requires updating the registry — both the CLI and MCP server pick it up automatically.

### Phase 3: Interactive / Chat Mode

Add an interactive REPL and optional LLM-powered chat mode (inspired by chrishayuk/mcp-cli):

```bash
# Interactive REPL (no LLM)
ableton-cli interactive
> list
> call get_session_info
> call set_tempo {"tempo": 120}
> exit

# Chat mode (with LLM)
ableton-cli chat --provider anthropic --model claude-sonnet-4-20250514
> "Create a 4-bar drum pattern at 120 BPM"
  → Calls: set_tempo, create_midi_track, create_clip, add_notes_to_clip
```

**Chat mode dependencies:**
- `anthropic` SDK (or `openai` for OpenAI models)
- Tool definitions automatically derived from registry
- Streaming responses with tool call display

### Phase 4: MCP Client Mode (philschmid/mcp-cli compatibility)

Add support for connecting to arbitrary MCP servers via config:

```bash
# Use mcp_servers.json config
ableton-cli mcp --config ./mcp_servers.json list
ableton-cli mcp --config ./mcp_servers.json call ableton get_session_info
```

This uses the MCP Python SDK's `ClientSession` + `stdio_client` to spawn and connect to MCP servers defined in config, following the philschmid pattern but in Python.

---

## File Structure (final)

```
ableton-mcp/
├── cli/
│   ├── __init__.py
│   ├── main.py               # Click CLI entry point
│   ├── registry.py            # Shared tool definitions
│   ├── connection.py          # Reuses/wraps MCP_Server/connection.py
│   └── commands/
│       ├── __init__.py
│       ├── call.py            # Execute a tool
│       ├── list.py            # List tools
│       ├── info.py            # Tool schema/help
│       ├── grep.py            # Search tools
│       ├── interactive.py     # REPL mode
│       └── chat.py            # LLM chat mode
├── MCP_Server/                # Existing (refactored to use registry)
│   ├── server.py
│   ├── connection.py
│   ├── grid_notation.py
│   └── tools/...
├── AbletonMCP_Remote_Script/  # Unchanged
└── pyproject.toml             # Add CLI entry point + new deps
```

## pyproject.toml Changes

```toml
[project]
dependencies = [
    "mcp[cli]>=1.3.0",
    "click>=8.0",            # CLI framework
    "rich>=13.0",            # Pretty terminal output (tables, syntax highlighting)
]

[project.optional-dependencies]
chat = [
    "anthropic>=0.40.0",     # For chat mode with Claude
    "openai>=1.0",           # For chat mode with OpenAI
]

[project.scripts]
ableton-mcp-macwhite = "MCP_Server.server:main"   # Existing
ableton-cli = "cli.main:cli"                       # New CLI entry point
```

---

## Implementation Order

| Step | What | Why |
|------|------|-----|
| 1 | `cli/registry.py` — tool definitions | Foundation everything else builds on |
| 2 | `cli/main.py` + `cli/commands/list.py` | Verify registry works, see all tools |
| 3 | `cli/commands/call.py` | Core functionality — call any tool |
| 4 | `cli/commands/info.py` + `grep.py` | Discovery and search |
| 5 | Refactor `MCP_Server/tools/*.py` to use registry | DRY — single source of truth |
| 6 | `cli/commands/interactive.py` | REPL mode |
| 7 | `cli/commands/chat.py` | LLM-powered mode |
| 8 | MCP client mode | philschmid compatibility |

---

## Key Design Decisions

1. **Click over argparse** — Better UX, subcommands, help generation, parameter types
2. **Rich for output** — Pretty tables for `list`, syntax-highlighted JSON for `call`
3. **Direct socket over MCP client** — For the core CLI, talking directly to Ableton's TCP socket is simpler and faster than spawning an MCP server subprocess
4. **Shared registry** — Prevents tool definitions from drifting between MCP server and CLI
5. **JSON args + named flags** — Support both `'{"tempo": 120}'` and `--tempo 120` for ergonomics
6. **stdin support** — Enable piping: `echo '{"tempo":120}' | ableton-cli call set_tempo`
7. **`--json` flag** — Machine-readable output for all commands, enabling scripting and agent use
