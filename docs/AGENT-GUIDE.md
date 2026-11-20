# Developing the extended ableton-mcp tools

This fork adds tools on top of upstream ableton-mcp 1.4.5 (Remote Script 1.7.1 → 1.8.0) without
reshaping upstream's files, so upstream releases still merge cleanly.

## Where things live

| Piece | File |
| --- | --- |
| Live-side commands | `AbletonMCP_Remote_Script/__init__.py`: `EXTENDED_COMMANDS` registry (name → handler, main-thread?) and the `_cmd_*` handlers in the "Extended commands" section. One hook in `_process_command` routes them. |
| Bundled copy the installer ships | `MCP_Server/bundled_ableton_remote_script/AbletonMCP_init.py`. Must be byte-identical: `cp AbletonMCP_Remote_Script/__init__.py MCP_Server/bundled_ableton_remote_script/AbletonMCP_init.py` |
| MCP tools | `MCP_Server/extended_tools.py`, registered from `server.py` by `extended_tools.register(...)`. Writing commands go in `MODIFYING_COMMANDS` (longer socket timeout). |
| Fake Live objects | `tests/live_fakes.py`. Same attribute names as the real Python LOM; every write is logged in `song.history`. |
| Unit tests | `tests/test_extended_commands.py`, `tests/test_mixer_routing.py` (script side), `tests/test_extended_tools.py` (tool side, through `FastMCP.call_tool`) |
| Live tests | `scripts/live_harness.py` + `scripts/live_test*.py` |
| Safety switches | `MCP_Server/safety.py`: command -> category, config `~/.config/ableton-mcp/safety.json` (env `ABLETON_MCP_SAFETY_CONFIG`), checked in `AbletonConnection.send_command` before anything reaches Live. New writing commands must get a category in `CATEGORIES` (unlisted non-`get_*` commands count as `edit`). |
| Host-side audio check | `scripts/ableton_io_check.py` (`~/bin/ableton-io-check`): Live <-> Scarlett links, Line Out sources, USB stream, `--listen` levels |
| LOM coverage | `scripts/api_coverage.py` → `docs/api-coverage.md`; roadmap in `docs/fork-roadmap.md` |

## Adding a command

1. Handler `_cmd_<name>(self, params)` in the Remote Script; add it to `EXTENDED_COMMANDS` with
   `True` if it writes (it then runs on Live's main thread). Resolve tracks with
   `self._resolve_track(params)` (`track_type` track/return/master). Read with `self._read(...)` so a
   property Live refuses becomes `null` + an `unavailable` reason, never a fake 0/False.
2. Validate everything before the first write, so a refused call changes nothing. Build the reply
   (anything read back after the write) inside `return Later(lambda: ...)`, or it shows the old state.
3. Tool in `extended_tools.register()`; writers also go in `MODIFYING_COMMANDS`.
4. Tests: script side against `FakeSong` (assert `song.history == []` on refusals), tool side for the
   params forwarded. `test_every_remote_command_has_a_tool` keeps the two lists in step.
5. Give the command a safety category in `MCP_Server/safety.py` if it writes (test_safety checks every
   MODIFYING_COMMANDS entry has one).
6. Bump `SCRIPT_VERSION` and `EXPECTED_REMOTE_SCRIPT_VERSION` together when the command surface changes
   (versions are compared for equality only, so 1.10.0 after 1.9.0 is fine).
7. Add a live test, regenerate `docs/api-coverage.md`, update the ableton skill.

## Testing

```sh
uv run --frozen --with pytest pytest -q          # unit tests, no Live needed
scripts/deploy.sh                                # tests, then install server (editable) + Remote Script
# restart Live with an EMPTY set (File > New Live Set); reconnect the MCP server
python3 scripts/live_test.py                     # undo/redo/delete_track
python3 scripts/live_test_mixer.py               # mixer, routing, monitoring, meters, automation
python3 scripts/live_test_devices.py             # 1.9.0: safety, devices, signal path, clips, scenes
python3 scripts/live_test_transport.py           # 1.10.0: transport, settings, locators, notes by id
scripts/restart_live.sh                          # guarded kill + relaunch (empty set only)
```

Each live-test run gets its own safety config (everything allowed except deletes in saved sets), so the
user's switches don't change results; `m.set_safety({...})` switches categories mid-test.

`restart_live.sh` refuses unless the guard passes (or `--unresponsive-ok` after checking the set by other
means), hard-kills Live, and moves `CrashDetection.cfg` / `CrashRecoveryInfo.cfg` to
`~/programs/ableton-mcp-crash-markers/` so Live doesn't stop on the recovery dialog. It still can't get past
Live's other startup modals (the Trial's online licence check, update prompts): while one is open Live's
Python threads get no time, port 9877 accepts at the kernel level but nothing answers ("No data received").
With the screen locked nothing can dismiss them, so unattended restarts only work while Jeremy is around.

Use `--frozen` so uv doesn't rewrite `uv.lock`.

Live tests refuse any set with more than 4 tracks, a track not named like Live's defaults
(`1-MIDI`, `3-Audio`) or more than 2 returns; `--force` only overrides clips/devices on default tracks.
They create `mcp-test-*` tracks, touch only those, and delete them (`--keep` leaves them).
**Never run them, or try a new write command, on a song.**

## Live/LOM facts learned

- Live loads Remote Scripts only at startup: a new script needs a Live restart.
- Live ran a stale `__pycache__/__init__.cpython-311.pyc` instead of the newer source (1.7.1 bytecode with
  1.8.0 source); deploy.sh now deletes `__pycache__`.
- Live merged an API `set_track_name` and a following `delete_track` into one undo step; extended writes now
  run inside `song.begin_undo_step()` / `end_undo_step()` (Python API, not in the Max LOM docs).
- `Song.file_path` / `Song.name` are empty for an unsaved set: that is how saved sets (songs) are told apart.
- Device sidechain routing: Compressor (and others with a sidechain) expose `input_routing_type` /
  `input_routing_channel` / `available_*` like a track.
- Several clients may connect to port 9877 at once (one thread each).
- `Track.solo` set through the API doesn't unsolo other tracks; `set_track_mixer(exclusive_solo=true)` does.
- Volume is 0..1 (0.85 = 0 dB, 1.0 = +6 dB); `volume_db` bisects `str_for_value` to find the value.
- Return tracks DO have input routing in Live 12 (measured 2026-11-19: Ext. In 1/2, choices incl.
  Resampling); the master has no mute/solo/sends.
- **Writes land when the main-thread tick ends.** Reading a property back in the same tick returns the
  old value: `Song.loop`, `Track.solo`, `current_song_time` (2026-11-19). Upstream's `create_locator`
  moved the playhead and toggled the cue in one tick, so the cue landed at the old position; it is
  replaced by a version that takes three ticks. A handler that needs the result returns `Later(fn)`
  (see `_run_extended`); the undo step spans the ticks.
- Live 12's Utility calls its level parameter **Output** (Live 11: Gain).
- Live returns a **new Python wrapper per read**: `song.tracks[0] is song.tracks[0]` is False. Compare
  positions, never identity (exclusive solo unsoloed its own target until 2026-11-20).
- `Track.muted_via_solo` stayed False 2 s after a solo (2026-11-20, screen locked); `silenced_by_solo`
  is worked out from the solo states instead.
- Reading `RackDevice.has_drum_pads` on a non-drum rack raises ("Only drum racks can have pads!");
  use `_is_drum_rack`. `DrumPad.name` has no setter (a pad shows its first chain's name); Live ignores
  mute on an empty pad.
- `Live.Clip.WarpMarker(sample_time, beat_time)`: positional, both required; `sample_time` is seconds,
  `Clip.sample_length` is samples.
- Live names External Audio Effect "Ext. Audio Effect" in a device chain.
- Not in the LOM: Track Delay, arrangement automation envelopes, Live's audio I/O preferences.
