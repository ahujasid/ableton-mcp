# Requirements: AbletonMCP

**Defined:** 2026-03-10
**Core Value:** An AI assistant can produce actual music in Ableton — instruments load, notes play, effects shape sound, and the mix comes together.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Foundation

- [x] **FNDN-01**: Server runs on Python 3 only — all Python 2 compatibility code removed
- [x] **FNDN-02**: Remote Script uses Python 3.11 idioms (super(), f-strings, type hints, queue module)
- [x] **FNDN-03**: Socket protocol uses length-prefix framing instead of JSON-completeness parsing
- [x] **FNDN-04**: Global connection protected by threading.Lock for concurrent tool invocations
- [x] **FNDN-05**: All error handling uses specific exception types — no bare except:pass blocks
- [ ] **FNDN-06**: Remote Script command dispatch uses dict-based router instead of if/elif chain
- [ ] **FNDN-07**: MCP tools organized into domain modules (tracks, clips, mixing, etc.)
- [ ] **FNDN-08**: Remote Script handlers organized into domain modules with @main_thread decorator
- [ ] **FNDN-09**: Linting configured with ruff (target Python 3.11, PEP 8, import ordering)
- [ ] **FNDN-10**: Test infrastructure with pytest + pytest-asyncio using FastMCP in-memory client

### Track Management

- [ ] **TRCK-01**: User can create MIDI tracks at specified index
- [ ] **TRCK-02**: User can create audio tracks at specified index
- [ ] **TRCK-03**: User can create return tracks
- [ ] **TRCK-04**: User can create group tracks
- [ ] **TRCK-05**: User can delete any track by index
- [ ] **TRCK-06**: User can duplicate any track by index
- [ ] **TRCK-07**: User can rename any track
- [ ] **TRCK-08**: User can set track color
- [ ] **TRCK-09**: User can get detailed info about any track (name, type, devices, clips, routing)

### Mixing

- [ ] **MIX-01**: User can set track volume (0.0–1.0 normalized)
- [ ] **MIX-02**: User can set track pan (-1.0 to 1.0)
- [ ] **MIX-03**: User can mute/unmute any track
- [ ] **MIX-04**: User can solo/unsolo any track
- [ ] **MIX-05**: User can arm/disarm any track for recording
- [ ] **MIX-06**: User can set send levels for any track to any return
- [ ] **MIX-07**: User can set master track volume
- [ ] **MIX-08**: User can set return track volume and pan

### Clip Management

- [ ] **CLIP-01**: User can create MIDI clips with specified length in any clip slot
- [ ] **CLIP-02**: User can delete clips from any clip slot
- [ ] **CLIP-03**: User can duplicate clips to another slot
- [ ] **CLIP-04**: User can rename clips
- [ ] **CLIP-05**: User can set clip loop enabled/disabled
- [ ] **CLIP-06**: User can set clip loop start and end positions
- [ ] **CLIP-07**: User can set clip start and end markers
- [ ] **CLIP-08**: User can fire (launch) any clip
- [ ] **CLIP-09**: User can stop any clip

### MIDI Editing

- [ ] **MIDI-01**: User can add MIDI notes to a clip (pitch, start, duration, velocity)
- [ ] **MIDI-02**: User can read back all notes from a clip
- [ ] **MIDI-03**: User can remove notes from a clip (by time/pitch range)
- [ ] **MIDI-04**: User can quantize notes in a clip (grid size, strength)
- [ ] **MIDI-05**: User can transpose all notes in a clip by semitones

### Device & Browser

- [ ] **DEV-01**: User can load instruments onto tracks via browser (working — currently broken)
- [ ] **DEV-02**: User can load effects onto tracks via browser
- [ ] **DEV-03**: User can get all parameters of any device (name, value, min, max)
- [ ] **DEV-04**: User can set any device parameter by name or index
- [ ] **DEV-05**: User can browse the Ableton browser tree by category
- [ ] **DEV-06**: User can navigate browser items at a specific path
- [ ] **DEV-07**: User can navigate into Instrument Racks, Drum Racks, and Effect Racks
- [ ] **DEV-08**: User can get a bulk session state dump (all tracks, clips, devices in one call)

### Scene & Transport

- [ ] **SCNE-01**: User can create scenes
- [ ] **SCNE-02**: User can name scenes
- [ ] **SCNE-03**: User can fire (launch) scenes
- [ ] **SCNE-04**: User can delete scenes
- [ ] **TRNS-01**: User can start playback
- [ ] **TRNS-02**: User can stop playback
- [ ] **TRNS-03**: User can continue playback from current position
- [ ] **TRNS-04**: User can stop all clips
- [ ] **TRNS-05**: User can set tempo
- [ ] **TRNS-06**: User can set time signature (numerator and denominator)
- [ ] **TRNS-07**: User can set loop region (enabled, start, length)
- [ ] **TRNS-08**: User can get current playback position
- [ ] **TRNS-09**: User can undo last action
- [ ] **TRNS-10**: User can redo last undone action

### Automation

- [ ] **AUTO-01**: User can get automation envelope for a device parameter in a clip
- [ ] **AUTO-02**: User can insert automation breakpoints into a clip envelope
- [ ] **AUTO-03**: User can clear automation envelopes from a clip

### Routing

- [ ] **ROUT-01**: User can get available input routing types for a track
- [ ] **ROUT-02**: User can set track input routing
- [ ] **ROUT-03**: User can get available output routing types for a track
- [ ] **ROUT-04**: User can set track output routing

### Audio Clip Controls

- [ ] **ACLP-01**: User can set audio clip pitch (coarse and fine)
- [ ] **ACLP-02**: User can set audio clip gain
- [ ] **ACLP-03**: User can toggle audio clip warping on/off

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Session

- **SESS-01**: User can manage cue points (set, delete, jump to)
- **SESS-02**: User can configure clip follow actions (action type, chance, time)
- **SESS-03**: User can tap tempo
- **SESS-04**: User can toggle metronome
- **SESS-05**: User can set groove/swing amount

### MIDI Advanced

- **MIDA-01**: User can select/deselect specific notes in a clip
- **MIDA-02**: User can replace selected notes (selective editing workflow)

### Track Advanced

- **TRKA-01**: User can freeze/unfreeze tracks
- **TRKA-02**: User can create arrangement clips (if API supports it)
- **TRKA-03**: User can set scene tempo per scene

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Audio export / render | Live Python API does not expose export functions; only brittle GUI automation possible |
| Real-time audio input processing | MCP latency (100ms-1s) makes this impractical; requires hardware config |
| MIDI 2.0 features | Python Remote Script API does not expose MIDI 2.0 properties |
| Video features | Ableton's video support is minimal and not exposed in Python API |
| Max for Live device creation | Separate domain requiring Max/MSP knowledge; can load M4L devices but not create them |
| Parameter listeners / real-time push | Socket protocol is request-response; listeners need different architecture |
| Direct .als file manipulation | Undocumented gzip'd XML format; risks corrupting projects |
| Multi-session management | Socket server is one-to-one; port-per-instance adds complexity for edge-case benefit |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FNDN-01 | Phase 1 | Complete |
| FNDN-02 | Phase 1 | Complete |
| FNDN-03 | Phase 1 | Complete |
| FNDN-04 | Phase 1 | Complete |
| FNDN-05 | Phase 1 | Complete |
| FNDN-06 | Phase 1 | Pending |
| FNDN-07 | Phase 2 | Pending |
| FNDN-08 | Phase 2 | Pending |
| FNDN-09 | Phase 2 | Pending |
| FNDN-10 | Phase 2 | Pending |
| TRCK-01 | Phase 3 | Pending |
| TRCK-02 | Phase 3 | Pending |
| TRCK-03 | Phase 3 | Pending |
| TRCK-04 | Phase 3 | Pending |
| TRCK-05 | Phase 3 | Pending |
| TRCK-06 | Phase 3 | Pending |
| TRCK-07 | Phase 3 | Pending |
| TRCK-08 | Phase 3 | Pending |
| TRCK-09 | Phase 3 | Pending |
| MIX-01 | Phase 4 | Pending |
| MIX-02 | Phase 4 | Pending |
| MIX-03 | Phase 4 | Pending |
| MIX-04 | Phase 4 | Pending |
| MIX-05 | Phase 4 | Pending |
| MIX-06 | Phase 4 | Pending |
| MIX-07 | Phase 4 | Pending |
| MIX-08 | Phase 4 | Pending |
| CLIP-01 | Phase 5 | Pending |
| CLIP-02 | Phase 5 | Pending |
| CLIP-03 | Phase 5 | Pending |
| CLIP-04 | Phase 5 | Pending |
| CLIP-05 | Phase 5 | Pending |
| CLIP-06 | Phase 5 | Pending |
| CLIP-07 | Phase 5 | Pending |
| CLIP-08 | Phase 5 | Pending |
| CLIP-09 | Phase 5 | Pending |
| MIDI-01 | Phase 6 | Pending |
| MIDI-02 | Phase 6 | Pending |
| MIDI-03 | Phase 6 | Pending |
| MIDI-04 | Phase 6 | Pending |
| MIDI-05 | Phase 6 | Pending |
| DEV-01 | Phase 7 | Pending |
| DEV-02 | Phase 7 | Pending |
| DEV-03 | Phase 7 | Pending |
| DEV-04 | Phase 7 | Pending |
| DEV-05 | Phase 7 | Pending |
| DEV-06 | Phase 7 | Pending |
| DEV-07 | Phase 7 | Pending |
| DEV-08 | Phase 7 | Pending |
| SCNE-01 | Phase 8 | Pending |
| SCNE-02 | Phase 8 | Pending |
| SCNE-03 | Phase 8 | Pending |
| SCNE-04 | Phase 8 | Pending |
| TRNS-01 | Phase 8 | Pending |
| TRNS-02 | Phase 8 | Pending |
| TRNS-03 | Phase 8 | Pending |
| TRNS-04 | Phase 8 | Pending |
| TRNS-05 | Phase 8 | Pending |
| TRNS-06 | Phase 8 | Pending |
| TRNS-07 | Phase 8 | Pending |
| TRNS-08 | Phase 8 | Pending |
| TRNS-09 | Phase 8 | Pending |
| TRNS-10 | Phase 8 | Pending |
| AUTO-01 | Phase 9 | Pending |
| AUTO-02 | Phase 9 | Pending |
| AUTO-03 | Phase 9 | Pending |
| ROUT-01 | Phase 10 | Pending |
| ROUT-02 | Phase 10 | Pending |
| ROUT-03 | Phase 10 | Pending |
| ROUT-04 | Phase 10 | Pending |
| ACLP-01 | Phase 10 | Pending |
| ACLP-02 | Phase 10 | Pending |
| ACLP-03 | Phase 10 | Pending |

**Coverage:**
- v1 requirements: 53 total
- Mapped to phases: 53
- Unmapped: 0

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-10 after roadmap creation — all 53 requirements mapped*
