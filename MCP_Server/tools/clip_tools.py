"""Clip operation tools for AbletonMCP"""
import json
import logging
from typing import List, Dict, Union
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: FastMCP, get_connection, cache):
    """Register clip tools with the MCP server"""

    @mcp.tool()
    async def create_clip(track_index: int, clip_index: int, length: float = 4.0) -> str:
        """Create a new MIDI clip in the specified track and clip slot.

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
            length: The length of the clip in beats (default 4.0).
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("create_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
                "length": length,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error creating clip at track {track_index}, slot {clip_index}: {e}")
            return f"Error creating clip at track {track_index}, slot {clip_index}: {e}"

    @mcp.tool()
    async def add_notes_to_clip(
        track_index: int,
        clip_index: int,
        notes: List[Dict[str, Union[int, float, bool]]],
    ) -> str:
        """Add MIDI notes to a clip.

        Each note is a dictionary with the following keys:
            pitch: MIDI note number (0-127).
            start_time: Note start position in beats.
            duration: Note length in beats.
            velocity: Note velocity (0-127).
            mute: Whether the note is muted (bool).

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
            notes: A list of note dictionaries to add.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("add_notes_to_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
                "notes": notes,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error adding notes to clip at track {track_index}, slot {clip_index}: {e}")
            return f"Error adding notes to clip at track {track_index}, slot {clip_index}: {e}"

    @mcp.tool()
    async def set_clip_name(track_index: int, clip_index: int, name: str) -> str:
        """Set the name of a clip.

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
            name: The new name for the clip.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_clip_name", {
                "track_index": track_index,
                "clip_index": clip_index,
                "name": name,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting clip name at track {track_index}, slot {clip_index}: {e}")
            return f"Error setting clip name at track {track_index}, slot {clip_index}: {e}"

    @mcp.tool()
    async def delete_clip(track_index: int, clip_index: int) -> str:
        """Delete a clip from a clip slot.

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("delete_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error deleting clip at track {track_index}, slot {clip_index}: {e}")
            return f"Error deleting clip at track {track_index}, slot {clip_index}: {e}"

    @mcp.tool()
    async def duplicate_clip_to_slot(
        track_index: int,
        clip_index: int,
        target_track: int,
        target_clip: int,
    ) -> str:
        """Duplicate a clip to another slot.

        Reads notes from the source clip, creates a new clip at the target
        location, and writes the notes to it.

        Args:
            track_index: The zero-based index of the source track.
            clip_index: The zero-based index of the source clip slot.
            target_track: The zero-based index of the destination track.
            target_clip: The zero-based index of the destination clip slot.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("duplicate_clip_to_slot", {
                "track_index": track_index,
                "clip_index": clip_index,
                "target_track": target_track,
                "target_clip": target_clip,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(
                f"Error duplicating clip from track {track_index}, slot {clip_index} "
                f"to track {target_track}, slot {target_clip}: {e}"
            )
            return (
                f"Error duplicating clip from track {track_index}, slot {clip_index} "
                f"to track {target_track}, slot {target_clip}: {e}"
            )

    @mcp.tool()
    async def get_clip_notes(track_index: int, clip_index: int) -> str:
        """Get all MIDI notes from a clip.

        Returns a JSON array of note dictionaries, each containing pitch,
        start_time, duration, velocity, and mute.

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
        """
        try:
            cache_key = f"clip_notes_{track_index}_{clip_index}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_clip_notes", {
                "track_index": track_index,
                "clip_index": clip_index,
            })
            response = json.dumps(result, indent=2)
            cache.set(cache_key, response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting clip notes at track {track_index}, slot {clip_index}: {e}")
            return f"Error getting clip notes at track {track_index}, slot {clip_index}: {e}"

    @mcp.tool()
    async def remove_notes_from_clip(
        track_index: int,
        clip_index: int,
        from_time: float = 0.0,
        time_span: float = 999.0,
        from_pitch: int = 0,
        pitch_span: int = 127,
    ) -> str:
        """Remove notes from a clip within the specified range.

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
            from_time: Start of the time range in beats (default 0.0).
            time_span: Length of the time range in beats (default 999.0).
            from_pitch: Lowest MIDI pitch to remove (default 0).
            pitch_span: Number of pitches above from_pitch to include (default 127).
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("remove_notes_from_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
                "from_time": from_time,
                "time_span": time_span,
                "from_pitch": from_pitch,
                "pitch_span": pitch_span,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error removing notes from clip at track {track_index}, slot {clip_index}: {e}")
            return f"Error removing notes from clip at track {track_index}, slot {clip_index}: {e}"

    @mcp.tool()
    async def set_clip_loop(
        track_index: int,
        clip_index: int,
        looping: bool = True,
        loop_start: float = 0.0,
        loop_end: float = 4.0,
    ) -> str:
        """Set clip loop settings.

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
            looping: Whether looping is enabled (default True).
            loop_start: Loop start position in beats (default 0.0).
            loop_end: Loop end position in beats (default 4.0).
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_clip_loop", {
                "track_index": track_index,
                "clip_index": clip_index,
                "looping": looping,
                "loop_start": loop_start,
                "loop_end": loop_end,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting loop for clip at track {track_index}, slot {clip_index}: {e}")
            return f"Error setting loop for clip at track {track_index}, slot {clip_index}: {e}"

    @mcp.tool()
    async def quantize_clip(
        track_index: int,
        clip_index: int,
        quantization: int = 5,
        amount: float = 1.0,
    ) -> str:
        """Quantize notes in a clip.

        Args:
            track_index: The zero-based index of the track.
            clip_index: The zero-based index of the clip slot.
            quantization: Quantization grid size (1=1 bar, 2=1/2, 3=1/4,
                4=1/8, 5=1/16, 6=1/32). Default is 5 (1/16).
            amount: Quantization strength from 0.0 (no change) to 1.0
                (fully quantized). Default is 1.0.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("quantize_clip", {
                "track_index": track_index,
                "clip_index": clip_index,
                "quantization": quantization,
                "amount": amount,
            })
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error quantizing clip at track {track_index}, slot {clip_index}: {e}")
            return f"Error quantizing clip at track {track_index}, slot {clip_index}: {e}"
