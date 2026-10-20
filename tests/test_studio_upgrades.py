"""Tests for the studio-upgrades fork: locator fix, mixer, drum pads, clip
copy, arrangement fill/delete/loop helpers and server-side note tiling.

Live-side code runs against small fakes of the Live Object Model; nothing
here needs Ableton or a network.
"""

import asyncio
import inspect
import json
import math
import queue

import pytest

import MCP_Server.server as server
from MCP_Server.remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION

from test_remote_script_bridge import (
    BUNDLED_SCRIPT,
    REPO_SCRIPT,
    _load_script_module,
    make_instance,
)

NEW_COMMANDS = [
    "set_track_mixer", "get_drum_pads", "copy_clip", "fill_arrangement",
    "delete_arrangement_clips", "back_to_arrangement", "set_arrangement_loop",
]


@pytest.fixture(scope="module")
def mod():
    return _load_script_module()


# ------------------------------------------------------------------ packaging

def test_repo_and_bundled_scripts_are_identical():
    assert REPO_SCRIPT.read_bytes() == BUNDLED_SCRIPT.read_bytes()


def test_version_handshake_matches(mod):
    assert mod.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION


def test_new_commands_are_advertised(mod):
    for name in NEW_COMMANDS + ["create_locator"]:
        assert name in mod.SCRIPT_CAPABILITIES


# ------------------------------------------------------------------ fakes

class Ticker:
    """Collects schedule_message callbacks and runs them one tick at a time,
    applying the song's deferred changes between ticks like Live does."""

    def __init__(self, song):
        self.song = song
        self.pending = []

    def schedule_message(self, delay, callback):
        self.pending.append(callback)

    def run(self, max_ticks=10):
        for _ in range(max_ticks):
            if not self.pending:
                return
            self.song.apply_deferred()
            batch, self.pending = self.pending, []
            for cb in batch:
                cb()


class Cue(object):
    def __init__(self, time, name=""):
        self.time = time
        self.name = name


class LocatorSong(object):
    """set_or_delete_cue() only shows up in cue_points on the next tick --
    the behaviour that broke the upstream same-tick implementation."""

    def __init__(self, cues=(), playing=False, snap=0.0):
        self.cue_points = list(cues)
        self.current_song_time = 0.0
        self.is_playing = playing
        self.snap = snap
        self._deferred = []
        self.toggles = 0

    def set_or_delete_cue(self):
        self.toggles += 1
        t = self.current_song_time + self.snap
        self._deferred.append(lambda: self.cue_points.append(Cue(t)))

    def apply_deferred(self):
        for fn in self._deferred:
            fn()
        self._deferred = []


def locator_instance(mod, song):
    inst = make_instance(mod)
    inst._song = song
    ticker = Ticker(song)
    inst.schedule_message = ticker.schedule_message
    return inst, ticker


def run_locator(mod, song, name, time):
    inst, ticker = locator_instance(mod, song)
    q = queue.Queue()
    inst._create_locator_async(name, time, q)
    ticker.run()
    return q.get_nowait()


# ------------------------------------------------------------------ create_locator

def test_locator_waits_a_tick_before_looking_for_the_cue(mod):
    song = LocatorSong()
    song.current_song_time = 12.0
    out = run_locator(mod, song, "Drop", 64.0)
    assert out["status"] == "success", out
    assert out["result"]["time"] == 64.0
    assert out["result"]["name"] == "Drop"
    assert song.toggles == 1
    assert song.current_song_time == 12.0  # playhead restored


def test_existing_locator_is_renamed_not_toggled_off(mod):
    song = LocatorSong(cues=[Cue(32.0, "old")])
    out = run_locator(mod, song, "Verse", 32.0)
    assert out["result"]["name"] == "Verse"
    assert song.toggles == 0
    assert len(song.cue_points) == 1


def test_locator_snapped_by_live_is_still_found(mod):
    song = LocatorSong(snap=0.25)
    out = run_locator(mod, song, "Break", 16.0)
    assert out["status"] == "success"
    assert out["result"]["time"] == 16.25


def test_locator_refuses_while_playing(mod):
    song = LocatorSong(playing=True)
    inst, _ = locator_instance(mod, song)
    with pytest.raises(Exception, match="Stop playback"):
        inst._create_locator_async("x", 8.0, queue.Queue())


def test_locator_failure_reports_existing_cues(mod):
    song = LocatorSong(cues=[Cue(0.0)])
    song.set_or_delete_cue = lambda: None  # Live ignores the toggle
    out = run_locator(mod, song, "Nope", 8.0)
    assert out["status"] == "error"
    assert "[0.0]" in out["message"]


def test_create_locator_dispatch_goes_through_scheduler(mod):
    song = LocatorSong()
    song.apply_deferred = lambda: None
    original = song.set_or_delete_cue

    def immediate():
        original()
        for fn in song._deferred:
            fn()
        song._deferred = []
    song.set_or_delete_cue = immediate

    inst = make_instance(mod)
    inst._song = song
    inst.schedule_message = lambda delay, cb: cb()
    resp = inst._process_command({"type": "create_locator",
                                  "params": {"name": "Intro", "time": 0.0}})
    assert resp["status"] == "success", resp
    assert resp["result"]["name"] == "Intro"


# ------------------------------------------------------------------ mixer

class VolumeParam(object):
    """Live-like fader: 0.85 is 0 dB, 1.0 is +6 dB, 0.0 is -inf."""
    min, max = 0.0, 1.0

    def __init__(self, value=0.85):
        self.value = value

    def str_for_value(self, v):
        if v <= 0:
            return "-inf dB"
        if v >= 0.85:
            db = (v - 0.85) / 0.15 * 6.0
        else:
            db = 40.0 * math.log10(v / 0.85)
        return "%.1f dB" % db


class LinearParam(object):
    def __init__(self, value=0.0, lo=0.0, hi=1.0):
        self.value, self.min, self.max = value, lo, hi

    def str_for_value(self, v):
        return "%.2f" % v


class Mixer(object):
    def __init__(self, n_sends=2):
        self.volume = VolumeParam()
        self.panning = LinearParam(0.0, -1.0, 1.0)
        self.sends = [LinearParam() for _ in range(n_sends)]


class Track(object):
    def __init__(self, name="T", devices=(), slots=0):
        self.name = name
        self.mixer_device = Mixer()
        self.mute = False
        self.solo = False
        self.devices = list(devices)
        self.clip_slots = [Slot() for _ in range(slots)]
        self.arrangement_clips = []
        self.placed = []

    def duplicate_clip_to_arrangement(self, clip, time):
        self.placed.append(time)

    def delete_clip(self, clip):
        self.arrangement_clips.remove(clip)


class Song(object):
    def __init__(self, tracks=(), returns=()):
        self.tracks = list(tracks)
        self.return_tracks = list(returns)
        self.master_track = Track("Master")
        self.back_to_arranger = True
        self.loop = False
        self.loop_start = 0.0
        self.loop_length = 4.0


def song_instance(mod, song):
    inst = make_instance(mod)
    inst._song = song
    return inst


def test_mixer_sets_volume_in_db(mod):
    song = Song([Track("Bass")])
    out = song_instance(mod, song)._set_track_mixer(0, volume_db=-6.0)
    assert out["volume_display"] == "-6.0 dB"
    assert out["changed"] == ["volume"]


def test_mixer_pan_mute_and_sends(mod):
    song = Song([Track("Keys")])
    out = song_instance(mod, song)._set_track_mixer(
        0, panning=-0.3, mute=True, sends={"1": 0.25})
    track = song.tracks[0]
    assert track.mixer_device.panning.value == pytest.approx(-0.3)
    assert track.mute is True
    assert track.mixer_device.sends[1].value == 0.25
    assert out["mute"] is True


def test_mixer_clamps_and_rejects_bad_send(mod):
    song = Song([Track("Pad")])
    inst = song_instance(mod, song)
    inst._set_track_mixer(0, panning=5.0)
    assert song.tracks[0].mixer_device.panning.value == 1.0
    with pytest.raises(IndexError):
        inst._set_track_mixer(0, sends={"7": 0.5})


def test_mixer_return_and_master(mod):
    song = Song([Track("A")], returns=[Track("Reverb")])
    inst = song_instance(mod, song)
    assert inst._set_track_mixer(0, track_type="return", volume_db=-10)["track_name"] == "Reverb"
    assert inst._set_track_mixer(0, track_type="master", volume_db=-1)["track_name"] == "Master"
    with pytest.raises(Exception):
        inst._set_track_mixer(0, track_type="master", mute=True)


# ------------------------------------------------------------------ drum pads

class Chain(object):
    def __init__(self, name, devices=()):
        self.name = name
        self.devices = list(devices)


class Pad(object):
    def __init__(self, note, name="", chains=()):
        self.note = note
        self.name = name
        self.chains = list(chains)
        self.mute = False
        self.solo = False


class DrumRack(object):
    can_have_drum_pads = True
    can_have_chains = True

    def __init__(self, loaded):
        self.name = "Kit"
        self.drum_pads = [Pad(n, loaded.get(n, ""),
                              [Chain(loaded[n])] if n in loaded else [])
                          for n in range(128)]
        self.chains = []


class InstrumentRack(object):
    can_have_drum_pads = False
    can_have_chains = True

    def __init__(self, inner):
        self.name = "Wrapper"
        self.chains = [Chain("c", [inner])]


def test_drum_pads_lists_loaded_pads_with_note_names(mod):
    rack = DrumRack({36: "Kick", 38: "Snare", 42: "Closed Hat"})
    song = Song([Track("Drums", devices=[rack])])
    out = song_instance(mod, song)._get_drum_pads(0)
    assert out["pad_count"] == 3
    assert out["pads"][0] == {"note": 36, "note_name": "C1", "name": "Kick",
                              "mute": False, "solo": False, "chains": ["Kick"]}
    assert [p["note_name"] for p in out["pads"]] == ["C1", "D1", "F#1"]


def test_drum_pads_finds_nested_rack(mod):
    rack = DrumRack({60: "Clap"})
    song = Song([Track("Drums", devices=[InstrumentRack(rack)])])
    out = song_instance(mod, song)._get_drum_pads(0)
    assert out["pads"][0]["note_name"] == "C3"


def test_drum_pads_without_rack_errors(mod):
    song = Song([Track("Bass")])
    with pytest.raises(Exception, match="No Drum Rack"):
        song_instance(mod, song)._get_drum_pads(0)


def test_drum_pads_runs_off_main_thread_via_dispatch(mod):
    song = Song([Track("Drums", devices=[DrumRack({36: "Kick"})])])
    resp = song_instance(mod, song)._process_command(
        {"type": "get_drum_pads", "params": {"track_index": 0}})
    assert resp["status"] == "success"
    assert resp["result"]["pads"][0]["name"] == "Kick"


# ------------------------------------------------------------------ clips

class Clip(object):
    def __init__(self, name="Groove", length=4.0, notes=(), start_time=0.0):
        self.name = name
        self.length = length
        self.is_midi_clip = True
        self.start_time = start_time
        self._notes = list(notes)

    def set_notes(self, notes):
        self._notes.extend(notes)


class Slot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None

    def delete_clip(self):
        self.clip = None

    def create_clip(self, length):
        self.clip = Clip(name="", length=length)


class DupSlot(Slot):
    def duplicate_clip_to(self, other):
        other.clip = Clip(self.clip.name, self.clip.length, self.clip._notes)


def test_copy_clip_uses_duplicate_clip_to(mod):
    t = Track("Bass")
    t.clip_slots = [DupSlot(Clip("Line A", 8.0)), DupSlot()]
    out = song_instance(mod, Song([t]))._copy_clip(0, 0, 0, 1, new_name="Line B")
    assert out["method"] == "duplicate_clip_to"
    assert t.clip_slots[1].clip.name == "Line B"
    assert t.clip_slots[0].clip.name == "Line A"


def test_copy_clip_falls_back_to_note_copy(mod):
    src = Clip("Keys", 4.0)
    a, b = Track("A"), Track("B")
    a.clip_slots = [Slot(src)]
    b.clip_slots = [Slot()]
    inst = song_instance(mod, Song([a, b]))
    inst._notes_from_clip = lambda clip: [
        {"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 90, "mute": False}]
    out = inst._copy_clip(0, 0, 1, 0)
    assert out["method"] == "note_copy"
    assert b.clip_slots[0].clip._notes == [(60, 0.0, 1.0, 90, False)]
    assert b.clip_slots[0].clip.name == "Keys"


def test_copy_clip_will_not_overwrite_by_default(mod):
    t = Track("T")
    t.clip_slots = [DupSlot(Clip("a")), DupSlot(Clip("b"))]
    inst = song_instance(mod, Song([t]))
    with pytest.raises(Exception, match="overwrite"):
        inst._copy_clip(0, 0, 0, 1)
    inst._copy_clip(0, 0, 0, 1, overwrite=True)
    assert t.clip_slots[1].clip.name == "a"


def test_fill_arrangement_places_back_to_back(mod):
    t = Track("Drums")
    t.clip_slots = [Slot(Clip("Beat", 8.0))]
    out = song_instance(mod, Song([t]))._fill_arrangement(0, 0, 32.0, 64.0)
    assert t.placed == [32.0, 40.0, 48.0, 56.0]
    assert out["copies"] == 4
    assert out["ends_at"] == 64.0


def test_fill_arrangement_custom_step_and_bad_range(mod):
    t = Track("Hats")
    t.clip_slots = [Slot(Clip("Hat", 4.0))]
    inst = song_instance(mod, Song([t]))
    inst._fill_arrangement(0, 0, 0.0, 16.0, step=8.0)
    assert t.placed == [0.0, 8.0]
    with pytest.raises(ValueError):
        inst._fill_arrangement(0, 0, 16.0, 16.0)


def test_delete_arrangement_clips_in_range(mod):
    t = Track("Bass")
    t.arrangement_clips = [Clip("a", start_time=0.0), Clip("b", start_time=16.0),
                           Clip("c", start_time=32.0), Clip("d", start_time=48.0)]
    out = song_instance(mod, Song([t]))._delete_arrangement_clips(0, 16.0, 48.0)
    assert out["deleted"] == 2
    assert [c.name for c in t.arrangement_clips] == ["a", "d"]


def test_delete_arrangement_clips_to_end(mod):
    t = Track("Bass")
    t.arrangement_clips = [Clip("a", start_time=0.0), Clip("b", start_time=16.0)]
    song_instance(mod, Song([t]))._delete_arrangement_clips(0, 8.0)
    assert [c.name for c in t.arrangement_clips] == ["a"]


# ------------------------------------------------------------------ transport

def test_back_to_arrangement_and_loop(mod):
    song = Song([Track()])
    inst = song_instance(mod, song)
    assert inst._back_to_arrangement() == {"back_to_arranger_lit": False}
    out = inst._set_arrangement_loop(64.0, 32.0, True)
    assert out == {"loop": True, "loop_start": 64.0, "loop_length": 32.0}
    with pytest.raises(ValueError):
        inst._set_arrangement_loop(0.0, 0.0)


# ------------------------------------------------------------------ server side

def call(tool, *args, **kwargs):
    result = tool(*args, **kwargs)
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


class FakeConnection(object):
    def __init__(self, response=None):
        self.response = response or {}
        self.sent = []

    def send_command(self, command_type, params=None):
        self.sent.append((command_type, params or {}))
        return self.response


@pytest.fixture
def conn(monkeypatch):
    import MCP_Server.dataset.consent as consent
    import MCP_Server.script_handshake as sh
    import MCP_Server.telemetry_decorator as td

    class _Dummy(object):
        def record_event(self, *a, **k):
            pass

    monkeypatch.setattr(td, "get_telemetry", lambda: _Dummy(), raising=False)
    monkeypatch.setattr(consent, "maybe_consent_notice", lambda: "")
    monkeypatch.setattr(sh, "require_capability", lambda name: None)
    c = FakeConnection()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: c)
    return c


def test_tile_notes_repeats_pattern():
    pattern = [{"pitch": 42, "start_time": 0.5, "duration": 0.25, "velocity": 80, "mute": False}]
    tiled = server._tile_notes(pattern, 4.0, 3)
    assert [n["start_time"] for n in tiled] == [0.5, 4.5, 8.5]
    assert pattern[0]["start_time"] == 0.5  # input untouched
    assert server._tile_notes(pattern, 0, 5) == pattern


def test_add_notes_tiles_before_sending(conn):
    notes = [{"pitch": 36, "start_time": 0.0, "duration": 0.25, "velocity": 100, "mute": False},
             {"pitch": 36, "start_time": 2.0, "duration": 0.25, "velocity": 100, "mute": False}]
    out = call(server.add_notes_to_clip, None, 0, 0, notes, repeat_every=4.0, repeat_count=4)
    sent = conn.sent[0][1]["notes"]
    assert len(sent) == 8
    assert sent[-1]["start_time"] == 14.0
    assert "Added 8 notes" in out


def test_set_track_mixer_only_sends_given_fields(conn):
    conn.response = {"track_name": "Bass", "volume_display": "-6.0 dB",
                     "panning_display": "C", "sends": []}
    out = call(server.set_track_mixer, None, track_index=1, volume_db=-6.0)
    assert conn.sent == [("set_track_mixer",
                          {"track_index": 1, "track_type": "track", "volume_db": -6.0})]
    assert "-6.0 dB" in out


def test_get_drum_pads_returns_json(conn):
    conn.response = {"pads": [{"note": 36, "name": "Kick"}]}
    out = json.loads(call(server.get_drum_pads, None, 2))
    assert out["pads"][0]["name"] == "Kick"
    assert conn.sent == [("get_drum_pads", {"track_index": 2})]


def test_copy_clip_defaults_target_track(conn):
    conn.response = {"source": {"name": "A"}, "target": {"track_index": 3, "clip_index": 1,
                                                          "name": "A"}, "length": 4.0}
    call(server.copy_clip, None, 3, 0, 1)
    assert conn.sent[0][1]["target_track_index"] == 3


def test_fill_and_delete_and_loop_commands(conn):
    conn.response = {"clip_name": "Beat", "copies": 4, "track_name": "Drums",
                     "ends_at": 64.0, "deleted": 2, "loop": True,
                     "loop_start": 0.0, "loop_length": 16.0}
    assert "4x" in call(server.fill_arrangement, None, 0, 0, 32.0, 64.0)
    assert "Deleted 2" in call(server.delete_arrangement_clips, None, 0, 16.0)
    assert "Loop on" in call(server.set_arrangement_loop, None, 0.0, 16.0)
    assert "Arrangement" in call(server.back_to_arrangement, None)
    assert [c for c, _ in conn.sent] == ["fill_arrangement", "delete_arrangement_clips",
                                         "set_arrangement_loop", "back_to_arrangement"]
    assert "end_time" not in conn.sent[1][1]


def test_missing_capability_rechecks_handshake(monkeypatch):
    import MCP_Server.script_handshake as sh
    c = FakeConnection()
    monkeypatch.setattr(server, "get_ableton_connection", lambda: c)
    monkeypatch.setattr(sh, "require_capability", lambda name: "missing " + name)
    calls = []
    monkeypatch.setattr(sh, "handshake", lambda send: calls.append(send))
    result, missing = server._fork_command("copy_clip", "copy_clip", {})
    assert result is None and missing == "missing copy_clip"
    assert len(calls) == 1
    assert c.sent == []
