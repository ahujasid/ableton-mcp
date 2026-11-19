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

1. Launch (or **restart**) Ableton Live
2. Go to **Settings/Preferences → Link, Tempo & MIDI**
3. In the **Control Surface** dropdown, select **AbletonMCP**
4. Set **Input** and **Output** to **None**

That's it — ask Claude to build something. To check the setup, ask Claude to run `get_remote_script_info`: it should report `up_to_date: true`.

---

## Table of Contents

- [Quickstart](#quickstart)
- [Features](#features)
- [Components](#components)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Claude for Desktop Integration](#claude-for-desktop-integration)
  - [Cursor Integration](#cursor-integration)
  - [Claude Code Integration](#claude-code-integration)
  - [Installing the Ableton Remote Script](#installing-the-ableton-remote-script)
- [Usage](#usage)
  - [Starting the Connection](#starting-the-connection)
  - [Using with Claude](#using-with-claude)
  - [Capabilities](#capabilities)
  - [Mixer, track and scene tools](#mixer-track-and-scene-tools)
  - [Behavior worth knowing](#behavior-worth-knowing)
  - [Example Commands](#example-commands)
- [Troubleshooting](#troubleshooting)
  - [Known limitations](#known-limitations)
- [Changelog](CHANGELOG.md)
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
| **Mixer control** | Volume, panning, sends, mute, solo and arm on tracks, return tracks and the master |
| **Scenes** | List, create, rename, duplicate, launch and delete Session View scenes |
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

### Claude Code Integration

In the terminal, run:

```
claude mcp add AbletonMCP uvx ableton-mcp
```

### Installing the Ableton Remote Script

[Follow along with the setup instructions video](https://youtu.be/iJWJqyVuPS8)

Install the Remote Script with:

```bash
uvx --from ableton-mcp ableton-mcp-install-script
uvx --from ableton-mcp ableton-mcp-install-script --list-targets   # preview target folders first
```

> If you installed the package with `pip` or `pipx`, the command is on your PATH directly — just run `ableton-mcp-install-script`.

This copies the matching Remote Script into your Ableton **User Library**'s `Remote Scripts` folder — the location Live (10.1.13+) scans for third-party control surface scripts. The installer reads the User Library location from Live's `Library.cfg`, falling back to the default (`~/Music/Ableton/User Library` on macOS, `Documents\Ableton\User Library` on Windows). If a different version of the script is already there, the existing file is backed up to `__init__.py.bak` before being replaced.

If your User Library lives somewhere non-standard and isn't detected, point the installer at it directly:

```bash
uvx --from ableton-mcp ableton-mcp-install-script --target "/path/to/User Library/Remote Scripts"
```

> The legacy `Preferences/User Remote Scripts` folder (used for instant-mapping configs, not Python control surfaces) is no longer targeted by default; pass `--legacy` if you need it for an old Live version.

Then **restart Ableton** so Live loads it. Re-run the command after upgrading the package — the server logs a warning when the loaded script version doesn't match what it expects.

> **Restart Live, don't just re-select the control surface.** Switching the Control Surface to *None* and back re-creates the script from the Python module Live already imported, so a new `__init__.py` is **not** picked up. Only a restart of Live reloads the code.

> **Note:** The server does **not** install the script on startup. Writing into Ableton's preferences directory is an explicit action, not a side effect of launching a server.

**First-time Ableton setup:**

1. Run `uvx --from ableton-mcp ableton-mcp-install-script`
2. Launch Ableton Live
3. Go to **Settings/Preferences → Link, Tempo & MIDI**
4. In the **Control Surface** dropdown, select **AbletonMCP**
5. Set **Input** and **Output** to **None**

<details>
<summary><b>Manual fallback locations (User Library → Remote Scripts)</b></summary>

- **macOS:** `~/Music/Ableton/User Library/Remote Scripts/AbletonMCP/`
- **Windows:** `C:\Users\[Username]\Documents\Ableton\User Library\Remote Scripts\AbletonMCP\`

If you've moved your User Library, use its actual location (shown in Live under **Preferences → Library → Location of User Library**), and create the `Remote Scripts` folder inside it if it doesn't exist yet.
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
- Read and set device parameters
- Mix: volume, panning, sends, mute, solo, arm
- Duplicate and delete tracks
- Manage scenes
- Delete Arrangement clips

### Mixer, track and scene tools

| Tool | What it does |
|---|---|
| `set_track_volume` | Fader, normalized 0.0–1.0 (0.85 ≈ 0 dB). `track_type`: `track` (default), `return` or `master`. Values above 1.0 are clamped to 1.0 (+6 dB). |
| `set_track_panning` | −1.0 (left) … 0.0 (center) … 1.0 (right). Same `track_type` values. |
| `set_track_send` | Send level 0.0–1.0; `send_index` 0 = first return track (Send A). |
| `set_track_mute` / `set_track_solo` | Mute / solo a track or return track. |
| `set_track_arm` | Arm or disarm a track for recording. |
| `duplicate_track` | Copies a track with its clips and devices, inserted right after it. |
| `delete_track` | Deletes a track; later track indexes shift down by one. Destructive. |
| `get_scenes` | Lists scenes (index, name, tempo; `null` when a scene has no tempo). |
| `create_scene` | Adds a scene (`index` −1 = at the end). |
| `set_scene_name` | Renames a scene. |
| `duplicate_scene` | Copies a scene with its clips, inserted right after it. |
| `fire_scene` | Launches every clip in a scene's row. |
| `delete_scene` | Deletes a scene and every clip in its row. Destructive. |
| `delete_arrangement_clip` | Deletes an Arrangement clip, indexed as listed by `get_arrangement_clips` (Live 11+). |

The mixer tools reply with Live's display value (e.g. `-6.0 dB`, `25L`), so you can check what actually changed.

### Behavior worth knowing

- **`create_locator`** moves the playhead to the target beat, waits for Live to get there, creates the cue, then puts the playhead back. If a locator already exists at that beat it is renamed. It refuses while the transport is playing, since Live would place the cue at the moving playhead.
- **`set_arrangement_time`** replies only once Live reports the playhead at the new position.
- **`load_instrument_or_effect`** replies once the device has appeared on the track and lists the new device(s). Loading the **same** device that is already on the track (e.g. Drift over Drift) doesn't replace it: Live keeps it and resets its parameters to their defaults. The reply says so ("reloaded in place"). If the parameters were already at their defaults, there is nothing to observe and the reply says it couldn't confirm the load.

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
| *"Turn the bass down 3 dB, pan it slightly left and send some reverb"* | |
| *"Duplicate scene 1, name the copy 'Chorus' and launch it"* | |
| *"Solo the drums"* | |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Connection issues** | Make sure the Ableton Remote Script is loaded, and the MCP server is configured on Claude |
| **Timeout errors** | Try simplifying your requests or breaking them into smaller steps |
| **Have you tried turning it off and on again?** | If you're still having connection errors, try restarting both Claude and Ableton Live |
| **`up_to_date: false` in `get_remote_script_info`** | The script loaded in Live doesn't match the server. Re-run `ableton-mcp-install-script` from the same source as the server, then **restart Live** (re-selecting the control surface is not enough) |
| **"missing capability" errors on the new tools** | Live is running the original (or an older) Remote Script. Same fix as above |
| **Server still runs old code after an update** | Restart your MCP client. If it persists, clear uv's cache: `uv cache clean ableton-mcp` (close the MCP client first, it holds a lock on the cache) |

### Known limitations

- There is no tool to **delete a locator** yet; remove it by hand in the Arrangement view.
- Device `type` is reported as `unknown` for Live's native instruments and effects.
- The capability list returned by `get_remote_script_info` doesn't include every command the script supports (e.g. `set_tempo`, `fire_clip`), but they work.

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

There are two tiers, and they have different defaults.

**Anonymous telemetry — on by default.** A random install ID, a per-run session ID, which tools ran, whether they succeeded, and how long they took. This is what counts active users and catches broken tools. It contains none of your content: no prompts, no MIDI, no track or clip names, no device settings.

**Dataset recording — off by default, opt-in.** Everything with your work in it: prompts, MIDI notes, track and clip names, and device settings, which may be published as part of an open dataset used to train music-production models. Nothing here is collected unless you explicitly turn it on.

To see exactly what data each tier collects, see the [Terms & Data Use](TERMS.md).

### Opting in to dataset recording

Either set the environment variable before starting the server:

```bash
export ABLETON_MCP_ENABLE_DATASET=true
```

…or answer the question when your client asks it. On your first tool call you're asked once — as a dialog if your client supports MCP elicitation, otherwise as a message in the chat — and answering yes turns it on from that point. Your answer is stored in `~/.ableton-mcp/consent.json`. Declining, or never answering, records nothing. If you dismiss the dialog without choosing, that isn't treated as an answer and you may be asked again in a later session.

### Opting out of anonymous telemetry

Set one of these before starting the MCP server:

```bash
export ABLETON_MCP_DISABLE_TELEMETRY=true
```

Or use any of these alternatives:

- `DISABLE_TELEMETRY=true`
- `MCP_DISABLE_TELEMETRY=true`

This also disables dataset recording. `ABLETON_MCP_DISABLE_DATASET=true` turns off dataset recording only, and overrides any stored grant.

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
