"""
Track manipulation commands.

These commands create, modify, and delete tracks. All commands in this
module modify Live's state and must be executed on the main thread.
"""

from typing import Any, Dict

from . import CommandContext, CommandRegistry, ModifyingCommand


@CommandRegistry.register
class CreateMidiTrackCommand(ModifyingCommand):
    """Create a new MIDI track."""

    command_type = "create_midi_track"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        index = params.get("index", -1)
        return context.facade.create_midi_track(index)


@CommandRegistry.register
class CreateAudioTrackCommand(ModifyingCommand):
    """Create a new audio track."""

    command_type = "create_audio_track"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        index = params.get("index", -1)
        return context.facade.create_audio_track(index)


@CommandRegistry.register
class DeleteTrackCommand(ModifyingCommand):
    """Delete a track."""

    command_type = "delete_track"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        return context.facade.delete_track(track_index)


@CommandRegistry.register
class SetTrackNameCommand(ModifyingCommand):
    """Set the name of a track."""

    command_type = "set_track_name"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        name = params.get("name", "")
        return context.facade.set_track_name(track_index, name)


@CommandRegistry.register
class SetTrackMuteCommand(ModifyingCommand):
    """Mute or unmute a track."""

    command_type = "set_track_mute"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        muted = params.get("muted", False)
        return context.facade.set_track_mute(track_index, muted)


@CommandRegistry.register
class SetTrackSoloCommand(ModifyingCommand):
    """Solo or unsolo a track."""

    command_type = "set_track_solo"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        solo = params.get("solo", False)
        return context.facade.set_track_solo(track_index, solo)


@CommandRegistry.register
class SetTrackArmCommand(ModifyingCommand):
    """Arm or disarm a track for recording."""

    command_type = "set_track_arm"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        armed = params.get("armed", False)
        return context.facade.set_track_arm(track_index, armed)


@CommandRegistry.register
class SetTrackVolumeCommand(ModifyingCommand):
    """Set track volume (0.0 to 1.0)."""

    command_type = "set_track_volume"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        volume = params.get("volume", 0.85)
        return context.facade.set_track_volume(track_index, volume)


@CommandRegistry.register
class SetTrackPanningCommand(ModifyingCommand):
    """Set track panning (-1.0 to 1.0)."""

    command_type = "set_track_panning"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        track_index = params.get("track_index", 0)
        pan = params.get("pan", 0.0)
        return context.facade.set_track_panning(track_index, pan)
