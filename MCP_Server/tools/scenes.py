"""Scene tools: create, trigger, set name."""

import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def create_scene(ctx: Context, index: int = -1, name: str = "") -> str:
        """Create a new scene. Parameters: index (-1 = end), name (optional)."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("create_scene", {"index": index, "name": name})
            return f"Created scene at index {result.get('index', index)}: {result.get('name', name) or '(unnamed)'}"
        except Exception as e:
            logger.error(f"Error creating scene: {str(e)}")
            return f"Error creating scene: {str(e)}"

    @mcp.tool()
    def trigger_scene(ctx: Context, scene_index: int) -> str:
        """Trigger/fire a scene. Parameters: scene_index."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("trigger_scene", {"scene_index": scene_index})
            return f"Triggered scene {scene_index}"
        except Exception as e:
            logger.error(f"Error triggering scene: {str(e)}")
            return f"Error triggering scene: {str(e)}"

    @mcp.tool()
    def set_scene_name(ctx: Context, scene_index: int, name: str) -> str:
        """Set the name of a scene. Parameters: scene_index, name."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_scene_name", {"scene_index": scene_index, "name": name})
            return f"Set scene {scene_index} name to '{name}'"
        except Exception as e:
            logger.error(f"Error setting scene name: {str(e)}")
            return f"Error setting scene name: {str(e)}"
