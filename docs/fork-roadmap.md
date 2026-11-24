# Fork roadmap: LOM features ableton-mcp doesn't expose

Generated from `python3 scripts/api_coverage.py` against the Live 12.4.5 LOM reference on 2026-11-01:
the Remote Script references **109 of 570** LOM members. Name matching overcounts, so many of the 109 are
only read, never set (`mute`, `solo`, `arm`, `volume`, `panning` are reported but never written).

Not possible through the LOM at all: Track Delay, reading/deleting **arrangement** automation envelopes,
Live's audio Input/Output Config (app settings), saving the set, exporting audio, warping a clip to
another tempo map by analysis, Stem Separation, MIDI Generators/Transformations.

## Tier 1: mixer, routing, monitoring, meters (what gets checked by eye)

| Tool | LOM | Notes |
| --- | --- | --- |
| `get_track_routing(track, track_type)` | `Track.input/output_routing_type/_channel`, `available_*` | Current + choices, e.g. Ext. In 3/4, Ext. Out 3 |
| `set_track_routing(...)` | same, set | Match by display name; error lists valid choices |
| `set_track_monitoring(in/auto/off)` | `Track.current_monitoring_state` | Not in the local LOM page, is in the Python API |
| `get_track_meters(tracks, duration)` | `input/output_meter_left/right/level` | Sample for N ms, return peak: "is signal leaving X, arriving on Y" |
| `get_mixer_state()` | all of the above + `muted_via_solo`, sends | One call for every track, return and master |
| `set_track_mixer(volume, volume_db, pan, sends, mute, solo, arm)` | `MixerDevice.volume/panning/sends`, `Track.mute/solo/arm` | dB via `str_for_value` bisection; solo is non-exclusive in the API |
| `back_to_arrangement()` | `Song.back_to_arranger` | Read + trigger |
| `get_overridden_automation()` / `re_enable_automation(...)` | `DeviceParameter.automation_state`, `.re_enable_automation`, `Song.re_enable_automation` | Find which params you overrode, re-enable one or all |
| return + master tracks | `Song.return_tracks`, `Song.master_track` | Every tool above takes `track_type` |

Status: built in 1.8.0 (with `undo`, `redo`, `get_undo_state`, `delete_track`), unit-tested; live test
`scripts/live_test_mixer.py`.

## Status (2026-11-01)

| Version | What | Unit tests | Live tested |
| --- | --- | --- | --- |
| 1.8.0 | Tier 1 + undo/redo/delete_track | yes | live_test.py 16/17 (undo merged rename+delete: fixed in 1.9.0 with one undo step per call), live_test_mixer.py not yet |
| 1.9.0 | safety switches; Tier 2 (all but presets); device display values; signal path; clip info/properties; scenes | yes | live_test_devices.py not yet |
| 1.10.0 | Tier 4 (transport, settings, locators, CPU); Tier 3 notes by id, quantize, duplicate_loop, crop | yes | 2026-11-19 (on 1.10.0): live_test.py 17/17, live_test_mixer.py 39/43, live_test_transport.py 27/31, live_test_devices.py crashed (Utility's "Gain" is "Output" in Live 12) |
| 1.11.0 | insert_device by name, plugin presets, racks (macros, variations, chains), drum pads, Simpler, arrangement clip create/delete, note edits (quantize_pitch, duplicate_region/notes), warp markers, session clip envelopes; `Later` (next-tick readback) fixing the 1.10.0 live failures; create_locator replaced | yes | 2026-11-20 all green: live_test.py 17/17, mixer 43/43, devices 47/47, transport 29/29, racks 21/21 (pad mute/rename on a loaded pad and copy_drum_pad not live-tested: no API to load a pad) |

The 1.10.0 live failures were all one cause, except the test assumptions: writes apply when Live's tick
ends, so same-tick readbacks (loop, solo) were stale and upstream's create_locator put the cue at the
old playhead. Fixed in 1.11.0 and confirmed live 2026-11-20, along with five more Live facts (see AGENT-GUIDE).

Still open: Tier 5 device-specific tools beyond Simpler (Wavetable, Drift, EQ Eight specifics),
`map_rack_magnitude` tool, arrangement envelopes (not in the API), take lanes.

## Tier 2: editing safety and structure

- Sidechain / device input routing (`DeviceIO`: `routing_type`, `routing_channel`, `available_routing_*`),
  e.g. a compressor's sidechain source.

- `undo` / `redo` (`Song.undo/redo`, `can_undo`): lets the agent revert its own mistake.
- `delete_track`, `duplicate_track`, `delete_device`, `move_device` (`Song.move_device`).
- `create_return_track`, `create_scene`, `duplicate_scene`, `delete_scene`, scene name/tempo/time signature.
- `set_track_color`, `fold_state`, group info (`is_grouped`, `group_track`).
- `get_device_parameters` with `display_value`/`str_for_value`, `is_quantized`/`value_items` (show "-6 dB", not 0.72).
- Device on/off (`is_active` + `track_activator`), plugin presets (`PluginDevice.presets`).

## Tier 3: clips

- Clip properties: loop start/end, start/end markers, looping, muted, gain, pitch, warp mode, warping,
  launch mode/quantization, color.
- Note editing by id (`get_all_notes_extended`, `apply_note_modifications`, `remove_notes_extended`):
  true edits without clear-and-rewrite; probability/velocity deviation fields.
- `quantize`, `quantize_pitch`, `duplicate_loop`, `crop`, `duplicate_region`.
- Session clip envelopes (`clear_envelope`, `clear_all_envelopes`). Arrangement envelopes stay out of reach.
- Arrangement: `Track.create_midi_clip(start, length)`, `create_audio_clip(path, position)`, `delete_clip`.
- Warp markers (`add/move/remove_warp_marker`).

## Tier 4: transport and song settings

- Loop on/start/length, metronome, overdub, record mode, punch in/out, session record, count-in.
- Global quantization, groove amount, swing; scale (`root_note`, `scale_name`).
- Cue points: `jump_to_next/prev_cue`, `CuePoint.jump`.
- `stop_all_clips`, `capture_midi`, `tap_tempo`, CPU (`Application.average/peak_process_usage`).

## Tier 5: device-specific

Simpler/Sample (slices, warp, crop, reverse, `replace_sample`), Rack chains (`insert_chain`, variations,
macros), Drum pads (`copy_pad`), Wavetable/Drift/Meld/EQ Eight specifics.

Also unexposed already-written script commands: `inspect_rack`, `map_rack_magnitude`.
