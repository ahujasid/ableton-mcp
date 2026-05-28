"""MIDI: get notes, quantize, transpose, duplicate clip, capture, groove."""

from __future__ import absolute_import, print_function, unicode_literals


def _normalize_note(note, ctrl=None):
    """Convert a note (tuple, list, or object) to a JSON-safe dict."""
    if isinstance(note, (tuple, list)) and len(note) >= 5:
        return {
            "pitch": int(note[0]),
            "start_time": float(note[1]),
            "duration": float(note[2]),
            "velocity": int(note[3]),
            "mute": bool(note[4]),
        }
    if hasattr(note, "pitch"):
        return {
            "pitch": int(getattr(note, "pitch", 0)),
            "start_time": float(getattr(note, "start_time", 0.0)),
            "duration": float(getattr(note, "duration", 0.0)),
            "velocity": int(getattr(note, "velocity", 100)),
            "mute": bool(getattr(note, "mute", False)),
        }
    if isinstance(note, dict) and "pitch" in note:
        return {
            "pitch": int(note.get("pitch", 0)),
            "start_time": float(note.get("start_time", 0.0)),
            "duration": float(note.get("duration", 0.0)),
            "velocity": int(note.get("velocity", 100)),
            "mute": bool(note.get("mute", note.get("muted", False))),
        }
    return None


def _get_raw_notes(clip, ctrl=None):
    """Retrieve raw notes from clip with API fallback for Live version compatibility."""
    if hasattr(clip, "get_all_notes_extended"):
        raw = clip.get_all_notes_extended()
    elif hasattr(clip, "get_all_notes"):
        raw = clip.get_all_notes()
    elif hasattr(clip, "get_notes_extended"):
        raw = clip.get_notes_extended(
            from_pitch=0, pitch_span=128, from_time=0, time_span=clip.length
        )
    else:
        notes_data = clip.get_notes(0, 0, clip.length, 128)
        raw = notes_data[0] if notes_data and len(notes_data) > 0 else []

    if isinstance(raw, dict):
        return raw.get("notes", [])
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return []


def get_clip_notes(song, track_index, clip_index, ctrl=None):
    """Read all MIDI notes from a clip with metadata (quantization, scale, clip length).

    Returns notes as JSON-safe dicts (pitch, start_time, duration, velocity, mute)
    compatible with add_notes_to_clip for round-trip workflows.
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
        clip = clip_slot.clip
        if not clip.is_midi_clip:
            raise Exception("Clip is not a MIDI clip")

        raw_notes = _get_raw_notes(clip, ctrl)
        notes_list = []
        for note in raw_notes:
            normalized = _normalize_note(note, ctrl)
            if normalized is not None:
                notes_list.append(normalized)

        clip_length = float(clip.length)
        quantization = getattr(clip, "launch_quantization", None)
        if quantization is not None and not isinstance(quantization, (int, float, type(None))):
            try:
                quantization = int(quantization)
            except (TypeError, ValueError):
                quantization = None

        scale_info = None
        if hasattr(song, "scale_mode"):
            scale_info = {
                "enabled": bool(getattr(song, "scale_mode", False)),
                "root_note": getattr(song, "root_note", None),
                "scale_name": getattr(song, "scale_name", None),
                "scale_intervals": list(getattr(song, "scale_intervals", []))
                    if getattr(song, "scale_intervals", None) is not None else None,
            }
            scale_info = {k: v for k, v in scale_info.items() if v is not None or k == "enabled"}

        return {
            "clip_name": clip.name,
            "clip_length": clip_length,
            "note_count": len(notes_list),
            "notes": notes_list,
            "quantization": quantization,
            "scale_info": scale_info,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message(
                "Error getting clip notes (track=%s, clip=%s): %s"
                % (track_index, clip_index, str(e))
            )
        raise


def get_notes_from_clip(song, track_index, clip_index, ctrl=None):
    """Get all MIDI notes from a clip (delegates to get_clip_notes for consistency)."""
    result = get_clip_notes(song, track_index, clip_index, ctrl)
    return {
        "clip_name": result["clip_name"],
        "clip_length": result["clip_length"],
        "note_count": result["note_count"],
        "notes": result["notes"],
    }


def quantize_clip(song, track_index, clip_index, quantize_to, ctrl=None):
    """Quantize notes in a clip."""
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
        clip.quantize(quantize_to, 1.0)
        return {"quantized": True, "quantize_to": quantize_to}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error quantizing clip: " + str(e))
        raise


def transpose_clip(song, track_index, clip_index, semitones, ctrl=None):
    """Transpose notes in a clip."""
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
        clip.select_all_notes()
        notes = clip.get_selected_notes()
        new_notes = []
        for note in notes:
            pitch, time_val, duration, velocity, mute = note
            new_pitch = max(0, min(127, pitch + semitones))
            new_notes.append((new_pitch, time_val, duration, velocity, mute))
        clip.replace_selected_notes(tuple(new_notes))
        clip.deselect_all_notes()
        return {
            "transposed": True,
            "semitones": semitones,
            "note_count": len(new_notes),
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error transposing clip: " + str(e))
        raise


def duplicate_clip(
    song, source_track, source_clip, dest_track, dest_clip, ctrl=None
):
    """Duplicate a clip."""
    try:
        if source_track < 0 or source_track >= len(song.tracks):
            raise IndexError("Source track index out of range")
        if dest_track < 0 or dest_track >= len(song.tracks):
            raise IndexError("Destination track index out of range")
        src_track = song.tracks[source_track]
        dst_track = song.tracks[dest_track]
        if source_clip < 0 or source_clip >= len(src_track.clip_slots):
            raise IndexError("Source clip index out of range")
        if dest_clip < 0 or dest_clip >= len(dst_track.clip_slots):
            raise IndexError("Destination clip index out of range")
        src_slot = src_track.clip_slots[source_clip]
        if not src_slot.has_clip:
            raise Exception("No clip in source slot")
        src_track.duplicate_clip_slot(source_clip)
        try:
            song.view.highlighted_clip_slot = src_track.clip_slots[
                source_clip + 1
            ]
            song.view.highlighted_clip_slot.clip.duplicate_loop()
        except Exception:
            pass
        return {"duplicated": True}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error duplicating clip: " + str(e))
        raise


def capture_midi(song, track_index, clip_index, ctrl=None):
    """Capture recently played MIDI into a clip slot."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        clip_slot = track.clip_slots[clip_index]
        if not hasattr(song, "capture_midi"):
            raise Exception(
                "Capture MIDI is not available (requires Live 11 or later)"
            )
        song.capture_midi()
        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "captured": True,
            "has_clip": clip_slot.has_clip,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error capturing MIDI: " + str(e))
        raise


def apply_groove(song, track_index, clip_index, groove_amount, ctrl=None):
    """Apply groove to a MIDI clip."""
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
        if clip.is_audio_clip:
            raise Exception("Cannot apply groove to audio clips")
        if hasattr(clip, "groove_amount"):
            clip.groove_amount = groove_amount
        else:
            raise Exception("Groove amount not available on this clip")
        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "groove_amount": groove_amount,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error applying groove: " + str(e))
        raise
