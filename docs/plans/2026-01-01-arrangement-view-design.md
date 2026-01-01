# Arrangement View Features Design

**Date:** 2026-01-01
**Status:** Approved

## Overview

Add comprehensive arrangement view support to AbletonMCP, enabling AI-assisted composition and production workflows in Ableton's arrangement timeline.

## Implementation Approach

Incremental feature groups delivered in 3 phases, each providing standalone value.

---

## Phase 1: Navigation & Playback

Control over arrangement playhead and loop region.

### Commands

| Command | Parameters | Description |
|---------|------------|-------------|
| `get_arrangement_info` | none | Returns current playhead position, loop settings, playing state, record state |
| `set_song_time` | `time: float` | Jump playhead to specific beat position |
| `set_loop_region` | `start: float, length: float` | Set arrangement loop brace position and length |
| `set_loop_enabled` | `enabled: bool` | Enable/disable arrangement loop |
| `continue_playing` | none | Resume from current position (vs `start_playback` which respects launch quantization) |
| `jump_by_bars` | `bars: int` | Move playhead forward/backward by N bars |

### Implementation Notes

- Times are in beats (not bars) to match Ableton's internal representation
- `jump_by_bars` calculates beats based on time signature from session info
- All read operations are non-blocking; playhead changes scheduled on main thread

### LOM Properties Used

- `Song.current_song_time` - get/set playhead position
- `Song.loop_start` - loop brace start position
- `Song.loop_length` - loop brace length
- `Song.loop` - loop enabled state
- `Song.continue_playing()` - resume playback
- `Song.signature_numerator/denominator` - for bar calculations

---

## Phase 2: Markers & Structure

Access to cue points (arrangement markers) for navigation and song structure.

### Commands

| Command | Parameters | Description |
|---------|------------|-------------|
| `get_cue_points` | none | List all cue points with name and time position |
| `jump_to_cue_point` | `index: int` | Jump playhead to a specific cue point |
| `create_cue_point` | `time: float, name: str` | Create a new cue point at the specified position |
| `delete_cue_point` | `index: int` | Remove a cue point |
| `set_cue_point_name` | `index: int, name: str` | Rename an existing cue point |
| `jump_to_next_cue_point` | none | Jump to the next cue point from current position |
| `jump_to_prev_cue_point` | none | Jump to the previous cue point from current position |

### Implementation Notes

- Cue points accessed via `Song.cue_points` property
- Each CuePoint has `name` and `time` properties
- `CuePoint.jump()` method moves playhead to that position

### LOM Properties Used

- `Song.cue_points` - list of CuePoint objects
- `CuePoint.name` - marker name
- `CuePoint.time` - position in beats
- `CuePoint.jump()` - navigate to cue point
- `Song.set_or_delete_cue()` - create/delete cue points

---

## Phase 3: Clip Operations & Recording

Arrangement clip manipulation and recording controls.

### Commands

| Command | Parameters | Description |
|---------|------------|-------------|
| `get_arrangement_clips` | `track_index: int` | List all clips in arrangement for a track |
| `duplicate_clip_to_arrangement` | `track_index: int, clip_index: int, time: float` | Copy session clip to arrangement at specified time |
| `get_arrangement_clip_info` | `track_index: int, clip_id: int` | Get details of an arrangement clip |
| `delete_arrangement_clip` | `track_index: int, clip_id: int` | Remove a clip from arrangement |
| `set_arrangement_overdub` | `enabled: bool` | Enable/disable arrangement overdub mode |
| `set_punch_in` | `enabled: bool` | Enable/disable punch-in recording |
| `set_punch_out` | `enabled: bool` | Enable/disable punch-out recording |
| `set_record_mode` | `enabled: bool` | Enable/disable global arrangement recording |

### Implementation Notes

- Arrangement clips accessed via `Track.arrangement_clips`
- `Track.duplicate_clip_to_arrangement(slot, time)` copies from clip slot
- Recording state changes scheduled on main thread

### LOM Properties Used

- `Track.arrangement_clips` - list of arrangement clips
- `Track.duplicate_clip_to_arrangement()` - copy clip to arrangement
- `Clip.start_time`, `Clip.end_time` - clip boundaries
- `Clip.is_arrangement_clip` - distinguish from session clips
- `Song.arrangement_overdub` - overdub state
- `Song.punch_in`, `Song.punch_out` - punch recording
- `Song.record_mode` - global record state

---

## Architecture

### Remote Script Changes (`AbletonMCP_Remote_Script/__init__.py`)

Add new command handlers in `_process_command()`:
- Phase 1: 6 new handlers for navigation/loop commands
- Phase 2: 7 new handlers for cue point commands
- Phase 3: 8 new handlers for clip/recording commands

All state-modifying commands use `schedule_message(0, callback)` pattern.

### MCP Server Changes (`MCP_Server/server.py`)

Add corresponding `@mcp.tool()` decorated functions:
- Each tool wraps `send_command_async()` with appropriate parameters
- Error handling follows existing patterns
- Modifying commands added to `is_modifying_command` list

### Testing

Unit tests for each phase following existing patterns in `tests/`.

---

## References

- [Live Object Model Documentation](https://docs.cycling74.com/legacy/max8/vignettes/live_object_model)
- [Python Live API Reference](https://structure-void.com/PythonLiveAPI_documentation/)
