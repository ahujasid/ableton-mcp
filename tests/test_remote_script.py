import copy
import importlib.util
import sys
import types

import pytest


class _ControlSurface:
    def __init__(self, c_instance=None):
        self._c_instance = c_instance

    def log_message(self, message):
        pass

    def show_message(self, message):
        pass

    def song(self):
        return None

    def application(self):
        return None

    def schedule_message(self, delay, callback):
        callback()

    def disconnect(self):
        pass


_framework = types.ModuleType("_Framework")
_framework_control_surface = types.ModuleType("_Framework.ControlSurface")
_framework_control_surface.ControlSurface = _ControlSurface
sys.modules.setdefault("_Framework", _framework)
sys.modules.setdefault("_Framework.ControlSurface", _framework_control_surface)

_module_spec = importlib.util.spec_from_file_location(
    "ableton_remote_script_test_target",
    "/Users/mateo/Developer/ableton-mcp-mateo/AbletonMCP_Remote_Script/__init__.py",
)
remote = importlib.util.module_from_spec(_module_spec)
_module_spec.loader.exec_module(remote)


class Parameter:
    def __init__(self, name, value, minimum=0.0, maximum=1.0, quantized=False, value_items=None):
        self.name = name
        self._value = value
        self.min = minimum
        self.max = maximum
        self.is_quantized = quantized
        self.value_items = value_items
        self.set_count = 0
        self.fail_once = False

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self.set_count += 1
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("synthetic parameter failure")
        self._value = value

    @property
    def display_value(self):
        return str(self._value)

    def str_for_value(self, value):
        return str(value)


class Mixer:
    def __init__(self):
        self.volume = Parameter("Volume", 0.75)
        self.panning = Parameter("Pan", 0.0, -1.0, 1.0)
        self.sends = [Parameter("Send A", 0.1)]


class Clip:
    def __init__(self, name, length=4.0, notes=None):
        self.name = name
        self.length = length
        self.notes = copy.deepcopy(notes or [])
        self.loop = True
        self.loop_start = 0.0
        self.loop_end = length
        self.start_marker = 0.0
        self.end_marker = length
        self.fail_next_add = False
        self.get_all_calls = 0
        self.get_extended_calls = 0

    def get_all_notes_extended(self):
        self.get_all_calls += 1
        return copy.deepcopy(self.notes)

    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self.get_extended_calls += 1
        return copy.deepcopy([
            note for note in self.notes
            if from_pitch <= note["pitch"] < from_pitch + pitch_span
            and from_time <= note["start_time"] < from_time + time_span
        ])

    def remove_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self.notes = [
            note for note in self.notes
            if not (
                from_pitch <= note["pitch"] < from_pitch + pitch_span
                and from_time <= note["start_time"] < from_time + time_span
            )
        ]

    def add_new_notes(self, payload):
        if isinstance(payload, dict):
            payload = payload["notes"]
        if self.fail_next_add:
            self.fail_next_add = False
            raise RuntimeError("synthetic note failure after clear")
        self.notes.extend(copy.deepcopy(payload))


class ClipSlot:
    def __init__(self, clip=None):
        self.clip = clip
        self.duplicate_count = 0

    @property
    def has_clip(self):
        return self.clip is not None

    def delete_clip(self):
        self.clip = None

    def duplicate_clip_to(self, target_slot):
        self.duplicate_count += 1
        target_slot.clip = copy.deepcopy(self.clip)


class Device:
    def __init__(self, name, class_name, parameters=None, chains=None):
        self.name = name
        self.class_name = class_name
        self.parameters = parameters or []
        self.chains = chains if chains is not None else []


class Chain:
    def __init__(self, name, devices):
        self.name = name
        self.devices = devices


class Track:
    def __init__(self, name, clips=None, devices=None):
        self.name = name
        self.clip_slots = clips or []
        self.devices = devices or []
        self.mixer_device = Mixer()
        self.mute = False
        self.solo = False
        self.arm = False
        self.arrangement_clips = []
        self.stop_count = 0
        self.output_meter_left = 0.25
        self.output_meter_right = 0.5
        self.arrangement_duplicate_length_override = None

    def stop_all_clips(self):
        self.stop_count += 1

    def delete_clip(self, clip):
        self.arrangement_clips.remove(clip)

    def duplicate_clip_to_arrangement(self, clip, destination_time):
        length = self.arrangement_duplicate_length_override
        if length is None:
            length = clip.length
        self.arrangement_clips.append(
            ArrangementClip(clip.name, destination_time, length)
        )


class ArrangementClip:
    def __init__(self, name, start_time, length):
        self.name = name
        self.start_time = start_time
        self.length = length
        self.end_time = start_time + length
        self.color = 0
        self.is_midi_clip = True
        self.is_audio_clip = False
        self.is_playing = False


class Scene:
    def __init__(self, name):
        self.name = name
        self.fire_args = None

    def fire(self, force_legato=False, can_select_scene_on_launch=True):
        self.fire_args = (force_legato, can_select_scene_on_launch)


class Song:
    def __init__(self, tracks, scenes=None, return_tracks=None):
        self.tracks = tracks
        self.return_tracks = return_tracks or []
        self.master_track = Track("Master")
        self.scenes = scenes or []
        self.version = "12.3-test"
        self.is_playing = False
        self.stop_count = 0
        self.back_to_arranger = 1
        self.clip_trigger_quantization = 4

    def stop_all_clips(self, quantized=None):
        self.stop_count += 1


def make_remote(song):
    instance = remote.AbletonMCP.__new__(remote.AbletonMCP)
    instance._song = song
    instance.log_message = lambda message: None
    instance.show_message = lambda message: None
    instance.schedule_message = lambda delay, callback: callback()
    instance.application = lambda: types.SimpleNamespace(
        get_version_string=lambda: "12.3-test"
    )
    return instance


def session_with_clip():
    clip = Clip("[MCP TEST] A", notes=[{
        "pitch": 36, "start_time": 0.0, "duration": 1.0,
        "velocity": 100, "mute": False,
    }])
    track = Track("[MCP TEST] Bass", [ClipSlot(clip), ClipSlot()])
    return Song([track]), track, clip


def test_track_identity_mismatch_has_no_mixer_side_effect():
    song, track, _clip = session_with_clip()
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._set_mixer_parameter({
            "track_index": 0,
            "expected_track_name": "[MCP TEST] Wrong",
            "parameter_name": "volume",
            "value": 0.5,
        })
    assert error.value.code == "track_identity_mismatch"
    assert track.mixer_device.volume.value == 0.75
    assert track.mixer_device.volume.set_count == 0


def test_mixer_batch_preflight_rejects_second_target_before_any_write():
    song, track, _clip = session_with_clip()
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError):
        instance._set_mixer_parameters({
            "parameters": [
                {"track_index": 0, "expected_track_name": track.name,
                 "parameter_name": "volume", "value": 0.5},
                {"track_index": 0, "expected_track_name": track.name,
                 "parameter_name": "panning", "expected_parameter_name": "Wrong",
                 "value": 0.2},
            ]
        })
    assert track.mixer_device.volume.value == 0.75
    assert track.mixer_device.volume.set_count == 0


def test_mixer_batch_rolls_back_when_second_write_fails():
    song, track, _clip = session_with_clip()
    track.mixer_device.panning.fail_once = True
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._set_mixer_parameters({
            "parameters": [
                {"track_index": 0, "expected_track_name": track.name,
                 "parameter_name": "volume", "value": 0.5,
                 "expected_current_value": 0.75},
                {"track_index": 0, "expected_track_name": track.name,
                 "parameter_name": "panning", "value": 0.2,
                 "expected_current_value": 0.0},
            ]
        })
    assert error.value.code == "batch_rolled_back"
    assert track.mixer_device.volume.value == 0.75


def test_nested_device_path_checks_device_and_chain_names_and_classes():
    nested = Device("Bass Synth", "Instrument", [Parameter("Cutoff", 0.4)])
    chain = Chain("Bass", [nested])
    rack = Device("Instrument Rack", "InstrumentGroupDevice", chains=[chain])
    song, track, _clip = session_with_clip()
    track.devices = [rack]
    instance = make_remote(song)
    device, path = instance._resolve_device_path({
        "track_index": 0,
        "expected_track_name": track.name,
        "device_path": [
            {"index": 0, "expected_name": "Instrument Rack", "expected_class_name": "InstrumentGroupDevice"},
            {"index": 0, "expected_name": "Bass"},
            {"index": 0, "expected_name": "Bass Synth", "expected_class_name": "Instrument"},
        ],
    })
    assert device.name == "Bass Synth"
    assert [item["name"] for item in path] == ["Instrument Rack", "Bass", "Bass Synth"]


def test_replace_clip_notes_restores_snapshot_after_write_failure():
    song, _track, clip = session_with_clip()
    before = copy.deepcopy(clip.notes)
    clip.fail_next_add = True
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._replace_clip_notes({
            "track_index": 0,
            "expected_track_name": "[MCP TEST] Bass",
            "clip_index": 0,
            "expected_clip_name": "[MCP TEST] A",
            "notes": [{"pitch": 40, "start_time": 0.0, "duration": 1.0,
                       "velocity": 90, "mute": False}],
        })
    assert error.value.code == "notes_rolled_back"
    assert clip.notes == before


def test_duplicate_preflight_rejects_occupied_destination_without_mutation():
    source_clip = Clip("[MCP TEST] Source")
    destination_clip = Clip("[MCP TEST] Existing")
    source_slot = ClipSlot(source_clip)
    destination_slot = ClipSlot(destination_clip)
    track = Track("[MCP TEST] Variants", [source_slot, destination_slot])
    instance = make_remote(Song([track]))
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._duplicate_session_clip({
            "source_track_index": 0,
            "expected_source_track_name": track.name,
            "source_clip_index": 0,
            "expected_source_clip_name": source_clip.name,
            "destination_track_index": 0,
            "expected_destination_track_name": track.name,
            "destination_clip_index": 1,
            "overwrite": False,
        })
    assert error.value.code == "destination_occupied"
    assert source_slot.duplicate_count == 0
    assert destination_slot.clip.name == "[MCP TEST] Existing"


def test_arrangement_target_requires_exact_name_start_and_duration():
    song, track, _clip = session_with_clip()
    first = ArrangementClip("[MCP TEST] A", 32.0, 4.0)
    second = ArrangementClip("[MCP TEST] A", 40.0, 4.0)
    track.arrangement_clips[:] = [first, second]
    instance = make_remote(song)
    result = instance._delete_arrangement_clip({
        "track_index": 0,
        "expected_track_name": track.name,
        "expected_clip_name": "[MCP TEST] A",
        "start_time": 40.0,
        "duration": 4.0,
    })
    assert result["after"]["exists"] is False
    assert track.arrangement_clips == [first]


def test_capabilities_are_safe_and_report_live_version_and_lom_probes():
    song, track, clip = session_with_clip()
    track.devices = [Device("Synth", "Instrument", [Parameter("Cutoff", 0.5)])]
    instance = make_remote(song)
    capabilities = instance._get_capabilities()
    assert capabilities["live_version"] == "12.3-test"
    assert capabilities["operations"]["clip.get_all_notes_extended"] is True
    assert capabilities["operations"]["track.delete_clip"] is True
    assert capabilities["operations"]["clip.add_new_notes"] is True


def test_process_command_schedules_mixer_mutation_through_existing_owner():
    song, track, _clip = session_with_clip()
    instance = make_remote(song)
    scheduled = []

    def schedule(delay, callback):
        scheduled.append(delay)
        callback()

    instance.schedule_message = schedule
    response = instance._process_command({
        "type": "set_mixer_parameter",
        "params": {
            "track_index": 0,
            "expected_track_name": track.name,
            "parameter_name": "volume",
            "value": 0.5,
            "expected_current_value": 0.75,
        },
    })
    assert response["status"] == "success"
    assert scheduled == [0]
    assert track.mixer_device.volume.value == 0.5


def test_actual_parameter_mutation_requires_expected_current_or_overwrite():
    song, track, _clip = session_with_clip()
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._set_mixer_parameter({
            "track_index": 0,
            "expected_track_name": track.name,
            "parameter_name": "volume",
            "value": 0.5,
        })
    assert error.value.code == "expected_current_value_required"
    assert track.mixer_device.volume.value == 0.75


def test_explicit_note_range_uses_filtered_api_and_rejects_outside_notes():
    song, track, clip = session_with_clip()
    clip.notes.append({
        "pitch": 40, "start_time": 2.0, "duration": 1.0,
        "velocity": 90, "mute": False,
    })
    instance = make_remote(song)
    result = instance._get_clip_notes({
        "track_index": 0,
        "expected_track_name": track.name,
        "clip_index": 0,
        "expected_clip_name": clip.name,
        "from_time": 0.0,
        "time_span": 1.0,
    })
    assert result["note_count"] == 1
    assert clip.get_all_calls == 0
    assert clip.get_extended_calls == 1

    before = copy.deepcopy(clip.notes)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._replace_clip_notes({
            "track_index": 0,
            "expected_track_name": track.name,
            "clip_index": 0,
            "expected_clip_name": clip.name,
            "from_time": 0.0,
            "time_span": 1.0,
            "notes": [{"pitch": 42, "start_time": 2.0, "duration": 0.5,
                       "velocity": 80, "mute": False}],
        })
    assert error.value.code == "note_outside_replacement_range"
    assert clip.notes == before


def test_scene_quantization_is_verified_instead_of_simulated():
    scene = Scene("[MCP TEST] Scene")
    song, _track, _clip = session_with_clip()
    song.scenes = [scene]
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._fire_scene({
            "scene_index": 0,
            "expected_scene_name": scene.name,
            "expected_global_quantization": 5,
        })
    assert error.value.code == "quantization_mismatch"
    assert scene.fire_args is None

    result = instance._fire_scene({
        "scene_index": 0,
        "expected_scene_name": scene.name,
        "expected_global_quantization": 4,
    })
    assert result["applied"]["global_quantization"] == 4
    assert scene.fire_args == (False, True)


def test_session_info_exposes_scene_identity_and_empty_state():
    song, track, _clip = session_with_clip()
    song.tempo = 120.0
    song.signature_numerator = 4
    song.signature_denominator = 4
    empty_slot = ClipSlot()
    occupied_slot = track.clip_slots[0]
    scene_a = Scene("A")
    scene_a.clip_slots = [occupied_slot]
    scene_b = Scene("B")
    scene_b.clip_slots = [empty_slot]
    song.scenes = [scene_a, scene_b]
    result = make_remote(song)._get_session_info()
    assert result["scenes"] == [
        {"index": 0, "name": "A", "is_empty": False},
        {"index": 1, "name": "B", "is_empty": True},
    ]


def test_session_duplicate_refuses_unrecoverable_occupied_overwrite():
    song, track, clip = session_with_clip()
    destination = ClipSlot(Clip("Existing", notes=[]))
    track.clip_slots.append(destination)
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._duplicate_session_clip({
            "source_track_index": 0,
            "expected_source_track_name": track.name,
            "source_clip_index": 0,
            "expected_source_clip_name": clip.name,
            "destination_track_index": 0,
            "expected_destination_track_name": track.name,
            "destination_clip_index": len(track.clip_slots) - 1,
            "expected_destination_clip_name": "Existing",
            "overwrite": True,
        })
    assert error.value.code == "overwrite_unsupported"
    assert destination.clip.name == "Existing"


def test_scene_duplicate_validates_expected_clip_name_from_track_subset():
    song, track, clip = session_with_clip()
    song.scenes = [Scene("A"), Scene("B")]
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._duplicate_session_scene_clips({
            "source_scene_index": 0,
            "expected_source_scene_name": "A",
            "destination_scene_index": 1,
            "expected_destination_scene_name": "B",
            "track_subset": [{
                "track_index": 0,
                "expected_track_name": track.name,
                "expected_clip_name": clip.name + " wrong",
            }],
        })
    assert error.value.code == "clip_identity_mismatch"


def test_arrangement_duplicate_readback_failure_removes_inserted_clip():
    song, track, clip = session_with_clip()
    track.arrangement_duplicate_length_override = clip.length + 1.0
    instance = make_remote(song)
    with pytest.raises(remote._RemoteScriptError) as error:
        instance._duplicate_session_clip_to_arrangement({
            "track_index": 0,
            "expected_track_name": track.name,
            "clip_index": 0,
            "expected_clip_name": clip.name,
            "destination_time": 32.0,
        })
    assert error.value.code == "arrangement_duplicate_rolled_back"
    assert track.arrangement_clips == []
