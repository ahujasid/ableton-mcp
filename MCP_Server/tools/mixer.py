"""Mixer tools: volume, pan, mute, solo, sends."""

import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def set_track_volume(ctx: Context, track_index: int, volume: float) -> str:
        """Set track volume. Parameters: track_index, volume (0.0 = -inf dB, 0.85 = 0 dB, 1.0 = +6 dB)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_track_volume", {"track_index": track_index, "volume": volume})
            return f"Set track {track_index} volume to {volume}"
        except Exception as e:
            logger.error(f"Error setting track volume: {str(e)}")
            return f"Error setting track volume: {str(e)}"

    @mcp.tool()
    def set_track_pan(ctx: Context, track_index: int, pan: float) -> str:
        """Set track pan. Parameters: track_index, pan (-1.0 = full left, 0.0 = center, 1.0 = full right)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_track_pan", {"track_index": track_index, "pan": pan})
            return f"Set track {track_index} pan to {pan}"
        except Exception as e:
            logger.error(f"Error setting track pan: {str(e)}")
            return f"Error setting track pan: {str(e)}"

    @mcp.tool()
    def set_track_mute(ctx: Context, track_index: int, mute: bool) -> str:
        """Set track mute. Parameters: track_index, mute (True/False)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_track_mute", {"track_index": track_index, "mute": mute})
            return f"Set track {track_index} mute to {mute}"
        except Exception as e:
            logger.error(f"Error setting track mute: {str(e)}")
            return f"Error setting track mute: {str(e)}"

    @mcp.tool()
    def set_track_solo(ctx: Context, track_index: int, solo: bool) -> str:
        """Set track solo. Parameters: track_index, solo (True/False)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_track_solo", {"track_index": track_index, "solo": solo})
            return f"Set track {track_index} solo to {solo}"
        except Exception as e:
            logger.error(f"Error setting track solo: {str(e)}")
            return f"Error setting track solo: {str(e)}"

    @mcp.tool()
    def set_track_send(ctx: Context, track_index: int, send_index: int, value: float) -> str:
        """Set track send level. Parameters: track_index, send_index (0=Send A, 1=Send B), value (0.0-1.0)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_track_send", {
                "track_index": track_index, "send_index": send_index, "value": value
            })
            return f"Set track {track_index} send {send_index} to {value}"
        except Exception as e:
            logger.error(f"Error setting track send: {str(e)}")
            return f"Error setting track send: {str(e)}"
