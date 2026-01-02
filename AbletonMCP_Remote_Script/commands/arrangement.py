"""
Arrangement view commands.

These commands handle arrangement view operations including:
- Song time / playhead position
- Loop settings
- Cue points (markers)
- Arrangement clips

Cue point operations use a two-step scheduling pattern because Ableton's
set_or_delete_cue() API toggles at the current playhead position. We must:
1. Set the playhead position
2. Wait one frame for Ableton to process
3. Toggle the cue point
"""

from typing import Any, Dict

from . import Command, CommandContext, CommandRegistry, ModifyingCommand


@CommandRegistry.register
class GetArrangementInfoCommand(Command):
    """Get arrangement view information."""

    command_type = "get_arrangement_info"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song

        return {
            "current_song_time": song.current_song_time,
            "loop_start": song.loop_start,
            "loop_length": song.loop_length,
            "loop_enabled": song.loop,
            "is_playing": song.is_playing,
            "record_mode": song.record_mode,
            "arrangement_overdub": song.arrangement_overdub,
            "signature_numerator": song.signature_numerator,
            "signature_denominator": song.signature_denominator,
        }


@CommandRegistry.register
class GetCuePointsCommand(Command):
    """Get all cue points in the arrangement."""

    command_type = "get_cue_points"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        cue_points = []

        for i, cue_point in enumerate(song.cue_points):
            cue_points.append({
                "index": i,
                "name": cue_point.name,
                "time": cue_point.time,
            })

        return {
            "cue_points": cue_points,
            "count": len(cue_points),
        }


@CommandRegistry.register
class GetArrangementClipsCommand(Command):
    """Get clips from the arrangement view."""

    command_type = "get_arrangement_clips"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index")

        result = {
            "tracks": [],
            "total_clips": 0,
        }

        # Determine which tracks to process
        if track_index is not None:
            if track_index < 0 or track_index >= len(song.tracks):
                raise IndexError("Track index out of range")
            tracks_to_process = [(track_index, song.tracks[track_index])]
        else:
            tracks_to_process = list(enumerate(song.tracks))

        for idx, track in tracks_to_process:
            track_clips = []
            arrangement_clips_supported = hasattr(track, "arrangement_clips")

            if not arrangement_clips_supported:
                context.log(
                    f"Warning: track '{track.name}' does not support arrangement_clips API"
                )
            elif track.arrangement_clips:
                for clip in track.arrangement_clips:
                    clip_info = {
                        "name": clip.name,
                        "length": clip.length,
                        "is_midi_clip": clip.is_midi_clip,
                        "is_audio_clip": clip.is_audio_clip,
                    }

                    # Handle optional attributes
                    clip_info["start_time"] = (
                        clip.start_time if hasattr(clip, "start_time") else 0.0
                    )
                    clip_info["end_time"] = (
                        clip.end_time if hasattr(clip, "end_time") else 0.0
                    )
                    clip_info["color"] = clip.color if hasattr(clip, "color") else None

                    track_clips.append(clip_info)

            result["tracks"].append({
                "track_index": idx,
                "track_name": track.name,
                "clips": track_clips,
                "clip_count": len(track_clips),
            })
            result["total_clips"] += len(track_clips)

        return result


@CommandRegistry.register
class SetSongTimeCommand(ModifyingCommand):
    """Set the song playhead position."""

    command_type = "set_song_time"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        time = params.get("time", 0.0)

        song.current_song_time = max(0.0, float(time))

        return {"current_song_time": song.current_song_time}


@CommandRegistry.register
class SetLoopRegionCommand(ModifyingCommand):
    """Set the arrangement loop region."""

    command_type = "set_loop_region"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        start = params.get("start", 0.0)
        length = params.get("length", 4.0)

        song.loop_start = max(0.0, float(start))
        song.loop_length = max(0.0, float(length))

        return {
            "loop_start": song.loop_start,
            "loop_length": song.loop_length,
        }


@CommandRegistry.register
class SetLoopEnabledCommand(ModifyingCommand):
    """Enable or disable the arrangement loop."""

    command_type = "set_loop_enabled"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        enabled = params.get("enabled", True)

        song.loop = bool(enabled)

        return {"loop_enabled": song.loop}


@CommandRegistry.register
class JumpByBarsCommand(ModifyingCommand):
    """Jump playhead forward or backward by N bars."""

    command_type = "jump_by_bars"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        bars = params.get("bars", 1)

        beats_per_bar = song.signature_numerator
        jump_beats = bars * beats_per_bar
        new_time = max(0.0, song.current_song_time + jump_beats)
        song.current_song_time = new_time

        return {
            "current_song_time": song.current_song_time,
            "bars_jumped": bars,
        }


@CommandRegistry.register
class JumpToCuePointCommand(ModifyingCommand):
    """Jump to a cue point by index."""

    command_type = "jump_to_cue_point"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        index = params.get("index", 0)

        cue_points = list(song.cue_points)
        if index < 0 or index >= len(cue_points):
            raise IndexError("Cue point index out of range")

        cue_point = cue_points[index]
        cue_point.jump()

        return {
            "jumped_to": cue_point.name,
            "time": cue_point.time,
        }


@CommandRegistry.register
class JumpToNextCuePointCommand(ModifyingCommand):
    """Jump to the next cue point after current song time."""

    command_type = "jump_to_next_cue_point"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        current_time = song.current_song_time
        cue_points = list(song.cue_points)

        # Sort by time and find the first one after current time
        sorted_cues = sorted(cue_points, key=lambda c: c.time)
        next_cue = None
        for cue in sorted_cues:
            if cue.time > current_time + 0.001:  # Small tolerance
                next_cue = cue
                break

        if next_cue is None:
            return {
                "jumped": False,
                "message": "No cue point after current position",
            }

        next_cue.jump()
        return {
            "jumped": True,
            "name": next_cue.name,
            "time": next_cue.time,
        }


@CommandRegistry.register
class JumpToPrevCuePointCommand(ModifyingCommand):
    """Jump to the previous cue point before current song time."""

    command_type = "jump_to_prev_cue_point"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        current_time = song.current_song_time
        cue_points = list(song.cue_points)

        # Sort by time descending and find the first one before current time
        sorted_cues = sorted(cue_points, key=lambda c: c.time, reverse=True)
        prev_cue = None
        for cue in sorted_cues:
            if cue.time < current_time - 0.001:  # Small tolerance
                prev_cue = cue
                break

        if prev_cue is None:
            return {
                "jumped": False,
                "message": "No cue point before current position",
            }

        prev_cue.jump()
        return {
            "jumped": True,
            "name": prev_cue.name,
            "time": prev_cue.time,
        }


@CommandRegistry.register
class CreateCuePointCommand(ModifyingCommand):
    """
    Create a cue point at a specific time.

    Note: The Ableton API's set_or_delete_cue() toggles cue points - if one
    already exists at the target time, it would be deleted. This command
    checks for existing cue points first to prevent accidental deletion.

    This command schedules a two-step operation:
    1. Move playhead to target time
    2. Toggle cue point at playhead position
    """

    command_type = "create_cue_point"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        target_time = max(0.0, float(params.get("time", 0.0)))
        name = params.get("name", "")

        # Pre-check: Look for existing cue point at target time
        existing_cue_point = None
        for cue_point in song.cue_points:
            if abs(cue_point.time - target_time) < 0.001:
                existing_cue_point = cue_point
                break

        if existing_cue_point:
            # Cue point already exists at this time - update name if provided
            if name:
                existing_cue_point.name = name
            return {
                "created": False,
                "updated": True,
                "time": target_time,
                "name": existing_cue_point.name,
                "message": (
                    "Cue point already exists at this time; updated name"
                    if name
                    else "Cue point already exists at this time"
                ),
            }

        # Schedule the cue point creation using two-step process
        # Store pending operation for the callback
        context._pending_cue_create = {"time": target_time, "name": name}

        def step1_set_position():
            """Step 1: Set position on Ableton's main thread."""
            try:
                song.current_song_time = target_time
                context.log(f"CUE CREATE STEP1: Position set to {target_time}")
                # Schedule toggle for next frame
                context.schedule_message(1, step2_toggle)
            except Exception as e:
                context.log(f"CUE CREATE STEP1 ERROR: {e}")

        def step2_toggle():
            """Step 2: Toggle cue point after position has been set."""
            try:
                song.set_or_delete_cue()
                context.log("CUE CREATE STEP2: Toggled")

                # Set name if provided
                if name:
                    for cp in song.cue_points:
                        if abs(cp.time - target_time) < 0.001:
                            cp.name = name
                            context.log(f"CUE CREATE STEP2: Named '{name}'")
                            break
            except Exception as e:
                context.log(f"CUE CREATE STEP2 ERROR: {e}")

        # Schedule step 1
        context.schedule_message(0, step1_set_position)
        context.log(f"CUE CREATE: Scheduled for time {target_time}")

        return {
            "created": True,
            "time": target_time,
            "name": name if name else "",
            "message": "Cue point creation scheduled",
        }


@CommandRegistry.register
class ToggleCueAtPlayheadCommand(ModifyingCommand):
    """
    Toggle a cue point at the current playhead position.

    This is a simple wrapper that just calls set_or_delete_cue().
    The MCP server should move the playhead first before calling this.
    """

    command_type = "toggle_cue_at_playhead"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        current_time = song.current_song_time
        context.log(f"TOGGLE CUE: At playhead position {current_time}")

        # Check if cue point exists at current position
        existing = None
        for cp in song.cue_points:
            if abs(cp.time - current_time) < 0.001:
                existing = cp
                break

        # Toggle
        song.set_or_delete_cue()

        if existing:
            return {
                "toggled": True,
                "action": "deleted",
                "time": current_time,
                "message": "Deleted cue point at current position",
            }
        else:
            return {
                "toggled": True,
                "action": "created",
                "time": current_time,
                "message": "Created cue point at current position",
            }


@CommandRegistry.register
class SetCuePointNameCommand(ModifyingCommand):
    """Set the name of a cue point at a specific time."""

    command_type = "set_cue_point_name"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        target_time = float(params.get("time", 0.0))
        name = params.get("name", "")

        for cp in song.cue_points:
            if abs(cp.time - target_time) < 0.001:
                cp.name = name
                return {
                    "success": True,
                    "time": target_time,
                    "name": name,
                    "message": "Cue point renamed",
                }

        return {
            "success": False,
            "time": target_time,
            "message": "No cue point found at this time",
        }


@CommandRegistry.register
class DeleteCuePointCommand(ModifyingCommand):
    """Delete a cue point by index."""

    command_type = "delete_cue_point"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        index = params.get("index", 0)

        cue_points = list(song.cue_points)
        if index < 0 or index >= len(cue_points):
            raise IndexError("Cue point index out of range")

        cue_point = cue_points[index]
        cue_name = cue_point.name
        cue_time = cue_point.time

        def step1_set_position():
            """Step 1: Set position on Ableton's main thread."""
            try:
                song.current_song_time = cue_time
                context.log(f"CUE DELETE STEP1: Position set to {cue_time}")
                # Schedule toggle for next frame
                context.schedule_message(1, step2_toggle)
            except Exception as e:
                context.log(f"CUE DELETE STEP1 ERROR: {e}")

        def step2_toggle():
            """Step 2: Toggle cue point (should delete)."""
            try:
                song.set_or_delete_cue()
                context.log("CUE DELETE STEP2: Toggled")
            except Exception as e:
                context.log(f"CUE DELETE STEP2 ERROR: {e}")

        # Schedule step 1
        context.schedule_message(0, step1_set_position)
        context.log(f"CUE DELETE: Scheduled for time {cue_time}")

        return {
            "deleted": True,
            "name": cue_name,
            "time": cue_time,
            "message": "Cue point deletion scheduled",
        }
