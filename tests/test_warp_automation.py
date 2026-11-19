"""Warp and clip-automation commands (Remote Script 1.9.0).

The fakes model the parts of Live's Clip / AutomationEnvelope API these
commands use. They can't prove Live accepts every call (that needs a run in
Live, see docs/), but they pin down the arithmetic and the argument checks.
"""

import pytest

from test_remote_script_bridge import _load_script_module, make_instance


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeWarpMarker(object):
    def __init__(self, beat_time, sample_time):
        self.beat_time = beat_time
        self.sample_time = sample_time


class FakeEnvelope(object):
    def __init__(self):
        self.steps = []

    def insert_step(self, start, duration, value):
        self.steps.append((start, duration, value))

    initial = 0.0

    def value_at_time(self, t):
        # Left-continuous like Live: on a boundary, the previous step's value.
        value = self.initial
        for start, duration, v in self.steps:
            if start < t <= start + duration:
                value = v
        return value


class FakeClip(object):
    def __init__(self, audio=True, length=16.0, seconds=8.0, sample_rate=44100,
                 markers=((0.0, 0.0), (16.0, 8.0))):
        self.name = "clip"
        self.is_audio_clip = audio
        self.length = length
        self.start_marker = 0.0
        self.end_marker = length
        self.warping = False
        self.warp_mode = 0
        self.available_warp_modes = [0, 1, 2, 3, 4, 6]
        self.warp_markers = [FakeWarpMarker(b, s) for b, s in markers]
        self.pitch_coarse = 0
        self.pitch_fine = 0.0
        self.gain = 0.4
        self.gain_display_string = "0.0 dB"
        self.sample_rate = sample_rate
        self.sample_length = int(seconds * sample_rate)
        self.envelopes = {}

    def remove_warp_marker(self, beat_time):
        self.warp_markers = [m for m in self.warp_markers if m.beat_time != beat_time]

    def move_warp_marker(self, beat_time, distance):
        for m in self.warp_markers:
            if m.beat_time == beat_time:
                m.beat_time += distance

    def add_warp_marker(self, marker):
        self.warp_markers.append(
            FakeWarpMarker(marker["beat_time"], marker.get("sample_time", -1.0)))
        self.warp_markers.sort(key=lambda m: m.beat_time)

    def automation_envelope(self, param):
        return self.envelopes.get(id(param))

    def create_automation_envelope(self, param):
        env = FakeEnvelope()
        self.envelopes[id(param)] = env
        return env

    def clear_envelope(self, param):
        self.envelopes.pop(id(param), None)


class FakeSlot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None


class FakeParam(object):
    def __init__(self, name, lo=0.0, hi=1.0, value=0.5):
        self.name = name
        self.min = lo
        self.max = hi
        self.value = value


class FakeDevice(object):
    def __init__(self):
        self.parameters = [FakeParam("Device On"), FakeParam("Filter Freq", 20.0, 135.0, 100.0)]


class FakeMixer(object):
    def __init__(self):
        self.volume = FakeParam("Track Volume")
        self.panning = FakeParam("Track Panning", -1.0, 1.0, 0.0)
        self.sends = [FakeParam("A-Reverb")]


class FakeTrack(object):
    def __init__(self, clips):
        self.clip_slots = [FakeSlot(c) for c in clips]
        self.arrangement_clips = []
        self.devices = [FakeDevice()]
        self.mixer_device = FakeMixer()


class FakeSong(object):
    def __init__(self, tracks):
        self.tracks = tracks
        self.return_tracks = []
        self.tempo = 120.0


def make(script_module, clip=None, arrangement_clip=None):
    clip = clip if clip is not None else FakeClip()
    track = FakeTrack([clip, None])
    if arrangement_clip is not None:
        track.arrangement_clips = [arrangement_clip]
    inst = make_instance(script_module)
    inst._song = FakeSong([track])
    return inst, clip, track


# ------------------------------------------------------------------- warp

def test_get_clip_warp_reports_mode_names_markers_and_duration(script_module):
    inst, clip, _ = make(script_module)
    info = inst._get_clip_warp(0, 0)
    assert info["warp_mode"] == "beats"
    assert "complex_pro" in info["available_warp_modes"]
    assert info["warp_markers"] == [{"beat_time": 0.0, "sample_time": 0.0},
                                    {"beat_time": 16.0, "sample_time": 8.0}]
    assert info["sample_seconds"] == pytest.approx(8.0)


def test_set_clip_warp_accepts_mode_names_and_clamps(script_module):
    inst, clip, _ = make(script_module)
    info = inst._set_clip_warp(0, 0, warping=True, warp_mode="Complex Pro",
                               pitch_coarse=99, pitch_fine=-80, gain=2.0)
    assert clip.warping is True
    assert clip.warp_mode == 6 and info["warp_mode"] == "complex_pro"
    assert clip.pitch_coarse == 48
    assert clip.pitch_fine == -50.0
    assert clip.gain == 1.0


def test_set_clip_warp_leaves_unset_fields_alone(script_module):
    inst, clip, _ = make(script_module)
    clip.warping = True
    clip.warp_mode = 4
    inst._set_clip_warp(0, 0, pitch_coarse=-3)
    assert clip.warping is True and clip.warp_mode == 4
    assert clip.pitch_coarse == -3


def test_unknown_or_unavailable_warp_mode_is_refused(script_module):
    inst, clip, _ = make(script_module)
    with pytest.raises(ValueError, match="Unknown warp mode"):
        inst._set_clip_warp(0, 0, warp_mode="stretchy")
    with pytest.raises(ValueError, match="not available"):
        inst._set_clip_warp(0, 0, warp_mode="rex")


def test_original_bpm_rebuilds_markers_at_the_last_whole_beat(script_module):
    # 8 s at 131 BPM = 17.47 beats -> marker at beat 17 = 17 * 60/131 s.
    inst, clip, _ = make(script_module)
    info = inst._set_clip_warp(0, 0, original_bpm=131)
    assert clip.warping is True
    assert [(m.beat_time, round(m.sample_time, 4)) for m in clip.warp_markers] == [
        (0.0, 0.0), (17.0, round(17 * 60.0 / 131, 4))]
    assert any("131.00 BPM" in n for n in info["notes"])


def test_original_bpm_keeps_an_offset_first_marker(script_module):
    clip = FakeClip(markers=((0.0, 0.5), (16.0, 8.0)))
    inst, clip, _ = make(script_module, clip=clip)
    inst._set_clip_warp(0, 0, original_bpm=120)
    # 7.5 s after the first marker at 120 BPM = 15 beats.
    assert [(m.beat_time, m.sample_time) for m in clip.warp_markers] == [
        (0.0, 0.5), (15.0, 8.0)]


def test_original_bpm_reports_markers_live_refuses_to_remove(script_module):
    inst, clip, _ = make(script_module)

    def refuse(beat_time):
        raise RuntimeError("Cannot remove")
    clip.remove_warp_marker = refuse
    info = inst._set_clip_warp(0, 0, original_bpm=120)
    assert any("kept the warp marker at beat 16.000" in n for n in info["notes"])


def test_original_bpm_must_be_positive_and_is_checked_before_any_write(script_module):
    inst, clip, _ = make(script_module)
    with pytest.raises(ValueError, match="positive"):
        inst._set_clip_warp(0, 0, warp_mode="complex", original_bpm=0)
    assert clip.warp_mode == 0


def test_warp_on_a_midi_clip_is_refused(script_module):
    inst, _, _ = make(script_module, clip=FakeClip(audio=False))
    with pytest.raises(ValueError, match="audio clips"):
        inst._set_clip_warp(0, 0, warping=True)


def test_edit_warp_markers_removes_moves_then_adds(script_module):
    inst, clip, _ = make(script_module, clip=FakeClip(
        markers=((0.0, 0.0), (8.0, 4.0), (16.0, 8.0))))
    clip.warping = True
    inst._edit_warp_markers(0, 0, remove=[16.0],
                            move=[{"beat_time": 8.0, "beat_time_distance": 0.5}],
                            add=[{"beat_time": 12.0, "sample_time": 6.0}])
    assert [(m.beat_time, m.sample_time) for m in clip.warp_markers] == [
        (0.0, 0.0), (8.5, 4.0), (12.0, 6.0)]


def test_edit_warp_markers_requires_warping(script_module):
    inst, _, _ = make(script_module)
    with pytest.raises(ValueError, match="Turn warping on"):
        inst._edit_warp_markers(0, 0, remove=[16.0])


def test_arrangement_clips_are_addressed_by_location(script_module):
    arr = FakeClip()
    inst, _, _ = make(script_module, arrangement_clip=arr)
    inst._set_clip_warp(0, 0, location="arrangement", warp_mode="tones")
    assert arr.warp_mode == 1
    with pytest.raises(IndexError, match="Arrangement clip index"):
        inst._get_clip_warp(0, 3, location="arrangement")


def test_empty_slot_and_bad_location_are_refused(script_module):
    inst, _, _ = make(script_module)
    with pytest.raises(ValueError, match="No clip in slot 1"):
        inst._get_clip_warp(0, 1)
    with pytest.raises(ValueError, match="location"):
        inst._get_clip_warp(0, 0, location="timeline")


# ------------------------------------------------------------- automation

def test_linear_automation_ramps_in_resolution_steps(script_module):
    inst, clip, track = make(script_module, clip=FakeClip(audio=False, length=8.0))
    result = inst._set_clip_automation(
        0, 0, device_index=0, parameter_index=1,
        points=[{"time": 0, "value": 20}, {"time": 4, "value": 120}],
        interpolation="linear", resolution=1.0)
    env = clip.automation_envelope(track.devices[0].parameters[1])
    assert env.steps == [(0.0, 1.0, 20.0), (1.0, 1.0, 45.0), (2.0, 1.0, 70.0),
                         (3.0, 1.0, 95.0), (4.0, 4.0, 120.0)]
    assert result["parameter"] == "Filter Freq"
    assert result["steps_written"] == 5


def test_step_automation_holds_each_value_and_clamps(script_module):
    inst, clip, track = make(script_module, clip=FakeClip(audio=False, length=8.0))
    result = inst._set_clip_automation(
        0, 0, mixer_parameter="volume", interpolation="step",
        points=[{"time": 4, "value": 1.5}, {"time": 0, "value": 0.2}])
    env = clip.automation_envelope(track.mixer_device.volume)
    assert env.steps == [(0.0, 4.0, 0.2), (4.0, 4.0, 1.0)]
    assert "clamped" in result["note"]


def test_mixer_sends_and_panning_are_addressable(script_module):
    inst, clip, track = make(script_module, clip=FakeClip(audio=False, length=4.0))
    inst._set_clip_automation(0, 0, mixer_parameter="send:0",
                              points=[{"time": 0, "value": 0.7}])
    inst._set_clip_automation(0, 0, mixer_parameter="pan",
                              points=[{"time": 0, "value": -1.0}])
    assert clip.automation_envelope(track.mixer_device.sends[0]).steps == [(0.0, 4.0, 0.7)]
    assert clip.automation_envelope(track.mixer_device.panning).steps == [(0.0, 4.0, -1.0)]
    with pytest.raises(IndexError, match="Send index"):
        inst._set_clip_automation(0, 0, mixer_parameter="send:3",
                                  points=[{"time": 0, "value": 0.1}])


def test_clear_first_replaces_and_empty_points_clear(script_module):
    inst, clip, track = make(script_module, clip=FakeClip(audio=False, length=4.0))
    param = track.mixer_device.volume
    inst._set_clip_automation(0, 0, mixer_parameter="volume",
                              points=[{"time": 0, "value": 0.1}])
    inst._set_clip_automation(0, 0, mixer_parameter="volume",
                              points=[{"time": 0, "value": 0.9}])
    assert clip.automation_envelope(param).steps == [(0.0, 4.0, 0.9)]
    result = inst._set_clip_automation(0, 0, mixer_parameter="volume", points=[])
    assert clip.automation_envelope(param) is None
    assert result["cleared"] is True


def test_too_many_steps_is_refused_before_touching_the_clip(script_module):
    inst, clip, track = make(script_module, clip=FakeClip(audio=False, length=4.0))
    param = track.mixer_device.volume
    inst._set_clip_automation(0, 0, mixer_parameter="volume",
                              points=[{"time": 0, "value": 0.3}])
    with pytest.raises(ValueError, match="Too many steps"):
        inst._set_clip_automation(
            0, 0, mixer_parameter="volume", resolution=0.0001,
            points=[{"time": 0, "value": 0}, {"time": 4, "value": 1}])
    assert clip.automation_envelope(param).steps == [(0.0, 4.0, 0.3)]


def test_get_clip_automation_samples_the_envelope(script_module):
    inst, clip, track = make(script_module, clip=FakeClip(audio=False, length=4.0))
    none = inst._get_clip_automation(0, 0, mixer_parameter="volume")
    assert none["has_envelope"] is False and none["samples"] == []
    inst._set_clip_automation(0, 0, mixer_parameter="volume", interpolation="step",
                              points=[{"time": 0, "value": 0.2}, {"time": 2, "value": 0.8}])
    got = inst._get_clip_automation(0, 0, mixer_parameter="volume", resolution=1.0)
    assert [s["value"] for s in got["samples"]] == [0.2, 0.2, 0.8, 0.8, 0.8]


def test_bad_parameter_targets_are_refused(script_module):
    inst, _, _ = make(script_module, clip=FakeClip(audio=False))
    with pytest.raises(IndexError, match="Device index"):
        inst._set_clip_automation(0, 0, device_index=4, points=[{"time": 0, "value": 0}])
    with pytest.raises(IndexError, match="Parameter index"):
        inst._set_clip_automation(0, 0, device_index=0, parameter_index=9,
                                  points=[{"time": 0, "value": 0}])
    with pytest.raises(ValueError, match="mixer_parameter"):
        inst._set_clip_automation(0, 0, mixer_parameter="cutoff",
                                  points=[{"time": 0, "value": 0}])


# ------------------------------------------------------------ dispatch

def test_new_commands_are_advertised(script_module):
    for name in ("get_clip_warp", "set_clip_warp", "edit_warp_markers",
                 "get_clip_automation", "set_clip_automation"):
        assert name in script_module.SCRIPT_CAPABILITIES


def test_read_commands_dispatch_through_process_command(script_module):
    inst, _, _ = make(script_module)
    reply = inst._process_command({"type": "get_clip_warp",
                                   "params": {"track_index": 0, "clip_index": 0}})
    assert reply["status"] == "success"
    assert reply["result"]["warp_mode"] == "beats"


def test_write_commands_dispatch_on_the_main_thread(script_module):
    inst, clip, _ = make(script_module)
    inst.schedule_message = lambda delay, fn: fn()
    reply = inst._process_command({"type": "set_clip_warp", "params": {
        "track_index": 0, "clip_index": 0, "warp_mode": "complex", "original_bpm": 120}})
    assert reply["status"] == "success", reply
    assert clip.warp_mode == 4 and clip.warping is True


# --------------------------------------- Live.Clip.WarpMarker (1.9.0 fix)
# Found in Live 12.4.5: Clip.add_warp_marker refuses a dict ("No registered
# converter ... TWarpMarker from this Python object of type dict") and, as
# the markers had already been removed, left the clip without its end marker.

class _StrictClip(FakeClip):
    """Accepts only FakeLiveWarpMarker objects, like Live's Python API."""

    def add_warp_marker(self, marker):
        if not isinstance(marker, FakeLiveWarpMarker):
            raise TypeError("No registered converter to TWarpMarker from dict")
        self.warp_markers.append(FakeWarpMarker(marker.beat_time, marker.sample_time))
        self.warp_markers.sort(key=lambda m: m.beat_time)


class FakeLiveWarpMarker(object):
    """Live 12.4.5's signature: __init__(double sample_time, double beat_time),
    both required."""

    def __init__(self, sample_time, beat_time):
        self.sample_time = sample_time
        self.beat_time = beat_time


@pytest.fixture
def live_api(script_module, monkeypatch):
    import types
    live = types.SimpleNamespace(Clip=types.SimpleNamespace(WarpMarker=FakeLiveWarpMarker))
    monkeypatch.setattr(script_module, "Live", live)
    return live


def test_conform_builds_a_live_warp_marker_in_the_right_order(script_module, live_api):
    inst, clip, _ = make(script_module, clip=_StrictClip())
    inst._set_clip_warp(0, 0, original_bpm=120)
    assert [(m.beat_time, m.sample_time) for m in clip.warp_markers] == [
        (0.0, 0.0), (16.0, 8.0)]


def test_refused_end_marker_restores_the_removed_markers(script_module, live_api):
    inst, clip, _ = make(script_module, clip=_StrictClip(
        markers=((0.0, 0.0), (16.0, 8.0), (16.03125, 8.015))))
    original_add = clip.add_warp_marker
    calls = {"n": 0}

    def refuse_first(marker):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Constraint violated")
        original_add(marker)
    clip.add_warp_marker = refuse_first
    # The shadow marker (16.03125) isn't removed, so only the one at 16 is.
    with pytest.raises(RuntimeError, match="restored 1 of 1"):
        inst._set_clip_warp(0, 0, original_bpm=120)
    assert [(m.beat_time, m.sample_time) for m in clip.warp_markers] == [
        (0.0, 0.0), (16.0, 8.0), (16.03125, 8.015)]


def test_edit_warp_markers_builds_markers_before_touching_the_clip(script_module, live_api):
    inst, clip, _ = make(script_module, clip=_StrictClip())
    clip.warping = True
    inst._edit_warp_markers(0, 0, add=[{"beat_time": 8.0, "sample_time": 4.0}])
    assert (8.0, 4.0) in [(m.beat_time, m.sample_time) for m in clip.warp_markers]


def test_arrangement_automation_is_refused_with_an_explanation(script_module):
    # Live 12.4.5: "Not a session clip or parameter belongs to another track."
    arr = FakeClip(audio=False)
    inst, _, _ = make(script_module, arrangement_clip=arr)
    with pytest.raises(ValueError, match="Session clips"):
        inst._set_clip_automation(0, 0, location="arrangement", mixer_parameter="volume",
                                  points=[{"time": 0, "value": 0.5}])
    assert arr.envelopes == {}


def test_conform_leaves_the_shadow_marker_alone(script_module, live_api):
    # Live 12.4.5: "The shadow marker can't be deleted."
    clip = _StrictClip(markers=((0.0, 0.0), (15.0, 8.0), (15.03125, 8.015)))

    def remove(beat_time):
        if beat_time == 15.03125:
            raise RuntimeError("The shadow marker can't be deleted.")
        clip.warp_markers = [m for m in clip.warp_markers if m.beat_time != beat_time]
    clip.remove_warp_marker = remove
    inst, clip, _ = make(script_module, clip=clip)
    info = inst._set_clip_warp(0, 0, original_bpm=120)
    assert not any("kept" in n for n in info["notes"])
    assert (16.0, 8.0) in [(m.beat_time, m.sample_time) for m in clip.warp_markers]


def test_adding_a_marker_without_sample_time_is_refused_before_any_change(
        script_module, live_api):
    inst, clip, _ = make(script_module, clip=_StrictClip(
        markers=((0.0, 0.0), (8.0, 4.0), (16.0, 8.0))))
    clip.warping = True
    with pytest.raises(ValueError, match="needs a sample_time"):
        inst._edit_warp_markers(0, 0, remove=[8.0], add=[{"beat_time": 4.0}])
    assert [m.beat_time for m in clip.warp_markers] == [0.0, 8.0, 16.0]



# ------------------------------------------- original_bpm rounding (demo)
# A 16-beat drum loop at 140 BPM measured 6.856 s (1 ms short of 6.857 s):
# rounding down put the end marker at beat 15.

def test_a_loop_a_hair_short_of_16_beats_is_pinned_to_beat_16(script_module):
    seconds = 6.856031746031746
    inst, clip, _ = make(script_module, clip=FakeClip(
        seconds=seconds, markers=((0.0, 0.0), (16.0, seconds))))
    info = inst._set_clip_warp(0, 0, original_bpm=140)
    end = [m for m in clip.warp_markers if m.beat_time > 0][-1]
    assert end.beat_time == 16.0
    assert end.sample_time == pytest.approx(seconds, abs=1e-4)  # clamped to the file
    assert any("before beat 16" in n for n in info["notes"])


def test_a_loop_a_hair_long_is_pinned_to_the_exact_beat_time(script_module):
    seconds = 16 * 60.0 / 140 + 0.002
    inst, clip, _ = make(script_module, clip=FakeClip(seconds=seconds))
    info = inst._set_clip_warp(0, 0, original_bpm=140)
    end = [m for m in clip.warp_markers if m.beat_time > 0][-1]
    assert (end.beat_time, round(end.sample_time, 6)) == (16.0, round(16 * 60.0 / 140, 6))
    assert not any("before beat" in n for n in info["notes"])


def test_a_real_partial_beat_still_rounds_down(script_module):
    # 8 s at 131 BPM = 17.47 beats: not near a whole beat, keep 17.
    inst, clip, _ = make(script_module)
    inst._set_clip_warp(0, 0, original_bpm=131)
    assert [m.beat_time for m in clip.warp_markers][-1] == 17.0
