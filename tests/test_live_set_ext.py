"""Tests for the live-set extension commands of the Remote Script.

Live is not available here, so the song, tracks, clips and devices are small
fakes that expose only what the handlers touch.
"""

import sys
import types

import pytest

from tests.test_remote_script_bridge import BUNDLED_SCRIPT, REPO_SCRIPT, _load_script_module


class Param(object):
    def __init__(self, name, value=0.0, lo=0.0, hi=1.0):
        self.name, self.value, self.min, self.max = name, value, lo, hi


class Device(object):
    def __init__(self, name):
        self.name = name
        self.class_name = name
        self.parameters = [Param("Device On", 1.0), Param("Amount", 0.5)]


class Mixer(object):
    def __init__(self, n_sends):
        self.sends = [Param("Send", 0.0) for _ in range(n_sends)]


class Routing(object):
    def __init__(self, display_name):
        self.display_name = display_name


class Clip(object):
    def __init__(self):
        self.name = "clip"
        self.length = 16.0
        self.legato = False
        self.launch_quantization = 0
        self.follow_action_a = 0
        self.notes = []

    def add_new_notes(self, specs):
        self.notes.extend(specs)

    def get_notes_extended(self, from_pitch, pitch_span, from_time, span):
        return [n for n in self.notes
                if from_pitch <= n.pitch < from_pitch + pitch_span
                and from_time <= n.start_time < from_time + span]

    def apply_note_modifications(self, notes):
        self.applied = list(notes)


class Slot(object):
    def __init__(self, clip=None):
        self.clip = clip
        self.has_clip = clip is not None


class Track(object):
    def __init__(self, name, n_sends=2):
        self.name = name
        self.devices = [Device("EQ Eight")]
        self.mixer_device = Mixer(n_sends)
        self.clip_slots = [Slot(Clip()), Slot()]
        self.available_input_routing_types = [Routing("Ext. In"), Routing("No Input")]
        self.input_routing_type = self.available_input_routing_types[1]
        self.available_input_routing_channels = [Routing("1"), Routing("2")]
        self.input_routing_channel = self.available_input_routing_channels[0]
        self.current_monitoring_state = 1


class Scene(object):
    def __init__(self):
        self.name = ""


class View(object):
    selected_track = None


class Song(object):
    def __init__(self):
        self.tracks = [Track("Kick"), Track("Whistle")]
        self.return_tracks = [Track("A"), Track("B")]
        self.master_track = Track("Master", n_sends=0)
        self.scenes = [Scene() for _ in range(8)]
        self.view = View()

    def create_scene(self, index):
        if index == -1:
            self.scenes.append(Scene())
        else:
            self.scenes.insert(index, Scene())

    def create_return_track(self):
        self.return_tracks.append(Track("Return", n_sends=len(self.return_tracks) + 1))
        for t in self.tracks:
            t.mixer_device.sends.append(Param("Send", 0.0))


class NoteSpec(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture()
def script(monkeypatch):
    live = types.ModuleType("Live")
    live.Clip = types.SimpleNamespace(MidiNoteSpecification=NoteSpec)
    monkeypatch.setitem(sys.modules, "Live", live)
    module = _load_script_module()
    instance = module.AbletonMCP.__new__(module.AbletonMCP)
    instance._song = Song()
    instance.schedule_message = lambda delay, fn: fn()
    return instance


def run(script, command, **params):
    response = script._process_command({"type": command, "params": params})
    assert response["status"] == "success", response
    return response["result"]


def test_repo_and_bundled_scripts_identical():
    assert REPO_SCRIPT.read_text() == BUNDLED_SCRIPT.read_text()


def test_every_ext_command_is_a_capability_with_a_handler():
    module = _load_script_module()
    for command in module.AbletonMCP._EXT_COMMANDS:
        assert command in module.SCRIPT_CAPABILITIES
        assert hasattr(module.AbletonMCP, "_ext_" + command)


def test_create_scenes_and_name_them(script):
    result = run(script, "create_scene", count=22, name="")
    assert result["scene_count"] == 30
    run(script, "set_scene_name", scene_index=5, name="Pulse")
    assert script._song.scenes[5].name == "Pulse"


def test_create_return_and_set_send(script):
    result = run(script, "create_return_track", name="C · Espace")
    assert result == {"return_index": 2, "name": "C · Espace"}
    run(script, "set_send", track_index=1, send_index=2, value=1.5)
    assert script._song.tracks[1].mixer_device.sends[2].value == 1.0


def test_device_on_return_and_master(script):
    run(script, "set_device_parameter_ex", track_kind="return", track_index=1,
        device_index=0, parameter_index=1, value=0.8)
    assert script._song.return_tracks[1].devices[0].parameters[1].value == 0.8
    run(script, "set_device_name", track_kind="master", device_index=0, name="Wash")
    assert script._song.master_track.devices[0].name == "Wash"


def test_notes_with_probability(script):
    run(script, "add_notes_extended", track_index=0, clip_index=0, notes=[
        {"pitch": 42, "start_time": 0.5, "duration": 0.1, "velocity": 80},
        {"pitch": 42, "start_time": 0.75, "duration": 0.1, "velocity": 40,
         "probability": 0.5},
    ])
    clip = script._song.tracks[0].clip_slots[0].clip
    assert [n.probability for n in clip.notes] == [1.0, 0.5]
    result = run(script, "set_notes_probability", track_index=0, clip_index=0,
                 probability=0.3, pitch=42, start_times=[0.75])
    assert result == {"changed": 1}
    assert clip.notes[1].probability == 0.3 and clip.notes[0].probability == 1.0


def test_clip_properties_whitelist(script):
    props = run(script, "get_clip_properties", track_index=0, clip_index=0)["properties"]
    assert "follow_action_a" in props and "launch_quantization" in props
    run(script, "set_clip_property", track_index=0, clip_index=0,
        name="follow_action_a", value=3)
    assert script._song.tracks[0].clip_slots[0].clip.follow_action_a == 3
    response = script._process_command({"type": "set_clip_property", "params": {
        "track_index": 0, "clip_index": 0, "name": "name", "value": "x"}})
    assert response["status"] == "error"


def test_whistle_input_and_monitoring(script):
    result = run(script, "set_track_input", track_index=1, input_type="Ext. In",
                 input_channel="2", monitoring="in")
    assert result["input_type"] == "Ext. In"
    assert result["input_channel"] == "2"
    assert result["monitoring"] == 0


def test_return_name_letter_prefix_is_stripped(script):
    # Live shows the letter itself ("C-Espace"), so a typed prefix must not double it.
    result = run(script, "create_return_track", name="C-Espace")
    assert result["name"] == "Espace"
