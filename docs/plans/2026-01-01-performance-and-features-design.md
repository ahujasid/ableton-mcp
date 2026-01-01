# AbletonMCP Performance & Features Design

**Date:** 2026-01-01
**Approach:** Performance First, Then Features

## Overview

This design addresses 4 performance issues in the existing MCP server and outlines high-value feature additions based on Ableton Live Object Model (LOM) API research.

## Part 1: Performance Fixes

### Fix 1: Async Socket Communication

**Problem:** Synchronous `socket.socket()` blocks the FastMCP event loop, preventing concurrent request handling.

**Location:** `MCP_Server/server.py` - `AbletonConnection` class (lines 16-162)

**Solution:** Replace blocking socket with async I/O:
- Use `asyncio.open_connection()` instead of `socket.socket()`
- Convert `send_command()` to async with `await reader.read()` / `writer.write()`
- Alternative: Wrap sync socket in `anyio.to_thread.run_sync()` for simpler migration

### Fix 2: Remove Hardcoded Delays

**Problem:** 200ms of hardcoded delays per state-modifying command (100ms before + 100ms after response) at `server.py:119-142`.

**Location:** `MCP_Server/server.py` - `send_command()` method

**Solution:** Remove both `time.sleep(0.1)` calls. The socket already waits for Ableton's response. If settling time is needed, handle it in the Remote Script where Ableton's state is known.

### Fix 3: Browser Item URI Cache

**Problem:** Recursive DFS through entire browser tree on every `load_browser_item` call via `_find_browser_item_by_uri()`.

**Location:** `AbletonMCP_Remote_Script/__init__.py` (lines 761-800)

**Solution:**
- Add `_browser_uri_cache = {}` instance variable
- Populate cache lazily on first browser access
- Direct URI lookup: O(1) instead of O(n) tree traversal
- Invalidate cache on session change or browser refresh

### Fix 4: Proper Connection Health Check

**Problem:** Health check sends empty bytes `b''` which doesn't validate connection responsiveness.

**Location:** `MCP_Server/server.py:200-214`

**Solution:** Implement dedicated `ping` command:
- Remote Script: Handle `ping` command, return `{"status": "ok"}`
- MCP Server: Use ping with short timeout (1s) for health checks
- Fall back to `get_session_info` if ping unavailable (backward compat)

## Part 2: High-Value Features

### Group 1: Simple Additions

Wire existing LOM methods to new MCP tools:

| MCP Tool | Remote Script Call | Notes |
|----------|-------------------|-------|
| `undo()` | `self._song.undo()` | Essential for AI experimentation |
| `redo()` | `self._song.redo()` | Pairs with undo |
| `delete_track(index)` | `self._song.delete_track(index)` | Cleanup |
| `create_audio_track(index)` | `self._song.create_audio_track(index)` | Currently only MIDI exists |
| `delete_clip(track, slot)` | `clip_slot.delete_clip()` | Cleanup |
| `set_metronome(on)` | `self._song.metronome = on` | Recording workflow |
| `fire_scene(index)` | `self._song.scenes[index].fire()` | Trigger entire rows |
| `capture_midi()` | `self._song.capture_midi()` | Grab recently played notes |

### Group 2: Track Property Setters

Expose write access for properties currently read-only:

| MCP Tool | Parameters | Remote Script |
|----------|-----------|---------------|
| `set_track_mute` | `track_index: int, muted: bool` | `track.mute = muted` |
| `set_track_solo` | `track_index: int, solo: bool` | `track.solo = solo` |
| `set_track_arm` | `track_index: int, armed: bool` | `track.arm = armed` |
| `set_track_volume` | `track_index: int, volume: float` | `track.mixer_device.volume.value = volume` |
| `set_track_panning` | `track_index: int, pan: float` | `track.mixer_device.panning.value = pan` |

### Group 3: New Data Retrieval

| MCP Tool | Returns |
|----------|---------|
| `get_notes_from_clip(track, slot)` | List of `{pitch, start_time, duration, velocity, mute}` |
| `get_scene_info(index)` | `{name, tempo, color, clip_count}` |
| `get_all_tracks_summary()` | Bulk track data in one call (reduces round-trips) |

## Part 3: Error Handling

### Structured Error Responses

Replace string errors with structured responses:

```python
# Instead of: "Error getting track info: Track index out of range"
# Return:
{
    "error": "track_not_found",
    "message": "Track index 5 out of range (0-3)",
    "track_index": 5
}
```

### Error Categories

- `IndexError` - Invalid track/clip/scene index
- `RuntimeError` - Ableton state issue (no clip in slot, browser unavailable)
- `ConnectionError` - Socket issues (MCP server handles, retries once)

### Reconnection Logic

On `ConnectionError` in MCP server:
1. Close existing socket
2. Attempt single reconnect
3. Retry original command
4. Fail with clear error if reconnect fails

## Part 4: Testing Strategy

### Mock Testing (MCP Server)

Test server logic with fake Ableton responses:
- Connection lifecycle (connect, reconnect, disconnect)
- Command routing (each command type reaches correct handler)
- Error propagation (Remote Script error to MCP tool error response)

### Integration Testing

Python script for manual testing against live Ableton:
- Requires Ableton running with Remote Script loaded
- Tests real LOM interactions
- Document expected setup in README

### Remote Script Debugging

Leverage existing `self.log_message()`:
- Add structured output for debugging
- View in Ableton's Log.txt

## Implementation Order

1. **Performance fixes** (all 4)
2. **Group 1 features** (simple additions)
3. **Group 2 features** (track setters)
4. **Group 3 features** (new data retrieval)
5. **Error handling improvements**

## Research Sources

- [AbletonOSC](https://github.com/ideoforms/AbletonOSC) - Reference for LOM API coverage
- [Structure Void Live API Docs](https://structure-void.com/PythonLiveAPI_documentation/Live10.0.1.xml) - Python API reference
- [Cycling '74 LOM Reference](https://docs.cycling74.com/apiref/lom/) - Official LOM documentation
- [FastMCP Documentation](https://github.com/jlowin/fastmcp) - Async patterns and middleware
