"""Session information tools for AbletonMCP"""
import json
import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: FastMCP, get_connection, cache):
    """Register session tools with the MCP server"""

    @mcp.tool()
    async def get_session_info() -> str:
        """Get basic information about the current Ableton Live session.

        Returns tempo, time signature, track count, return track count,
        and master track info.
        """
        try:
            cached = cache.get("session_info")
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_session_info", {})
            response = json.dumps(result, indent=2)
            cache.set("session_info", response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting session info: {e}")
            return f"Error getting session info: {e}"

    @mcp.tool()
    async def get_track_info(track_index: int) -> str:
        """Get detailed information about a specific track.

        Returns the track's name, type, mute/solo/arm state, volume, pan,
        clip slots, and devices.

        Args:
            track_index: The zero-based index of the track to query.
        """
        try:
            cache_key = f"track_info_{track_index}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_track_info", {"track_index": track_index})
            response = json.dumps(result, indent=2)
            cache.set(cache_key, response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting track info for track {track_index}: {e}")
            return f"Error getting track info for track {track_index}: {e}"

    @mcp.tool()
    async def get_full_session_state() -> str:
        """Get the complete session state in a single call.

        This is the fastest way to get a full picture of the Ableton session.
        Returns everything at once: tempo, time signature, all tracks with
        their clips and devices, scenes, return tracks, and master track info.

        Use this instead of calling get_session_info + get_track_info for each
        track to avoid N+1 round-trips.
        """
        try:
            cached = cache.get("full_session_state")
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_full_session_state", {})
            response = json.dumps(result, indent=2)
            cache.set("full_session_state", response, ttl=3)
            return response
        except Exception as e:
            logger.error(f"Error getting full session state: {e}")
            return f"Error getting full session state: {e}"

    @mcp.tool()
    async def get_all_tracks_info() -> str:
        """Get summary information for all tracks at once.

        Returns a list of all tracks with their name, type, mute, solo,
        and arm state. Useful for getting a quick overview of the session's
        track layout without the full detail of get_full_session_state.
        """
        try:
            cached = cache.get("all_tracks_info")
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_all_tracks_info", {})
            response = json.dumps(result, indent=2)
            cache.set("all_tracks_info", response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting all tracks info: {e}")
            return f"Error getting all tracks info: {e}"
