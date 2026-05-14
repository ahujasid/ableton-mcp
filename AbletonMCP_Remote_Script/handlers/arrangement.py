"""Arrangement: locators (multi-tick stays in __init__), copy to arrangement, get arrangement clips."""

from __future__ import absolute_import, print_function, unicode_literals


def copy_clip_to_arrangement(song, track_index, clip_index, arrangement_time, ctrl=None):
    """Copy a clip from session view to arrangement view."""
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
        try:
            clip.duplicate_clip_to(track, arrangement_time)
            return {
                "copied": True,
                "track_index": track_index,
                "clip_index": clip_index,
                "arrangement_time": arrangement_time,
            }
        except AttributeError:
            if ctrl:
                ctrl.log_message("Using alternative clip copy method")
            clip_length = clip.length
            return {
                "copied": False,
                "note": (
                    "Direct arrangement copy not supported in this API version. "
                    "Use duplicate_clip instead."
                ),
                "clip_length": clip_length,
                "suggested_time": arrangement_time,
            }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error copying clip to arrangement: " + str(e))
        raise


def get_arrangement_clips(song, track_index, ctrl=None):
    """Get all clips in arrangement view for a track."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        clips = []
        if not hasattr(track, "arrangement_clips"):
            raise Exception(
                "Track does not have arrangement clips "
                "(may be a group track or return track)"
            )
        for clip in track.arrangement_clips:
            clip_info = {
                "name": clip.name,
                "start_time": clip.start_time,
                "end_time": clip.end_time,
                "length": clip.length,
                "loop_start": getattr(clip, "loop_start", None),
                "loop_end": getattr(clip, "loop_end", None),
                "is_audio_clip": clip.is_audio_clip,
                "is_midi_clip": clip.is_midi_clip,
                "muted": getattr(clip, "muted", False),
                "color_index": getattr(clip, "color_index", None),
            }
            clips.append(clip_info)
        return {
            "track_index": track_index,
            "track_name": track.name,
            "clip_count": len(clips),
            "clips": clips,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error getting arrangement clips: " + str(e))
        raise


def delete_arrangement_clip(song, track_index, start_time=None, end_time=None,
                            arrangement_clip_index=None, ctrl=None):
    """Delete arrangement clip(s) on a track.

    Match by either:
      - arrangement_clip_index: index into track.arrangement_clips
      - start_time + end_time: delete every clip whose start_time falls in [start_time, end_time)
        (use end_time = start_time + 0.001 to target one exact start_time)
    """
    if track_index < 0 or track_index >= len(song.tracks):
        raise IndexError("Track index out of range")
    track = song.tracks[track_index]
    if not hasattr(track, "arrangement_clips"):
        raise Exception("Track has no arrangement clips")

    arr_clips = list(track.arrangement_clips)
    targets = []
    if arrangement_clip_index is not None:
        if arrangement_clip_index < 0 or arrangement_clip_index >= len(arr_clips):
            raise IndexError("arrangement_clip_index out of range")
        targets = [arr_clips[arrangement_clip_index]]
    elif start_time is not None and end_time is not None:
        targets = [c for c in arr_clips if start_time <= c.start_time < end_time]
    else:
        raise ValueError("Must provide arrangement_clip_index or (start_time, end_time)")

    deleted = []
    for c in targets:
        info = {"name": c.name, "start_time": c.start_time, "end_time": c.end_time}
        # Try multiple delete methods; Live API surface varies by version
        deleted_ok = False
        for fn in (
            lambda: track.delete_clip(c),
            lambda: c.delete(),
            lambda: song.delete_clip(c),
        ):
            try:
                fn()
                deleted_ok = True
                break
            except Exception:
                continue
        if not deleted_ok:
            # Fall back to song.delete_time to surgically remove this clip's slice on this track
            raise Exception(
                "No working delete method for arrangement clip at {0}".format(c.start_time)
            )
        deleted.append(info)

    return {
        "track_index": track_index,
        "track_name": track.name,
        "deleted_count": len(deleted),
        "deleted": deleted,
    }


def inspect_arrangement_clip(song, track_index, arrangement_clip_index, ctrl=None):
    """Inspect available attributes/methods on an arrangement clip for debugging."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]

        # If arrangement_clip_index == -1, inspect the clip slot instead
        if arrangement_clip_index == -1:
            slot = track.clip_slots[0]
            attrs = []
            for attr in dir(slot):
                if attr.startswith("_"):
                    continue
                try:
                    val = getattr(slot, attr)
                    if callable(val):
                        attrs.append({"name": attr, "type": "method"})
                    else:
                        attrs.append({"name": attr, "type": "property", "value": str(val)[:100]})
                except Exception:
                    attrs.append({"name": attr, "type": "inaccessible"})
            return {"object": "ClipSlot", "attributes": attrs}

        arr_clips = list(track.arrangement_clips)
        if arrangement_clip_index < 0 or arrangement_clip_index >= len(arr_clips):
            raise IndexError("Arrangement clip index out of range")
        clip = arr_clips[arrangement_clip_index]

        attrs = []
        for attr in dir(clip):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(clip, attr)
                if callable(val):
                    attrs.append({"name": attr, "type": "method"})
                else:
                    attrs.append({"name": attr, "type": "property", "value": str(val)[:100]})
            except Exception:
                attrs.append({"name": attr, "type": "inaccessible"})

        return {
            "track_index": track_index,
            "clip_name": clip.name,
            "attributes": attrs,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error inspecting clip: " + str(e))
        raise


def copy_arrangement_to_session(song, track_index, arrangement_clip_index, clip_slot_index, ctrl=None):
    """Copy an arrangement clip into a session clip slot.

    Uses create_audio_clip on the target slot with the arrangement clip's file_path.
    """
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]

        if not hasattr(track, "arrangement_clips"):
            raise Exception("Track has no arrangement clips")

        arr_clips = list(track.arrangement_clips)
        if arrangement_clip_index < 0 or arrangement_clip_index >= len(arr_clips):
            raise IndexError(
                "Arrangement clip index %d out of range (track has %d)"
                % (arrangement_clip_index, len(arr_clips))
            )

        if clip_slot_index < 0 or clip_slot_index >= len(track.clip_slots):
            raise IndexError("Clip slot index out of range")

        src = arr_clips[arrangement_clip_index]
        target_slot = track.clip_slots[clip_slot_index]

        if target_slot.has_clip:
            raise Exception("Target clip slot already has a clip")

        if not src.is_audio_clip:
            raise Exception("Only audio clips supported")

        file_path = src.file_path
        if not file_path:
            raise Exception("Arrangement audio clip has no file_path")

        # Create audio clip in session slot from the same file
        target_slot.create_audio_clip(file_path)

        # Copy properties from arrangement clip
        if target_slot.has_clip:
            new_clip = target_slot.clip
            new_clip.name = src.name
            new_clip.looping = True
            new_clip.loop_start = src.loop_start
            new_clip.loop_end = src.loop_end
            new_clip.warping = src.warping
            if hasattr(src, "warp_mode"):
                new_clip.warp_mode = src.warp_mode
            if hasattr(src, "gain"):
                new_clip.gain = src.gain

        return {
            "copied": True,
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "clip_name": src.name,
            "file_path": file_path,
        }

    except Exception as e:
        if ctrl:
            ctrl.log_message("Error copying arrangement to session: " + str(e))
        raise
