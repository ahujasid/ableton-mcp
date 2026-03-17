"""Track management tools for AbletonMCP"""
import json
import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: FastMCP, get_connection, cache):
    """Register track tools with the MCP server"""

    @mcp.tool()
    async def create_midi_track(index: int = -1) -> str:
        """Create a new MIDI track. Use index=-1 to add at the end of the track list."""
        try:
            conn = await get_connection()
            result = await conn.send_command("create_midi_track", {"index": index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error creating MIDI track: {e}")
            return f"Error creating MIDI track: {e}"

    @mcp.tool()
    async def create_audio_track(index: int = -1) -> str:
        """Create a new audio track. Use index=-1 to add at the end of the track list."""
        try:
            conn = await get_connection()
            result = await conn.send_command("create_audio_track", {"index": index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error creating audio track: {e}")
            return f"Error creating audio track: {e}"

    @mcp.tool()
    async def delete_track(track_index: int) -> str:
        """Delete a track by index."""
        try:
            conn = await get_connection()
            result = await conn.send_command("delete_track", {"track_index": track_index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error deleting track: {e}")
            return f"Error deleting track: {e}"

    @mcp.tool()
    async def duplicate_track(track_index: int) -> str:
        """Duplicate a track."""
        try:
            conn = await get_connection()
            result = await conn.send_command("duplicate_track", {"track_index": track_index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error duplicating track: {e}")
            return f"Error duplicating track: {e}"

    @mcp.tool()
    async def set_track_name(track_index: int, name: str) -> str:
        """Rename a track."""
        try:
            conn = await get_connection()
            result = await conn.send_command("set_track_name", {"track_index": track_index, "name": name})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting track name: {e}")
            return f"Error setting track name: {e}"

    @mcp.tool()
    async def set_track_volume(track_index: int, volume: float) -> str:
        """Set track volume (0.0 to 1.0, where 0.85 is approximately 0dB)."""
        try:
            conn = await get_connection()
            result = await conn.send_command("set_track_volume", {"track_index": track_index, "volume": volume})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting track volume: {e}")
            return f"Error setting track volume: {e}"

    @mcp.tool()
    async def set_track_pan(track_index: int, pan: float) -> str:
        """Set track panning (-1.0 left to 1.0 right, 0.0 center)."""
        try:
            conn = await get_connection()
            result = await conn.send_command("set_track_pan", {"track_index": track_index, "pan": pan})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting track pan: {e}")
            return f"Error setting track pan: {e}"

    @mcp.tool()
    async def set_track_mute(track_index: int, mute: bool) -> str:
        """Mute or unmute a track."""
        try:
            conn = await get_connection()
            result = await conn.send_command("set_track_mute", {"track_index": track_index, "mute": mute})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting track mute: {e}")
            return f"Error setting track mute: {e}"

    @mcp.tool()
    async def set_track_solo(track_index: int, solo: bool) -> str:
        """Solo or unsolo a track."""
        try:
            conn = await get_connection()
            result = await conn.send_command("set_track_solo", {"track_index": track_index, "solo": solo})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting track solo: {e}")
            return f"Error setting track solo: {e}"

    @mcp.tool()
    async def set_track_arm(track_index: int, arm: bool) -> str:
        """Arm or disarm a track for recording."""
        try:
            conn = await get_connection()
            result = await conn.send_command("set_track_arm", {"track_index": track_index, "arm": arm})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting track arm: {e}")
            return f"Error setting track arm: {e}"

    @mcp.tool()
    async def set_track_send(track_index: int, send_index: int, value: float) -> str:
        """Set the send level for a track's send (0.0 to 1.0)."""
        try:
            conn = await get_connection()
            result = await conn.send_command(
                "set_track_send", {"track_index": track_index, "send_index": send_index, "value": value}
            )
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting track send: {e}")
            return f"Error setting track send: {e}"
