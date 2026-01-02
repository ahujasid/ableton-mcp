"""
Session and track information commands.

These commands query information about the Live session, tracks, clips,
and scenes without modifying any state.
"""

from typing import Any, Dict

from . import Command, CommandContext, CommandRegistry


def _get_device_type(device: Any) -> str:
    """Get the type of a device."""
    try:
        if device.can_have_drum_pads:
            return "drum_machine"
        elif device.can_have_chains:
            return "rack"
        elif "instrument" in device.class_display_name.lower():
            return "instrument"
        elif "audio_effect" in device.class_name.lower():
            return "audio_effect"
        elif "midi_effect" in device.class_name.lower():
            return "midi_effect"
        else:
            return "unknown"
    except Exception:
        return "unknown"


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
        song = context.song
        return {
            "tempo": song.tempo,
            "signature_numerator": song.signature_numerator,
            "signature_denominator": song.signature_denominator,
            "track_count": len(song.tracks),
            "return_track_count": len(song.return_tracks),
            "master_track": {
                "name": "Master",
                "volume": song.master_track.mixer_device.volume.value,
                "panning": song.master_track.mixer_device.panning.value,
            },
        }


@CommandRegistry.register
class GetTrackInfoCommand(Command):
    """Get detailed information about a specific track."""

    command_type = "get_track_info"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        # Get clip slots
        clip_slots = []
        for slot_index, slot in enumerate(track.clip_slots):
            clip_info = None
            if slot.has_clip:
                clip = slot.clip
                clip_info = {
                    "name": clip.name,
                    "length": clip.length,
                    "is_playing": clip.is_playing,
                    "is_recording": clip.is_recording,
                }

            clip_slots.append({
                "index": slot_index,
                "has_clip": slot.has_clip,
                "clip": clip_info,
            })

        # Get devices
        devices = []
        for device_index, device in enumerate(track.devices):
            devices.append({
                "index": device_index,
                "name": device.name,
                "class_name": device.class_name,
                "type": _get_device_type(device),
            })

        return {
            "index": track_index,
            "name": track.name,
            "is_audio_track": track.has_audio_input,
            "is_midi_track": track.has_midi_input,
            "mute": track.mute,
            "solo": track.solo,
            "arm": track.arm,
            "volume": track.mixer_device.volume.value,
            "panning": track.mixer_device.panning.value,
            "clip_slots": clip_slots,
            "devices": devices,
        }


@CommandRegistry.register
class GetNotesFromClipCommand(Command):
    """Get all MIDI notes from a clip."""

    command_type = "get_notes_from_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")

        clip_slot = track.clip_slots[clip_index]

        if not clip_slot.has_clip:
            raise ValueError("No clip in slot")

        clip = clip_slot.clip

        # Get notes from the entire clip
        # get_notes(start_time, start_pitch, time_span, pitch_span)
        notes_tuple = clip.get_notes(0.0, 0, clip.length, 128)

        notes = []
        for note in notes_tuple:
            notes.append({
                "pitch": note[0],
                "start_time": note[1],
                "duration": note[2],
                "velocity": note[3],
                "mute": note[4],
            })

        return {
            "clip_name": clip.name,
            "clip_length": clip.length,
            "note_count": len(notes),
            "notes": notes,
        }


@CommandRegistry.register
class GetSceneInfoCommand(Command):
    """Get information about a scene."""

    command_type = "get_scene_info"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        scene_index = params.get("scene_index", 0)

        if scene_index < 0 or scene_index >= len(song.scenes):
            raise IndexError("Scene index out of range")

        scene = song.scenes[scene_index]

        # Count clips in this scene
        clip_count = 0
        clips = []
        for track_index, track in enumerate(song.tracks):
            if scene_index < len(track.clip_slots):
                slot = track.clip_slots[scene_index]
                if slot.has_clip:
                    clip_count += 1
                    clips.append({
                        "track_index": track_index,
                        "track_name": track.name,
                        "clip_name": slot.clip.name,
                    })

        return {
            "index": scene_index,
            "name": scene.name,
            "tempo": scene.tempo if hasattr(scene, "tempo") else None,
            "color": scene.color if hasattr(scene, "color") else None,
            "clip_count": clip_count,
            "clips": clips,
        }
