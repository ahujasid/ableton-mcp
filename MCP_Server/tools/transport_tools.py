"""Transport and global session control tools for AbletonMCP"""
import json
import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: FastMCP, get_connection, cache):
    """Register transport tools with the MCP server"""

    @mcp.tool()
    async def start_playback() -> str:
        """Start playing the session."""
        try:
            conn = await get_connection()
            result = await conn.send_command("start_playback", {})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error starting playback: {e}")
            return f"Error starting playback: {e}"

    @mcp.tool()
    async def stop_playback() -> str:
        """Stop playing the session."""
        try:
            conn = await get_connection()
            result = await conn.send_command("stop_playback", {})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error stopping playback: {e}")
            return f"Error stopping playback: {e}"

    @mcp.tool()
    async def fire_clip(track_index: int, clip_index: int) -> str:
        """Start playing a specific clip.

        Args:
            track_index: The zero-based index of the track containing the clip.
            clip_index: The zero-based index of the clip slot to fire.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("fire_clip", {"track_index": track_index, "clip_index": clip_index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error firing clip: {e}")
            return f"Error firing clip: {e}"

    @mcp.tool()
    async def stop_clip(track_index: int, clip_index: int) -> str:
        """Stop playing a specific clip.

        Args:
            track_index: The zero-based index of the track containing the clip.
            clip_index: The zero-based index of the clip slot to stop.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("stop_clip", {"track_index": track_index, "clip_index": clip_index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error stopping clip: {e}")
            return f"Error stopping clip: {e}"

    @mcp.tool()
    async def set_tempo(tempo: float) -> str:
        """Set the session tempo in BPM (20.0 to 999.0).

        Args:
            tempo: The tempo in beats per minute, between 20.0 and 999.0.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_tempo", {"tempo": tempo})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting tempo: {e}")
            return f"Error setting tempo: {e}"

    @mcp.tool()
    async def undo() -> str:
        """Undo the last action."""
        try:
            conn = await get_connection()
            result = await conn.send_command("undo", {})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error undoing action: {e}")
            return f"Error undoing action: {e}"

    @mcp.tool()
    async def redo() -> str:
        """Redo the last undone action."""
        try:
            conn = await get_connection()
            result = await conn.send_command("redo", {})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error redoing action: {e}")
            return f"Error redoing action: {e}"

    @mcp.tool()
    async def set_metronome(enabled: bool) -> str:
        """Enable or disable the metronome.

        Args:
            enabled: True to enable the metronome, False to disable it.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_metronome", {"enabled": enabled})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting metronome: {e}")
            return f"Error setting metronome: {e}"

    @mcp.tool()
    async def set_loop(enabled: bool, start: float = 0.0, length: float = 4.0) -> str:
        """Set loop on/off and configure the loop range in beats.

        Args:
            enabled: True to enable looping, False to disable it.
            start: Loop start position in beats. Defaults to 0.0.
            length: Loop length in beats. Defaults to 4.0.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_loop", {"enabled": enabled, "start": start, "length": length})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting loop: {e}")
            return f"Error setting loop: {e}"

    @mcp.tool()
    async def get_playing_position() -> str:
        """Get the current playback position including time in beats, bar, and beat."""
        try:
            cached = cache.get("playing_position")
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_playing_position", {})
            response = json.dumps(result, indent=2)
            cache.set("playing_position", response, ttl=0.5)
            return response
        except Exception as e:
            logger.error(f"Error getting playing position: {e}")
            return f"Error getting playing position: {e}"

    @mcp.tool()
    async def set_time_signature(numerator: int = 4, denominator: int = 4) -> str:
        """Set the time signature.

        Args:
            numerator: The top number of the time signature. Defaults to 4.
            denominator: The bottom number of the time signature. Defaults to 4.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command(
                "set_time_signature", {"numerator": numerator, "denominator": denominator}
            )
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting time signature: {e}")
            return f"Error setting time signature: {e}"

    @mcp.tool()
    async def capture_midi() -> str:
        """Capture recently played MIDI into a clip (Ableton Live 10.1+).

        Turns the last played MIDI notes into a new clip on the active track.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("capture_midi", {})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error capturing MIDI: {e}")
            return f"Error capturing MIDI: {e}"

    @mcp.tool()
    async def tap_tempo() -> str:
        """Tap tempo - call multiple times to set tempo by tapping."""
        try:
            conn = await get_connection()
            result = await conn.send_command("tap_tempo", {})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error tapping tempo: {e}")
            return f"Error tapping tempo: {e}"

    @mcp.tool()
    async def set_arrangement_position(position: float) -> str:
        """Set the playback position in the arrangement view.

        Args:
            position: The position in beats to jump to.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_arrangement_position", {"position": position})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting arrangement position: {e}")
            return f"Error setting arrangement position: {e}"

    @mcp.tool()
    async def set_record(enabled: bool) -> str:
        """Enable or disable session recording.

        Args:
            enabled: True to start recording, False to stop recording.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_record", {"enabled": enabled})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting record: {e}")
            return f"Error setting record: {e}"
