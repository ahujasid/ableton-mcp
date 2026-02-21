"""Session tools: session info, tempo, playback."""

import json
import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def get_session_info(ctx: Context) -> str:
        """Get detailed information about the current Ableton session."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_session_info")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting session info from Ableton: {str(e)}")
            return f"Error getting session info: {str(e)}"

    @mcp.tool()
    def set_tempo(ctx: Context, tempo: float) -> str:
        """Set the tempo of the Ableton session. Parameters: tempo (BPM)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_tempo", {"tempo": tempo})
            return f"Set tempo to {tempo} BPM"
        except Exception as e:
            logger.error(f"Error setting tempo: {str(e)}")
            return f"Error setting tempo: {str(e)}"

    @mcp.tool()
    def start_playback(ctx: Context) -> str:
        """Start playing the Ableton session."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("start_playback")
            return "Started playback"
        except Exception as e:
            logger.error(f"Error starting playback: {str(e)}")
            return f"Error starting playback: {str(e)}"

    @mcp.tool()
    def stop_playback(ctx: Context) -> str:
        """Stop playing the Ableton session."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("stop_playback")
            return "Stopped playback"
        except Exception as e:
            logger.error(f"Error stopping playback: {str(e)}")
            return f"Error stopping playback: {str(e)}"

    @mcp.tool()
    def switch_to_view(ctx: Context, view_name: str) -> str:
        """Switch Live UI view. Parameters: view_name ('session' or 'arrangement')."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("switch_to_view", {"view_name": view_name})
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error switching view: {str(e)}")
            return f"Error switching view: {str(e)}"

    @mcp.tool()
    def get_project_overview(ctx: Context) -> str:
        """Get a complete project overview in a single call: session info, all tracks with devices, group structure, and arrangement clips for every track. Use this instead of calling get_session_info + get_all_tracks_info + get_arrangement_clips individually."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_project_overview")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting project overview: {str(e)}")
            return f"Error getting project overview: {str(e)}"

    @mcp.tool()
    def reload_handlers(ctx: Context) -> str:
        """Hot-reload all AbletonMCP handler modules without restarting Ableton. Use after deploying code changes."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("reload_handlers")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error reloading handlers: {str(e)}")
            return f"Error reloading handlers: {str(e)}"

    @mcp.tool()
    def record_arrangement_clip(
        ctx: Context,
        track_index: int,
        clip_index: int,
        start_time: float = 0.0,
    ) -> str:
        """Start arrangement recording and fire a session clip at start_time."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command(
                "record_arrangement_clip",
                {
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "start_time": start_time,
                },
            )
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error recording arrangement clip: {str(e)}")
            return f"Error recording arrangement clip: {str(e)}"
