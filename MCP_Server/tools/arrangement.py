"""Arrangement tools: locator, copy clip to arrangement, get arrangement clips, create automation."""

import json
import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def create_locator(ctx: Context, position: float, name: str = "") -> str:
        """Create a locator/marker at a position. Parameters: position (beats), name (optional)."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("create_locator", {"position": position, "name": name})
            return f"Created locator '{name}' at position {position} beats"
        except Exception as e:
            logger.error(f"Error creating locator: {str(e)}")
            return f"Error creating locator: {str(e)}"

    @mcp.tool()
    def copy_clip_to_arrangement(
        ctx: Context,
        track_index: int,
        clip_index: int,
        arrangement_time: float,
    ) -> str:
        """Copy a session clip to arrangement at a time. Parameters: track_index, clip_index, arrangement_time (beats)."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("copy_clip_to_arrangement", {
                "track_index": track_index,
                "clip_index": clip_index,
                "arrangement_time": arrangement_time,
            })
            if result.get("copied", False):
                return f"Copied clip to arrangement at {arrangement_time} beats"
            return result.get("note", str(result))
        except Exception as e:
            logger.error(f"Error copying clip to arrangement: {str(e)}")
            return f"Error copying clip to arrangement: {str(e)}"

    @mcp.tool()
    def get_arrangement_clips(ctx: Context, track_index: int) -> str:
        """Get all clips in arrangement view for a track. Parameters: track_index."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_arrangement_clips", {"track_index": track_index})
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting arrangement clips: {str(e)}")
            return f"Error getting arrangement clips: {str(e)}"

    @mcp.tool()
    def create_automation(
        ctx: Context,
        track_index: int,
        parameter_name: str,
        automation_points: str,
    ) -> str:
        """Create automation for a parameter. Parameters: track_index, parameter_name (e.g. 'Volume', 'Pan'), automation_points (JSON string e.g. '[{\"time\": 0, \"value\": 0.5}]')."""
        try:
            points = __import__("json").loads(automation_points)
            ableton = get_ableton_connection()
            ableton.send_command("create_automation", {
                "track_index": track_index,
                "parameter_name": parameter_name,
                "automation_points": points,
            })
            return f"Created automation for {parameter_name} on track {track_index} with {len(points)} points"
        except Exception as e:
            logger.error(f"Error creating automation: {str(e)}")
            return f"Error creating automation: {str(e)}"
