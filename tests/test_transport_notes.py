"""Remote Script side of 1.10.0: transport and song settings, locators,
notes by id, clip edits. Refusals must change nothing."""

import pytest

from live_fakes import FakeClip, FakeClipSlot, FakeSong, load_script_module, make_script


class Note(object):
    def __init__(self, note_id, pitch, start, dur=0.5, vel=100.0):
        self.note_id = note_id
        self.pitch = pitch
        self.start_time = start
        self.duration = dur
        self.velocity = vel
        self.mute = False
        self.probability = 1.0
        self.velocity_deviation = 0.0
        self.release_velocity = 64.0


class MidiClip(FakeClip):
    def __init__(self, history):
        super(MidiClip, self).__init__("beat", history, audio=False)
        self.__dict__["_notes"] = [Note(1, 60, 1.0), Note(2, 64, 0.0), Note(3, 67, 0.0)]

    def get_all_notes_extended(self):
        return list(self._notes)

    def apply_note_modifications(self, notes):
        self._history.log("apply_note_modifications", [(n.note_id, n.pitch, n.velocity) for n in notes])

    def remove_notes_by_id(self, ids):
        self._history.log("remove_notes_by_id", list(ids))
        self.__dict__["_notes"] = [n for n in self._notes if n.note_id not in ids]

    def quantize(self, grid, amount):
        self._history.log("quantize", grid, amount)

    def duplicate_loop(self):
        self._history.log("duplicate_loop")

    def crop(self):
        self._history.log("crop")


class Cue(object):
    def __init__(self, name, time, history):
        self.name, self.time, self._h = name, time, history

    def jump(self):
        self._h.log("cue.jump", self.name)


class TransportSong(FakeSong):
    def __init__(self):
        super(TransportSong, self).__init__()
        object.__setattr__(self, "_ready", False)
        self.is_playing = False
        self.current_song_time = 0.0
        self.signature_numerator, self.signature_denominator = 4, 4
        self.loop, self.loop_start, self.loop_length = False, 0.0, 16.0
        self.metronome = self.overdub = self.arrangement_overdub = False
        self.record_mode = self.session_record = self.punch_in = self.punch_out = False
        self.count_in_duration = 0
        self.clip_trigger_quantization = 4
        self.midi_recording_quantization = 0
        self.groove_amount, self.swing_amount = 1.0, 0.0
        self.root_note, self.scale_name, self.scale_mode = 0, "Major", False
        self.song_length = 64.0
        self.can_capture_midi = False
        self.cue_points = [Cue("Chorus", 32.0, self.h), Cue("Verse", 0.0, self.h)]
        object.__setattr__(self, "_ready", True)

    def __setattr__(self, key, value):
        if self.__dict__.get("_ready") and not key.startswith("_") and key not in ("undo_steps",):
            self.h.log("song", key, value)
        object.__setattr__(self, key, value)

    def stop_all_clips(self):
        self.h.log("stop_all_clips")

    def capture_midi(self):
        self.h.log("capture_midi")


class App(object):
    average_process_usage = 0.12
    peak_process_usage = 0.3


@pytest.fixture(scope="module")
def script_module():
    return load_script_module()


@pytest.fixture
def song():
    s = TransportSong()
    s.tracks[1].clip_slots = [FakeClipSlot(MidiClip(s.h)), FakeClipSlot(FakeClip("audio", s.h))]
    s.h.events.clear()
    return s


@pytest.fixture
def script(script_module, song):
    inst = make_script(script_module, song)
    inst.application = lambda: App()
    return inst


def run(script, command, **params):
    return script._process_command({"type": command, "params": params})


def ok(script, command, **params):
    reply = run(script, command, **params)
    assert reply["status"] == "success", reply
    return reply["result"]


def err(script, command, **params):
    reply = run(script, command, **params)
    assert reply["status"] == "error", reply
    return reply["message"]


def test_transport_state(script):
    t = ok(script, "get_transport")
    assert t["signature"] == "4/4" and t["clip_trigger_quantization"] == "1 Bar"
    assert t["root_note"] == "C" and t["midi_recording_quantization"] == "None"
    assert [c["name"] for c in t["cue_points"]] == ["Verse", "Chorus"]
    assert t["cpu"] == {"average": 0.12, "peak": 0.3}


def test_set_song_settings(script, song):
    r = ok(script, "set_song_settings", loop=True, loop_start=8, loop_length=4, metronome=True,
           clip_trigger_quantization="1/16", root_note="F#", scale_name="Minor", signature_numerator=7,
           signature_denominator=8)
    a = r["after"]
    assert a["loop"] and a["loop_start"] == 8.0 and a["loop_length"] == 4.0 and a["metronome"]
    assert a["clip_trigger_quantization"] == "1/16" and a["root_note"] == "F#" and a["signature"] == "7/8"


@pytest.mark.parametrize("kwargs, msg", [
    (dict(clip_trigger_quantization="1/64"), "choose one of"),
    (dict(root_note="H"), "choose one of"),
    (dict(loop_length=0), "out of range"),
    (dict(swing_amount=2), "out of range"),
    (dict(signature_denominator=3), "1, 2, 4, 8 or 16"),
    (dict(metronome=True, signature_numerator=0), "1..99"),
    (dict(), "Nothing to set"),
])
def test_bad_song_settings_change_nothing(script, song, kwargs, msg):
    assert msg in err(script, "set_song_settings", **kwargs)
    assert song.history == []


def test_recording_is_not_settable(script, song):
    assert "Nothing to set" in err(script, "set_song_settings", record_mode=True, session_record=True)
    assert song.record_mode is False


def test_jump_to_cue(script, song):
    assert ok(script, "jump_to_cue", cue="chorus")["time"] == 32.0
    assert ok(script, "jump_to_cue", cue=0)["jumped_to"] == "Verse"
    assert "Locators: Verse, Chorus" in err(script, "jump_to_cue", cue="Bridge")
    assert "out of range" in err(script, "jump_to_cue", cue=5)


def test_stop_all_and_capture(script, song):
    ok(script, "stop_all_clips")
    assert "Nothing to capture" in err(script, "capture_midi")
    song.can_capture_midi = True
    ok(script, "capture_midi")
    assert ("capture_midi",) in song.history


def test_get_notes_sorted_with_ids(script):
    n = ok(script, "get_notes", track_index=1, clip_index=0)
    assert [x["note_id"] for x in n["notes"]] == [2, 3, 1]
    assert n["notes"][0]["probability"] == 1.0 and n["notes"][0]["mute"] is False


def test_modify_notes_in_place(script, song):
    ok(script, "modify_notes", track_index=1, clip_index=0,
       notes=[{"note_id": 2, "velocity": 90, "probability": 0.5}, {"note_id": 1, "pitch": 62}])
    notes = {n.note_id: n for n in song.tracks[1].clip_slots[0].clip._notes}
    assert notes[2].velocity == 90.0 and notes[2].probability == 0.5 and notes[1].pitch == 62


@pytest.mark.parametrize("change, msg", [
    ({"note_id": 9, "velocity": 1}, "not in this clip"),
    ({"note_id": 1, "pitch": 200}, "0..127"),
    ({"note_id": 1, "probability": 2}, "0..1"),
    ({"note_id": 1, "duration": 0}, "> 0"),
    ({"note_id": 1, "colour": 3}, "unknown note field"),
    ({"velocity": 3}, "needs note_id"),
])
def test_bad_note_changes_change_nothing(script, song, change, msg):
    good = {"note_id": 2, "velocity": 10}
    assert msg in err(script, "modify_notes", track_index=1, clip_index=0, notes=[good, change])
    assert song.history == []
    assert {n.note_id: n.velocity for n in song.tracks[1].clip_slots[0].clip._notes}[2] == 100.0


def test_remove_notes(script, song):
    assert "not in this clip" in err(script, "remove_notes", track_index=1, clip_index=0, note_ids=[1, 99])
    assert song.history == []
    ok(script, "remove_notes", track_index=1, clip_index=0, note_ids=[1, 3])
    assert [n.note_id for n in song.tracks[1].clip_slots[0].clip._notes] == [2]


def test_notes_need_a_midi_clip(script):
    assert "not a MIDI clip" in err(script, "get_notes", track_index=1, clip_index=1)


def test_edit_clip_actions(script, song):
    ok(script, "edit_clip", track_index=1, clip_index=0, action="quantize", grid="1/16", amount=0.5)
    assert ("quantize", 5, 0.5) in song.history
    ok(script, "edit_clip", track_index=1, clip_index=0, action="duplicate_loop")
    ok(script, "edit_clip", track_index=1, clip_index=0, action="crop")
    assert "MIDI clips only" in err(script, "edit_clip", track_index=1, clip_index=1, action="duplicate_loop")
    assert "grid" in err(script, "edit_clip", track_index=1, clip_index=0, action="quantize", grid="1/5")
    assert "amount" in err(script, "edit_clip", track_index=1, clip_index=0, action="quantize", amount=0)
    assert "action must be" in err(script, "edit_clip", track_index=1, clip_index=0, action="reverse")
