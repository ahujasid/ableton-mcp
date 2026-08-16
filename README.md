<div align="center">

# Ableton MCP

**Connect Ableton Live to Claude AI**

Prompt-assisted music production, end-to-end track creation, and Live session and arrangement manipulation — driven by AI.

[![PyPI Version](https://img.shields.io/pypi/v/ableton-mcp?color=blue)](https://pypi.org/project/ableton-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?logo=discord&logoColor=white)](https://discord.gg/JK4hNKGprW)

[**Setup Video**](https://youtu.be/iJWJqyVuPS8) · [**Discord**](https://discord.gg/JK4hNKGprW) · [**Issues**](https://github.com/ahujasid/ableton-mcp/issues)

</div>

---

## Quickstart

Three steps: install `uv`, point your MCP client at the server, install the Ableton Remote Script.

**1. Install uv**

```bash
# macOS
brew install uv
```

Otherwise, install from [uv's official website](https://docs.astral.sh/uv/getting-started/installation/).

> **Warning:** Do not proceed before installing uv.

**2. Add the MCP server to your client**

<details open>
<summary><b>Claude Desktop</b> — Settings → Developer → Edit Config</summary>

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": [
                "ableton-mcp"
            ]
        }
    }
}
```
</details>

<details>
<summary><b>Cursor</b> — Settings → MCP</summary>

Paste this as a command:

```
uvx ableton-mcp
```
</details>

> **Warning:** Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both.

**3. Install the Ableton Remote Script**

```bash
uvx --from ableton-mcp ableton-mcp-install-script
uvx --from ableton-mcp ableton-mcp-install-script --list-targets   # preview target folders first
```

**4. Connect**

1. Launch Ableton Live
2. Go to **Settings/Preferences → Link, Tempo & MIDI**
3. In the **Control Surface** dropdown, select **AbletonMCP**
4. Set **Input** and **Output** to **None**

That's it — ask Claude to build something.

---

## Table of Contents

- [Quickstart](#quickstart)
- [Features](#features)
- [Components](#components)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Claude for Desktop Integration](#claude-for-desktop-integration)
  - [Cursor Integration](#cursor-integration)
  - [Installing the Ableton Remote Script](#installing-the-ableton-remote-script)
- [Usage](#usage)
  - [Starting the Connection](#starting-the-connection)
  - [Using with Claude](#using-with-claude)
  - [Capabilities](#capabilities)
  - [Example Commands](#example-commands)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)
- [Limitations & Security Considerations](#limitations--security-considerations)
- [Telemetry](#telemetry)
- [Join the Community](#join-the-community)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)

---

## Features

| | |
|---|---|
| **Two-way communication** | Connect Claude AI to Ableton Live through a socket-based server |
| **Track manipulation** | Create, modify, and manipulate MIDI and audio tracks |
| **Instrument and effect selection** | Claude can access and load the right instruments, effects and sounds from Ableton's library |
| **Clip creation** | Create and edit MIDI clips with notes |
| **Arrangement view composition** | Build full songs autonomously in Arrangement View, including sections like intro, buildup, drop, breakdown, and outro |
| **Session control** | Start and stop playback, fire clips, and control transport across Session View and Arrangement View |
| **Anonymous telemetry** | Usage tracking to help improve the tool (can be disabled) |

## Components

The system consists of two main components:

1. **Ableton Remote Script** (`Ableton_Remote_Script/__init__.py`) — a MIDI Remote Script for Ableton Live that creates a socket server to receive and execute commands
2. **MCP Server** (`server.py`) — a Python server that implements the Model Context Protocol and connects to the Ableton Remote Script

---

## Installation

### Prerequisites

- **Ableton Live** 10 or newer
- **Python** 3.8 or newer
- **uv** package manager

If you're on Mac, please install uv as:

```
brew install uv
```

Otherwise, install from [uv's official website](https://docs.astral.sh/uv/getting-started/installation/)

> **Warning:** Do not proceed before installing uv.

### Claude for Desktop Integration

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

Go to **Claude → Settings → Developer → Edit Config → `claude_desktop_config.json`** to include the following:

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": [
                "ableton-mcp"
            ]
        }
    }
}
```

### Cursor Integration

Run ableton-mcp without installing it permanently through uvx. Go to **Cursor Settings → MCP** and paste this as a command:

```
uvx ableton-mcp
```

> **Warning:** Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both.

### Installing the Ableton Remote Script

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

Install the Remote Script with:

```bash
uvx --from ableton-mcp ableton-mcp-install-script
uvx --from ableton-mcp ableton-mcp-install-script --list-targets   # preview target folders first
```

> If you installed the package with `pip` or `pipx`, the command is on your PATH directly — just run `ableton-mcp-install-script`.

This copies the matching Remote Script into Ableton's **User Remote Scripts** folder. If a different version of the script is already there, the existing file is backed up to `__init__.py.bak` before being replaced.

Then **restart Ableton** (or re-select the AbletonMCP control surface) so Live loads it. Re-run the command after upgrading the package — the server logs a warning when the loaded script version doesn't match what it expects.

> **Note:** The server does **not** install the script on startup. Writing into Ableton's preferences directory is an explicit action, not a side effect of launching a server.

**First-time Ableton setup:**

1. Run `uvx --from ableton-mcp ableton-mcp-install-script`
2. Launch Ableton Live
3. Go to **Settings/Preferences → Link, Tempo & MIDI**
4. In the **Control Surface** dropdown, select **AbletonMCP**
5. Set **Input** and **Output** to **None**

<details>
<summary><b>Manual fallback locations (User Remote Scripts)</b></summary>

- **macOS:** `/Users/[Username]/Library/Preferences/Ableton/Live XX/User Remote Scripts/AbletonMCP/`
- **Windows:** `C:\Users\[Username]\AppData\Roaming\Ableton\Live x.x.x\Preferences\User Remote Scripts\AbletonMCP\`
</details>

The MCP server and Remote Script share a version handshake (`get_remote_script_info`). If they diverge, newer tools degrade gracefully until Live is restarted.

---

## Usage

### Starting the Connection

1. Ensure the Ableton Remote Script is loaded in Ableton Live
2. Make sure the MCP server is configured in Claude Desktop or Cursor
3. The connection should be established automatically when you interact with Claude

### Using with Claude

Once the config file has been set on Claude, and the remote script is running in Ableton, you will see a hammer icon with tools for the Ableton MCP.

### Capabilities

- Get session and track information
- Create and modify MIDI and audio tracks
- Create full song arrangements from start to finish in Arrangement View
- Create, edit, and trigger clips
- Control playback
- Load instruments and effects from Ableton's browser
- Add notes to MIDI clips
- Change tempo and other session parameters

### Example Commands

Here are some examples of what you can ask Claude to do:

| Prompt | Demo |
|---|---|
| *"Create an 80s synthwave track"* | [Watch](https://youtu.be/VH9g66e42XA) |
| *"Create a Metro Boomin style hip-hop beat"* | |
| *"Create a full arrangement with an intro, buildup, drop, breakdown, and outro"* | |
| *"Create a new MIDI track with a synth bass instrument"* | |
| *"Add reverb to my drums"* | |
| *"Create a 4-bar MIDI clip with a simple melody"* | |
| *"Get information about the current Ableton session"* | |
| *"Load a 808 drum rack into the selected track"* | |
| *"Add a jazz chord progression to the clip in track 1"* | |
| *"Set the tempo to 120 BPM"* | |
| *"Play the clip in track 2"* | |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Connection issues** | Make sure the Ableton Remote Script is loaded, and the MCP server is configured on Claude |
| **Timeout errors** | Try simplifying your requests or breaking them into smaller steps |
| **Have you tried turning it off and on again?** | If you're still having connection errors, try restarting both Claude and Ableton Live |

## Technical Details

### Communication Protocol

The system uses a simple JSON-based protocol over TCP sockets:

- **Commands** are sent as JSON objects with a `type` and optional `params`
- **Responses** are JSON objects with a `status` and `result` or `message`

## Limitations & Security Considerations

- Creating complex musical arrangements might need to be broken down into smaller steps
- The tool is designed to work with Ableton's default devices and browser items
- Always save your work before extensive experimentation

---

## Telemetry

AbletonMCP collects usage data to help improve the tool. This includes:

- Anonymous tool usage statistics (which features are used)
- Anonymous session start information (for daily/monthly active user counts)
- Anonymous rates and performance metrics
- Prompts, MIDI notes, track and clip names, and device settings

Telemetry is **on** by default. To see exactly what data is collected, see the [Terms & Data Use](TERMS.md).

### Opting Out

To disable telemetry, set one of these environment variables before starting the MCP server:

```bash
export ABLETON_MCP_DISABLE_TELEMETRY=true
```

Or use any of these alternatives:

- `DISABLE_TELEMETRY=true`
- `MCP_DISABLE_TELEMETRY=true`

For Claude Desktop, add the environment variable to your config:

```json
{
    "mcpServers": {
        "AbletonMCP": {
            "command": "uvx",
            "args": ["ableton-mcp"],
            "env": {
                "ABLETON_MCP_DISABLE_TELEMETRY": "true"
            }
        }
    }
}
```

---

## Join the Community

Give feedback, get inspired, and build on top of the MCP: [**Discord**](https://discord.gg/JK4hNKGprW)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This is a third-party integration and not made by Ableton. Made by [Siddharth](https://x.com/sidahuj).

---

<div align="center">

**If Ableton MCP is useful to you, consider starring the repo**

</div>
