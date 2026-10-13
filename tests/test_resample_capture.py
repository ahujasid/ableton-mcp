"""Tests for the resample-capture audio export in the Live-side script.

Live is faked with just enough of the Song / Track / Clip surface for the
capture to arm, record, stop and restore. No Ableton, no network.
"""

import pytest

from test_remote_script_bridge import _load_script_module, make_instance


class FakeRouting(object):
    def __init__(self, display_name):
        self.display_name = display_name


class FakeClip(object):
    def __init__(self, start_time, end_time, file_path=None):
        self.start_time = start_time
        self.end_time = end_time
        self.file_path = file_path


class FakeTrack(object):
    def __init__(self, name="Track", arm=False, clips=()):
        self.name = name
        self.arm = arm
        self.can_be_armed = True
        self.arrangement_clips = list(clips)
        self.available_input_routing_types = [
            FakeRouting("Ext. In"), FakeRouting("Resampling"), FakeRouting("No Input")]
        self.input_routing_type = self.available_input_routing_types[0]
        self.current_monitoring_state = 1


class FakeSong(object):
    def __init__(self, tracks):
        self.tracks = list(tracks)
        self.is_playing = False
        self.record_mode = False
        self.loop = True
        self.metronome = True
        self.back_to_arranger = True
        self.current_song_time = 0.0
        self.song_length = 64.0
        self.tempo = 120.0
        self._time_listeners = []

    def create_audio_track(self, index):
        self.tracks.append(FakeTrack())

    def delete_track(self, index):
        del self.tracks[index]

    def start_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False

    def add_current_song_time_listener(self, cb):
        self._time_listeners.append(cb)

    def remove_current_song_time_listener(self, cb):
        self._time_listeners.remove(cb)

    def current_song_time_has_listener(self, cb):
        return cb in self._time_listeners

    def advance_to(self, beat):
        self.current_song_time = beat
        for cb in list(self._time_listeners):
            cb()


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


def make_capture(script_module, tracks):
    inst = make_instance(script_module)
    inst._song = FakeSong(tracks)
    # Run deferred work immediately, as Live's next tick would.
    inst.schedule_message = lambda _delay, fn: fn()
    return inst


def test_start_sets_up_a_resampling_track_and_records(script_module):
    armed = FakeTrack("Vocals", arm=True)
    inst = make_capture(script_module, [armed, FakeTrack("Drums", clips=[FakeClip(0, 32)])])

    result = inst._start_resample_capture(0.0, None)
    song = inst._song
    capture = song.tracks[-1]

    assert result["end_time"] == 32  # last arrangement clip, not song_length
    assert result["estimated_seconds"] == pytest.approx(16.0)
    assert capture.name == "MCP Resample"
    assert capture.input_routing_type.display_name == "Resampling"
    assert capture.current_monitoring_state == 2  # Off: no feedback loop
    assert capture.arm is True
    assert armed.arm is False  # would otherwise be recorded too
    assert song.record_mode and song.is_playing
    assert not song.loop and not song.metronome and not song.back_to_arranger


def test_reaching_the_end_stops_and_restores(script_module):
    armed = FakeTrack("Vocals", arm=True)
    inst = make_capture(script_module, [armed])
    inst._start_resample_capture(0.0, 16.0)
    song = inst._song

    song.advance_to(8.0)
    assert inst._get_resample_capture_status()["progress"] == pytest.approx(0.5)

    song.tracks[-1].arrangement_clips.append(FakeClip(0, 16, "C:/Set/Samples/Recorded/x.wav"))
    song.advance_to(16.0)

    assert not song.record_mode and not song.is_playing
    assert armed.arm is True
    assert song.tracks[-1].arm is False
    assert song.loop and song.metronome
    assert song._time_listeners == []

    status = inst._get_resample_capture_status()
    assert status["status"] == "done"
    assert status["reason"] == "completed"
    assert status["file_path"] == "C:/Set/Samples/Recorded/x.wav"
    assert status["track_index"] == 1


def test_stopping_the_transport_by_hand_ends_the_capture(script_module):
    inst = make_capture(script_module, [FakeTrack()])
    inst._start_resample_capture(0.0, 16.0)
    inst._song.stop_playing()

    status = inst._get_resample_capture_status()
    assert status["status"] == "done"
    assert status["reason"] == "stopped_early"
    assert not inst._song.record_mode


def test_refuses_to_start_twice_or_while_playing(script_module):
    inst = make_capture(script_module, [FakeTrack()])
    inst._start_resample_capture(0.0, 16.0)
    with pytest.raises(Exception, match="already running"):
        inst._start_resample_capture(0.0, 16.0)

    other = make_capture(script_module, [FakeTrack()])
    other._song.is_playing = True
    with pytest.raises(Exception, match="Stop playback"):
        other._start_resample_capture(0.0, 16.0)


def test_empty_range_is_rejected_before_touching_the_set(script_module):
    inst = make_capture(script_module, [FakeTrack()])
    with pytest.raises(ValueError):
        inst._start_resample_capture(8.0, 8.0)
    assert len(inst._song.tracks) == 1


def test_cancel_stops_and_deletes_the_capture_track(script_module):
    armed = FakeTrack("Vocals", arm=True)
    inst = make_capture(script_module, [armed])
    inst._start_resample_capture(0.0, 16.0)

    assert inst._cancel_resample_capture()["cancelled"] is True
    assert len(inst._song.tracks) == 1
    assert armed.arm is True
    assert not inst._song.is_playing
    assert inst._get_resample_capture_status() == {"status": "idle"}
