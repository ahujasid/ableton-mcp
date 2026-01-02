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
        song = context.song
        index = params.get("index", -1)

        song.create_midi_track(index)

        new_track_index = len(song.tracks) - 1 if index == -1 else index
        new_track = song.tracks[new_track_index]

        return {
            "index": new_track_index,
            "name": new_track.name,
        }


@CommandRegistry.register
class CreateAudioTrackCommand(ModifyingCommand):
    """Create a new audio track."""

    command_type = "create_audio_track"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        index = params.get("index", -1)

        song.create_audio_track(index)

        new_track_index = len(song.tracks) - 1 if index == -1 else index
        new_track = song.tracks[new_track_index]

        return {
            "index": new_track_index,
            "name": new_track.name,
        }


@CommandRegistry.register
class DeleteTrackCommand(ModifyingCommand):
    """Delete a track."""

    command_type = "delete_track"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track_name = song.tracks[track_index].name
        song.delete_track(track_index)

        return {
            "deleted": True,
            "track_name": track_name,
        }


@CommandRegistry.register
class SetTrackNameCommand(ModifyingCommand):
    """Set the name of a track."""

    command_type = "set_track_name"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        name = params.get("name", "")

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]
        track.name = name

        return {"name": track.name}


@CommandRegistry.register
class SetTrackMuteCommand(ModifyingCommand):
    """Mute or unmute a track."""

    command_type = "set_track_mute"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        muted = params.get("muted", False)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]
        track.mute = muted

        return {
            "mute": track.mute,
            "track_name": track.name,
        }


@CommandRegistry.register
class SetTrackSoloCommand(ModifyingCommand):
    """Solo or unsolo a track."""

    command_type = "set_track_solo"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        solo = params.get("solo", False)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]
        track.solo = solo

        return {
            "solo": track.solo,
            "track_name": track.name,
        }


@CommandRegistry.register
class SetTrackArmCommand(ModifyingCommand):
    """Arm or disarm a track for recording."""

    command_type = "set_track_arm"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        armed = params.get("armed", False)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        if track.can_be_armed:
            track.arm = armed
            return {
                "arm": track.arm,
                "track_name": track.name,
            }
        else:
            return {
                "arm": False,
                "track_name": track.name,
                "message": "Track cannot be armed",
            }


@CommandRegistry.register
class SetTrackVolumeCommand(ModifyingCommand):
    """Set track volume (0.0 to 1.0)."""

    command_type = "set_track_volume"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        volume = params.get("volume", 0.85)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        # Clamp volume to valid range
        volume = max(0.0, min(1.0, volume))
        track.mixer_device.volume.value = volume

        return {
            "volume": track.mixer_device.volume.value,
            "track_name": track.name,
        }


@CommandRegistry.register
class SetTrackPanningCommand(ModifyingCommand):
    """Set track panning (-1.0 to 1.0)."""

    command_type = "set_track_panning"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        pan = params.get("pan", 0.0)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        # Clamp pan to valid range
        pan = max(-1.0, min(1.0, pan))
        track.mixer_device.panning.value = pan

        return {
            "panning": track.mixer_device.panning.value,
            "track_name": track.name,
        }
