"""Remote Script side of 1.11.0: arrangement clips, note edits, warp markers,
clip envelopes, insert_device, plugin presets, racks, drum pads, Simpler.
Refusals must change nothing."""

import pytest

from live_fakes import (FakeChain, FakeClip, FakeClipSlot, FakeDevice, FakeParameter, FakeSong,
                        load_script_module, make_script)


# --- fakes ----------------------------------------------------------------

class Note(object):
    def __init__(self, note_id, pitch, start):
        self.note_id, self.pitch, self.start_time = note_id, pitch, start
        self.duration, self.velocity, self.mute = 0.5, 100.0, False


class Marker(object):
    def __init__(self, beat_time, sample_time):
        self.beat_time, self.sample_time = beat_time, sample_time


class Envelope(object):
    def __init__(self, h, value=0.5):
        self.h, self.value = h, value

    def value_at_time(self, t):
        return self.value

    def insert_step(self, t, length, value):
        self.h.log("env.insert_step", t, length, value)


class ToolClip(FakeClip):
    """A clip with the 1.11.0 methods; MIDI or audio."""

    def __init__(self, name, h, audio=False, arrangement=False, start=0.0):
        super(ToolClip, self).__init__(name, h, audio=audio, arrangement=arrangement)
        d = self.__dict__
        d["start_time"], d["end_time"] = start, start + 4.0
        d["_notes"] = [Note(1, 60, 0.0), Note(2, 64, 1.0)]
        d["_markers"] = [Marker(0.0, 0.0), Marker(4.0, 2.0)]
        d["sample_length"] = 480000  # samples: 10 s at 48 kHz
        d["_envs"] = {}

    def get_all_notes_extended(self):
        return list(self._notes)

    def quantize_pitch(self, pitch, grid, amount):
        self._history.log("quantize_pitch", pitch, grid, amount)

    def duplicate_region(self, start, length, dest, pitch, transpose):
        self._history.log("duplicate_region", start, length, dest, pitch, transpose)
        self._notes.append(Note(3, 60, dest))

    def duplicate_notes_by_id(self, spec):
        self._history.log("duplicate_notes_by_id", spec)
        self._notes.append(Note(4, 60, 2.0))

    @property
    def warp_markers(self):
        return list(self._markers)

    def add_warp_marker(self, m):
        b = m["beat_time"] if isinstance(m, dict) else m.beat_time
        self._history.log("add_warp_marker", b)
        self._markers.append(Marker(b, 1.0))
        self._markers.sort(key=lambda x: x.beat_time)

    def move_warp_marker(self, b, dist):
        self._history.log("move_warp_marker", b, dist)
        for m in self._markers:
            if m.beat_time == b:
                m.beat_time = b + dist

    def remove_warp_marker(self, b):
        self._history.log("remove_warp_marker", b)
        self.__dict__["_markers"] = [m for m in self._markers if m.beat_time != b]

    def automation_envelope(self, param):
        return self._envs.get(id(param))

    def create_automation_envelope(self, param):
        self._history.log("create_envelope", param.name)
        self._envs[id(param)] = Envelope(self._history)
        return self._envs[id(param)]

    def clear_envelope(self, param):
        self._history.log("clear_envelope", param.name)
        self._envs.pop(id(param), None)

    def clear_all_envelopes(self):
        self._history.log("clear_all_envelopes")
        self._envs.clear()


class Pad(object):
    """Like Live: name is read-only and shows the first chain's name."""

    def __init__(self, note, h, loaded=False):
        self.note, self._h = note, h
        self.mute = self.solo = False
        self.chains = [FakeChain("Kick", [FakeDevice("Simpler", [], h)], h)] if loaded else []

    @property
    def name(self):
        return self.chains[0].name if self.chains else ""

    def delete_all_chains(self):
        self._h.log("pad.delete_all_chains", self.note)
        self.chains = []


class DrumChain(FakeChain):
    def __init__(self, name, h):
        super(DrumChain, self).__init__(name, [], h)
        self.in_note, self.out_note, self.choke_group = 36, 60, 0
        self.color_index = 0


class Rack(FakeDevice):
    def __init__(self, h, drum=False):
        macros = [FakeParameter("Cutoff" if i == 0 else "Macro %d" % (i + 1), 0.0, 0.0, 127.0, history=h)
                  for i in range(16)]
        chains = [DrumChain("Kick", h)] if drum else [FakeChain("Dry", [], h), FakeChain("Wet", [], h)]
        super(Rack, self).__init__("Drum Rack" if drum else "Audio Effect Rack", macros, h,
                                   class_name="DrumGroupDevice" if drum else "AudioEffectGroupDevice", chains=chains)
        for c in self.chains:
            c.color_index = 0
            c.mixer_device = type("M", (), {})()
            c.mixer_device.volume = FakeParameter("Volume", 0.85, 0.0, 1.0, history=h, kind="volume")
            c.mixer_device.panning = FakeParameter("Pan", 0.0, -1.0, 1.0, history=h, kind="pan")
        self.visible_macro_count = 8
        self.variation_count = 2
        self.selected_variation_index = 0
        self.has_macro_mappings = True
        self._drum = drum
        self.return_chains = []
        if drum:
            self.drum_pads = [Pad(n, h, loaded=(n == 36)) for n in range(128)]

    @property
    def has_drum_pads(self):
        if not self._drum:
            raise RuntimeError("Only drum racks can have pads!")  # what Live does
        return True

    def add_macro(self):
        self._history.log("add_macro")
        self.visible_macro_count += 1

    def remove_macro(self):
        self._history.log("remove_macro")
        self.visible_macro_count -= 1

    def randomize_macros(self):
        self._history.log("randomize_macros")

    def store_variation(self):
        self._history.log("store_variation")
        self.variation_count += 1

    def recall_selected_variation(self):
        self._history.log("recall_variation", self.selected_variation_index)

    def recall_last_used_variation(self):
        self._history.log("recall_last")

    def delete_selected_variation(self):
        self._history.log("delete_variation", self.selected_variation_index)
        self.variation_count -= 1

    def insert_chain(self, index=None):
        self._history.log("insert_chain", index)
        c = FakeChain("Chain", [], self._history)
        self.chains.insert(len(self.chains) if index is None else index, c)

    def copy_pad(self, src, dst):
        self._history.log("copy_pad", src, dst)
        self.drum_pads[dst].chains = list(self.drum_pads[src].chains)


class Plugin(FakeDevice):
    def __init__(self, h):
        super(Plugin, self).__init__("Vital", [], h, class_name="PluginDevice", dtype=1)
        self.presets = ["Init", "Big Pad", "Pluck"]
        self._sel = 0

    selected_preset_index = property(lambda s: s._sel, lambda s, v: (s._history.log("preset", v),
                                                                     setattr(s, "_sel", v)))


class Sample(object):
    def __init__(self, h):
        self._h = h
        self.file_path, self.length, self.sample_rate = "Z:\\kick.wav", 48000, 48000
        self.start_marker, self.end_marker = 0, 48000
        self.warping, self.warp_mode, self.slicing_style = False, 0, 0
        self.slices = [0, 12000]

    def gain_display_string(self):
        return "0.0 dB"

    def insert_slice(self, t):
        self._h.log("insert_slice", t)
        self.slices.append(t)

    def remove_slice(self, t):
        self._h.log("remove_slice", t)
        self.slices.remove(t)

    def clear_slices(self):
        self._h.log("clear_slices")
        self.slices = []

    def reset_slices(self):
        self._h.log("reset_slices")


class Simpler(FakeDevice):
    def __init__(self, h, loaded=True):
        super(Simpler, self).__init__("Simpler", [], h, class_name="OriginalSimpler", dtype=1)
        self.sample = Sample(h) if loaded else None
        self.playback_mode, self.voices, self.retrigger, self.multi_sample_mode = 0, 1, False, False
        self.can_warp_as = self.can_warp_double = self.can_warp_half = True

    def crop(self):
        self._history.log("crop")

    def reverse(self):
        self._history.log("reverse")

    def warp_as(self, beats):
        self._history.log("warp_as", beats)

    def warp_double(self):
        self._history.log("warp_double")

    def warp_half(self):
        self._history.log("warp_half")

    def replace_sample(self, path):
        self._history.log("replace_sample", path)


@pytest.fixture(scope="module")
def script_module():
    return load_script_module()


@pytest.fixture
def song():
    s = FakeSong()
    h = s.h
    audio, midi = s.tracks
    midi.has_audio_input, midi.has_midi_input = False, True
    midi.clip_slots = [FakeClipSlot(ToolClip("beat", h)), FakeClipSlot()]
    audio.clip_slots = [FakeClipSlot(ToolClip("take", h, audio=True))]
    midi.arrangement_clips = [ToolClip("intro", h, arrangement=True, start=0.0)]

    def create_midi_clip(start, length):
        h.log("create_midi_clip", start, length)
        midi.arrangement_clips.append(ToolClip("", h, arrangement=True, start=start))
    midi.create_midi_clip = create_midi_clip

    def create_audio_clip(path, pos):
        h.log("create_audio_clip", path, pos)
        audio.arrangement_clips.append(ToolClip("take", h, audio=True, arrangement=True, start=pos))
    audio.create_audio_clip = create_audio_clip

    def delete_clip(clip):
        h.log("delete_clip", clip.name)
        midi.arrangement_clips.remove(clip)
    midi.delete_clip = delete_clip

    def insert_device(name, index=None):
        h.log("insert_device", name, index)
        audio.devices.insert(len(audio.devices) if index is None else index, FakeDevice(name, [], h))
    audio.insert_device = insert_device
    audio.devices = [Rack(h), Plugin(h)]
    midi.devices = [Rack(h, drum=True), Simpler(h)]
    h.events.clear()
    return s


@pytest.fixture
def script(script_module, song):
    return make_script(script_module, song)


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


def writes(song):
    """History without the undo-step bookkeeping."""
    return [e for e in song.history if e[0] not in ("begin_undo_step", "end_undo_step")]


# --- arrangement clips ------------------------------------------------------

def test_create_arrangement_midi_clip(script, song):
    r = ok(script, "create_arrangement_clip", track_index=1, start_time=16.0, length=8.0, name="verse")
    assert ("create_midi_clip", 16.0, 8.0) in song.history
    assert r["kind"] == "midi" and r["arrangement_index"] == 1 and r["name"] == "verse"


def test_create_arrangement_audio_clip(script, song):
    r = ok(script, "create_arrangement_clip", track_index=0, start_time=4.0, file_path="Z:\\a.wav")
    assert ("create_audio_clip", "Z:\\a.wav", 4.0) in song.history and r["kind"] == "audio"


@pytest.mark.parametrize("kw, msg", [
    (dict(track_index=0, start_time=0), "is an audio track"),
    (dict(track_index=1, start_time=0, file_path="Z:\\a.wav"), "is a MIDI track"),
    (dict(track_index=1, start_time=-1), ">= 0"),
    (dict(track_index=1, start_time=0, length=0), "> 0"),
    (dict(track_index=0, track_type="return", start_time=0), "regular tracks"),
])
def test_create_arrangement_clip_refusals(script, song, kw, msg):
    assert msg in err(script, "create_arrangement_clip", **kw)
    assert writes(song) == []


def test_delete_arrangement_clip_needs_matching_name(script, song):
    assert "expected_clip_name" in err(script, "delete_arrangement_clip", track_index=1, arrangement_index=0)
    assert "does not match" in err(script, "delete_arrangement_clip", track_index=1, arrangement_index=0,
                                   expected_clip_name="outro")
    assert writes(song) == []
    r = ok(script, "delete_arrangement_clip", track_index=1, arrangement_index=0, expected_clip_name="intro")
    assert r["deleted"] == "intro" and r["remaining"] == 0


# --- note edits -------------------------------------------------------------

def test_edit_notes_actions(script, song):
    ok(script, "edit_notes", track_index=1, clip_index=0, action="quantize_pitch", pitch=60, grid="1/8")
    assert ("quantize_pitch", 60, 2, 1.0) in song.history
    r = ok(script, "edit_notes", track_index=1, clip_index=0, action="duplicate_region", region_start=0,
           region_length=2, destination_time=2, transpose=12)
    assert ("duplicate_region", 0.0, 2.0, 2.0, -1, 12) in song.history and r["notes_after"] == 3
    ok(script, "edit_notes", track_index=1, clip_index=0, action="duplicate_notes", note_ids=[1],
       destination_time=3, transpose=-12)
    assert ("duplicate_notes_by_id", {"note_ids": [1], "destination_time": 3.0, "transposition_amount": -12}) \
        in song.history


@pytest.mark.parametrize("kw, msg", [
    (dict(action="quantize_pitch", pitch=200), "0..127"),
    (dict(action="quantize_pitch", pitch=60, grid="None"), "does not quantize"),
    (dict(action="duplicate_region", region_length=0, destination_time=1), "region_length"),
    (dict(action="duplicate_region", region_length=1), "destination_time"),
    (dict(action="duplicate_notes", note_ids=[9]), "not in this clip"),
    (dict(action="transpose"), "action must be"),
])
def test_edit_notes_refusals(script, song, kw, msg):
    assert msg in err(script, "edit_notes", track_index=1, clip_index=0, **kw)
    assert writes(song) == []


# --- warp markers -----------------------------------------------------------

def test_warp_markers(script, song):
    r = ok(script, "get_warp_markers", track_index=0, clip_index=0)
    assert r["warp_markers"] == [{"beat_time": 0.0, "sample_time": 0.0}, {"beat_time": 4.0, "sample_time": 2.0}]
    r = ok(script, "edit_warp_markers", track_index=0, clip_index=0, action="add", beat_time=2.0)
    assert len(r["after"]) == 3
    assert script._sample_time_at(r["before"], 2.0) == 1.0  # halfway between (0, 0) and (4, 2)
    assert script._sample_time_at(r["before"], 6.0) == 3.0  # last segment extended
    ok(script, "edit_warp_markers", track_index=0, clip_index=0, action="move", beat_time=2.0, distance=0.5)
    assert ("move_warp_marker", 2.0, 0.5) in song.history
    ok(script, "edit_warp_markers", track_index=0, clip_index=0, action="remove", beat_time=2.5)
    assert ("remove_warp_marker", 2.5) in song.history


@pytest.mark.parametrize("kw, msg", [
    (dict(action="add", beat_time=4.0), "already a warp marker"),
    (dict(action="add", beat_time=2.0, sample_time=11), "outside the sample (0..10.000)"),
    (dict(action="remove", beat_time=3.0), "Markers at: 0, 4"),
    (dict(action="move", beat_time=4.0), "distance"),
])
def test_warp_marker_refusals(script, song, kw, msg):
    assert msg in err(script, "edit_warp_markers", track_index=0, clip_index=0, **kw)
    assert writes(song) == []


def test_warp_markers_need_audio_and_warping(script, song):
    assert "not an audio clip" in err(script, "get_warp_markers", track_index=1, clip_index=0)
    song.tracks[0].clip_slots[0].clip.__dict__["warping"] = False
    assert "not warped" in err(script, "edit_warp_markers", track_index=0, clip_index=0, action="add", beat_time=1)


# --- clip envelopes ---------------------------------------------------------

def test_set_and_read_envelope(script, song):
    r = ok(script, "set_clip_envelope", track_index=0, clip_index=0, mixer="volume",
           points=[{"time": 2, "value": 0.5}, {"time": 0, "display": "0.0 dB"}])
    assert r["created"] and [s["time"] for s in r["steps"]] == [0.0, 2.0]
    assert [s["length"] for s in r["steps"]] == [2.0, 2.0]
    r = ok(script, "get_clip_envelope", track_index=0, clip_index=0, mixer="volume", points=3)
    assert r["has_envelope"] and len(r["samples"]) == 3 and r["samples"][0]["display"].endswith("dB")


def test_envelope_on_device_parameter_and_send(script, song):
    ok(script, "set_clip_envelope", track_index=0, clip_index=0, device="0", parameter="Cutoff",
       points=[{"time": 0, "value": 64}])
    assert ("create_envelope", "Cutoff") in song.history
    assert ok(script, "get_clip_envelope", track_index=0, clip_index=0, mixer="send B")["has_envelope"] is False


@pytest.mark.parametrize("kw, msg", [
    (dict(mixer="volume", points=[]), "Give points"),
    (dict(mixer="volume", points=[{"time": 0}]), "exactly one of value or display"),
    (dict(mixer="volume", points=[{"time": 0, "value": 3}]), "outside"),
    (dict(mixer="volume", points=[{"time": 0, "value": 0.5, "length": -1}]), "length must be > 0"),
    (dict(mixer="tempo", points=[{"time": 0, "value": 0.5}]), "mixer must be"),
    (dict(points=[{"time": 0, "value": 0.5}]), "Give mixer"),
])
def test_envelope_refusals(script, song, kw, msg):
    assert msg in err(script, "set_clip_envelope", track_index=0, clip_index=0, **kw)
    assert writes(song) == []


def test_arrangement_envelope_refused(script, song):
    assert "Arrangement clip envelopes" in err(script, "set_clip_envelope", track_index=1, arrangement_index=0,
                                               mixer="volume", points=[{"time": 0, "value": 0.5}])


def test_clear_envelope(script, song):
    assert "has no envelope" in err(script, "clear_clip_envelope", track_index=0, clip_index=0, mixer="pan")
    ok(script, "set_clip_envelope", track_index=0, clip_index=0, mixer="pan", points=[{"time": 0, "value": 0}])
    ok(script, "clear_clip_envelope", track_index=0, clip_index=0, mixer="pan")
    assert ("clear_envelope", "Track Panning") in song.history
    ok(script, "clear_clip_envelope", track_index=0, clip_index=0, all=True)
    assert ("clear_all_envelopes",) in song.history


# --- insert_device, plugin presets -------------------------------------------

def test_insert_device(script, song):
    r = ok(script, "insert_device", track_index=0, device_name="Utility", index=0)
    assert ("insert_device", "Utility", 0) in song.history and r["devices"][0] == "Utility"
    assert "out of range" in err(script, "insert_device", track_index=0, device_name="EQ Eight", index=9)
    assert "device_name" in err(script, "insert_device", track_index=0, device_name=" ")


def test_insert_device_into_chain_needs_live_12_3(script, song):
    assert "needs Live 12.3" in err(script, "insert_device", track_index=0, device_name="Utility", chain="0/1")
    assert "rack/chain" in err(script, "insert_device", track_index=0, device_name="Utility", chain="0")


def test_plugin_presets(script, song):
    chain = ok(script, "get_device_chain", track_index=0, include_parameters=False)
    plug = chain["devices"][1]
    assert plug["preset"] == "Init" and plug["preset_count"] == 3
    r = ok(script, "set_plugin_preset", track_index=0, device="1", preset="big pad")
    assert r["after"] == "Big Pad" and ("preset", 1) in song.history
    assert "No preset" in err(script, "set_plugin_preset", track_index=0, device="1", preset="Nope")
    assert "out of range" in err(script, "set_plugin_preset", track_index=0, device="1", preset="7")
    assert "not a plugin" in err(script, "set_plugin_preset", track_index=0, device="0", preset="0")


# --- racks ----------------------------------------------------------------------

def test_get_rack(script):
    r = ok(script, "get_rack", track_index=0, device="0")
    assert r["visible_macro_count"] == 8 and len(r["macros"]) == 8
    assert r["macros"][0] == dict(r["macros"][0], name="Cutoff", mapped=True)
    assert r["macros"][1]["mapped"] is False
    assert [c["name"] for c in r["chains"]] == ["Dry", "Wet"] and r["chains"][0]["volume"] == "0.0 dB"
    assert r["is_drum_rack"] is False
    assert "not a rack" in err(script, "get_rack", track_index=0, device="1")


def test_get_drum_rack_pads(script):
    r = ok(script, "get_rack", track_index=1, device="0")
    assert r["is_drum_rack"] and [p["note"] for p in r["drum_pads"]] == [36]
    assert r["chains"][0]["in_note"] == 36
    assert len(ok(script, "get_rack", track_index=1, device="0", include_empty_pads=True)["drum_pads"]) == 128


def test_rack_macros(script, song):
    assert ok(script, "rack_macros", track_index=0, device="0", action="add_macro")["visible_macro_count"] == 9
    assert ok(script, "rack_macros", track_index=0, device="0", action="store_variation")["variation_count"] == 3
    ok(script, "rack_macros", track_index=0, device="0", action="recall_variation", variation=1)
    assert ("recall_variation", 1) in song.history
    assert "out of range" in err(script, "rack_macros", track_index=0, device="0", action="recall_variation",
                                 variation=7)
    assert "action must be" in err(script, "rack_macros", track_index=0, device="0", action="explode")


def test_delete_rack_variation(script, song):
    assert "out of range" in err(script, "delete_rack_variation", track_index=0, device="0", variation=5)
    assert ok(script, "delete_rack_variation", track_index=0, device="0", variation=1)["variation_count"] == 1


def test_insert_rack_chain(script, song):
    r = ok(script, "insert_rack_chain", track_index=0, device="0", index=1, name="Crush")
    assert r["chains"] == ["Dry", "Crush", "Wet"]
    assert "Drum Rack" in err(script, "insert_rack_chain", track_index=1, device="0")


def test_set_rack_chain(script, song):
    r = ok(script, "set_rack_chain", track_index=0, device="0", chain=1, name="Verb", mute=True, volume_db=-6,
           pan=-0.5)
    assert r["after"]["name"] == "Verb" and r["after"]["mute"] is True and r["after"]["volume"] == "-6.0 dB"
    assert "only exists on Drum Rack" in err(script, "set_rack_chain", track_index=0, device="0", chain=0,
                                             choke_group=1)
    ok(script, "set_rack_chain", track_index=1, device="0", chain=0, choke_group=2, in_note=38)
    chain = song.tracks[1].devices[0].chains[0]
    assert chain.choke_group == 2 and chain.in_note == 38


def test_set_rack_chain_refusals_change_nothing(script, song):
    for kw, msg in ((dict(chain=5, mute=True), "out of range"), (dict(chain=0, pan=2), "-1..1"),
                    (dict(chain=0, name="x", color_index=99), "0..69"), (dict(chain=0), "Nothing to set")):
        assert msg in err(script, "set_rack_chain", track_index=0, device="0", **kw)
    assert writes(song) == []


# --- drum pads -----------------------------------------------------------------

def test_pad_names_and_numbers(script_module):
    f = script_module.AbletonMCP._pad_index
    assert f("C1", "pad") == 36 and f("36", "pad") == 36 and f("D#1", "pad") == 39 and f("C-2", "pad") == 0
    with pytest.raises(ValueError):
        f("H2", "pad")


def test_set_drum_pad(script, song):
    r = ok(script, "set_drum_pad", track_index=1, device="0", pad="C1", name="Big Kick", mute=True)
    assert r["name"] == "Big Kick" and r["mute"] is True
    assert "empty" in err(script, "set_drum_pad", track_index=1, device="0", pad="D1", name="Snare")
    assert "nothing to mute" in err(script, "set_drum_pad", track_index=1, device="0", pad="D1", mute=True)
    assert "not a Drum Rack" in err(script, "set_drum_pad", track_index=0, device="0", pad="C1", mute=True)


def test_copy_drum_pad(script, song):
    assert "empty" in err(script, "copy_drum_pad", track_index=1, device="0", source=40, destination=41)
    ok(script, "copy_drum_pad", track_index=1, device="0", source="C1", destination="D1")
    assert ("copy_pad", 36, 38) in song.history
    assert "overwrite" in err(script, "copy_drum_pad", track_index=1, device="0", source=36, destination=38)
    ok(script, "copy_drum_pad", track_index=1, device="0", source=36, destination=38, overwrite=True)


def test_clear_drum_pad(script, song):
    assert "expected_pad_name" in err(script, "clear_drum_pad", track_index=1, device="0", pad=36)
    assert "does not match" in err(script, "clear_drum_pad", track_index=1, device="0", pad=36,
                                   expected_pad_name="Snare")
    assert "already empty" in err(script, "clear_drum_pad", track_index=1, device="0", pad=37,
                                  expected_pad_name="")
    assert writes(song) == []
    ok(script, "clear_drum_pad", track_index=1, device="0", pad="C1", expected_pad_name="Kick")
    assert ("pad.delete_all_chains", 36) in song.history


# --- Simpler -----------------------------------------------------------------

def test_get_simpler(script):
    r = ok(script, "get_simpler", track_index=1, device="1")
    assert r["playback_mode"] == "Classic" and r["sample"]["slices"] == [0, 12000]
    assert r["sample"]["slicing_style"] == "Transient"
    assert "not a Simpler" in err(script, "get_simpler", track_index=1, device="0")


def test_edit_simpler(script, song):
    r = ok(script, "edit_simpler", track_index=1, device="1", action="set", playback_mode="Slicing",
           slicing_style="beat", voices=4)
    assert r["playback_mode"] == "Slicing" and r["sample"]["slicing_style"] == "Beat"
    ok(script, "edit_simpler", track_index=1, device="1", action="warp_as", beats=8)
    assert ("warp_as", 8) in song.history
    ok(script, "edit_simpler", track_index=1, device="1", action="insert_slice", time=24000)
    ok(script, "edit_simpler", track_index=1, device="1", action="remove_slice", time=12000)
    assert ok(script, "get_simpler", track_index=1, device="1")["sample"]["slices"] == [0, 24000]
    ok(script, "edit_simpler", track_index=1, device="1", action="replace_sample", file_path="Z:\\snare.wav")
    assert ("replace_sample", "Z:\\snare.wav") in song.history


@pytest.mark.parametrize("kw, msg", [
    (dict(action="set", playback_mode="Granular"), "choose one of"),
    (dict(action="set", voices=0), "1..32"),
    (dict(action="set"), "Nothing to set"),
    (dict(action="warp_as"), "beats > 0"),
    (dict(action="remove_slice", time=5), "No slice at 5"),
    (dict(action="insert_slice", time=99999999), "outside the sample"),
    (dict(action="replace_sample"), "file_path"),
    (dict(action="explode"), "action must be"),
])
def test_edit_simpler_refusals(script, song, kw, msg):
    assert msg in err(script, "edit_simpler", track_index=1, device="1", **kw)
    assert writes(song) == []


def test_simpler_without_sample(script, song):
    song.tracks[1].devices[1].sample = None
    assert "no sample" in err(script, "edit_simpler", track_index=1, device="1", action="crop")
    assert ok(script, "get_simpler", track_index=1, device="1")["sample"] is None


# --- multi-tick commands: create_locator ---------------------------------------

class Cue(object):
    def __init__(self, time, name):
        self.time, self.name = time, name


def locator_song(song, ticks):
    """Make the fake song apply playhead moves only when a tick ends, as Live does."""
    song.cue_points = []
    song.is_playing = False
    song.__dict__["_pos"] = 0.0
    song.__dict__["_pending"] = None

    def get_pos(self):
        return self._pos

    def set_pos(self, v):
        self.__dict__["_pending"] = v

    # A per-test subclass, so the property doesn't leak into FakeSong.
    song.__class__ = type("TickSong", (type(song),), {"current_song_time": property(get_pos, set_pos)})

    def set_or_delete_cue():
        song.h.log("set_or_delete_cue", song._pos)
        song.cue_points.append(Cue(song._pos, str(len(song.cue_points) + 1)))
    song.set_or_delete_cue = set_or_delete_cue

    def end_tick():
        if song._pending is not None:
            song.__dict__["_pos"], song.__dict__["_pending"] = song._pending, None
    ticks.append(end_tick)


@pytest.fixture
def tick_script(script_module, song):
    """schedule_message runs each task in its own tick, ending the tick after it."""
    ticks = []
    locator_song(song, ticks)
    inst = make_script(script_module, song)

    queue = []

    def schedule_message(delay, fn):
        queue.append(fn)
        if len(queue) > 1:
            return  # scheduled from inside a running tick: runs on a later one
        while queue:
            queue[0]()
            for t in ticks:
                t()
            queue.pop(0)
    inst.schedule_message = schedule_message
    return inst


def test_create_locator_lands_at_the_requested_time(tick_script, song):
    r = ok(tick_script, "create_locator", name="Chorus", time=16.0)
    assert r == {"success": True, "time": 16.0, "name": "Chorus"}
    assert ("set_or_delete_cue", 16.0) in song.history
    assert song.current_song_time == 0.0  # playhead put back


def test_create_locator_renames_an_existing_one(tick_script, song):
    song.cue_points.append(Cue(8.0, "1"))
    assert ok(tick_script, "create_locator", name="Verse", time=8.0)["name"] == "Verse"
    assert len(song.cue_points) == 1


def test_create_locator_refuses_while_playing(tick_script, song):
    song.is_playing = True
    assert "Stop playback" in err(tick_script, "create_locator", name="x", time=4.0)
    assert song.cue_points == []


def test_multi_tick_command_is_one_undo_step(tick_script, song):
    ok(tick_script, "create_locator", name="Chorus", time=16.0)
    assert song.undo_steps == ["begin", "end"]
