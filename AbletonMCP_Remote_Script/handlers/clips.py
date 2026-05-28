"""Clip creation, notes, naming, fire/stop, colors, loop markers."""

from __future__ import absolute_import, print_function, unicode_literals


def create_clip(song, track_index, clip_index, length, ctrl=None):
    """Create a new MIDI clip in the specified track and clip slot."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if clip_slot.has_clip:
            raise Exception("Clip slot already has a clip")
        clip_slot.create_clip(length)
        return {
            "name": clip_slot.clip.name,
            "length": clip_slot.clip.length,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error creating clip: " + str(e))
        raise


def add_notes_to_clip(song, track_index, clip_index, notes, ctrl=None):
    """Add MIDI notes to a clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        live_notes = []
        for note in notes:
            pitch = note.get("pitch", 60)
            start_time = note.get("start_time", 0.0)
            duration = note.get("duration", 0.25)
            velocity = note.get("velocity", 100)
            mute = note.get("mute", False)
            live_notes.append((pitch, start_time, duration, velocity, mute))
        clip.set_notes(tuple(live_notes))
        return {"note_count": len(notes)}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error adding notes to clip: " + str(e))
        raise


def set_clip_name(song, track_index, clip_index, name, ctrl=None):
    """Set the name of a clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        clip.name = name
        return {"name": clip.name}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting clip name: " + str(e))
        raise


def fire_clip(song, track_index, clip_index, ctrl=None):
    """Fire a clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip_slot.fire()
        return {"fired": True}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error firing clip: " + str(e))
        raise


def stop_clip(song, track_index, clip_index, ctrl=None):
    """Stop a clip."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        clip_slot.stop()
        return {"stopped": True}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error stopping clip: " + str(e))
        raise


def set_clip_color(song, track_index, clip_index, color_index, ctrl=None):
    """Set clip color."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip_slot.clip.color_index = color_index
        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "color_index": color_index,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting clip color: " + str(e))
        raise


def set_clip_loop_points(song, track_index, clip_index, loop_start, loop_end, ctrl=None):
    """Set clip loop start and end points."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        clip.loop_start = loop_start
        clip.loop_end = loop_end
        return {
            "loop_start": clip.loop_start,
            "loop_end": clip.loop_end,
            "loop_length": clip.loop_end - clip.loop_start,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting clip loop points: " + str(e))
        raise


def set_clip_start_marker(song, track_index, clip_index, start_marker, ctrl=None):
    """Set clip start marker position."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        clip.start_marker = start_marker
        return {"start_marker": clip.start_marker}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting clip start marker: " + str(e))
        raise


def set_clip_end_marker(song, track_index, clip_index, end_marker, ctrl=None):
    """Set clip end marker position."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot")
        clip = clip_slot.clip
        if not clip.is_audio_clip:
            raise Exception("Clip is not an audio clip")
        clip.end_marker = end_marker
        return {"end_marker": clip.end_marker}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error setting clip end marker: " + str(e))
        raise


def delete_clip(song, track_index, clip_index, ctrl=None):
    """Delete a clip from a clip slot."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not clip_slot.has_clip:
            raise Exception("No clip in slot to delete")
        clip_slot.delete_clip()
        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "deleted": True,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error deleting clip: " + str(e))
        raise
