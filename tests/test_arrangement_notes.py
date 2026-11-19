"""Notes in Arrangement clips (Remote Script 1.10.0).

get_clip_notes / add_notes_to_clip / clear_notes_from_clip take
location="arrangement", and remove_notes removes a time/pitch range. The
Remote Script side runs against fake Live clips; the server side checks what
is sent, and that an older Remote Script (which would ignore location and
edit the Session clip instead) is refused.
"""

import json

import pytest

import MCP_Server.server as server
from test_clip_notes import call, fake_conn, FakeConnection  # noqa: F401  (fixtures)
from test_clip_notes import _silence_telemetry, _no_consent_prompt  # noqa: F401
from test_remote_script_bridge import _load_script_module, make_instance


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


# ------------------------------------------------------------ fake Live

class FakeNote(object):
    def __init__(self, pitch, start_time, duration, velocity, mute):
        self.pitch = pitch
        self.start_time = start_time
        self.duration = duration
        self.velocity = velocity
        self.mute = mute


class FakeMidiClip(object):
    is_midi_clip = True
    is_audio_clip = False

    def __init__(self, name="clip", length=16.0, start_time=0.0, start_marker=0.0):
        self.name = name
        self.length = length
        self.start_marker = start_marker
        self.end_marker = start_marker + length
        self.loop_end = start_marker + length
        self.looping = False
        self.start_time = start_time
        self.end_time = start_time + length
        self.notes = []

    def set_notes(self, notes):
        for pitch, start, duration, velocity, mute in notes:
            self.notes.append(FakeNote(pitch, start, duration, velocity, mute))

    def _in(self, n, from_pitch, pitch_span, from_time, time_span):
        return (from_pitch <= n.pitch < from_pitch + pitch_span
                and from_time <= n.start_time < from_time + time_span)

    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        return [n for n in self.notes if self._in(n, from_pitch, pitch_span, from_time, time_span)]

    def remove_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self.notes = [n for n in self.notes
                      if not self._in(n, from_pitch, pitch_span, from_time, time_span)]


class FakeSlot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None


class FakeTrack(object):
    def __init__(self, session_clip=None, arrangement_clips=()):
        self.clip_slots = [FakeSlot(session_clip), FakeSlot()]
        self.arrangement_clips = list(arrangement_clips)


class FakeSong(object):
    def __init__(self, tracks):
        self.tracks = tracks
        self.return_tracks = []


def make(script_module):
    session = FakeMidiClip("session")
    verse = FakeMidiClip("verse", length=16.0, start_time=32.0)
    chorus = FakeMidiClip("chorus", length=8.0, start_time=48.0, start_marker=4.0)
    inst = make_instance(script_module)
    inst._song = FakeSong([FakeTrack(session, [verse, chorus])])
    return inst, session, verse, chorus


DRUMS = [
    {"pitch": 36, "start_time": 0.0, "duration": 0.25, "velocity": 110, "mute": False},
    {"pitch": 38, "start_time": 1.0, "duration": 0.25, "velocity": 100, "mute": False},
    {"pitch": 36, "start_time": 4.0, "duration": 0.25, "velocity": 110, "mute": False},
    {"pitch": 42, "start_time": 4.5, "duration": 0.25, "velocity": 70, "mute": False},
]


# --------------------------------------------------- Remote Script side

def test_add_and_read_notes_on_an_arrangement_clip(script_module):
    inst, session, verse, _ = make(script_module)
    added = inst._add_notes_to_clip(0, 0, DRUMS, location="arrangement")
    assert added["note_count"] == 4 and added["clip_name"] == "verse"
    assert len(verse.notes) == 4 and session.notes == []
    got = inst._get_clip_notes(0, 0, location="arrangement")
    assert got["clip_name"] == "verse" and got["note_count"] == 4
    assert [n["pitch"] for n in got["notes"]] == [36, 38, 36, 42]
    assert got["location"] == "arrangement"
    assert got["arrangement_start"] == 32.0 and got["arrangement_end"] == 48.0


def test_arrangement_reply_carries_start_marker_for_placing_notes(script_module):
    inst, _, _, chorus = make(script_module)
    got = inst._get_clip_notes(0, 1, location="arrangement")
    assert got["clip_name"] == "chorus"
    assert got["start_marker"] == 4.0 and got["arrangement_start"] == 48.0


def test_session_calls_are_unchanged(script_module):
    inst, session, verse, _ = make(script_module)
    inst._add_notes_to_clip(0, 0, DRUMS[:1])
    got = inst._get_clip_notes(0, 0)
    assert got["clip_name"] == "session" and got["note_count"] == 1
    assert got["location"] == "session" and "arrangement_start" not in got
    assert verse.notes == []


def test_clear_arrangement_clip_reports_count(script_module):
    inst, session, verse, _ = make(script_module)
    inst._add_notes_to_clip(0, 0, DRUMS, location="arrangement")
    inst._add_notes_to_clip(0, 0, DRUMS[:2])
    result = inst._clear_notes_from_clip(0, 0, location="arrangement")
    assert result["cleared_count"] == 4 and verse.notes == []
    assert len(session.notes) == 2


def test_clear_catches_notes_past_the_clip_length(script_module):
    # A note beyond `length` (e.g. after moving the end marker) must go too.
    inst, _, verse, _ = make(script_module)
    verse.set_notes([(60, 15.9, 1.0, 100, False)])
    verse.end_marker = 20.0
    verse.set_notes([(62, 18.0, 1.0, 100, False)])
    assert inst._clear_notes_from_clip(0, 0, location="arrangement")["cleared_count"] == 2
    assert verse.notes == []


def test_remove_notes_by_time_range_keeps_the_rest(script_module):
    inst, _, verse, _ = make(script_module)
    inst._add_notes_to_clip(0, 0, DRUMS, location="arrangement")
    result = inst._remove_notes(0, 0, location="arrangement", from_time=4.0, time_span=4.0)
    assert result["removed_count"] == 2 and result["remaining_count"] == 2
    assert sorted(n.start_time for n in verse.notes) == [0.0, 1.0]


def test_remove_notes_by_pitch_only(script_module):
    inst, _, verse, _ = make(script_module)
    inst._add_notes_to_clip(0, 0, DRUMS, location="arrangement")
    result = inst._remove_notes(0, 0, location="arrangement", from_pitch=36, pitch_span=1)
    assert result["removed_count"] == 2
    assert sorted(n.pitch for n in verse.notes) == [38, 42]


def test_remove_notes_clamps_pitch_span_and_validates(script_module):
    inst, _, _, _ = make(script_module)
    result = inst._remove_notes(0, 0, location="arrangement", from_pitch=120, pitch_span=50)
    assert result["pitch_span"] == 8
    with pytest.raises(ValueError, match="positive"):
        inst._remove_notes(0, 0, location="arrangement", time_span=0)
    with pytest.raises(ValueError, match="0-127"):
        inst._remove_notes(0, 0, location="arrangement", from_pitch=200)


def test_audio_clip_and_bad_index_are_refused(script_module):
    inst, _, verse, _ = make(script_module)
    verse.is_midi_clip = False
    with pytest.raises(ValueError, match="not a MIDI clip"):
        inst._get_clip_notes(0, 0, location="arrangement")
    with pytest.raises(IndexError, match="Arrangement clip index"):
        inst._add_notes_to_clip(0, 5, DRUMS, location="arrangement")


def test_dispatch_routes_location_and_remove_notes(script_module):
    inst, session, verse, _ = make(script_module)
    inst.schedule_message = lambda delay, fn: fn()
    reply = inst._process_command({"type": "add_notes_to_clip", "params": {
        "track_index": 0, "clip_index": 0, "location": "arrangement", "notes": DRUMS}})
    assert reply["status"] == "success", reply
    reply = inst._process_command({"type": "remove_notes", "params": {
        "track_index": 0, "clip_index": 0, "location": "arrangement",
        "from_pitch": 42, "pitch_span": 1}})
    assert reply["status"] == "success", reply
    reply = inst._process_command({"type": "get_clip_notes", "params": {
        "track_index": 0, "clip_index": 0, "location": "arrangement"}})
    assert reply["result"]["note_count"] == 3
    assert session.notes == []
    assert "arrangement_notes" in script_module.SCRIPT_CAPABILITIES
    assert "remove_notes" in script_module.SCRIPT_CAPABILITIES


# ----------------------------------------------------------- server side

@pytest.fixture
def capabilities(monkeypatch):
    """Pretend the Remote Script advertises exactly these capabilities."""
    import MCP_Server.script_handshake as sh

    def _set(*names):
        monkeypatch.setattr(sh, "require_capability",
                            lambda name: None if name in names else "missing " + name)
    return _set


ALL = ("get_clip_notes", "clear_notes_from_clip", "arrangement_notes", "remove_notes")


def test_server_sends_location_only_for_the_arrangement(fake_conn, capabilities):
    capabilities(*ALL)
    conn = fake_conn(response={"notes": [], "note_count": 0})
    call(server.get_clip_notes, None, 1, 2)
    call(server.get_clip_notes, None, 1, 2, location="arrangement")
    assert conn.sent == [
        ("get_clip_notes", {"track_index": 1, "clip_index": 2}),
        ("get_clip_notes", {"track_index": 1, "clip_index": 2, "location": "arrangement"}),
    ]


def test_server_add_and_clear_forward_location(fake_conn, capabilities):
    capabilities(*ALL)
    conn = fake_conn(response={"note_count": 1, "clip_name": "verse", "cleared_count": 1})
    out = call(server.add_notes_to_clip, None, 0, 3, DRUMS[:1], location="arrangement")
    assert "arrangement clip 3" in out
    out = call(server.clear_notes_from_clip, None, 0, 3, location="arrangement")
    assert "arrangement clip 3" in out
    assert [c[1].get("location") for c in conn.sent] == ["arrangement", "arrangement"]


def test_server_refuses_arrangement_on_an_older_script(fake_conn, capabilities):
    # A 1.9.0 script would drop location and edit the Session clip instead.
    capabilities("get_clip_notes", "clear_notes_from_clip")
    conn = fake_conn(response={})
    assert "missing arrangement_notes" in call(
        server.add_notes_to_clip, None, 0, 0, DRUMS, location="arrangement")
    assert "missing arrangement_notes" in call(
        server.get_clip_notes, None, 0, 0, location="arrangement")
    assert "missing arrangement_notes" in call(
        server.clear_notes_from_clip, None, 0, 0, location="arrangement")
    assert conn.sent == []
    # Session calls still go through on the older script.
    call(server.add_notes_to_clip, None, 0, 0, DRUMS)
    assert conn.sent == [("add_notes_to_clip",
                          {"track_index": 0, "clip_index": 0, "notes": DRUMS})]


def test_server_remove_notes_params(fake_conn, capabilities):
    capabilities(*ALL)
    conn = fake_conn(response={"removed_count": 2})
    out = call(server.remove_notes, None, 0, 1, from_time=4.0, time_span=4.0,
               location="arrangement")
    assert json.loads(out)["removed_count"] == 2
    assert conn.sent == [("remove_notes", {
        "track_index": 0, "clip_index": 1, "location": "arrangement",
        "from_time": 4.0, "time_span": 4.0, "from_pitch": 0, "pitch_span": 128})]


def test_server_rejects_an_unknown_location(fake_conn, capabilities):
    capabilities(*ALL)
    conn = fake_conn(response={})
    assert "location must be" in call(server.get_clip_notes, None, 0, 0, location="timeline")
    assert "location must be" in call(server.remove_notes, None, 0, 0, location="timeline")
    assert conn.sent == []
