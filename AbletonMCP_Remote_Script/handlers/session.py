"""Session-level commands: tempo, playback, loop, recording, metronome."""

from __future__ import absolute_import, print_function, unicode_literals


def get_session_info(song, ctrl=None):
    """Get information about the current session."""
    try:
        result = {
            "tempo": song.tempo,
            "signature_numerator": song.signature_numerator,
            "signature_denominator": song.signature_denominator,
            "track_count": len(song.tracks),
            "return_track_count": len(song.return_tracks),
            "master_track": {
                "name": "Master",
                "volume": song.master_track.mixer_device.volume.value,
                "panning": song.master_track.mixer_device.panning.value,
            },
        }
        return result
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting session info: " + str(e))
        raise


def set_tempo(song, tempo, ctrl=None):
    """Set the tempo of the session."""
    try:
        song.tempo = tempo
        return {"tempo": song.tempo}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting tempo: " + str(e))
        raise


def start_playback(song, ctrl=None):
    """Start playing the session."""
    try:
        song.start_playing()
        return {"playing": song.is_playing}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error starting playback: " + str(e))
        raise


def stop_playback(song, ctrl=None):
    """Stop playing the session."""
    try:
        song.stop_playing()
        return {"playing": song.is_playing}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error stopping playback: " + str(e))
        raise


def get_loop_info(song, ctrl=None):
    """Get loop information."""
    try:
        return {
            "loop_start": song.loop_start,
            "loop_end": song.loop_end,
            "loop_length": song.loop_length,
            "loop": song.loop,
            "current_song_time": song.current_song_time,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting loop info: " + str(e))
        raise


def set_loop_start(song, position, ctrl=None):
    """Set the loop start position."""
    try:
        song.loop_start = position
        return {"loop_start": song.loop_start, "loop_end": song.loop_end}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting loop start: " + str(e))
        raise


def set_loop_end(song, position, ctrl=None):
    """Set the loop end position."""
    try:
        song.loop_end = position
        return {"loop_start": song.loop_start, "loop_end": song.loop_end}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting loop end: " + str(e))
        raise


def set_loop_length(song, length, ctrl=None):
    """Set the loop length."""
    try:
        song.loop_length = length
        return {
            "loop_start": song.loop_start,
            "loop_end": song.loop_end,
            "loop_length": song.loop_length,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting loop length: " + str(e))
        raise


def set_playback_position(song, position, ctrl=None):
    """Set the playback position."""
    try:
        song.current_song_time = position
        return {"current_song_time": song.current_song_time}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting playback position: " + str(e))
        raise


def set_arrangement_overdub(song, enabled, ctrl=None):
    """Enable or disable arrangement overdub mode."""
    try:
        song.arrangement_overdub = enabled
        return {"arrangement_overdub": song.arrangement_overdub}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting arrangement overdub: " + str(e))
        raise


def start_arrangement_recording(song, ctrl=None):
    """Start recording into the arrangement view."""
    try:
        song.record_mode = True
        if not song.is_playing:
            song.start_playing()
        return {
            "recording": song.record_mode,
            "playing": song.is_playing,
            "arrangement_overdub": song.arrangement_overdub,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error starting arrangement recording: " + str(e))
        raise


def stop_arrangement_recording(song, ctrl=None):
    """Stop arrangement recording."""
    try:
        song.record_mode = False
        if song.is_playing:
            song.stop_playing()
        return {"recording": song.record_mode, "playing": song.is_playing}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error stopping arrangement recording: " + str(e))
        raise


def get_recording_status(song, ctrl=None):
    """Get the current recording status."""
    try:
        armed_tracks = []
        for i, track in enumerate(song.tracks):
            if track.arm:
                armed_tracks.append({
                    "index": i,
                    "name": track.name,
                    "is_midi": track.has_midi_input,
                    "is_audio": track.has_audio_input,
                })
        return {
            "record_mode": song.record_mode,
            "arrangement_overdub": song.arrangement_overdub,
            "session_record": song.session_record,
            "is_playing": song.is_playing,
            "armed_tracks": armed_tracks,
            "armed_track_count": len(armed_tracks),
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting recording status: " + str(e))
        raise


def set_metronome(song, enabled, ctrl=None):
    """Enable or disable the metronome."""
    try:
        song.metronome = enabled
        return {"metronome": song.metronome}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting metronome: " + str(e))
        raise


def tap_tempo(song, ctrl=None):
    """Tap tempo to set BPM."""
    try:
        song.tap_tempo()
        return {"tempo": song.tempo}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error tapping tempo: " + str(e))
        raise


def switch_to_view(song, view_name, ctrl=None):
    """Switch Ableton UI focus between Session and Arrangement views."""
    try:
        if not ctrl:
            raise Exception("Control surface context is required for view switching")
        if not view_name:
            raise ValueError("view_name is required")

        normalized = str(view_name).strip().lower()
        view_map = {
            "session": "Session",
            "sessionview": "Session",
            "arrangement": "Arranger",
            "arranger": "Arranger",
            "arrangementview": "Arranger",
        }
        target = view_map.get(normalized)
        if not target:
            raise ValueError("view_name must be 'session' or 'arrangement'")

        app_view = ctrl.application().view
        app_view.show_view(target)
        app_view.focus_view(target)
        return {"view": target}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error switching view: " + str(e))
        raise


def record_arrangement_clip(song, track_index, clip_index, start_time=0.0, ctrl=None):
    """Start arrangement recording and launch a session clip at a target time.

    This starts recording and playback, launches the requested clip, and leaves
    transport running so callers can decide when to stop recording.
    """
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")

        if ctrl:
            try:
                app_view = ctrl.application().view
                app_view.show_view("Arranger")
                app_view.focus_view("Arranger")
            except Exception:
                pass

        if getattr(track, "can_be_armed", False):
            track.arm = True
        song.current_song_time = max(0.0, float(start_time))
        song.arrangement_overdub = True
        song.record_mode = True
        if not song.is_playing:
            song.start_playing()
        clip_slot.fire()

        return {
            "recording": song.record_mode,
            "playing": song.is_playing,
            "arrangement_overdub": song.arrangement_overdub,
            "track_index": track_index,
            "clip_index": clip_index,
            "start_time": song.current_song_time,
            "note": "Recording started. Call stop_arrangement_recording to end capture.",
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error recording arrangement clip: " + str(e))
        raise
