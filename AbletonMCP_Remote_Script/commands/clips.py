"""
Clip manipulation commands.

These commands create, modify, and delete clips. All commands in this
module modify Live's state and must be executed on the main thread.
"""

from typing import Any, Dict, List

from . import CommandContext, CommandRegistry, ModifyingCommand


@CommandRegistry.register
class CreateClipCommand(ModifyingCommand):
    """Create a new MIDI clip in a clip slot."""

    command_type = "create_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        length = params.get("length", 4.0)
        return context.facade.create_clip(track_index, clip_index, length)


@CommandRegistry.register
class DeleteClipCommand(ModifyingCommand):
    """Delete a clip from a clip slot."""

    command_type = "delete_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return context.facade.delete_clip(track_index, clip_index)


@CommandRegistry.register
class SetClipNameCommand(ModifyingCommand):
    """Set the name of a clip."""

    command_type = "set_clip_name"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        name = params.get("name", "")
        return context.facade.set_clip_name(track_index, clip_index, name)


@CommandRegistry.register
class AddNotesToClipCommand(ModifyingCommand):
    """Add MIDI notes to a clip."""

    command_type = "add_notes_to_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        notes: List[Dict[str, Any]] = params.get("notes", [])
        return context.facade.add_notes_to_clip(track_index, clip_index, notes)


@CommandRegistry.register
class FireClipCommand(ModifyingCommand):
    """Start playing a clip."""

    command_type = "fire_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return context.facade.fire_clip(track_index, clip_index)


@CommandRegistry.register
class StopClipCommand(ModifyingCommand):
    """Stop playing a clip."""

    command_type = "stop_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        return context.facade.stop_clip(track_index, clip_index)


@CommandRegistry.register
class DuplicateClipToArrangementCommand(ModifyingCommand):
    """Duplicate a session clip to the arrangement at a specific time."""

    command_type = "duplicate_clip_to_arrangement"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        time = params.get("time", 0.0)
        return context.facade.duplicate_clip_to_arrangement(track_index, clip_index, time)
