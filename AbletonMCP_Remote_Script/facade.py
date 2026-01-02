"""
Facade for Ableton Live Object Model (LOM) interactions.

This module provides a clean, typed interface to Ableton Live's Python API.
It separates LOM operations from command/socket handling, making the code:
- Easier to test (mock the facade, not individual LOM objects)
- Easier to understand (domain-focused method names)
- Easier to maintain (validation logic in one place)

Usage:
    facade = LiveSessionFacade(song, application)

    # Session info
    info = facade.get_session_info()

    # Track operations
    track = facade.get_track(0)
    new_track = facade.create_midi_track()

    # Clip operations
    clip = facade.get_clip(track_index=0, clip_index=0)
    facade.add_notes_to_clip(track_index=0, clip_index=0, notes=[...])
"""

from typing import Any, Dict, List, Optional


class LiveSessionFacade:
    """
    Clean, typed interface to Ableton Live Object Model.

    This facade encapsulates all direct LOM interactions, providing:
    - Validated access to tracks, clips, and devices
    - Domain-specific methods for common operations
    - Consistent error handling and response formatting
    """

    def __init__(self, song: Any, application: Any):
        """
        Initialize the facade with Live's core objects.

        Args:
            song: Live's Song object (self._c_instance.song())
            application: Live's Application object (self._c_instance.application())
        """
        self._song = song
        self._app = application

    @property
    def song(self) -> Any:
        """Direct access to the Song object for advanced operations."""
        return self._song

    @property
    def application(self) -> Any:
        """Direct access to the Application object for advanced operations."""
        return self._app

    @property
    def browser(self) -> Any:
        """Direct access to the Browser object."""
        return self._app.browser if self._app else None

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def get_track(self, index: int) -> Any:
        """
        Get a track by index with validation.

        Args:
            index: Track index (0-based)

        Returns:
            The track object

        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= len(self._song.tracks):
            raise IndexError("Track index out of range")
        return self._song.tracks[index]

    def get_clip_slot(self, track_index: int, clip_index: int) -> Any:
        """
        Get a clip slot by track and clip index with validation.

        Args:
            track_index: Track index (0-based)
            clip_index: Clip slot index (0-based)

        Returns:
            The clip slot object

        Raises:
            IndexError: If track or clip index is out of range
        """
        track = self.get_track(track_index)
        if clip_index < 0 or clip_index >= len(track.clip_slots):
            raise IndexError("Clip index out of range")
        return track.clip_slots[clip_index]

    def get_clip(self, track_index: int, clip_index: int) -> Any:
        """
        Get a clip by track and clip index with validation.

        Args:
            track_index: Track index (0-based)
            clip_index: Clip slot index (0-based)

        Returns:
            The clip object

        Raises:
            IndexError: If track or clip index is out of range
            ValueError: If the clip slot is empty
        """
        clip_slot = self.get_clip_slot(track_index, clip_index)
        if not clip_slot.has_clip:
            raise ValueError("No clip in slot")
        return clip_slot.clip

    def get_scene(self, index: int) -> Any:
        """
        Get a scene by index with validation.

        Args:
            index: Scene index (0-based)

        Returns:
            The scene object

        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= len(self._song.scenes):
            raise IndexError("Scene index out of range")
        return self._song.scenes[index]

    def get_cue_point(self, index: int) -> Any:
        """
        Get a cue point by index with validation.

        Args:
            index: Cue point index (0-based)

        Returns:
            The cue point object

        Raises:
            IndexError: If index is out of range
        """
        cue_points = list(self._song.cue_points)
        if index < 0 or index >= len(cue_points):
            raise IndexError("Cue point index out of range")
        return cue_points[index]

    # =========================================================================
    # Session Information
    # =========================================================================

    def get_session_info(self) -> Dict[str, Any]:
        """Get information about the current session."""
        return {
            "tempo": self._song.tempo,
            "signature_numerator": self._song.signature_numerator,
            "signature_denominator": self._song.signature_denominator,
            "track_count": len(self._song.tracks),
            "return_track_count": len(self._song.return_tracks),
            "master_track": {
                "name": "Master",
                "volume": self._song.master_track.mixer_device.volume.value,
                "panning": self._song.master_track.mixer_device.panning.value,
            },
        }

    def get_track_info(self, track_index: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific track.

        Args:
            track_index: Track index (0-based)

        Returns:
            Dictionary with track details including clips and devices
        """
        track = self.get_track(track_index)

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
                "type": self._get_device_type(device),
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

    def get_scene_info(self, scene_index: int) -> Dict[str, Any]:
        """
        Get information about a scene.

        Args:
            scene_index: Scene index (0-based)

        Returns:
            Dictionary with scene details
        """
        scene = self.get_scene(scene_index)

        # Count clips in this scene
        clip_count = 0
        clips = []
        for track_index, track in enumerate(self._song.tracks):
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

    def _get_device_type(self, device: Any) -> str:
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

    # =========================================================================
    # Track Operations
    # =========================================================================

    def create_midi_track(self, index: int = -1) -> Dict[str, Any]:
        """
        Create a new MIDI track.

        Args:
            index: Position to insert track (-1 for end)

        Returns:
            Dictionary with new track info
        """
        self._song.create_midi_track(index)
        new_track_index = len(self._song.tracks) - 1 if index == -1 else index
        new_track = self._song.tracks[new_track_index]
        return {"index": new_track_index, "name": new_track.name}

    def create_audio_track(self, index: int = -1) -> Dict[str, Any]:
        """
        Create a new audio track.

        Args:
            index: Position to insert track (-1 for end)

        Returns:
            Dictionary with new track info
        """
        self._song.create_audio_track(index)
        new_track_index = len(self._song.tracks) - 1 if index == -1 else index
        new_track = self._song.tracks[new_track_index]
        return {"index": new_track_index, "name": new_track.name}

    def delete_track(self, track_index: int) -> Dict[str, Any]:
        """
        Delete a track.

        Args:
            track_index: Track index to delete

        Returns:
            Dictionary confirming deletion
        """
        track = self.get_track(track_index)
        track_name = track.name
        self._song.delete_track(track_index)
        return {"deleted": True, "track_name": track_name}

    def set_track_name(self, track_index: int, name: str) -> Dict[str, Any]:
        """Set the name of a track."""
        track = self.get_track(track_index)
        track.name = name
        return {"name": track.name}

    def set_track_mute(self, track_index: int, muted: bool) -> Dict[str, Any]:
        """Mute or unmute a track."""
        track = self.get_track(track_index)
        track.mute = muted
        return {"mute": track.mute, "track_name": track.name}

    def set_track_solo(self, track_index: int, solo: bool) -> Dict[str, Any]:
        """Solo or unsolo a track."""
        track = self.get_track(track_index)
        track.solo = solo
        return {"solo": track.solo, "track_name": track.name}

    def set_track_arm(self, track_index: int, armed: bool) -> Dict[str, Any]:
        """Arm or disarm a track for recording."""
        track = self.get_track(track_index)
        if track.can_be_armed:
            track.arm = armed
            return {"arm": track.arm, "track_name": track.name}
        else:
            return {
                "arm": False,
                "track_name": track.name,
                "message": "Track cannot be armed",
            }

    def set_track_volume(self, track_index: int, volume: float) -> Dict[str, Any]:
        """Set track volume (0.0 to 1.0)."""
        track = self.get_track(track_index)
        volume = max(0.0, min(1.0, volume))
        track.mixer_device.volume.value = volume
        return {"volume": track.mixer_device.volume.value, "track_name": track.name}

    def set_track_panning(self, track_index: int, pan: float) -> Dict[str, Any]:
        """Set track panning (-1.0 to 1.0)."""
        track = self.get_track(track_index)
        pan = max(-1.0, min(1.0, pan))
        track.mixer_device.panning.value = pan
        return {"panning": track.mixer_device.panning.value, "track_name": track.name}

    # =========================================================================
    # Clip Operations
    # =========================================================================

    def create_clip(
        self, track_index: int, clip_index: int, length: float = 4.0
    ) -> Dict[str, Any]:
        """
        Create a new MIDI clip in a clip slot.

        Args:
            track_index: Track index
            clip_index: Clip slot index
            length: Clip length in beats

        Returns:
            Dictionary with new clip info
        """
        clip_slot = self.get_clip_slot(track_index, clip_index)
        if clip_slot.has_clip:
            raise ValueError("Clip slot already has a clip")
        clip_slot.create_clip(length)
        return {"name": clip_slot.clip.name, "length": clip_slot.clip.length}

    def delete_clip(self, track_index: int, clip_index: int) -> Dict[str, Any]:
        """Delete a clip from a clip slot."""
        clip = self.get_clip(track_index, clip_index)
        clip_name = clip.name
        clip_slot = self.get_clip_slot(track_index, clip_index)
        clip_slot.delete_clip()
        return {"deleted": True, "clip_name": clip_name}

    def set_clip_name(
        self, track_index: int, clip_index: int, name: str
    ) -> Dict[str, Any]:
        """Set the name of a clip."""
        clip = self.get_clip(track_index, clip_index)
        clip.name = name
        return {"name": clip.name}

    def add_notes_to_clip(
        self, track_index: int, clip_index: int, notes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Add MIDI notes to a clip.

        Args:
            track_index: Track index
            clip_index: Clip slot index
            notes: List of note dicts with pitch, start_time, duration, velocity, mute

        Returns:
            Dictionary with note count
        """
        clip = self.get_clip(track_index, clip_index)

        # Convert note data to Live's format
        live_notes = []
        for note in notes:
            pitch = note.get("pitch", 60)
            start_time = note.get("start_time", 0.0)
            duration = note.get("duration", 0.25)
            velocity = note.get("velocity", 100)
            mute = note.get("mute", False)
            live_notes.append((pitch, start_time, duration, velocity, mute))

        clip.set_notes(tuple(live_notes))
        return {"note_count": len(notes)}

    def get_notes_from_clip(
        self, track_index: int, clip_index: int
    ) -> Dict[str, Any]:
        """Get all MIDI notes from a clip."""
        clip = self.get_clip(track_index, clip_index)

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

    def fire_clip(self, track_index: int, clip_index: int) -> Dict[str, Any]:
        """Start playing a clip."""
        clip_slot = self.get_clip_slot(track_index, clip_index)
        if not clip_slot.has_clip:
            raise ValueError("No clip in slot")
        clip_slot.fire()
        return {"fired": True}

    def stop_clip(self, track_index: int, clip_index: int) -> Dict[str, Any]:
        """Stop playing a clip."""
        clip_slot = self.get_clip_slot(track_index, clip_index)
        clip_slot.stop()
        return {"stopped": True}

    def duplicate_clip_to_arrangement(
        self, track_index: int, clip_index: int, time: float
    ) -> Dict[str, Any]:
        """Duplicate a session clip to the arrangement at a specific time."""
        track = self.get_track(track_index)
        clip = self.get_clip(track_index, clip_index)
        clip_name = clip.name
        clip_length = clip.length

        track.duplicate_clip_to_arrangement(clip_index, float(time))

        return {
            "duplicated": True,
            "clip_name": clip_name,
            "destination_time": time,
            "clip_length": clip_length,
            "track_name": track.name,
        }

    # =========================================================================
    # Transport Operations
    # =========================================================================

    def start_playback(self) -> Dict[str, Any]:
        """Start playing the session."""
        self._song.start_playing()
        return {"playing": self._song.is_playing}

    def stop_playback(self) -> Dict[str, Any]:
        """Stop playing the session."""
        self._song.stop_playing()
        return {"playing": self._song.is_playing}

    def continue_playing(self) -> Dict[str, Any]:
        """Continue playing from current position."""
        self._song.continue_playing()
        return {
            "is_playing": self._song.is_playing,
            "current_song_time": self._song.current_song_time,
        }

    def set_tempo(self, tempo: float) -> Dict[str, Any]:
        """Set the tempo of the session."""
        self._song.tempo = tempo
        return {"tempo": self._song.tempo}

    def set_metronome(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable the metronome."""
        self._song.metronome = enabled
        return {"metronome": self._song.metronome}

    def fire_scene(self, scene_index: int) -> Dict[str, Any]:
        """Fire a scene (trigger all clips in a row)."""
        scene = self.get_scene(scene_index)
        scene.fire()
        return {
            "fired": True,
            "scene_name": scene.name,
            "scene_index": scene_index,
        }

    def undo(self) -> Dict[str, Any]:
        """Undo the last action."""
        if self._song.can_undo:
            self._song.undo()
            return {"undone": True}
        else:
            return {"undone": False, "message": "Nothing to undo"}

    def redo(self) -> Dict[str, Any]:
        """Redo the last undone action."""
        if self._song.can_redo:
            self._song.redo()
            return {"redone": True}
        else:
            return {"redone": False, "message": "Nothing to redo"}

    def set_record_mode(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable global record mode."""
        self._song.record_mode = bool(enabled)
        return {"record_mode": self._song.record_mode}

    def set_arrangement_overdub(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable arrangement overdub."""
        self._song.arrangement_overdub = bool(enabled)
        return {"arrangement_overdub": self._song.arrangement_overdub}

    # =========================================================================
    # Arrangement Operations
    # =========================================================================

    def get_arrangement_info(self) -> Dict[str, Any]:
        """Get arrangement view information."""
        return {
            "current_song_time": self._song.current_song_time,
            "loop_start": self._song.loop_start,
            "loop_length": self._song.loop_length,
            "loop_enabled": self._song.loop,
            "is_playing": self._song.is_playing,
            "record_mode": self._song.record_mode,
            "arrangement_overdub": self._song.arrangement_overdub,
            "signature_numerator": self._song.signature_numerator,
            "signature_denominator": self._song.signature_denominator,
        }

    def get_cue_points(self) -> Dict[str, Any]:
        """Get all cue points in the arrangement."""
        cue_points = []
        for i, cue_point in enumerate(self._song.cue_points):
            cue_points.append({
                "index": i,
                "name": cue_point.name,
                "time": cue_point.time,
            })
        return {"cue_points": cue_points, "count": len(cue_points)}

    def set_song_time(self, time: float) -> Dict[str, Any]:
        """Set the song playhead position."""
        self._song.current_song_time = max(0.0, float(time))
        return {"current_song_time": self._song.current_song_time}

    def set_loop_region(self, start: float, length: float) -> Dict[str, Any]:
        """Set the arrangement loop region."""
        self._song.loop_start = max(0.0, float(start))
        self._song.loop_length = max(0.0, float(length))
        return {
            "loop_start": self._song.loop_start,
            "loop_length": self._song.loop_length,
        }

    def set_loop_enabled(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable the arrangement loop."""
        self._song.loop = bool(enabled)
        return {"loop_enabled": self._song.loop}

    def jump_by_bars(self, bars: int) -> Dict[str, Any]:
        """Jump playhead forward or backward by N bars."""
        beats_per_bar = self._song.signature_numerator
        jump_beats = bars * beats_per_bar
        new_time = max(0.0, self._song.current_song_time + jump_beats)
        self._song.current_song_time = new_time
        return {
            "current_song_time": self._song.current_song_time,
            "bars_jumped": bars,
        }

    def jump_to_cue_point(self, index: int) -> Dict[str, Any]:
        """Jump to a cue point by index."""
        cue_point = self.get_cue_point(index)
        cue_point.jump()
        return {"jumped_to": cue_point.name, "time": cue_point.time}

    def jump_to_next_cue_point(self) -> Dict[str, Any]:
        """Jump to the next cue point after current song time."""
        current_time = self._song.current_song_time
        cue_points = list(self._song.cue_points)

        sorted_cues = sorted(cue_points, key=lambda c: c.time)
        next_cue = None
        for cue in sorted_cues:
            if cue.time > current_time + 0.001:
                next_cue = cue
                break

        if next_cue is None:
            return {
                "jumped": False,
                "message": "No cue point after current position",
            }

        next_cue.jump()
        return {"jumped": True, "name": next_cue.name, "time": next_cue.time}

    def jump_to_prev_cue_point(self) -> Dict[str, Any]:
        """Jump to the previous cue point before current song time."""
        current_time = self._song.current_song_time
        cue_points = list(self._song.cue_points)

        sorted_cues = sorted(cue_points, key=lambda c: c.time, reverse=True)
        prev_cue = None
        for cue in sorted_cues:
            if cue.time < current_time - 0.001:
                prev_cue = cue
                break

        if prev_cue is None:
            return {
                "jumped": False,
                "message": "No cue point before current position",
            }

        prev_cue.jump()
        return {"jumped": True, "name": prev_cue.name, "time": prev_cue.time}

    def find_cue_point_at_time(self, time: float) -> Optional[Any]:
        """Find a cue point at a specific time (within tolerance)."""
        for cue_point in self._song.cue_points:
            if abs(cue_point.time - time) < 0.001:
                return cue_point
        return None

    def set_or_delete_cue(self) -> None:
        """Toggle a cue point at the current playhead position."""
        self._song.set_or_delete_cue()

    def get_arrangement_clips(
        self, track_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get clips from the arrangement view.

        Args:
            track_index: Optional track index to filter by

        Returns:
            Dictionary with tracks and their arrangement clips
        """
        result = {"tracks": [], "total_clips": 0}

        if track_index is not None:
            track = self.get_track(track_index)
            tracks_to_process = [(track_index, track)]
        else:
            tracks_to_process = list(enumerate(self._song.tracks))

        for idx, track in tracks_to_process:
            track_clips = []
            arrangement_clips_supported = hasattr(track, "arrangement_clips")

            if arrangement_clips_supported and track.arrangement_clips:
                for clip in track.arrangement_clips:
                    clip_info = {
                        "name": clip.name,
                        "length": clip.length,
                        "is_midi_clip": clip.is_midi_clip,
                        "is_audio_clip": clip.is_audio_clip,
                        "start_time": (
                            clip.start_time if hasattr(clip, "start_time") else 0.0
                        ),
                        "end_time": (
                            clip.end_time if hasattr(clip, "end_time") else 0.0
                        ),
                        "color": clip.color if hasattr(clip, "color") else None,
                    }
                    track_clips.append(clip_info)

            result["tracks"].append({
                "track_index": idx,
                "track_name": track.name,
                "clips": track_clips,
                "clip_count": len(track_clips),
            })
            result["total_clips"] += len(track_clips)

        return result
