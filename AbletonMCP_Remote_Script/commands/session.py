"""
Session and track information commands.

These commands query information about the Live session, tracks, clips,
and scenes without modifying any state.
"""

from typing import Any, Dict

from . import Command, CommandContext, CommandRegistry


@CommandRegistry.register
class PingCommand(Command):
    """Simple ping command to test connectivity."""

    command_type = "ping"

    def execute(self, _context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok"}


@CommandRegistry.register
class GetSessionInfoCommand(Command):
    """Get information about the current session."""

    command_type = "get_session_info"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.get_session_info()


@CommandRegistry.register
class GetTrackInfoCommand(Command):
    """Get detailed information about a specific track."""

    command_type = "get_track_info"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        return context.facade.get_track_info(track_index)


@CommandRegistry.register
class GetNotesFromClipCommand(Command):
    """Get all MIDI notes from a clip."""

    command_type = "get_notes_from_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return context.facade.get_notes_from_clip(track_index, clip_index)


@CommandRegistry.register
class GetSceneInfoCommand(Command):
    """Get information about a scene."""

    command_type = "get_scene_info"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        scene_index = params.get("scene_index", 0)
        return context.facade.get_scene_info(scene_index)
