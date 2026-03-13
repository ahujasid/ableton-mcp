# Roadmap: AbletonMCP

## Overview

This roadmap transforms an existing but broken MCP server into a production-quality Ableton Live 12 bridge. The journey moves in three arcs: first, repair the foundation so the server is reliable (Phases 1-2); second, expand coverage across every production domain (Phases 3-8); third, add advanced capabilities that differentiate from competing implementations (Phases 9-10). Every phase delivers a coherent, verifiable capability — nothing is a pure "all models then all APIs" layer cake.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation Repair** - Fix the broken correctness issues that make the current server unreliable
- [ ] **Phase 2: Infrastructure Refactor** - Build extensible architecture before feature expansion
- [ ] **Phase 3: Track Management** - Full track type coverage (MIDI, audio, return, group)
- [ ] **Phase 4: Mixing Controls** - Complete mixer surface (volume, pan, mute, solo, sends)
- [ ] **Phase 5: Clip Management** - Full clip lifecycle (create, edit, loop, launch, delete)
- [ ] **Phase 6: MIDI Editing** - Complete MIDI note editing (add, read, remove, quantize, transpose)
- [ ] **Phase 7: Device & Browser** - Working instrument loading plus full device parameter control
- [ ] **Phase 8: Scene & Transport** - Scene management plus complete transport and session control
- [ ] **Phase 9: Automation** - Clip automation envelopes for parameter movement
- [ ] **Phase 10: Routing & Audio Clips** - Track routing control and audio clip properties

## Phase Details

### Phase 1: Foundation Repair
**Goal**: The server handles errors visibly, instrument loading works reliably, and concurrent tool calls do not crash
**Depends on**: Nothing (first phase)
**Requirements**: FNDN-01, FNDN-02, FNDN-03, FNDN-04, FNDN-05, FNDN-06
**Success Criteria** (what must be TRUE):
  1. Loading an instrument onto a MIDI track results in audible sound when notes play — no silent clips
  2. Running two MCP tool calls simultaneously does not crash or corrupt the connection
  3. Any failure in a tool call surfaces an error message — no silent pass-through
  4. The Remote Script communicates with the MCP server using length-prefix framing without parsing errors
  5. All Python 2 compatibility code is absent from the codebase — no `from __future__`, no `Queue as queue`, no `decode()` try/except
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — Python 3 cleanup: strip Py2 code, upgrade to Py3.11 idioms, replace bare excepts, set up test infrastructure
- [ ] 01-02-PLAN.md — Protocol and concurrency: length-prefix framing on both sides, threading.Lock, remove time.sleep delays, ping command
- [ ] 01-03-PLAN.md — Dispatch and reliability: dict-based command router, fix instrument loading, browser typo fix, health-check tool

### Phase 2: Infrastructure Refactor
**Goal**: The codebase is organized into domain modules with a scalable dispatch architecture ready to accept 50+ commands
**Depends on**: Phase 1
**Requirements**: FNDN-07, FNDN-08, FNDN-09, FNDN-10
**Success Criteria** (what must be TRUE):
  1. Adding a new MCP tool requires touching exactly one domain module and one handler file — no monolithic files to edit
  2. The Remote Script dispatches commands via dict lookup — no if/elif chain exists
  3. Linting passes with ruff on both the MCP server and Remote Script codebases
  4. A test suite with pytest can run smoke tests against the server using FastMCP in-memory client
**Plans**: TBD

Plans:
- [ ] 02-01: Extract Remote Script handlers into domain package (base.py, transport.py, tracks.py, clips.py, notes.py, devices.py, mixer.py, scenes.py, browser.py) with @main_thread decorator
- [ ] 02-02: Replace if/elif command chain with dict-based CommandDispatcher router
- [ ] 02-03: Split MCP_Server/server.py into tools/ domain modules (tracks, clips, mixing, devices, scenes, transport)
- [ ] 02-04: Configure ruff linting and establish pytest + pytest-asyncio test infrastructure with initial smoke tests

### Phase 3: Track Management
**Goal**: Users can create, configure, and inspect every track type that Ableton supports
**Depends on**: Phase 2
**Requirements**: TRCK-01, TRCK-02, TRCK-03, TRCK-04, TRCK-05, TRCK-06, TRCK-07, TRCK-08, TRCK-09
**Success Criteria** (what must be TRUE):
  1. User can create a MIDI track, an audio track, a return track, and a group track — each appears in Ableton's track list
  2. User can delete any track and it disappears from the session
  3. User can duplicate a track and the copy appears with its contents intact
  4. User can rename any track and set its color — changes reflect in Ableton's UI
  5. User can get full track info (name, type, devices, clips, routing) for any track in the session
**Plans**: TBD

Plans:
- [ ] 03-01: Implement TrackHandler in Remote Script — create_midi_track, create_audio_track, create_return_track, create_group_track
- [ ] 03-02: Implement delete_track, duplicate_track, rename_track, set_track_color in TrackHandler
- [ ] 03-03: Implement get_track_info with comprehensive response (name, type, devices, clips, arm state, routing)
- [ ] 03-04: Add corresponding MCP tools in tools/tracks.py with parameter validation

### Phase 4: Mixing Controls
**Goal**: Users can control the complete mixer surface — levels, panning, routing enables, and master/return channels
**Depends on**: Phase 3
**Requirements**: MIX-01, MIX-02, MIX-03, MIX-04, MIX-05, MIX-06, MIX-07, MIX-08
**Success Criteria** (what must be TRUE):
  1. User can set any track's volume and pan and hear the change immediately in Ableton
  2. User can mute, unmute, solo, and unsolo any track — state reflects in Ableton's mixer
  3. User can arm and disarm any track for recording
  4. User can set send levels from any track to any return channel
  5. User can set master track volume and return track volume/pan independently
**Plans**: TBD

Plans:
- [ ] 04-01: Implement MixerHandler in Remote Script — set_track_volume, set_track_pan, set_master_volume
- [ ] 04-02: Implement mute/unmute, solo/unsolo, arm/disarm in MixerHandler
- [ ] 04-03: Implement set_send_level and set_return_volume/pan in MixerHandler
- [ ] 04-04: Add corresponding MCP tools in tools/mixing.py

### Phase 5: Clip Management
**Goal**: Users can create, edit, launch, and delete clips with full control over loop and playback regions
**Depends on**: Phase 2
**Requirements**: CLIP-01, CLIP-02, CLIP-03, CLIP-04, CLIP-05, CLIP-06, CLIP-07, CLIP-08, CLIP-09
**Success Criteria** (what must be TRUE):
  1. User can create a MIDI clip of a specified length in any clip slot and it appears in Ableton's Session View
  2. User can delete a clip and it disappears from the slot
  3. User can duplicate a clip to another slot and the copy is independent
  4. User can set clip loop enabled/disabled and adjust loop start/end and clip start/end markers
  5. User can fire (launch) a clip and stop it — playback responds immediately
**Plans**: TBD

Plans:
- [ ] 05-01: Implement ClipHandler in Remote Script — create_midi_clip, delete_clip, duplicate_clip, rename_clip
- [ ] 05-02: Implement clip loop controls — set_clip_loop_enabled, set_clip_loop_start, set_clip_loop_end, set_clip_start_marker, set_clip_end_marker
- [ ] 05-03: Implement fire_clip and stop_clip in ClipHandler
- [ ] 05-04: Add corresponding MCP tools in tools/clips.py

### Phase 6: MIDI Editing
**Goal**: Users can read and write MIDI note data with full editing capabilities including quantize and transpose
**Depends on**: Phase 5
**Requirements**: MIDI-01, MIDI-02, MIDI-03, MIDI-04, MIDI-05
**Success Criteria** (what must be TRUE):
  1. User can add notes to a MIDI clip specifying pitch, start time, duration, and velocity — notes appear and play back
  2. User can read all notes from a clip and get the full list with their properties
  3. User can remove notes from a clip by specifying a time/pitch range — targeted notes disappear
  4. User can quantize notes in a clip to a specified grid size with adjustable strength
  5. User can transpose all notes in a clip by semitones — pitches shift correctly
**Plans**: TBD

Plans:
- [ ] 06-01: Implement NotesHandler in Remote Script — add_notes, get_notes with proper Live API note access
- [ ] 06-02: Implement remove_notes with time/pitch range filtering in NotesHandler
- [ ] 06-03: Implement quantize_clip_notes and transpose_clip_notes in NotesHandler
- [ ] 06-04: Add corresponding MCP tools in tools/notes.py

### Phase 7: Device & Browser
**Goal**: Users can load instruments and effects onto tracks reliably and control device parameters
**Depends on**: Phase 2
**Requirements**: DEV-01, DEV-02, DEV-03, DEV-04, DEV-05, DEV-06, DEV-07, DEV-08
**Success Criteria** (what must be TRUE):
  1. User can load an instrument onto a MIDI track from the browser and immediately play notes that produce sound
  2. User can load an effect onto any track from the browser and it appears in the device chain
  3. User can get all parameters of any device — name, current value, min, and max
  4. User can set any device parameter by name or index and hear the effect on the sound
  5. User can browse the Ableton browser tree by category and navigate to specific paths including Instrument Racks, Drum Racks, and Effect Racks
  6. User can get a bulk session state dump covering all tracks, clips, and devices in a single call
**Plans**: TBD

Plans:
- [ ] 07-01: Implement DeviceHandler in Remote Script — load_instrument, load_effect with race-condition-free loading verified by device count check
- [ ] 07-02: Implement get_device_parameters and set_device_parameter in DeviceHandler
- [ ] 07-03: Implement BrowserHandler — browse_browser_tree, navigate_browser_path with dict-based category dispatch (fixes instruments typo)
- [ ] 07-04: Implement rack navigation — navigate into Instrument Rack, Drum Rack, Effect Rack chains
- [ ] 07-05: Implement get_session_state bulk dump covering all tracks/clips/devices in DeviceHandler or a SessionHandler
- [ ] 07-06: Add corresponding MCP tools in tools/devices.py and tools/browser.py

### Phase 8: Scene & Transport
**Goal**: Users have complete control over Session View scenes and all transport/playback functions
**Depends on**: Phase 2
**Requirements**: SCNE-01, SCNE-02, SCNE-03, SCNE-04, TRNS-01, TRNS-02, TRNS-03, TRNS-04, TRNS-05, TRNS-06, TRNS-07, TRNS-08, TRNS-09, TRNS-10
**Success Criteria** (what must be TRUE):
  1. User can create, name, fire, and delete scenes — each action reflects immediately in Ableton's Session View
  2. User can start, stop, and continue playback — transport responds as expected
  3. User can stop all clips at once from a single tool call
  4. User can set tempo and time signature — changes take effect during or before playback
  5. User can set the loop region (enabled, start, length) and query the current playback position
  6. User can undo and redo the last action — Live's undo history is accessible
**Plans**: TBD

Plans:
- [ ] 08-01: Implement SceneHandler in Remote Script — create_scene, set_scene_name, fire_scene, delete_scene
- [ ] 08-02: Implement TransportHandler in Remote Script — start_playback, stop_playback, continue_playback, stop_all_clips
- [ ] 08-03: Implement tempo, time signature, loop region, and playback position in TransportHandler
- [ ] 08-04: Implement undo and redo in TransportHandler
- [ ] 08-05: Add corresponding MCP tools in tools/scenes.py and tools/transport.py

### Phase 9: Automation
**Goal**: Users can read, write, and clear clip automation envelopes for device parameter movement over time
**Depends on**: Phase 7
**Requirements**: AUTO-01, AUTO-02, AUTO-03
**Success Criteria** (what must be TRUE):
  1. User can get the automation envelope for a specific device parameter in a clip — returns breakpoint data
  2. User can insert automation breakpoints at specified positions and values — parameter moves in playback
  3. User can clear all automation from a clip's envelopes — parameters return to static values
**Plans**: TBD

Plans:
- [ ] 09-01: Implement AutomationHandler in Remote Script — get_clip_envelope, insert_envelope_breakpoints, clear_clip_envelopes
- [ ] 09-02: Add corresponding MCP tools in tools/automation.py with parameter targeting by device and parameter name

### Phase 10: Routing & Audio Clips
**Goal**: Users can inspect and set track signal routing and control audio clip properties
**Depends on**: Phase 3
**Requirements**: ROUT-01, ROUT-02, ROUT-03, ROUT-04, ACLP-01, ACLP-02, ACLP-03
**Success Criteria** (what must be TRUE):
  1. User can get available input and output routing types for any track
  2. User can set a track's input and output routing — signal flow changes as expected
  3. User can set audio clip pitch (coarse and fine) and hear the transposition
  4. User can set audio clip gain and toggle warping on/off
**Plans**: TBD

Plans:
- [ ] 10-01: Implement RoutingHandler in Remote Script — get_input_routing_types, set_input_routing, get_output_routing_types, set_output_routing
- [ ] 10-02: Implement AudioClipHandler in Remote Script — set_clip_pitch_coarse, set_clip_pitch_fine, set_clip_gain, set_clip_warping
- [ ] 10-03: Add corresponding MCP tools in tools/routing.py and tools/audio_clips.py

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation Repair | 1/3 | In progress | - |
| 2. Infrastructure Refactor | 0/4 | Not started | - |
| 3. Track Management | 0/4 | Not started | - |
| 4. Mixing Controls | 0/4 | Not started | - |
| 5. Clip Management | 0/4 | Not started | - |
| 6. MIDI Editing | 0/4 | Not started | - |
| 7. Device & Browser | 0/6 | Not started | - |
| 8. Scene & Transport | 0/5 | Not started | - |
| 9. Automation | 0/2 | Not started | - |
| 10. Routing & Audio Clips | 0/3 | Not started | - |
