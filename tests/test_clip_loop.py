"""Clip loop and markers (Remote Script 1.11.0).

FakeClip enforces what Live does: a start at or past the end (or an end at
or before the start) is refused, so these tests catch a wrong write order.
"""

import pytest

from test_remote_script_bridge import _load_script_module, make_instance


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


class FakeClip(object):
    def __init__(self, length=16.0, audio=False, warping=True):
        self.name = "clip"
        self.is_audio_clip = audio
        self.is_midi_clip = not audio
        self.warping = warping
        self.looping = True
        self._loop_start, self._loop_end = 0.0, length
        self._start_marker, self._end_marker = 0.0, length
        self.start_time, self.end_time = 32.0, 32.0 + length
        self.writes = []

    @property
    def length(self):
        return (self._loop_end - self._loop_start) if self.looping else (
            self._end_marker - self._start_marker)

    def _guard(self, name, start, end):
        if start >= end:
            raise RuntimeError("Invalid %s" % name)

    @property
    def loop_start(self):
        return self._loop_start

    @loop_start.setter
    def loop_start(self, v):
        self._guard("loop_start", v, self._loop_end)
        self._loop_start = v
        self.writes.append("loop_start")

    @property
    def loop_end(self):
        return self._loop_end

    @loop_end.setter
    def loop_end(self, v):
        self._guard("loop_end", self._loop_start, v)
        self._loop_end = v
        self.writes.append("loop_end")

    @property
    def start_marker(self):
        # Live 12.4.5: unlooped, start_marker mirrors loop_start.
        return self._start_marker if self.looping else self._loop_start

    @start_marker.setter
    def start_marker(self, v):
        if not self.looping:
            return  # Live ignores it, without an error
        self._guard("start_marker", v, self._end_marker)
        self._start_marker = v

    @property
    def end_marker(self):
        return self._end_marker

    @end_marker.setter
    def end_marker(self, v):
        self._guard("end_marker", self._start_marker, v)
        self._end_marker = v


class FakeSlot(object):
    def __init__(self, clip=None):
        self.clip = clip

    @property
    def has_clip(self):
        return self.clip is not None


class FakeTrack(object):
    def __init__(self, clip, arrangement=()):
        self.clip_slots = [FakeSlot(clip)]
        self.arrangement_clips = list(arrangement)


class FakeSong(object):
    def __init__(self, tracks):
        self.tracks = tracks
        self.return_tracks = []


def make(script_module, clip=None, arrangement=()):
    clip = clip or FakeClip()
    inst = make_instance(script_module)
    inst._song = FakeSong([FakeTrack(clip, arrangement)])
    return inst, clip


def test_get_clip_loop_reports_brace_markers_and_units(script_module):
    inst, _ = make(script_module)
    info = inst._get_clip_loop(0, 0)
    assert (info["loop_start"], info["loop_end"]) == (0.0, 16.0)
    assert info["looping"] is True and info["units"] == "beats"
    assert "arrangement_start" not in info


def test_unwarped_audio_is_reported_in_seconds(script_module):
    inst, _ = make(script_module, clip=FakeClip(audio=True, warping=False))
    assert inst._get_clip_loop(0, 0)["units"] == "seconds"


def test_shorten_loop_with_loop_length(script_module):
    inst, clip = make(script_module)
    info = inst._set_clip_loop(0, 0, loop_start=0, loop_length=4)
    assert (clip.loop_start, clip.loop_end) == (0.0, 4.0)
    assert "adjusted" not in info


def test_moving_the_loop_forward_past_its_end_writes_end_first(script_module):
    inst, clip = make(script_module, clip=FakeClip(length=4.0))
    inst._set_clip_loop(0, 0, loop_start=8, loop_end=12)
    assert (clip.loop_start, clip.loop_end) == (8.0, 12.0)
    assert clip.writes == ["loop_end", "loop_start"]


def test_moving_the_loop_backward_writes_start_first(script_module):
    inst, clip = make(script_module)
    clip._loop_start, clip._loop_end = 8.0, 12.0
    inst._set_clip_loop(0, 0, loop_start=0, loop_end=4)
    assert (clip.loop_start, clip.loop_end) == (0.0, 4.0)
    assert clip.writes == ["loop_start", "loop_end"]


def test_markers_on_a_looping_clip(script_module):
    inst, clip = make(script_module)
    info = inst._set_clip_loop(0, 0, start_marker=2, end_marker=6)
    assert (clip.start_marker, clip.end_marker) == (2.0, 6.0)
    assert info["playback"] == {"starts_at": 2.0, "repeats": [0.0, 16.0]}


def test_markers_on_an_unlooped_clip_go_to_the_loop_brace(script_module):
    # Live 12.4.5 ignored start_marker=2 on an unlooped clip; it plays
    # loop_start -> loop_end.
    inst, clip = make(script_module)
    info = inst._set_clip_loop(0, 0, looping=False, start_marker=2, end_marker=6)
    assert clip.looping is False
    assert (clip.loop_start, clip.loop_end) == (2.0, 6.0)
    assert info["playback"] == {"plays_once": [2.0, 6.0]}
    assert "adjusted" not in info
    assert any("loop_start/loop_end" in n for n in info["notes"])


def test_unlooped_markers_and_loop_values_together_are_refused(script_module):
    inst, clip = make(script_module)
    clip.looping = False
    with pytest.raises(ValueError, match="doesn't loop"):
        inst._set_clip_loop(0, 0, start_marker=2, loop_end=6)


def test_invalid_values_are_refused_before_any_write(script_module):
    inst, clip = make(script_module)
    with pytest.raises(ValueError, match="start_marker .* must be before end_marker"):
        inst._set_clip_loop(0, 0, loop_start=4, loop_end=8, start_marker=10, end_marker=6)
    assert (clip.loop_start, clip.loop_end) == (0.0, 16.0)
    with pytest.raises(ValueError, match="loop_length must be positive"):
        inst._set_clip_loop(0, 0, loop_length=0)
    with pytest.raises(ValueError, match="not both"):
        inst._set_clip_loop(0, 0, loop_start=0, loop_end=8, loop_length=4)


def test_adjusted_reports_values_live_changed(script_module):
    inst, clip = make(script_module)

    class Snapping(FakeClip):
        @FakeClip.loop_end.setter
        def loop_end(self, v):
            FakeClip.loop_end.fset(self, round(v))
    snapping = Snapping()
    inst, clip = make(script_module, clip=snapping)
    info = inst._set_clip_loop(0, 0, loop_end=7.6)
    assert info["adjusted"] == {"loop_end": {"requested": 7.6, "applied": 8.0}}


def test_arrangement_clip_reports_its_place(script_module):
    arr = FakeClip(length=8.0)
    inst, session = make(script_module, arrangement=[arr])
    info = inst._set_clip_loop(0, 0, location="arrangement", loop_length=2)
    assert arr.loop_end == 2.0 and session.loop_end == 16.0
    assert info["arrangement_start"] == 32.0


def test_dispatch(script_module):
    inst, clip = make(script_module)
    inst.schedule_message = lambda delay, fn: fn()
    reply = inst._process_command({"type": "set_clip_loop", "params": {
        "track_index": 0, "clip_index": 0, "loop_start": 4, "loop_length": 4}})
    assert reply["status"] == "success", reply
    reply = inst._process_command({"type": "get_clip_loop", "params": {
        "track_index": 0, "clip_index": 0}})
    assert (reply["result"]["loop_start"], reply["result"]["loop_end"]) == (4.0, 8.0)
    for name in ("get_clip_loop", "set_clip_loop"):
        assert name in script_module.SCRIPT_CAPABILITIES
