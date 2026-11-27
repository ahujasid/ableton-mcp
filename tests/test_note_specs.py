"""Live 13 note writing: extended note fields and Step Sequencer clip guard.

Covers both sides without Ableton:

* the Remote Script's pure ``normalize_note_specs`` (validation + defaults),
* ``_add_notes_to_clip`` / ``_clear_notes_from_clip`` / the readers against
  fake clip objects and a fake ``Live`` module,
* the MCP server tools (forwarding, result text, tool errors),
* the script/server version pin.
"""

import sys
import types

import pytest

import MCP_Server.server as server
from MCP_Server.remote_script_install import EXPECTED_REMOTE_SCRIPT_VERSION
from tests.test_clip_notes import call, fake_conn  # noqa: F401  (fixture)
from tests.test_clip_notes import (  # noqa: F401  (autouse fixtures)
    _silence_telemetry, _no_consent_prompt, _script_capabilities_available,
)
from tests.test_remote_script_bridge import _load_script_module


@pytest.fixture(scope="module")
def rs():
    return _load_script_module()


# --------------------------------------------------------------------------
# normalize_note_specs
# --------------------------------------------------------------------------

FULL_KEYS = {"pitch", "start_time", "duration", "velocity", "mute",
             "probability", "velocity_deviation", "release_velocity"}


def test_defaults_are_filled(rs):
    [spec] = rs.normalize_note_specs([{"pitch": 60}])
    assert spec == {
        "pitch": 60, "start_time": 0.0, "duration": 0.25, "velocity": 100.0,
        "mute": False, "probability": 1.0, "velocity_deviation": 0.0,
        "release_velocity": 64.0,
    }


def test_extended_fields_pass_through_exactly(rs):
    [spec] = rs.normalize_note_specs([{
        "pitch": 36, "start_time": 1.5, "duration": 0.5, "velocity": 90,
        "mute": True, "probability": 0.5, "velocity_deviation": 20,
        "release_velocity": 20,
    }])
    assert spec["probability"] == 0.5
    assert spec["velocity_deviation"] == 20.0
    assert spec["release_velocity"] == 20.0
    assert spec["mute"] is True
    assert set(spec) == FULL_KEYS


def test_unknown_keys_like_note_id_are_ignored(rs):
    [spec] = rs.normalize_note_specs([{"pitch": 60, "note_id": 7, "foo": 1}])
    assert set(spec) == FULL_KEYS


def test_boundary_values_are_accepted(rs):
    specs = rs.normalize_note_specs([
        {"pitch": 0, "velocity": 0, "probability": 0, "release_velocity": 0,
         "velocity_deviation": -127},
        {"pitch": 127, "velocity": 127, "probability": 1, "release_velocity": 127,
         "velocity_deviation": 127},
        {"pitch": 60.0, "mute": 1},
    ])
    assert specs[2]["pitch"] == 60 and specs[2]["mute"] is True


@pytest.mark.parametrize("note, field", [
    ({}, "pitch"),
    ({"pitch": -1}, "pitch"),
    ({"pitch": 128}, "pitch"),
    ({"pitch": 60.5}, "pitch"),
    ({"pitch": "60"}, "pitch"),
    ({"pitch": True}, "pitch"),
    ({"pitch": float("nan")}, "pitch"),
    ({"pitch": float("inf")}, "pitch"),
    ({"pitch": float("-inf")}, "pitch"),
    ({"pitch": 60, "velocity": float("inf")}, "velocity"),
    ({"pitch": 60, "probability": float("nan")}, "probability"),
    ({"pitch": 10 ** 400}, "pitch"),
    ({"pitch": 10 ** 5000}, "pitch"),  # repr() itself fails on 3.11+
    ({"pitch": 60, "start_time": 10 ** 400}, "start_time"),
    ({"pitch": 60, "velocity": -10 ** 400}, "velocity"),
    ({"pitch": 60, "velocity": -1}, "velocity"),
    ({"pitch": 60, "velocity": 128}, "velocity"),
    ({"pitch": 60, "probability": 1.1}, "probability"),
    ({"pitch": 60, "probability": -0.1}, "probability"),
    ({"pitch": 60, "release_velocity": 128}, "release_velocity"),
    ({"pitch": 60, "release_velocity": -1}, "release_velocity"),
    ({"pitch": 60, "velocity_deviation": 128}, "velocity_deviation"),
    ({"pitch": 60, "duration": 0}, "duration"),
    ({"pitch": 60, "start_time": float("nan")}, "start_time"),
    ({"pitch": 60, "mute": "yes"}, "mute"),
])
def test_invalid_values_are_rejected_not_clamped(rs, note, field):
    with pytest.raises(ValueError) as exc:
        rs.normalize_note_specs([{"pitch": 60}, note])
    msg = str(exc.value)
    assert "index 1" in msg and field in msg


def test_notes_must_be_a_list(rs):
    with pytest.raises(ValueError):
        rs.normalize_note_specs({"pitch": 60})
    with pytest.raises(ValueError):
        rs.normalize_note_specs([60])


# --------------------------------------------------------------------------
# Remote Script command handlers against fake Live objects
# --------------------------------------------------------------------------

class FakeSpec(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeNote(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeClip(object):
    """A MIDI clip. midi_clip_type=None models Live <= 12 (no attribute)."""

    def __init__(self, midi_clip_type=None, modern=True, is_midi=True):
        self.name = "Clip"
        self.length = 4.0
        self.is_playing = False
        self.is_recording = False
        self.is_midi_clip = is_midi
        self.is_audio_clip = not is_midi
        self.color = 0
        if midi_clip_type is not None:
            self.midi_clip_type = midi_clip_type
        self.notes = []
        self.legacy_writes = []
        if modern:
            self.add_new_notes = self._add_new_notes

    def _add_new_notes(self, specs):
        self.notes.extend(dict(s.__dict__) for s in specs)

    def set_notes(self, tuples):
        self.legacy_writes.extend(tuples)

    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        return [FakeNote(note_id=i + 1, **n) for i, n in enumerate(self.notes)]

    def remove_notes_extended(self, *args):
        self.notes = []


class BrokenTypeClip(FakeClip):
    """Live 13 clip whose midi_clip_type exists but cannot be read."""

    @property
    def midi_clip_type(self):
        raise RuntimeError("boom")


class WeirdTypeClip(FakeClip):
    def __init__(self, value):
        FakeClip.__init__(self)
        self._value = value

    @property
    def midi_clip_type(self):
        return self._value


class IntLikeEnum(int):
    """Stand-in for a Boost.Python enum value."""


class FakeSlot(object):
    def __init__(self, clip):
        self.clip = clip
        self.has_clip = clip is not None


def make_script(rs, clip):
    track = types.SimpleNamespace(
        clip_slots=[FakeSlot(clip)], devices=[], name="T",
        has_audio_input=False, has_midi_input=True, mute=False, solo=False,
        arm=False, can_be_armed=True,
        mixer_device=types.SimpleNamespace(
            volume=types.SimpleNamespace(value=0.85),
            panning=types.SimpleNamespace(value=0.0)),
    )
    inst = rs.AbletonMCP.__new__(rs.AbletonMCP)
    inst._song = types.SimpleNamespace(tracks=[track])
    return inst


@pytest.fixture
def fake_live(monkeypatch):
    live = types.ModuleType("Live")
    live.Clip = types.SimpleNamespace(MidiNoteSpecification=FakeSpec)
    monkeypatch.setitem(sys.modules, "Live", live)
    return live


@pytest.fixture
def no_live(monkeypatch):
    monkeypatch.setitem(sys.modules, "Live", None)  # import Live -> ImportError


NOTE = {"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 100,
        "release_velocity": 20, "probability": 0.5, "velocity_deviation": 20}


def test_add_uses_add_new_notes_and_keeps_all_fields(rs, fake_live):
    clip = FakeClip(midi_clip_type=0)
    result = make_script(rs, clip)._add_notes_to_clip(0, 0, [NOTE, {"pitch": 62}])
    assert result == {"note_count": 2, "api_used": "add_new_notes",
                      "midi_clip_type": 0}
    assert clip.notes[0]["release_velocity"] == 20.0
    assert clip.notes[0]["probability"] == 0.5
    assert clip.notes[0]["velocity_deviation"] == 20.0
    assert clip.notes[1]["release_velocity"] == 64.0
    assert clip.notes[1]["probability"] == 1.0
    assert clip.legacy_writes == []


def test_write_then_read_round_trips(rs, fake_live):
    clip = FakeClip(midi_clip_type=0)
    script = make_script(rs, clip)
    script._add_notes_to_clip(0, 0, [NOTE])
    read = script._get_clip_notes(0, 0)
    [n] = read["notes"]
    assert (n["release_velocity"], n["probability"], n["velocity_deviation"]) == (20.0, 0.5, 20.0)
    assert read["midi_clip_type"] == 0
    assert read["notes_may_not_match_ui"] is False


def test_add_falls_back_to_set_notes_without_live_spec(rs, no_live):
    clip = FakeClip(modern=False)
    result = make_script(rs, clip)._add_notes_to_clip(0, 0, [NOTE])
    assert result["api_used"] == "set_notes"
    assert result["midi_clip_type"] is None
    assert result["ignored_fields"] == ["probability", "release_velocity",
                                        "velocity_deviation"]
    assert clip.legacy_writes == [(60, 0.0, 1.0, 100.0, False)]


def test_add_falls_back_when_clip_lacks_add_new_notes(rs, fake_live):
    clip = FakeClip(modern=False)
    result = make_script(rs, clip)._add_notes_to_clip(0, 0, [{"pitch": 60}])
    assert result["api_used"] == "set_notes"
    assert "ignored_fields" not in result


@pytest.mark.parametrize("clip_type", [1, 2])
def test_add_refuses_step_sequencer_clip_and_leaves_it_untouched(rs, fake_live, clip_type):
    clip = FakeClip(midi_clip_type=clip_type)
    with pytest.raises(Exception) as exc:
        make_script(rs, clip)._add_notes_to_clip(0, 0, [NOTE])
    assert "midi_clip_type=%d" % clip_type in str(exc.value)
    assert "Convert the clip to MIDI first" in str(exc.value)
    assert clip.notes == [] and clip.legacy_writes == []


def test_clear_refuses_step_sequencer_clip(rs, fake_live):
    clip = FakeClip(midi_clip_type=1)
    clip.notes = [dict(rs.normalize_note_specs([{"pitch": 60}])[0])]
    with pytest.raises(Exception) as exc:
        make_script(rs, clip)._clear_notes_from_clip(0, 0)
    assert "Step Sequencer" in str(exc.value)
    assert len(clip.notes) == 1


def test_invalid_note_writes_nothing(rs, fake_live):
    clip = FakeClip(midi_clip_type=0)
    with pytest.raises(ValueError):
        make_script(rs, clip)._add_notes_to_clip(0, 0, [{"pitch": 60}, {"pitch": 200}])
    assert clip.notes == []


def test_add_refuses_audio_clip(rs, fake_live):
    clip = FakeClip(is_midi=False)
    with pytest.raises(Exception, match="not a MIDI clip"):
        make_script(rs, clip)._add_notes_to_clip(0, 0, [NOTE])


def test_readers_flag_step_sequencer_clips(rs):
    clip = FakeClip(midi_clip_type=1)
    clip.notes = [dict(rs.normalize_note_specs([{"pitch": 60}])[0])]
    script = make_script(rs, clip)
    read = script._get_clip_notes(0, 0)
    assert read["midi_clip_type"] == 1
    assert read["notes_may_not_match_ui"] is True
    ser = script._serialize_session_clip(clip)
    assert ser["midi_clip_type"] == 1 and ser["notes_may_not_match_ui"] is True


def test_readers_on_live12_report_null_type(rs):
    clip = FakeClip()  # no midi_clip_type attribute
    read = make_script(rs, clip)._get_clip_notes(0, 0)
    assert read["midi_clip_type"] is None
    assert read["notes_may_not_match_ui"] is False


def test_track_info_exposes_midi_clip_type(rs):
    info = make_script(rs, FakeClip(midi_clip_type=1))._get_track_info(0)
    assert info["clip_slots"][0]["clip"]["midi_clip_type"] == 1
    info = make_script(rs, FakeClip(midi_clip_type=0))._get_track_info(0)
    assert info["clip_slots"][0]["clip"]["midi_clip_type"] == 0


# --------------------------------------------------------------------------
# MCP server tools
# --------------------------------------------------------------------------

def test_server_forwards_extended_fields_unchanged(fake_conn):
    conn = fake_conn(response={"note_count": 1, "api_used": "add_new_notes",
                               "midi_clip_type": 0})
    call(server.add_notes_to_clip, None, 0, 0, [NOTE])
    assert conn.sent[0][1]["notes"] == [NOTE]


def test_server_result_reports_api_used(fake_conn):
    fake_conn(response={"note_count": 1, "api_used": "add_new_notes",
                        "midi_clip_type": 0})
    out = call(server.add_notes_to_clip, None, 0, 0, [NOTE])
    assert "Added 1 note(s)" in out
    assert "api_used=add_new_notes" in out
    assert "midi_clip_type=0" in out


def test_server_result_warns_about_ignored_fields(fake_conn):
    fake_conn(response={"note_count": 1, "api_used": "set_notes",
                        "midi_clip_type": None,
                        "ignored_fields": ["release_velocity"]})
    out = call(server.add_notes_to_clip, None, 0, 0, [NOTE])
    assert "api_used=set_notes" in out
    assert "midi_clip_type=null" in out
    assert "release_velocity" in out and "not stored" in out


def test_server_turns_script_errors_into_tool_errors(fake_conn):
    from mcp.server.fastmcp.exceptions import ToolError
    fake_conn(raise_exc=server.AbletonCommandError(
        "Clip is a Step Sequencer clip (midi_clip_type=1); ..."))
    with pytest.raises(ToolError) as exc:
        call(server.add_notes_to_clip, None, 0, 0, [NOTE])
    assert "Step Sequencer" in str(exc.value)


def test_script_error_keeps_connection_and_message():
    """An error *reply* is not a broken socket: keep it and pass the text on."""
    import json

    class Sock(object):
        def sendall(self, data):
            pass

        def settimeout(self, t):
            pass

    conn = server.AbletonConnection(host="x", port=1)
    sock = Sock()
    conn.sock = sock
    conn.receive_full_response = lambda s: json.dumps(
        {"status": "error", "message": "Clip is a Step Sequencer clip"}).encode()
    with pytest.raises(server.AbletonCommandError) as exc:
        conn.send_command("add_notes_to_clip", {})
    assert str(exc.value) == "Clip is a Step Sequencer clip"
    assert conn.sock is sock


# --------------------------------------------------------------------------
# Version pin
# --------------------------------------------------------------------------

def test_script_and_server_versions_match(rs):
    assert rs.SCRIPT_VERSION == EXPECTED_REMOTE_SCRIPT_VERSION


# --------------------------------------------------------------------------
# Fail-closed clip type detection
# --------------------------------------------------------------------------

def _seed(rs, clip):
    clip.notes = [dict(rs.normalize_note_specs([{"pitch": 60}])[0])]


@pytest.mark.parametrize("clip_factory", [
    lambda: BrokenTypeClip(),
    lambda: WeirdTypeClip("step"),
    lambda: WeirdTypeClip(None),
    lambda: WeirdTypeClip(1.5),
    lambda: WeirdTypeClip(True),
])
def test_unreadable_clip_type_blocks_writes(rs, fake_live, clip_factory):
    clip = clip_factory()
    script = make_script(rs, clip)
    with pytest.raises(Exception, match="Refusing to modify notes"):
        script._add_notes_to_clip(0, 0, [NOTE])
    assert clip.notes == [] and clip.legacy_writes == []
    _seed(rs, clip)
    with pytest.raises(Exception, match="Refusing to modify notes"):
        script._clear_notes_from_clip(0, 0)
    assert len(clip.notes) == 1


def test_unreadable_clip_type_is_flagged_by_readers_not_raised(rs):
    clip = BrokenTypeClip()
    script = make_script(rs, clip)
    read = script._get_clip_notes(0, 0)
    assert read["midi_clip_type"] is None
    assert read["notes_may_not_match_ui"] is True
    assert "boom" in read["midi_clip_type_error"]
    ser = script._serialize_session_clip(clip)
    assert ser["notes_may_not_match_ui"] is True
    slot = script._get_track_info(0)["clip_slots"][0]["clip"]
    assert slot["midi_clip_type"] is None
    assert "boom" in slot["midi_clip_type_error"]


def test_int_like_enum_clip_type_is_accepted(rs, fake_live):
    clip = WeirdTypeClip(IntLikeEnum(0))
    result = make_script(rs, clip)._add_notes_to_clip(0, 0, [NOTE])
    assert result["midi_clip_type"] == 0
    clip = WeirdTypeClip(IntLikeEnum(1))
    with pytest.raises(Exception, match="Step Sequencer"):
        make_script(rs, clip)._add_notes_to_clip(0, 0, [NOTE])


def test_missing_property_still_means_live12_normal_clip(rs, fake_live):
    clip = FakeClip()  # no midi_clip_type attribute at all
    result = make_script(rs, clip)._add_notes_to_clip(0, 0, [NOTE])
    assert result["midi_clip_type"] is None
    assert len(clip.notes) == 1


@pytest.mark.parametrize("modern", [False, True])
def test_zero_velocity_is_valid_and_preserved(rs, fake_live, modern):
    clip = FakeClip(modern=modern)
    make_script(rs, clip)._add_notes_to_clip(0, 0, [{"pitch": 60, "velocity": 0}])
    if modern:
        assert clip.notes[0]["velocity"] == 0
    else:
        assert clip.legacy_writes[0][3] == 0


def test_note_count_limit_checked_before_writes(rs, fake_live):
    clip = FakeClip()
    with pytest.raises(ValueError, match="10000"):
        make_script(rs, clip)._add_notes_to_clip(0, 0, [{"pitch": 60}] * 10001)
    assert clip.notes == [] and clip.legacy_writes == []
