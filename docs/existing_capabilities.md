# Ableton MCP: Existing Capabilities and Tools

## Overview

Ableton MCP is a system that allows external applications to control Ableton Live through a socket-based communication protocol. It consists of two main components:

1. **AbletonMCP_Remote_Script**: A Python script that runs within Ableton Live as a MIDI Remote Script
2. **MCP_Server**: A server that exposes a Model Context Protocol (MCP) interface for external applications to interact with Ableton Live

## Architecture

The system works as follows:

1. The **AbletonMCP_Remote_Script** runs inside Ableton Live and opens a socket server on port 9877
2. The **MCP_Server** connects to this socket server and provides a higher-level API for external applications
3. External applications can use the MCP tools to control Ableton Live

## Existing Capabilities

### Session Control

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_session_info` | Get detailed information about the current Ableton session | None |
| `set_tempo` | Set the tempo of the Ableton session | `tempo`: The new tempo in BPM |
| `start_playback` | Start playing the Ableton session | None |
| `stop_playback` | Stop playing the Ableton session | None |

### Track Management

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_track_info` | Get detailed information about a specific track | `track_index`: The index of the track |
| `create_midi_track` | Create a new MIDI track | `index`: The index to insert the track at (-1 = end of list) |
| `create_return_track` | Create a new return track | None (return tracks are always added at the end) |
| `set_track_name` | Set the name of a track | `track_index`: The index of the track, `name`: The new name |
| `set_send_level` | Set the level of a send from a track to a return track | `track_index`: The index of the track, `send_index`: The index of the send, `value`: The value to set (0.0 to 1.0) |
| `set_track_volume` | Set the volume level of a track | `track_index`: The index of the track, `volume`: The new volume level in dB |

### Clip Management

| Tool | Description | Parameters |
|------|-------------|------------|
| `create_clip` | Create a new MIDI clip | `track_index`: The track index, `clip_index`: The clip slot index, `length`: The length in beats |
| `add_notes_to_clip` | Add MIDI notes to a clip | `track_index`: The track index, `clip_index`: The clip slot index, `notes`: List of note dictionaries |
| `set_clip_name` | Set the name of a clip | `track_index`: The track index, `clip_index`: The clip slot index, `name`: The new name |
| `fire_clip` | Start playing a clip | `track_index`: The track index, `clip_index`: The clip slot index |
| `stop_clip` | Stop playing a clip | `track_index`: The track index, `clip_index`: The clip slot index |

### Browser and Device Management

| Tool | Description | Parameters | Implementation Details |
|------|-------------|------------|------------------------|
| `get_browser_tree` | Get a hierarchical tree of browser categories | `category_type`: Type of categories to get | Direct command to Remote Script |
| `get_browser_items_at_path` | Get browser items at a specific path | `path`: Path in the format "category/folder/subfolder" | Direct command to Remote Script |
| `load_instrument_or_effect` | Load an instrument or effect onto a track | `track_index`: The track index, `uri`: The URI of the instrument or effect | Sends `load_browser_item` command to Remote Script with parameters `track_index` and `item_uri` |
| `load_drum_kit` | Load a drum rack and a specific drum kit | `track_index`: The track index, `rack_uri`: The URI of the drum rack, `kit_path`: Path to the drum kit | Implemented as a sequence of commands: 1) `load_browser_item` to load drum rack, 2) `get_browser_items_at_path` to find kits, 3) `load_browser_item` to load kit |

## Communication Protocol

The communication between the MCP Server and the Remote Script follows this format:

### Command Format (from MCP Server to Remote Script)
```json
{
  "type": "command_name",
  "params": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

### Response Format (from Remote Script to MCP Server)
```json
{
  "status": "success",
  "result": {
    "key1": "value1",
    "key2": "value2"
  }
}
```

Or in case of an error:
```json
{
  "status": "error",
  "message": "Error message",
  "result": {}
}
```

## Implementation Details

### Remote Script Implementation

The Remote Script (`AbletonMCP_Remote_Script/__init__.py`) implements:

1. A socket server that listens for commands
2. Command handlers for each supported command
3. Proper thread management for Ableton Live's threading model
4. Error handling and logging

### MCP Server Implementation

The MCP Server (`MCP_Server/server.py`) implements:

1. A connection manager for the socket connection to the Remote Script
2. MCP tools that map to the commands supported by the Remote Script
3. Parameter validation and error handling
4. Proper response parsing and formatting

### Command Mapping

There's an important distinction between the commands exposed by the MCP Server and the actual commands sent to the Remote Script:

| MCP Server Command | Remote Script Command | Notes |
|-------------------|------------------------|-------|
| `load_instrument_or_effect` | `load_browser_item` | Parameter `uri` is mapped to `item_uri` |
| `load_drum_kit` | Multiple commands | Implemented as a sequence of `load_browser_item` and `get_browser_items_at_path` commands |

This abstraction allows the MCP Server to provide a more user-friendly API while maintaining compatibility with the Remote Script's command structure.

## Missing Features

Based on the codebase exploration, the following features appear to be missing or not fully implemented:

1. **Device Parameter Control**: No comprehensive way to control device parameters (like EQ settings)
2. **Track Mixer Control**: No tools for controlling track volume, pan, mute, solo, etc.
3. **MIDI Editing Tools**: Limited tools for editing MIDI notes after they're added
4. **Audio Clip Management**: No tools for working with audio clips
5. **Automation**: No tools for creating or editing automation

## Next Steps

To enhance the Ableton MCP system, we could consider implementing:

1. **EQ Eight Parameter Control**: Add tools for controlling EQ Eight parameters
2. **Device Chain Management**: Add tools for managing device chains
3. **Track Mixer Control**: Add tools for controlling track mixer settings
4. **Enhanced MIDI Editing**: Add more sophisticated MIDI editing capabilities
5. **Audio Clip Support**: Add support for audio clips
