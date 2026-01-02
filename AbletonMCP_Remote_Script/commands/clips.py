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
        song = context.song
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        length = params.get("length", 4.0)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")

        clip_slot = track.clip_slots[clip_index]

        if clip_slot.has_clip:
            raise ValueError("Clip slot already has a clip")

        clip_slot.create_clip(length)

        return {
            "name": clip_slot.clip.name,
            "length": clip_slot.clip.length,
        }


@CommandRegistry.register
class DeleteClipCommand(ModifyingCommand):
    """Delete a clip from a clip slot."""

    command_type = "delete_clip"

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

        clip_name = clip_slot.clip.name
        clip_slot.delete_clip()

        return {
            "deleted": True,
            "clip_name": clip_name,
        }


@CommandRegistry.register
class SetClipNameCommand(ModifyingCommand):
    """Set the name of a clip."""

    command_type = "set_clip_name"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        name = params.get("name", "")

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")

        clip_slot = track.clip_slots[clip_index]

        if not clip_slot.has_clip:
            raise ValueError("No clip in slot")

        clip = clip_slot.clip
        clip.name = name

        return {"name": clip.name}


@CommandRegistry.register
class AddNotesToClipCommand(ModifyingCommand):
    """Add MIDI notes to a clip."""

    command_type = "add_notes_to_clip"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        notes: List[Dict[str, Any]] = params.get("notes", [])

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")

        clip_slot = track.clip_slots[clip_index]

        if not clip_slot.has_clip:
            raise ValueError("No clip in slot")

        clip = clip_slot.clip

        # Convert note data to Live's format
        live_notes = []
        for note in notes:
            pitch = note.get("pitch", 60)
            start_time = note.get("start_time", 0.0)
            duration = note.get("duration", 0.25)
            velocity = note.get("velocity", 100)
            mute = note.get("mute", False)

            live_notes.append((pitch, start_time, duration, velocity, mute))

        # Add the notes
        clip.set_notes(tuple(live_notes))

        return {"note_count": len(notes)}


@CommandRegistry.register
class FireClipCommand(ModifyingCommand):
    """Start playing a clip."""

    command_type = "fire_clip"

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

        clip_slot.fire()

        return {"fired": True}


@CommandRegistry.register
class StopClipCommand(ModifyingCommand):
    """Stop playing a clip."""

    command_type = "stop_clip"

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
        clip_slot.stop()

        return {"stopped": True}


@CommandRegistry.register
class DuplicateClipToArrangementCommand(ModifyingCommand):
    """Duplicate a session clip to the arrangement at a specific time."""

    command_type = "duplicate_clip_to_arrangement"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        track_index = params.get("track_index", 0)
        clip_index = params.get("clip_index", 0)
        time = params.get("time", 0.0)

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")

        clip_slot = track.clip_slots[clip_index]

        if not clip_slot.has_clip:
            raise ValueError("No clip in slot")

        clip_name = clip_slot.clip.name
        clip_length = clip_slot.clip.length

        # Duplicate the clip to the arrangement
        track.duplicate_clip_to_arrangement(clip_index, float(time))

        return {
            "duplicated": True,
            "clip_name": clip_name,
            "destination_time": time,
            "clip_length": clip_length,
            "track_name": track.name,
        }
