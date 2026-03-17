"""Scene management tools for AbletonMCP"""
import json
import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: FastMCP, get_connection, cache):
    """Register scene tools with the MCP server"""

    @mcp.tool()
    async def get_scene_info(scene_index: int) -> str:
        """Get information about a specific scene.

        Returns the scene's name, tempo, and time signature if set.

        Args:
            scene_index: The zero-based index of the scene to query.
        """
        try:
            cache_key = f"scene_info_{scene_index}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_scene_info", {"scene_index": scene_index})
            response = json.dumps(result, indent=2)
            cache.set(cache_key, response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting scene info for scene {scene_index}: {e}")
            return f"Error getting scene info for scene {scene_index}: {e}"

    @mcp.tool()
    async def get_all_scenes() -> str:
        """Get information about all scenes in the session.

        Returns a list of all scenes with their names, tempos, and time
        signatures if set.
        """
        try:
            cached = cache.get("all_scenes")
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_all_scenes", {})
            response = json.dumps(result, indent=2)
            cache.set("all_scenes", response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting all scenes: {e}")
            return f"Error getting all scenes: {e}"

    @mcp.tool()
    async def create_scene(index: int = -1) -> str:
        """Create a new scene in the session.

        Args:
            index: The position to insert the new scene. Use -1 to add at
                   the end.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("create_scene", {"index": index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error creating scene: {e}")
            return f"Error creating scene: {e}"

    @mcp.tool()
    async def delete_scene(scene_index: int) -> str:
        """Delete a scene from the session.

        Args:
            scene_index: The zero-based index of the scene to delete.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("delete_scene", {"scene_index": scene_index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error deleting scene {scene_index}: {e}")
            return f"Error deleting scene {scene_index}: {e}"

    @mcp.tool()
    async def duplicate_scene(scene_index: int) -> str:
        """Duplicate a scene in the session.

        Args:
            scene_index: The zero-based index of the scene to duplicate.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("duplicate_scene", {"scene_index": scene_index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error duplicating scene {scene_index}: {e}")
            return f"Error duplicating scene {scene_index}: {e}"

    @mcp.tool()
    async def fire_scene(scene_index: int) -> str:
        """Fire (launch) a scene, triggering all clips in the scene.

        Args:
            scene_index: The zero-based index of the scene to fire.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("fire_scene", {"scene_index": scene_index})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error firing scene {scene_index}: {e}")
            return f"Error firing scene {scene_index}: {e}"

    @mcp.tool()
    async def set_scene_name(scene_index: int, name: str) -> str:
        """Set the name of a scene.

        Args:
            scene_index: The zero-based index of the scene to rename.
            name: The new name for the scene.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("set_scene_name", {"scene_index": scene_index, "name": name})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting name for scene {scene_index}: {e}")
            return f"Error setting name for scene {scene_index}: {e}"

    @mcp.tool()
    async def stop_all_clips() -> str:
        """Stop all playing clips in the session."""
        try:
            conn = await get_connection()
            result = await conn.send_command("stop_all_clips", {})
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error stopping all clips: {e}")
            return f"Error stopping all clips: {e}"
