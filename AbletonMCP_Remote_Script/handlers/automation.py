"""Automation and arrangement time: create/clear automation, delete/duplicate/insert time."""

from __future__ import absolute_import, print_function, unicode_literals

import traceback


def _find_parameter(track, parameter_name):
    """Find a parameter on a track by name (mixer or device)."""
    parameter = None
    parameter_path = parameter_name.lower()
    if hasattr(track, "mixer_device"):
        mixer = track.mixer_device
        if parameter_path == "volume":
            parameter = mixer.volume
        elif parameter_path in ("pan", "panning"):
            parameter = mixer.panning
        elif parameter_path.startswith("send"):
            send_char = (
                parameter_path.split()[-1]
                if len(parameter_path.split()) > 1
                else parameter_path[-1]
            )
            send_index = ord(send_char.upper()) - ord("A")
            if 0 <= send_index < len(mixer.sends):
                parameter = mixer.sends[send_index]
    if parameter is None and hasattr(track, "devices"):
        if "device" in parameter_path:
            parts = parameter_path.split()
            try:
                device_index = int(parts[1])
                param_index = int(parts[3])
                if 0 <= device_index < len(track.devices):
                    device = track.devices[device_index]
                    if hasattr(device, "parameters") and param_index < len(
                        device.parameters
                    ):
                        parameter = device.parameters[param_index]
            except (IndexError, ValueError):
                pass
    return parameter


def create_automation(song, track_index, parameter_name, automation_points, ctrl=None):
    """Create automation for a track parameter via clip envelopes.

    Works on session clips. For arrangement automation, write to session
    clips first then record to arrangement.

    Params:
        track_index: int
        parameter_name: str (Volume, Pan, Send A, device N param M)
        automation_points: list of {time, value, clip_index?}
            If clip_index is provided per point, writes to that clip slot.
            Otherwise uses clip_index param or defaults to 0.
        clip_index: int (default 0) - session clip slot to write to
        mode: 'clip' (default) or 'arrangement'
            clip: writes envelope on session clip
            arrangement: attempts arrangement clip (may not work in all cases)
    """
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        parameter = _find_parameter(track, parameter_name)
        if parameter is None:
            raise ValueError(
                "Parameter '{0}' not found on track {1}".format(
                    parameter_name, track_index
                )
            )

        # Group points by clip_index
        clip_index = 0  # default
        # Check if automation_points is passed with per-point clip_index
        # or if there's a top-level clip_index in the points
        grouped = {}
        for pt in automation_points:
            ci = pt.get("clip_index", clip_index)
            if ci not in grouped:
                grouped[ci] = []
            grouped[ci].append(pt)

        total_points = 0
        clips_written = []
        debug = []

        for ci, points in grouped.items():
            if ci < 0 or ci >= len(track.clip_slots):
                debug.append("slot {0} out of range".format(ci))
                continue
            slot = track.clip_slots[ci]
            if not slot.has_clip:
                debug.append("slot {0}: no clip".format(ci))
                continue
            clip = slot.clip
            debug.append("slot {0}: clip '{1}', is_audio={2}".format(
                ci, clip.name, clip.is_audio_clip))

            # Get or create envelope
            envelope = None
            try:
                envelope = clip.automation_envelope(parameter)
            except Exception:
                pass

            if envelope is None:
                try:
                    envelope = clip.create_automation_envelope(parameter)
                except Exception as e:
                    debug.append("slot {0}: create_envelope failed: {1}".format(ci, e))

            if envelope is None:
                debug.append("  FAILED: no envelope")
                continue

            # Write points - time is relative to clip start (0 = clip start)
            for pt in points:
                time_val = float(pt["time"])
                value = max(0.0, min(1.0, float(pt["value"])))
                try:
                    envelope.insert_step(time_val, 0.0, value)
                    total_points += 1
                except Exception as e:
                    debug.append("  insert_step error: {0}".format(e))

            clips_written.append(ci)

        if ctrl:
            for d in debug:
                ctrl.log_message("automation: " + d)

        return {
            "parameter": parameter_name,
            "track_index": track_index,
            "points_added": total_points,
            "clips_written": clips_written,
            "debug": debug,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error creating automation: " + str(e))
            ctrl.log_message(traceback.format_exc())
        raise


def clear_automation(
    song, track_index, parameter_name, start_time, end_time, ctrl=None
):
    """Clear automation for a parameter in a time range."""
    try:
        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")
        track = song.tracks[track_index]
        parameter = _find_parameter(track, parameter_name)
        if parameter is None:
            raise ValueError(
                "Parameter '{0}' not found on track {1}".format(
                    parameter_name, track_index
                )
            )
        if not hasattr(parameter, "automation_envelope"):
            raise Exception("Parameter does not support automation")
        automation_envelope = parameter.automation_envelope
        current_value = parameter.value
        automation_envelope.insert_step(
            start_time, end_time - start_time, current_value
        )
        return {
            "parameter": parameter_name,
            "track_index": track_index,
            "cleared_from": start_time,
            "cleared_to": end_time,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error clearing automation: " + str(e))
        raise


def delete_time(song, start_time, end_time, ctrl=None):
    """Delete a section of time from the arrangement."""
    try:
        if start_time >= end_time:
            raise ValueError("Start time must be less than end time")
        song.delete_time(start_time, end_time - start_time)
        return {
            "deleted_from": start_time,
            "deleted_to": end_time,
            "deleted_length": end_time - start_time,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error deleting time: " + str(e))
        raise


def duplicate_time(song, start_time, end_time, ctrl=None):
    """Duplicate a section of time in the arrangement."""
    try:
        if start_time >= end_time:
            raise ValueError("Start time must be less than end time")
        song.duplicate_time(start_time, end_time - start_time)
        return {
            "duplicated_from": start_time,
            "duplicated_to": end_time,
            "duplicated_length": end_time - start_time,
            "pasted_at": end_time,
        }
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error duplicating time: " + str(e))
        raise


def insert_silence(song, position, length, ctrl=None):
    """Insert silence at a position in the arrangement."""
    try:
        if length <= 0:
            raise ValueError("Length must be greater than 0")
        song.insert_time(position, length)
        return {"inserted_at": position, "inserted_length": length}
    except Exception as e:
        if ctrl:
            ctrl.log_message("Error inserting silence: " + str(e))
        raise
