# Ableton MCP Test Suite

A structured test suite for the Ableton MCP integration. Each test follows the pattern:
**Action** → **Verify** (read-back to confirm persistence). Run tests in order within each section.
Restore steps are included where a change could interfere with subsequent tests.

---

## Prerequisites

Before running: Ableton Live must be open with the AbletonMCP remote script active.
A session with at least 2 tracks, 1 return track, and 8+ scenes should be present.

---

## Phase 1 — Session & Transport

### T01 — get_session_info (baseline read)
- **Action:** `get_session_info`
- **Expect:** Response contains `tempo`, `signature_numerator`, `signature_denominator`, `track_count`, `return_track_count`, `master_track` fields. All numeric, no nulls.

### T02 — set_tempo
- **Action:** `set_tempo(140.0)`
- **Verify:** `get_session_info` → `tempo == 140.0`
- **Restore:** `set_tempo(120.0)` → `get_session_info` → `tempo == 120.0`

---

## Phase 1 — Master Track

### T03 — set_master_volume
- **Action:** `set_master_volume(0.5)`
- **Verify:** `get_session_info` → `master_track.volume ≈ 0.5`
- **Restore:** `set_master_volume(0.85)`

### T04 — set_master_panning
- **Action:** `set_master_panning(0.3)`
- **Verify:** `get_session_info` → `master_track.panning ≈ 0.3`
- **Restore:** `set_master_panning(0.0)`

---

## Phase 1 — Track Operations (track_index=0)

### T05 — get_track_info (baseline read)
- **Action:** `get_track_info(track_index=0)`
- **Expect:** Response contains `name`, `volume`, `panning`, `mute`, `solo`, `arm`, `color`, `sends` fields.

### T06 — set_track_name
- **Action:** `set_track_name(track_index=0, name="MCP Test")`
- **Verify:** `get_track_info(0)` → `name == "MCP Test"`
- **Restore:** `set_track_name(0, <original name>)`

### T07 — set_track_volume
- **Action:** `set_track_volume(track_index=0, volume=0.5)`
- **Verify:** `get_track_info(0)` → `volume ≈ 0.5`
- **Restore:** `set_track_volume(0, <original value>)`

### T08 — set_track_panning
- **Action:** `set_track_panning(track_index=0, panning=0.4)`
- **Verify:** `get_track_info(0)` → `panning ≈ 0.4`
- **Restore:** `set_track_panning(0, 0.0)`

### T09 — set_track_color
- **Action:** `set_track_color(track_index=0, color=0xFF0000)`
- **Verify:** `get_track_info(0)` → `color == 0xFF0000` (or nearest Ableton palette match)

### T10 — set_track_mute (enable)
- **Action:** `set_track_mute(track_index=0, mute=true)`
- **Verify:** `get_track_info(0)` → `mute == true`

### T11 — set_track_mute (disable)
- **Action:** `set_track_mute(track_index=0, mute=false)`
- **Verify:** `get_track_info(0)` → `mute == false`

### T12 — set_track_solo (enable)
- **Action:** `set_track_solo(track_index=0, solo=true)`
- **Verify:** `get_track_info(0)` → `solo == true`

### T13 — set_track_solo (disable)
- **Action:** `set_track_solo(track_index=0, solo=false)`
- **Verify:** `get_track_info(0)` → `solo == false`

### T14 — set_track_arm (enable)
- **Action:** `set_track_arm(track_index=0, arm=true)`
- **Verify:** `get_track_info(0)` → `arm == true`

### T15 — set_track_arm (disable)
- **Action:** `set_track_arm(track_index=0, arm=false)`
- **Verify:** `get_track_info(0)` → `arm == false`

### T16 — set_send
- **Action:** `set_send(track_index=0, return_index=0, value=0.75)`
- **Verify:** `get_track_info(0)` → `sends[0] ≈ 0.75`
- **Restore:** `set_send(0, 0, 0.0)`

---

## Phase 1 — Return Track Operations (return_index=0)

### T17 — get_return_tracks (baseline read)
- **Action:** `get_return_tracks`
- **Expect:** List with at least 1 entry, each containing `name`, `volume`, `panning`, `mute`, `color` fields.

### T18 — set_return_track_name
- **Action:** `set_return_track_name(return_index=0, name="MCP Return Test")`
- **Verify:** `get_return_tracks` → entry 0 `name == "MCP Return Test"`
- **Restore:** `set_return_track_name(0, <original name>)`

### T19 — set_return_track_volume
- **Action:** `set_return_track_volume(return_index=0, volume=0.6)`
- **Verify:** `get_return_tracks` → entry 0 `volume ≈ 0.6`
- **Restore:** `set_return_track_volume(0, <original value>)`

### T20 — set_return_track_panning
- **Action:** `set_return_track_panning(return_index=0, panning=-0.3)`
- **Verify:** `get_return_tracks` → entry 0 `panning ≈ -0.3`
- **Restore:** `set_return_track_panning(0, 0.0)`

### T21 — set_return_track_mute (enable)
- **Action:** `set_return_track_mute(return_index=0, mute=true)`
- **Verify:** `get_return_tracks` → entry 0 `mute == true`

### T22 — set_return_track_mute (disable)
- **Action:** `set_return_track_mute(return_index=0, mute=false)`
- **Verify:** `get_return_tracks` → entry 0 `mute == false`

### T23 — set_return_track_color
- **Action:** `set_return_track_color(return_index=0, color=0x00FF00)`
- **Verify:** `get_return_tracks` → entry 0 `color == 0x00FF00` (or nearest palette match)

---

## Phase 2 — Scene Operations

### T24 — get_scenes (baseline read)
- **Action:** `get_scenes`
- **Expect:** List with at least 1 scene. Each entry has `name`, `color`, `tempo` fields.

### T25 — set_scene_name
- **Action:** `set_scene_name(scene_index=0, name="Test Scene")`
- **Verify:** `get_scenes` → scene 0 `name == "Test Scene"`

### T26 — set_scene_color
- **Action:** `set_scene_color(scene_index=0, color=0xFF0000)`
- **Verify:** `get_scenes` → scene 0 `color == 0xff0000` (or nearest palette match)

### T27 — set_scene_tempo
- **Action:** `set_scene_tempo(scene_index=0, tempo=128.0)`
- **Verify:** `get_scenes` → scene 0 `tempo == 128.0`

### T28 — set_scene_tempo (clear)
- **Action:** `set_scene_tempo(scene_index=0, tempo=0.0)`
- **Verify:** `get_scenes` → scene 0 `tempo == -1.0` (Ableton's "no override" sentinel)

### T29 — create_scene
- **Action:** Record baseline scene count N via `get_scenes`. Then `create_scene(index=-1)`.
- **Verify:** `get_scenes` → total count == N+1

### T30 — duplicate_scene
- **Action:** `set_scene_name(0, "Dupe Source")`, `set_scene_color(0, 0x0000FF)`, `set_scene_tempo(0, 130.0)`. Then `duplicate_scene(scene_index=0)`.
- **Verify:** `get_scenes` → scene 1 `name == "Dupe Source"`, `color == 0x0000ff`, `tempo == 130.0`

### T31 — delete_scene
- **Action:** Record scene count N. Then `delete_scene(scene_index=1)` (the duplicate from T30).
- **Verify:** `get_scenes` → total count == N-1

### T32 — fire_scene
- **Action:** `fire_scene(scene_index=0)`
- **Expect:** No error. (Audible/visual confirmation in Ableton; no read-back available.)

### T33 — stop_all_clips
- **Action:** `stop_all_clips`
- **Expect:** No error. All clips stop in Ableton.

---

## Phase 3 — Track & Return Track Creation

### T34 — create_midi_track
- **Action:** Record baseline track count N from `get_session_info`. Then `create_midi_track(index=-1)`.
- **Verify:** `get_session_info` → `track_count == N+1`

### T35 — create_return_track
- **Action:** Record baseline return track count N. Then `create_return_track`.
- **Verify:** `get_session_info` → `return_track_count == N+1`

---

## Phase 4 — Clip Operations

### T36 — create_clip
- **Action:** `create_clip(track_index=0, scene_index=0, length=4)`
- **Expect:** No error. Clip visible in session view at track 0, scene 0.

### T37 — set_clip_name
- **Action:** `set_clip_name(track_index=0, scene_index=0, name="Test Clip")`
- **Expect:** No error. (No read-back tool yet; confirm visually in Ableton.)

### T38 — add_notes_to_clip
- **Action:** `add_notes_to_clip(track_index=0, scene_index=0, notes=[{pitch: 60, time: 0, duration: 0.5, velocity: 100}, {pitch: 64, time: 0.5, duration: 0.5, velocity: 90}])`
- **Expect:** No error. Two MIDI notes visible in the clip.

### T39 — fire_clip
- **Action:** `fire_clip(track_index=0, scene_index=0)`
- **Expect:** No error. Clip plays in Ableton.

### T40 — stop_clip
- **Action:** `stop_clip(track_index=0, scene_index=0)`
- **Expect:** No error. Clip stops.

---

## Phase 5 — Device Browser

### T41 — get_browser_tree
- **Action:** `get_browser_tree`
- **Expect:** Response contains top-level browser categories (Instruments, Audio Effects, MIDI Effects, etc.).

### T42 — get_browser_items_at_path
- **Action:** `get_browser_items_at_path(path="Instruments")`
- **Expect:** List of instrument categories or devices. Non-empty.

---

## Phase 6 — Device Loading

### T43 — load_instrument_or_effect
- **Action:** `load_instrument_or_effect(track_index=0, uri="query:Synths#Operator")`
- **Verify:** `get_track_info(0)` → `devices` array contains an entry with `name == "Operator"`
- **Expect:** Response: `Loaded 'Operator' onto track '1-MIDI' (index 0)`

### T44 — load_drum_kit
- **Action:** `load_drum_kit(track_index=0, rack_uri="query:Drums#Drum%20Rack", kit_uri="query:Drums#FileId_12860")`
- **Expect:** Response: `Loaded drum rack and kit '808 Core Kit.adg' on track '1-MIDI' (index 0)`
- **Note:** Use `get_browser_items_at_path("Drums")` to enumerate available kits and their URIs.

### T45 — load_device_on_return
- **Action:** `load_device_on_return(return_track_index=0, uri="query:AudioFx#Reverb")`
- **Verify:** `get_return_tracks` → return track 0 `devices` array contains an entry with `name == "Reverb"`

---

## Phase 7 — Transport

### T46 — start_playback
- **Action:** `start_playback`
- **Expect:** No error. Ableton begins playing.

### T47 — stop_playback
- **Action:** `stop_playback`
- **Expect:** No error. Ableton stops.

---

## Phase 8 — Device Parameters

Prerequisites: Track 0 must have at least one device loaded (e.g. load Operator via `load_instrument_or_effect`).

### T48 — get_device_parameters
- **Action:** `get_device_parameters(track_index=0, device_index=0)`
- **Expect:** Returns `device_name`, and `parameters` array where each entry has `index`, `name`, `value`, `min`, `max`, `is_quantized`, `value_string`.

### T49 — set_device_parameter
- **Action:** Note the current value of param 0 from T48. Call `set_device_parameter(track_index=0, device_index=0, param_index=1, value=<new_value>)`
- **Verify:** `get_device_parameters(0, 0)` → param 1's `value` matches the new value.
- **Restore:** Set param 1 back to its original value.
- **Expect:** Response: `Set '<device>' param '<name>' to <value_string> (raw: <float>)`

### T50 — set_device_parameter value clamping
- **Action:** `set_device_parameter(track_index=0, device_index=0, param_index=1, value=999999.0)`
- **Expect:** No error. Value is clamped to the parameter's `max`. Response shows the clamped value.

### T51 — get_device_parameters out-of-bounds device
- **Action:** `get_device_parameters(track_index=0, device_index=99)`
- **Expect:** Clean error: "Device index out of range"

### T52 — set_device_parameter out-of-bounds param
- **Action:** `set_device_parameter(track_index=0, device_index=0, param_index=9999, value=0.5)`
- **Expect:** Clean error: "Parameter index out of range"

---

## Phase 5 — Clip Operations

Prerequisites: Track 0, scene/clip-slot 0 must have a MIDI clip with at least a few notes. Track 0 must have an empty clip slot at index 2 for the duplicate test.

### T53 — get_notes_from_clip (baseline read)
- **Action:** `get_notes_from_clip(track_index=0, clip_index=0)`
- **Expect:** Returns a `notes` array where each entry has `pitch`, `time`, `duration`, `velocity`, `mute`. Array may be empty if clip has no notes — create notes first if needed.

### T54 — set_clip_color
- **Action:** Note current color via `get_track_info(0)` → `clip_slots[0].clip.color` (if exposed). Call `set_clip_color(track_index=0, clip_index=0, color=16711680)` (red = 0xFF0000).
- **Verify:** `get_track_info(0)` → `clip_slots[0].clip.color` — expect value close to 16711680 (may snap to nearest palette color).
- **Restore:** `set_clip_color(track_index=0, clip_index=0, color=<original_color>)`

### T55 — set_clip_loop
- **Action:** `set_clip_loop(track_index=0, clip_index=0, loop_start=0.0, loop_end=4.0, loop_on=True)`
- **Verify:** No error returned. Optionally verify by reading clip info if available.
- **Restore:** `set_clip_loop(track_index=0, clip_index=0, loop_start=0.0, loop_end=<original_length>, loop_on=True)`

### T56 — set_clip_loop disabled
- **Action:** `set_clip_loop(track_index=0, clip_index=0, loop_start=0.0, loop_end=4.0, loop_on=False)`
- **Expect:** No error. Loop is disabled on the clip.
- **Restore:** `set_clip_loop(track_index=0, clip_index=0, loop_start=0.0, loop_end=4.0, loop_on=True)`

### T57 — duplicate_clip
- **Action:** Ensure clip slot 2 on track 0 is empty. Call `duplicate_clip(track_index=0, clip_index=0, target_clip_index=2)`.
- **Verify:** `get_track_info(0)` → `clip_slots[2]` should now have a clip. Name should match the source clip.
- **Restore:** (Leave the duplicate — it won't interfere with other tests.)

### T58 — quantize_clip (full, 16th notes)
- **Action:** Add a few off-grid notes to the clip first if needed. Call `quantize_clip(track_index=0, clip_index=0, quantize_to=0.25, amount=1.0)`.
- **Verify:** `get_notes_from_clip(track_index=0, clip_index=0)` → note `time` values should be multiples of 0.25.
- **Expect:** Clean success response.

### T59 — quantize_clip (partial, 50%)
- **Action:** `quantize_clip(track_index=0, clip_index=0, quantize_to=0.25, amount=0.5)`
- **Expect:** No error. Notes move partially toward the grid (result depends on their starting positions — just verify no crash).

### T60 — duplicate_clip to occupied slot
- **Action:** `duplicate_clip(track_index=0, clip_index=0, target_clip_index=0)` (source and target are the same occupied slot)
- **Hypothesis:** Error ("target slot is not empty" or similar). Should not crash.

### T61 — get_notes_from_clip on empty slot
- **Action:** `get_notes_from_clip(track_index=0, clip_index=7)` (assumes slot 7 is empty)
- **Hypothesis:** Error ("no clip in slot") or returns empty notes array.

### T62 — set_clip_color out-of-bounds color
- **Action:** `set_clip_color(track_index=0, clip_index=0, color=0x1FF0000)` (> 0xFFFFFF)
- **Hypothesis:** Clean error "Color value out of range" (consistent with scene color validation).

---

## Phase 5 — Song Transport & Global State

### T63 — get_current_song_time (baseline read)
- **Action:** `get_current_song_time`
- **Expect:** Returns current playback position in beats as a float. Returns `0.0` when stopped at the start.

### T64 — set_current_song_time
- **Action:** `set_current_song_time(time=8.0)`
- **Verify:** `get_current_song_time` → `8.0`
- **Restore:** `set_current_song_time(time=0.0)`
- **Note:** Response message echoes the requested value (not a read-back) — Ableton's `current_song_time` property does not update synchronously on the same tick.

### T65 — set_metronome (enable)
- **Action:** `set_metronome(metronome=true)` while Ableton is playing
- **Expect:** Metronome button lights up in transport bar; click audible.
- **Restore:** `set_metronome(metronome=false)`

### T66 — set_session_record
- **Action:** `set_session_record(record=true)`, then `set_session_record(record=false)`
- **Expect:** Session record button toggles on/off in transport bar. No error.

### T67 — set_arrangement_record
- **Action:** Start playback with `start_playback`. Then `set_arrangement_record(record=true)`.
- **Expect:** Record button (circle) in transport bar lights red.
- **Restore:** `set_arrangement_record(record=false)`, `stop_playback`
- **Note:** Arrangement record only engages while playback is active. Calling without playback silently no-ops.

### T68 — undo / redo
- **Action:** `set_tempo(140.0)`. Then `undo`. Verify `get_session_info` → `tempo == 120.0`. Then `redo`. Verify `get_session_info` → `tempo == 140.0`.
- **Restore:** `set_tempo(120.0)`
- **Expect:** Both operations confirmed via read-back.

### T69 — set_nudge_up / set_nudge_down
- **Action:** `set_nudge_up(nudge=true)` then `set_nudge_up(nudge=false)`. Repeat for `set_nudge_down`.
- **Expect:** Nudge arrow buttons in transport bar flash briefly. No error.
- **Note:** Effect is only audible/visible during playback.

### T70 — tap_tempo
- **Action:** Call `tap_tempo` 4+ times
- **Expect:** Each call returns "Tap received. Current tempo: X BPM". Tap button flashes in Ableton.
- **Note:** Programmatic calls with no delay between them are too fast to calculate a new BPM — tempo won't change. Interval between taps determines the computed BPM.

---

## Phase 6 — Clip Read-back, Clip Slot State, Time Signature

### T71 — get_clip_slot_info on empty slot
- **Action:** `get_clip_slot_info(0, 0)` on a slot with no clip
- **Expect:** `has_clip: false`, `clip: null`, `has_stop_button: true`, `is_triggered: false`
- **Result:** ✅ Passed 2026-05-06

### T72 — get_clip_slot_info on occupied slot
- **Action:** Create a clip at track 0, slot 0, then call `get_clip_slot_info(0, 0)`
- **Expect:** `has_clip: true`, `clip` object with name, length, color, playback state
- **Result:** ✅ Passed 2026-05-06

### T73 — get_clip_info full detail read
- **Action:** `get_clip_info(0, 0)` on an existing MIDI clip
- **Expect:** Returns `is_midi_clip: true`, `loop_on`, `loop_start`, `loop_end`, `start_marker`, `end_marker`, `is_playing`, `is_recording`
- **Result:** ✅ Passed 2026-05-06

### T74 — get_clip_info round-trip after name + color set
- **Action:** Set clip name to "TestClip" and color to 255, then `get_clip_info(0, 0)`
- **Expect:** `name: "TestClip"`, color reflects Ableton palette snap (same behavior as set_clip_color)
- **Result:** ✅ Passed 2026-05-06

### T75 — get_clip_slot_info and get_clip_info out-of-bounds
- **Action:** `get_clip_slot_info(999, 0)` and `get_clip_info(0, 999)`
- **Expect:** Clean "index out of range" errors from both tools
- **Result:** ✅ Passed 2026-05-06

### T76 — set_time_signature round-trip
- **Action:** `set_time_signature(3, 8)`, then `get_session_info` to verify
- **Expect:** `signature_numerator: 3`, `signature_denominator: 8`
- **Result:** ✅ Passed 2026-05-06

### T77 — set_time_signature invalid denominator
- **Action:** `set_time_signature(4, 7)`
- **Expect:** Clean error "Denominator must be one of: 1, 2, 4, 8, 16, 32"
- **Result:** ✅ Passed 2026-05-06

---

## Phase 7 — Input/Output Routing

### T78 — get_track_routing
- **Action:** `get_track_routing(0)`
- **Expect:** Returns `input_routing_type`, `input_routing_channel`, `output_routing_type`, `output_routing_channel`
- **Result:** ✅ Passed 2026-05-07 — returned `input_routing_type: "All Ins"`, `input_routing_channel: "All Channels"`, `output_routing_type: "No Output"`, `output_routing_channel: ""`

### T79 — get_available_routings
- **Action:** `get_available_routings(0)`
- **Expect:** Returns lists of `available_input_routing_types` and `available_output_routing_types`
- **Result:** ✅ Passed 2026-05-07 — inputs: `["All Ins", "Computer Keyboard", "2-MIDI", "No Input"]`; outputs: `["2-MIDI", "No Output"]`

### T80 — set_input_routing round-trip
- **Action:** `set_input_routing(0, "No Input")`, then `get_track_routing(0)`
- **Expect:** `input_routing_type` changes to "No Input", `input_routing_channel` becomes `""`
- **Result:** ✅ Passed 2026-05-07

### T81 — set_output_routing round-trip
- **Action:** `set_output_routing(0, "2-MIDI")`, then `get_track_routing(0)`
- **Expect:** `output_routing_type` changes to "2-MIDI", `output_routing_channel` populates (e.g. "Track In")
- **Result:** ✅ Passed 2026-05-07 — `output_routing_channel: "Track In"`

### T82 — restore routing
- **Action:** `set_input_routing(0, "All Ins")` + `set_output_routing(0, "No Output")` in parallel, verify via `get_track_routing`
- **Expect:** Both routing types restored to original values
- **Result:** ✅ Passed 2026-05-07

---

## Phase 10 — Audio Clips

### T83 — get_audio_clip_info baseline
- **Action:** `get_audio_clip_info(track_index, clip_index)` on a track with an audio clip
- **Expect:** Returns `name`, `length`, `gain`, `pitch_coarse`, `pitch_fine`, `warping`, `warp_mode`
- **Result:** ✅ Passed 2026-05-15

### T84 — set_audio_clip_gain round-trip
- **Action:** `set_audio_clip_gain(track_index, clip_index, gain=1.5)`, then `get_audio_clip_info`
- **Expect:** `gain` reflects new value
- **Result:** ✅ Passed 2026-05-15

### T85 — set_audio_clip_pitch round-trip
- **Action:** `set_audio_clip_pitch(track_index, clip_index, pitch_coarse=3, pitch_fine=-15)`, then `get_audio_clip_info`
- **Expect:** `pitch_coarse` and `pitch_fine` reflect new values
- **Result:** ✅ Passed 2026-05-15

### T86 — set_audio_clip_warp round-trip
- **Action:** `set_audio_clip_warp(track_index, clip_index, warping=True, warp_mode=0)`, then `get_audio_clip_info`
- **Expect:** `warping` is `true`, `warp_mode` is 0 (Beats)
- **Result:** ✅ Passed 2026-05-15

---

## Phase 11 — Note Editing

### T87 — get_notes_from_clip regression check
- **Action:** `add_notes_to_clip` with 8-note C major scale, then `get_notes_from_clip`
- **Expect:** All 8 notes returned with correct pitch, start_time, duration, velocity, mute via `get_notes_extended` API
- **Result:** ✅ Passed 2026-05-15

### T88 — add_notes_to_clip regression check
- **Action:** `add_notes_to_clip` with 4 notes using `add_new_notes` + `MidiNoteSpecification`
- **Expect:** Notes added, `note_count` returned, read-back confirms
- **Result:** ✅ Passed 2026-05-15 (implicit — used throughout T87–T93 setup)

### T89 — remove_notes_from_clip by pitch range
- **Action:** `remove_notes_from_clip(from_pitch=60, pitch_span=3)` on 8-note clip
- **Expect:** Pitches 60–62 removed, remaining notes untouched
- **Result:** ✅ Passed 2026-05-15 — pitches 60 (C4) and 62 (D4) removed, 6 notes remain

### T90 — remove_notes_from_clip by time range
- **Action:** `remove_notes_from_clip(from_time=0, time_span=2)` on 6-note clip
- **Expect:** Notes with start_time < 2 removed
- **Result:** ✅ Passed 2026-05-15 — 2 notes removed, 4 remain (beats 2.0–3.5)

### T91 — remove_notes_from_clip all notes
- **Action:** `remove_notes_from_clip()` with no range args
- **Expect:** Clip is empty
- **Result:** ✅ Passed 2026-05-15 — 0 notes returned after call

### T92 — apply_note_modifications: pitch change
- **Action:** `apply_note_modifications` identifying note by `(pitch=60, start_time=0)`, setting `new_pitch=64`
- **Expect:** That note's pitch changes to 64; other notes unaffected
- **Result:** ✅ Passed 2026-05-15 — pitch 60 at beat 0 became 64; 3 other notes unchanged

### T93 — apply_note_modifications: velocity + duration
- **Action:** `apply_note_modifications` on note `(pitch=62, start_time=0.5)`, setting `new_velocity=127, new_duration=1`
- **Expect:** Velocity and duration updated in place
- **Result:** ✅ Passed 2026-05-15 — vel=127.0, dur=1.000 confirmed via read-back

---

## Phase 11 — Follow Actions (NOT IMPLEMENTED)

**Not implemented.** Follow action properties (`follow_action_A`, `follow_action_B`, `follow_action_chance_A/B`, `follow_action_time`, `follow_actions_enabled`) raise `AttributeError` on the Live 12 `Clip` object — they are not exposed in the Remote Script Python API in Live 12. Confirmed by live probing on Live 12.2.7. Tools were removed from the codebase.

~~T101–T106 — skipped~~

---

## Adversarial Tests

These tests are designed to find edge cases, crashes, and unexpected behavior in the MCP ↔ Remote Script mapping. Document the actual result for each — the "expect" here is a hypothesis, not a guarantee.

---

### Boundary Values

#### A01 — Volume above 1.0 (over-ceiling)
- **Action:** `set_track_volume(track_index=0, volume=1.5)`
- **Verify:** `get_track_info(0)` → `volume` field
- **Hypothesis:** Clamped to 1.0. Could also error or wrap.

#### A02 — Volume below 0.0 (negative)
- **Action:** `set_track_volume(track_index=0, volume=-0.5)`
- **Verify:** `get_track_info(0)` → `volume` field
- **Hypothesis:** Clamped to 0.0 or error.

#### A03 — Panning at hard limits
- **Action:** `set_track_panning(track_index=0, panning=-1.0)` then `set_track_panning(0, 1.0)`
- **Verify:** `get_track_info(0)` → `panning` matches each value
- **Hypothesis:** Both accepted cleanly.

#### A04 — Panning beyond limits
- **Action:** `set_track_panning(track_index=0, panning=2.0)`
- **Verify:** `get_track_info(0)` → `panning` field
- **Hypothesis:** Clamped to 1.0.

#### A05 — Tempo at Ableton floor (20 BPM)
- **Action:** `set_tempo(20.0)`
- **Verify:** `get_session_info` → `tempo == 20.0`
- **Restore:** `set_tempo(120.0)`

#### A06 — Tempo at Ableton ceiling (999 BPM)
- **Action:** `set_tempo(999.0)`
- **Verify:** `get_session_info` → `tempo == 999.0`
- **Restore:** `set_tempo(120.0)`

#### A07 — Tempo at zero
- **Action:** `set_tempo(0.0)`
- **Verify:** `get_session_info` → `tempo` field
- **Hypothesis:** Error or clamped to minimum (20.0). Could crash the remote script.

#### A08 — Tempo as fractional value
- **Action:** `set_tempo(93.3)`
- **Verify:** `get_session_info` → `tempo ≈ 93.3` (check if float precision is preserved)

#### A09 — Scene tempo negative
- **Action:** `set_scene_tempo(scene_index=0, tempo=-10.0)`
- **Verify:** `get_scenes` → scene 0 `tempo` field
- **Hypothesis:** Treated as "clear" (returns -1.0 sentinel), or error.

#### A10 — Color at black (0x000000)
- **Action:** `set_scene_color(scene_index=0, color=0x000000)`
- **Verify:** `get_scenes` → scene 0 `color` field
- **Hypothesis:** Accepted but may snap to nearest non-black palette color, or render as transparent/no color.

#### A11 — Color at white (0xFFFFFF)
- **Action:** `set_scene_color(scene_index=0, color=0xFFFFFF)`
- **Verify:** `get_scenes` → scene 0 `color` field

#### A12 — Color value exceeding 0xFFFFFF
- **Action:** `set_scene_color(scene_index=0, color=0x1FF0000)`
- **Verify:** `get_scenes` → scene 0 `color` field
- **Hypothesis:** Masked to lower 24 bits, or error.

#### A13 — Color as negative integer
- **Action:** `set_scene_color(scene_index=0, color=-1)`
- **Verify:** `get_scenes` → scene 0 `color` field
- **Hypothesis:** Error, or interpreted as a large unsigned int (0xFFFFFFFF → snaps to palette).

---

### String Edge Cases

#### A14 — Empty string name
- **Action:** `set_scene_name(scene_index=0, name="")`
- **Verify:** `get_scenes` → scene 0 `name == ""`
- **Hypothesis:** Accepted. Ableton allows unnamed scenes.

#### A15 — Very long name (500 characters)
- **Action:** `set_scene_name(scene_index=0, name="A" * 500)`
- **Verify:** `get_scenes` → scene 0 `name` — check if truncated and at what length.

#### A16 — Emoji in name
- **Action:** `set_scene_name(scene_index=0, name="🔥 Drop")`
- **Verify:** `get_scenes` → scene 0 `name == "🔥 Drop"`
- **Hypothesis:** Accepted; Ableton supports Unicode. Could fail at the OSC/socket layer.

#### A17 — CJK characters in name
- **Action:** `set_scene_name(scene_index=0, name="音楽")`
- **Verify:** `get_scenes` → scene 0 `name == "音楽"`

#### A18 — Special characters in name (slashes, quotes, backslash)
- **Action:** `set_scene_name(scene_index=0, name='A/B\\C"D')`
- **Verify:** `get_scenes` → scene 0 `name` — check for escaping issues or truncation.

#### A19 — Newline in name
- **Action:** `set_scene_name(scene_index=0, name="Line1\nLine2")`
- **Verify:** `get_scenes` → scene 0 `name` — does it store the newline, strip it, or error?

---

### Out-of-Bounds Indices

#### A20 — track_index beyond track count
- **Action:** `set_track_volume(track_index=999, volume=0.5)`
- **Hypothesis:** Error with a clear message. Should not crash the remote script.

#### A21 — track_index = -1
- **Action:** `set_track_volume(track_index=-1, volume=0.5)`
- **Hypothesis:** Danger zone — Python's `-1` index resolves to the *last* item in a list. May silently modify the last track instead of erroring.
- **Verify:** `get_track_info` on the last known track — check if volume changed.

#### A22 — scene_index beyond scene count
- **Action:** `set_scene_name(scene_index=999, name="Ghost")`
- **Hypothesis:** Error with a clear message.

#### A23 — scene_index = -1
- **Action:** `set_scene_name(scene_index=-1, name="Last?")`
- **Hypothesis:** Same Python negative-index risk as A21 — may silently modify last scene.
- **Verify:** `get_scenes` → check last scene name.

#### A24 — return_index beyond return track count
- **Action:** `set_return_track_volume(return_index=999, volume=0.5)`
- **Hypothesis:** Error with a clear message.

#### A25 — return_index = -1
- **Action:** `set_return_track_volume(return_index=-1, volume=0.5)`
- **Hypothesis:** Same silent-last-item risk.
- **Verify:** `get_return_tracks` → check last return track volume.

---

### State Conflicts

#### A26 — Solo two tracks simultaneously
- **Action:** `set_track_solo(track_index=0, solo=true)` then `set_track_solo(track_index=1, solo=true)`
- **Verify:** `get_track_info(0)` and `get_track_info(1)` → check `solo` on both
- **Hypothesis:** Ableton may auto-unsolo track 0 when track 1 is soloed, or both may be soloed.

#### A27 — Arm multiple tracks simultaneously
- **Action:** `set_track_arm(0, true)` then `set_track_arm(1, true)`
- **Verify:** `get_track_info(0)` and `get_track_info(1)` → check `arm` on both
- **Hypothesis:** Ableton may auto-disarm track 0 (exclusive arm mode is common).

#### A28 — Delete a currently-firing scene
- **Action:** `fire_scene(scene_index=0)` then immediately `delete_scene(scene_index=0)`
- **Hypothesis:** Clips stop or keep playing on the now-orphaned scene. Possible crash.

#### A29 — Create a clip on a slot that already has one
- **Action:** `create_clip(track_index=0, scene_index=0, length=4)` twice
- **Hypothesis:** Second call overwrites, errors, or silently no-ops.

#### A30 — fire_scene on an empty scene (no clips)
- **Action:** Ensure scene 7 is empty, then `fire_scene(scene_index=7)`
- **Hypothesis:** No-op or error. Should not crash.

---

### MIDI Note Edge Cases

#### A31 — Velocity 0
- **Action:** `add_notes_to_clip(track_index=0, scene_index=0, notes=[{pitch: 60, time: 0, duration: 0.5, velocity: 0}])`
- **Hypothesis:** Velocity 0 is a MIDI note-off. Ableton may reject it, clamp to 1, or store it.

#### A32 — Pitch at floor and ceiling
- **Action:** `add_notes_to_clip(0, 0, notes=[{pitch: 0, time: 0, duration: 0.5, velocity: 100}, {pitch: 127, time: 0.5, duration: 0.5, velocity: 100}])`
- **Hypothesis:** Both accepted.

#### A33 — Note duration 0
- **Action:** `add_notes_to_clip(0, 0, notes=[{pitch: 60, time: 0, duration: 0.0, velocity: 100}])`
- **Hypothesis:** Error or note is ignored.

#### A34 — Note duration negative
- **Action:** `add_notes_to_clip(0, 0, notes=[{pitch: 60, time: 0, duration: -1.0, velocity: 100}])`
- **Hypothesis:** Error or crash.

#### A35 — Note time beyond clip length
- **Action:** Create a 4-bar clip, then add a note at `time=8.0` (beyond the 4-bar boundary)
- **Hypothesis:** Silently wrapped, clipped, or error.

#### A36 — Overlapping notes (same pitch)
- **Action:** `add_notes_to_clip(0, 0, notes=[{pitch: 60, time: 0, duration: 2.0, velocity: 100}, {pitch: 60, time: 1.0, duration: 2.0, velocity: 80}])`
- **Hypothesis:** Ableton accepts overlapping notes, or auto-trims the first.

#### A37 — Large note batch (500 notes)
- **Action:** `add_notes_to_clip(0, 0, notes=[{pitch: i%128, time: i*0.1, duration: 0.1, velocity: 100} for i in range(500)])`
- **Hypothesis:** Accepted, or socket/buffer limit hit. Tests OSC message size limits.

---

### Rapid Sequential Calls

#### A38 — Rapid volume changes (10 calls, same track)
- **Action:** Call `set_track_volume(0, v)` 10 times with values 0.1 through 1.0 in quick succession (no delay between calls)
- **Verify:** `get_track_info(0)` → `volume` should match the last value sent (1.0)
- **Hypothesis:** Last write wins. Could expose a race condition or dropped message.

#### A39 — fire_scene immediately followed by stop_all_clips
- **Action:** `fire_scene(0)` then `stop_all_clips` with no delay
- **Hypothesis:** Clean stop. Could expose a timing race in the remote script.

---

## Known Behaviors / Notes

### Verified in test run 2026-05-04

**Ableton-native behaviors (expected, not bugs):**
- **Color snapping:** Ableton maps requested RGB values to the nearest palette color. Read-back color may differ from the value written. Black (0x000000) and white (0xFFFFFF) are valid and accepted without snapping.
- **Color out of range:** Values > 0xFFFFFF or negative return a clean "Color value out of range" error.
- **`create_scene` name inheritance:** A new scene inherits the name and tempo (but not color) of the scene at the insertion index. Ableton-native behavior.
- **Tempo sentinel:** `tempo == -1.0` in `get_scenes` means "no tempo override" — not a real BPM value.
- **Tempo range:** Ableton enforces 20–999 BPM. Values of 0 or negative return a clean "Tempo out of range" error. Scene tempo negatives behave the same.
- **Float precision:** Tempos and pan/volume values are stored as 32-bit floats; expect minor rounding (e.g. 93.3 → 93.300003).
- **Volume/panning clamping:** Values outside [0.0, 1.0] for volume and [-1.0, 1.0] for panning are clamped silently by Ableton. No error is returned.
- **Return track name prefix:** Ableton auto-prefixes return track names with their letter label (A-, B-, C-). Setting name "Reverb" becomes "A-Reverb".
- **Multi-solo and multi-arm:** Ableton allows multiple MIDI tracks to be soloed or armed simultaneously. No exclusive enforcement.
- **`create_clip` silent overwrite:** Creating a clip on an occupied slot silently replaces the existing clip with no warning. Ableton-native.
- **Velocity 0 accepted:** Ableton stores notes with velocity 0 without error. In the MIDI wire protocol this means note-off, but inside Live's clip model it is stored as a very quiet note.
- **Duration 0 accepted:** Zero-length notes are stored silently. They produce no audible output.
- **Notes past clip boundary accepted:** Notes with `start_time` beyond the clip length are stored silently. They don't play but remain in the data.
- **Overlapping same-pitch notes accepted:** Ableton stores them; playback behavior depends on the instrument.
- **Large note batches:** 335+ notes in a single `add_notes_to_clip` call handled without buffer issues.
- **Rapid sequential writes:** 10 parallel writes to the same parameter all landed; last value wins. No dropped messages or race conditions observed.
- **fire_scene on empty scene:** No error. Ableton accepts it as a no-op.
- **fire_scene then delete_scene:** Clean. The scene is deleted; no crash.
- **fire_scene then stop_all_clips immediately:** No race condition observed.

**Index validation:**
- All out-of-bounds indices (999, -1, -2, etc.) return clean "index out of range" errors. The Python negative-index trap is handled server-side — index -1 does NOT silently resolve to the last item.

**Browser:**
- `get_browser_tree` returns display names (e.g. "Audio Effects") but `get_browser_items_at_path` originally required snake_case keys (e.g. "audio_effects"). **Fixed:** path input is now normalized with `.lower().replace(" ", "_")` so both forms work.
- Drum kit URIs are FileId-based (e.g. `query:Drums#FileId_12860`). Use `get_browser_items_at_path("Drums")` to enumerate available kits.

**Clip read-back:**
- `get_track_info` exposes `clip_slots[n].clip.name`, `length`, `is_playing`, and `is_recording`. Clip name and playback state ARE readable without a dedicated `get_clip_info` tool.
- Use `get_notes_from_clip` to read individual MIDI notes from a clip.

**Device loading:**
- `get_track_info` and `get_return_tracks` expose the `devices` array, so device loading can be verified via read-back.
- `get_device_parameters` and `set_device_parameter` are now implemented (Phase 8 in TEST_SUITE, "Phase 3 — Device Parameters" in roadmap).
