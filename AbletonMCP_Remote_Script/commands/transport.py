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
        song = context.song
        song.start_playing()

        return {"playing": song.is_playing}


@CommandRegistry.register
class StopPlaybackCommand(ModifyingCommand):
    """Stop playing the session."""

    command_type = "stop_playback"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        song.stop_playing()

        return {"playing": song.is_playing}


@CommandRegistry.register
class ContinuePlayingCommand(ModifyingCommand):
    """Continue playing from current position."""

    command_type = "continue_playing"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        song.continue_playing()

        return {
            "is_playing": song.is_playing,
            "current_song_time": song.current_song_time,
        }


@CommandRegistry.register
class SetTempoCommand(ModifyingCommand):
    """Set the tempo of the session."""

    command_type = "set_tempo"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        tempo = params.get("tempo", 120.0)

        song.tempo = tempo

        return {"tempo": song.tempo}


@CommandRegistry.register
class SetMetronomeCommand(ModifyingCommand):
    """Enable or disable the metronome."""

    command_type = "set_metronome"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        enabled = params.get("enabled", True)

        song.metronome = enabled

        return {"metronome": song.metronome}


@CommandRegistry.register
class FireSceneCommand(ModifyingCommand):
    """Fire a scene (trigger all clips in a row)."""

    command_type = "fire_scene"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        scene_index = params.get("scene_index", 0)

        if scene_index < 0 or scene_index >= len(song.scenes):
            raise IndexError("Scene index out of range")

        scene = song.scenes[scene_index]
        scene.fire()

        return {
            "fired": True,
            "scene_name": scene.name,
            "scene_index": scene_index,
        }


@CommandRegistry.register
class UndoCommand(ModifyingCommand):
    """Undo the last action."""

    command_type = "undo"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song

        if song.can_undo:
            song.undo()
            return {"undone": True}
        else:
            return {"undone": False, "message": "Nothing to undo"}


@CommandRegistry.register
class RedoCommand(ModifyingCommand):
    """Redo the last undone action."""

    command_type = "redo"

    def execute(self, context: CommandContext, _params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song

        if song.can_redo:
            song.redo()
            return {"redone": True}
        else:
            return {"redone": False, "message": "Nothing to redo"}


@CommandRegistry.register
class SetRecordModeCommand(ModifyingCommand):
    """Enable or disable global record mode."""

    command_type = "set_record_mode"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        enabled = params.get("enabled", False)

        song.record_mode = bool(enabled)

        return {"record_mode": song.record_mode}


@CommandRegistry.register
class SetArrangementOverdubCommand(ModifyingCommand):
    """Enable or disable arrangement overdub."""

    command_type = "set_arrangement_overdub"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        enabled = params.get("enabled", False)

        song.arrangement_overdub = bool(enabled)

        return {"arrangement_overdub": song.arrangement_overdub}
