# Changelog

Remote Script changes.

The version numbers below are the **Remote Script** version (`SCRIPT_VERSION`), which the server checks through `get_remote_script_info`. After updating, reinstall the script with `ableton-mcp-install-script` and **restart Live** — re-selecting the control surface does not reload the code.

## Remote Script 1.11.0

### Added

- **Clip loop and markers:** `get_clip_loop` and `set_clip_loop` read and change the loop switch, the loop brace (`loop_start`, `loop_end`, or `loop_length`) and the start/end markers, on Session and Arrangement clips. Live refuses a start at or past the end at any moment, so the writes are ordered by the direction of the move, and both ranges are checked before anything is written. The reply gives the applied values and an `adjusted` entry for any value Live changed. Units are reported: beats, or seconds for an unwarped audio clip.
- A `playback` summary says what actually plays. Live 12.4.5 plays an unlooped clip from `loop_start` to `loop_end` and ignores a `start_marker` write on it, so start/end markers given for an unlooped clip are written to the loop brace (the reply says so).

### Fixed

- `set_clip_warp(original_bpm=…)` rounded the end marker down to a whole beat: a 16-beat drum loop 1 ms short at 140 BPM got its marker at beat 15. A file within 0.02 beat of a whole number of beats is now pinned to that beat (to the end of the file when it is a hair short, never past it), and the reply says so.

## Remote Script 1.10.0

### Added

- **Notes in Arrangement clips:** `get_clip_notes`, `add_notes_to_clip` and `clear_notes_from_clip` take `location="arrangement"`, with the clip index listed by `get_arrangement_clips`. Note times stay in clip beats; Arrangement replies add `arrangement_start`, `arrangement_end` and `start_marker` to place them in the song. Session calls are sent exactly as before.
- **`remove_notes`:** removes the notes that start in a time range and a pitch range, leaving the others, to rewrite one bar or one drum lane without clearing the clip.

### Safety

- The server only sends `location="arrangement"` to a Remote Script that advertises `arrangement_notes`: an older script would ignore it and edit the Session clip in the same slot.

### Fixed

- `clear_notes_from_clip` also removes notes past the clip's `length` (after its end marker or loop end were moved).

## Remote Script 1.9.0

### Added

New MCP tools and matching Remote Script commands. Each takes `location`: `session` (clip slot index) or `arrangement` (index as listed by `get_arrangement_clips`).

- **Warp:** `get_clip_warp`, `set_clip_warp` (warping, warp mode, pitch, gain), `edit_warp_markers` (Live 11+). `set_clip_warp(original_bpm=…)` conforms a loop to the song tempo: it turns warping on, keeps the first warp marker and pins the last whole beat of the file to its time at that tempo.
- **Clip automation:** `set_clip_automation` writes a clip envelope for a device parameter or a mixer control (volume, panning, sends), from points with linear ramps or held steps; an empty point list clears it. `get_clip_automation` samples an envelope back. Session clips only: Live 12 refuses clip automation on Arrangement clips from a script, and Arrangement automation lanes aren't reachable from its API.

### Internal

- `_resolve_clip()` resolves Session and Arrangement clips for the new commands.
- New tests in `tests/test_warp_automation.py` (fake Clip / AutomationEnvelope).

## Remote Script 1.8.2

### Fixed

- **Error messages:** refusals from Live (out-of-range index, master track can't be muted…) are no longer prefixed with `Communication error with Ableton:`, which suggested a connection problem. The server also keeps the socket open after such a refusal instead of dropping it and reconnecting. Real transport failures (timeout, lost connection, invalid response) are reported as before.
- **Master track name:** `get_session_info` reported the master as `"Master"` (hardcoded) while the mixer tools reported Live's actual name (`"Main"` in Live 12). It now reads the name from Live.

## Remote Script 1.8.1

### Fixed

Live applies some changes asynchronously: reading the state back right after a write returns the old value. Three commands were affected.

- **`set_arrangement_time`** reported the previous playhead position (e.g. asked for beat 16, replied "0.0"). It now replies once Live reports the playhead at the requested beat.
- **`create_locator`** failed with "Failed to create cue" unless the playhead was already at the target beat, because the cue was toggled at the old playhead position. It now waits for the playhead to arrive, creates the cue, waits for it to appear, names it, and restores the playhead. It now refuses to run while the transport is playing instead of misplacing the cue.
- **`load_instrument_or_effect`** replied "Devices on track:" with an empty list: the device chain was read before Live inserted the device, and the `new_devices` / `devices_after` fields the server expects were never sent. The reply now lists the new device(s). Loading the same device that is already on the track is detected as an in-place reload (Live keeps the device and resets its parameters).

When Live hasn't applied the change within the wait budget (1 s for the playhead, 5 s for a device load, 2 s for an in-place reload), the reply says so instead of reporting stale state.

### Internal

- Commands can now complete over several Live ticks (`_Deferred` + `_poll_until` in the Remote Script).
- New regression tests (`tests/test_async_live_state.py`) simulate Live applying writes one tick later.

## Remote Script 1.8.0

### Added

New MCP tools and matching Remote Script commands:

- **Mixer:** `set_track_volume`, `set_track_panning`, `set_track_send`, `set_track_mute`, `set_track_solo`, `set_track_arm` — on regular tracks, and (where it applies) return tracks and the master via `track_type`.
- **Tracks:** `duplicate_track`, `delete_track`.
- **Scenes:** `get_scenes`, `create_scene`, `set_scene_name`, `duplicate_scene`, `fire_scene`, `delete_scene`.
- **Arrangement:** `delete_arrangement_clip` (Live 11+).

See the [tool reference](README.md#mixer-track-and-scene-tools) for parameters.
