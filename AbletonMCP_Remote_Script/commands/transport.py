"""
Transport and playback control commands.

These commands control playback, tempo, metronome, and scene firing.
All commands in this module modify Live's state and must be executed
on the main thread.
"""

from typing import Any, Dict

from . import CommandContext, CommandRegistry, ModifyingCommand


@CommandRegistry.register
class StartPlaybackCommand(ModifyingCommand):
    """Start playing the session."""

    command_type = "start_playback"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.start_playback()


@CommandRegistry.register
class StopPlaybackCommand(ModifyingCommand):
    """Stop playing the session."""

    command_type = "stop_playback"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.stop_playback()


@CommandRegistry.register
class ContinuePlayingCommand(ModifyingCommand):
    """Continue playing from current position."""

    command_type = "continue_playing"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.continue_playing()


@CommandRegistry.register
class SetTempoCommand(ModifyingCommand):
    """Set the tempo of the session."""

    command_type = "set_tempo"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        tempo = params.get("tempo", 120.0)
        return context.facade.set_tempo(tempo)


@CommandRegistry.register
class SetMetronomeCommand(ModifyingCommand):
    """Enable or disable the metronome."""

    command_type = "set_metronome"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        enabled = params.get("enabled", True)
        return context.facade.set_metronome(enabled)


@CommandRegistry.register
class FireSceneCommand(ModifyingCommand):
    """Fire a scene (trigger all clips in a row)."""

    command_type = "fire_scene"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        scene_index = params.get("scene_index", 0)
        return context.facade.fire_scene(scene_index)


@CommandRegistry.register
class UndoCommand(ModifyingCommand):
    """Undo the last action."""

    command_type = "undo"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.undo()


@CommandRegistry.register
class RedoCommand(ModifyingCommand):
    """Redo the last undone action."""

    command_type = "redo"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        return context.facade.redo()


@CommandRegistry.register
class SetRecordModeCommand(ModifyingCommand):
    """Enable or disable global record mode."""

    command_type = "set_record_mode"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        enabled = params.get("enabled", False)
        return context.facade.set_record_mode(enabled)


@CommandRegistry.register
class SetArrangementOverdubCommand(ModifyingCommand):
    """Enable or disable arrangement overdub."""

    command_type = "set_arrangement_overdub"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        enabled = params.get("enabled", False)
        return context.facade.set_arrangement_overdub(enabled)
