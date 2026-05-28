"""Mixer: volume, pan, mute, solo, sends."""

from __future__ import absolute_import, print_function, unicode_literals


def set_track_volume(song, track_index, volume, ctrl=None):
    """Set track volume."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.mixer_device.volume.value = volume
        return {"track_index": track_index, "volume": track.mixer_device.volume.value}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track volume: " + str(e))
        raise


def set_track_pan(song, track_index, pan, ctrl=None):
    """Set track pan."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.mixer_device.panning.value = pan
        return {"track_index": track_index, "pan": track.mixer_device.panning.value}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track pan: " + str(e))
        raise


def set_track_mute(song, track_index, mute, ctrl=None):
    """Set track mute."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.mute = mute
        return {"track_index": track_index, "mute": track.mute}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track mute: " + str(e))
        raise


def set_track_solo(song, track_index, solo, ctrl=None):
    """Set track solo."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        track.solo = solo
        return {"track_index": track_index, "solo": track.solo}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track solo: " + str(e))
        raise


def set_track_send(song, track_index, send_index, value, ctrl=None):
    """Set track send level."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if not hasattr(track, "mixer_device"):
            raise Exception("Track has no mixer device")
        mixer = track.mixer_device
        if not hasattr(mixer, "sends"):
            raise Exception("Mixer has no sends")
        if send_index < 0 or send_index >= len(mixer.sends):
            raise IndexError("Send index out of range")
        send = mixer.sends[send_index]
        value = max(0.0, min(1.0, value))
        send.value = value
        return {
            "track_index": track_index,
            "send_index": send_index,
            "value": send.value,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting track send: " + str(e))
        raise
