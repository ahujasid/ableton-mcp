"""Clip tools: create, notes, name, fire, stop, delete."""

import json
import logging
from typing import Any, Callable, Dict, List, Union

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def create_clip(ctx: Context, track_index: int, clip_index: int, length: float = 4.0) -> str:
        """Create a new MIDI clip. Parameters: track_index, clip_index, length (beats, default 4.0)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("create_clip", {
                "track_index": track_index, "clip_index": clip_index, "length": length
            })
            return f"Created new clip at track {track_index}, slot {clip_index} with length {length} beats"
        except Exception as e:
            logger.error(f"Error creating clip: {str(e)}")
            return f"Error creating clip: {str(e)}"

    @mcp.tool()
    def add_notes_to_clip(
        ctx: Context,
        track_index: int,
        clip_index: int,
        notes: List[Dict[str, Union[int, float, bool]]],
    ) -> str:
        """Add MIDI notes to a clip. Parameters: track_index, clip_index, notes (list of {pitch, start_time, duration, velocity, mute})."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("add_notes_to_clip", {
                "track_index": track_index, "clip_index": clip_index, "notes": notes
            })
            return f"Added {len(notes)} notes to clip at track {track_index}, slot {clip_index}"
        except Exception as e:
            logger.error(f"Error adding notes to clip: {str(e)}")
            return f"Error adding notes to clip: {str(e)}"

    @mcp.tool()
    def set_clip_name(ctx: Context, track_index: int, clip_index: int, name: str) -> str:
        """Set the name of a clip. Parameters: track_index, clip_index, name."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_clip_name", {
                "track_index": track_index, "clip_index": clip_index, "name": name
            })
            return f"Renamed clip at track {track_index}, slot {clip_index} to '{name}'"
        except Exception as e:
            logger.error(f"Error setting clip name: {str(e)}")
            return f"Error setting clip name: {str(e)}"

    @mcp.tool()
    def fire_clip(ctx: Context, track_index: int, clip_index: int) -> str:
        """Start playing a clip. Parameters: track_index, clip_index."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("fire_clip", {"track_index": track_index, "clip_index": clip_index})
            return f"Started playing clip at track {track_index}, slot {clip_index}"
        except Exception as e:
            logger.error(f"Error firing clip: {str(e)}")
            return f"Error firing clip: {str(e)}"

    @mcp.tool()
    def stop_clip(ctx: Context, track_index: int, clip_index: int) -> str:
        """Stop playing a clip. Parameters: track_index, clip_index."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("stop_clip", {"track_index": track_index, "clip_index": clip_index})
            return f"Stopped clip at track {track_index}, slot {clip_index}"
        except Exception as e:
            logger.error(f"Error stopping clip: {str(e)}")
            return f"Error stopping clip: {str(e)}"

    @mcp.tool()
    def delete_clip(ctx: Context, track_index: int, clip_index: int) -> str:
        """Delete a clip from a clip slot. Parameters: track_index, clip_index."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("delete_clip", {"track_index": track_index, "clip_index": clip_index})
            return f"Deleted clip at track {track_index}, slot {clip_index}"
        except Exception as e:
            logger.error(f"Error deleting clip: {str(e)}")
            return f"Error deleting clip: {str(e)}"

    @mcp.tool()
    def get_clip_notes(ctx: Context, track_index: int, clip_index: int) -> str:
        """Read all MIDI notes from a clip. Parameters: track_index, clip_index."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_clip_notes", {
                "track_index": track_index, "clip_index": clip_index
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting clip notes: {str(e)}")
            return f"Error getting clip notes: {str(e)}"
