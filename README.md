# AbletonMCP - Ableton Live + AI via Model Context Protocol

Connect Ableton Live to AI assistants (Claude, Cursor, etc.) and control your DAW with natural language. Create tracks, generate chord progressions, design drum patterns, tweak parameters — all through conversation.

---

> **This is a fork.** The original project was created by [Siddharth Ahuja](https://x.com/sidahuj) ([original repo](https://github.com/ahujasid/ableton-mcp)). Huge thanks to Siddharth for building this and sharing it with the world — we need more people like him pushing the boundaries of what's possible when music meets AI. The kind of innovation that moves the industry forward starts with people willing to experiment in the open.
>
> I picked up this project to experiment, learn, and see how far it can go. If you want to contribute, you're welcome — whether it's fixing a bug, adding a new tool, improving the docs, or just sharing ideas. This is an open playground.

---

## What can it do?

Ask your AI assistant things like:

- *"Create an 80s synthwave track"*
- *"Generate a hip-hop drum pattern and a walking bassline in C minor"*
- *"What chords would work over this melody?"*
- *"Add reverb to track 2 and set the decay to 3 seconds"*
- *"Show me the full session state"*
- *"Duplicate track 1, mute the original, and set the tempo to 95 BPM"*

## Features

**67 tools** organized in 8 categories:

| Category | What you get |
|----------|-------------|
| **Session** | Full session snapshots in one call, track summaries |
| **Tracks** | Create, delete, duplicate, volume, pan, mute, solo, arm, sends |
| **Clips** | Create, delete, duplicate, add/get/remove MIDI notes, loop, quantize |
| **Scenes** | Create, delete, duplicate, fire scenes, stop all clips |
| **Devices** | Get/set parameters by name or index, toggle on/off, load instruments |
| **Transport** | Play, stop, undo, redo, metronome, loop, tempo, record, capture MIDI |
| **Browser** | Search instruments/effects by name, browse tree, load presets |
| **AI/Music Theory** | Chords (23 types), scales (15 types), progressions, drum patterns (10 styles), basslines, melodies, harmony suggestions |

The AI music theory tools work **without Ableton connected** — pure computation for generating MIDI data.

## Installation

### Prerequisites

- Ableton Live 10+
- Python 3.10+
- [uv](https://astral.sh/uv) (`brew install uv` on Mac)

### Quick install (macOS/Linux)

```bash
git clone https://github.com/Jeff909Dev/ableton-mcp.git
cd ableton-mcp
./install.sh
```

The script installs the MCP server and copies the Remote Script to Ableton automatically.

### Manual install

**1. MCP Server:**

```bash
git clone https://github.com/Jeff909Dev/ableton-mcp.git
cd ableton-mcp
uv pip install -e .
```

**2. Remote Script** — copy `AbletonMCP_Remote_Script/__init__.py` into a folder called `AbletonMCP` inside Ableton's Remote Scripts directory:

- **macOS:** `/Users/YOU/Library/Preferences/Ableton/Live XX/User Remote Scripts/AbletonMCP/`
- **Windows:** `C:\Users\YOU\AppData\Roaming\Ableton\Live XX\Preferences\User Remote Scripts\AbletonMCP\`

*(Replace XX with your Ableton version)*

**3. Enable in Ableton:** Settings > Link, Tempo & MIDI > Control Surface > select "AbletonMCP" > Input/Output: None

### Configure your AI client

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "AbletonMCP": {
      "command": "ableton-mcp"
    }
  }
}
```

**Cursor** — Settings > MCP > add command: `ableton-mcp`

### Updating

```bash
cd ableton-mcp
git pull
./install.sh
```

## How it works

```
AI Assistant  <──MCP──>  MCP Server (async Python)  <──TCP:9877──>  Ableton Remote Script
                         67 tools, response cache                    61 command handlers
                         AI music theory engine                      thread-safe execution
```

The MCP server talks to a Remote Script running inside Ableton via TCP. Read-only queries are cached (2s for session data, 60s for browser). No blocking delays — everything is async.

## Performance

Compared to the original:
- **Async connection** — no more `time.sleep()` blocking the pipeline
- **Session snapshots** — `get_full_session_state` returns everything in 1 call instead of N+1
- **Response caching** — repeated queries are instant
- **Batch commands** — multiple commands in a single TCP round-trip
- **Browser caching** — 60s cache for browser tree (first call may be slow, the rest are fast)

## Project structure

```
MCP_Server/
  server.py            # Entry point
  connection.py        # Async TCP connection
  cache.py             # Response cache
  tools/
    session_tools.py   # Session info
    track_tools.py     # Track management
    clip_tools.py      # Clip operations
    scene_tools.py     # Scene management
    device_tools.py    # Device parameters
    transport_tools.py # Transport controls
    browser_tools.py   # Browser navigation
    ai_tools.py        # Music theory

AbletonMCP_Remote_Script/
  __init__.py          # Runs inside Ableton
```

## Contributing

This project is open to everyone. Whether you're a producer, a developer, or just curious about what happens when AI meets a DAW — feel free to open an issue, submit a PR, or just fork it and make it your own.

Some ideas if you want to contribute:
- New drum pattern styles or chord voicings in `ai_tools.py`
- Support for audio clip operations
- Arrangement view tools
- Better browser search
- Tests

## Troubleshooting

- **Can't connect:** Make sure the Remote Script is loaded in Ableton (check Settings > Link, Tempo & MIDI)
- **Timeouts:** Break complex requests into smaller steps
- **Still stuck:** Restart both Ableton and your AI client

## Credits

- **Original project:** [Siddharth Ahuja](https://github.com/ahujasid/ableton-mcp) — thank you for starting this
- **Community:** [Discord](https://discord.gg/3ZrMyGKnaU)

## Disclaimer

This is an independent, community-driven project. It is not affiliated with or endorsed by Ableton.
