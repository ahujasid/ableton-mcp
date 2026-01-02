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
        return context.facade.get_arrangement_info()


@CommandRegistry.register
class GetCuePointsCommand(Command):
    """Get all cue points in the arrangement."""

    command_type = "get_cue_points"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.get_cue_points()


@CommandRegistry.register
class GetArrangementClipsCommand(Command):
    """Get clips from the arrangement view."""

    command_type = "get_arrangement_clips"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index")
        return context.facade.get_arrangement_clips(track_index)


@CommandRegistry.register
class SetSongTimeCommand(ModifyingCommand):
    """Set the song playhead position."""

    command_type = "set_song_time"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        time = params.get("time", 0.0)
        return context.facade.set_song_time(time)


@CommandRegistry.register
class SetLoopRegionCommand(ModifyingCommand):
    """Set the arrangement loop region."""

    command_type = "set_loop_region"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        start = params.get("start", 0.0)
        length = params.get("length", 4.0)
        return context.facade.set_loop_region(start, length)


@CommandRegistry.register
class SetLoopEnabledCommand(ModifyingCommand):
    """Enable or disable the arrangement loop."""

    command_type = "set_loop_enabled"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        enabled = params.get("enabled", True)
        return context.facade.set_loop_enabled(enabled)


@CommandRegistry.register
class JumpByBarsCommand(ModifyingCommand):
    """Jump playhead forward or backward by N bars."""

    command_type = "jump_by_bars"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        bars = params.get("bars", 1)
        return context.facade.jump_by_bars(bars)


@CommandRegistry.register
class JumpToCuePointCommand(ModifyingCommand):
    """Jump to a cue point by index."""

    command_type = "jump_to_cue_point"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        index = params.get("index", 0)
        return context.facade.jump_to_cue_point(index)


@CommandRegistry.register
class JumpToNextCuePointCommand(ModifyingCommand):
    """Jump to the next cue point after current song time."""

    command_type = "jump_to_next_cue_point"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.jump_to_next_cue_point()


@CommandRegistry.register
class JumpToPrevCuePointCommand(ModifyingCommand):
    """Jump to the previous cue point before current song time."""

    command_type = "jump_to_prev_cue_point"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.jump_to_prev_cue_point()


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
        facade = context.facade
        target_time = max(0.0, float(params.get("time", 0.0)))
        name = params.get("name", "")

        # Pre-check: Look for existing cue point at target time
        existing_cue_point = facade.find_cue_point_at_time(target_time)

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
        # Access song directly for scheduling callbacks
        song = facade.song

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
                    cue = facade.find_cue_point_at_time(target_time)
                    if cue:
                        cue.name = name
                        context.log(f"CUE CREATE STEP2: Named '{name}'")
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
        facade = context.facade
        current_time = facade.song.current_song_time
        context.log(f"TOGGLE CUE: At playhead position {current_time}")

        # Check if cue point exists at current position
        existing = facade.find_cue_point_at_time(current_time)

        # Toggle using facade
        facade.set_or_delete_cue()

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
        facade = context.facade
        target_time = float(params.get("time", 0.0))
        name = params.get("name", "")

        cue_point = facade.find_cue_point_at_time(target_time)
        if cue_point:
            cue_point.name = name
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
        facade = context.facade
        index = params.get("index", 0)

        # Use facade for validation
        cue_point = facade.get_cue_point(index)
        cue_name = cue_point.name
        cue_time = cue_point.time

        # Access song directly for scheduling callbacks
        song = facade.song

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
