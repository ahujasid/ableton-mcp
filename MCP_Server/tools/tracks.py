"""Track tools: info, create, delete, name, color, arm, bulk info."""

import json
import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def get_track_info(ctx: Context, track_index: int) -> str:
        """Get detailed information about a specific track. Parameters: track_index."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_track_info", {"track_index": track_index})
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting track info from Ableton: {str(e)}")
            return f"Error getting track info: {str(e)}"

    @mcp.tool()
    def create_midi_track(ctx: Context, index: int = -1) -> str:
        """Create a new MIDI track. Parameters: index (-1 = end of list)."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("create_midi_track", {"index": index})
            return f"Created new MIDI track: {result.get('name', 'unknown')}"
        except Exception as e:
            logger.error(f"Error creating MIDI track: {str(e)}")
            return f"Error creating MIDI track: {str(e)}"

    @mcp.tool()
    def create_audio_track(ctx: Context, index: int = -1) -> str:
        """Create a new audio track. Parameters: index (-1 = end of list)."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("create_audio_track", {"index": index})
            return f"Created new audio track: {result.get('name', 'unknown')}"
        except Exception as e:
            logger.error(f"Error creating audio track: {str(e)}")
            return f"Error creating audio track: {str(e)}"

    @mcp.tool()
    def create_return_track(ctx: Context) -> str:
        """Create a new return track (for sends like reverb/delay)."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("create_return_track")
            return f"Created return track: {result.get('name', 'unknown')}"
        except Exception as e:
            logger.error(f"Error creating return track: {str(e)}")
            return f"Error creating return track: {str(e)}"

    @mcp.tool()
    def set_track_name(ctx: Context, track_index: int, name: str) -> str:
        """Set the name of a track. Parameters: track_index, name."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("set_track_name", {"track_index": track_index, "name": name})
            return f"Renamed track to: {result.get('name', name)}"
        except Exception as e:
            logger.error(f"Error setting track name: {str(e)}")
            return f"Error setting track name: {str(e)}"

    @mcp.tool()
    def delete_track(ctx: Context, track_index: int) -> str:
        """Delete a track at the specified index."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("delete_track", {"track_index": track_index})
            return f"Deleted track {track_index}"
        except Exception as e:
            logger.error(f"Error deleting track: {str(e)}")
            return f"Error deleting track: {str(e)}"

    @mcp.tool()
    def set_track_color(ctx: Context, track_index: int, color_index: int) -> str:
        """Set track color. Parameters: track_index, color_index (0-69)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_track_color", {"track_index": track_index, "color_index": color_index})
            return f"Set track {track_index} color to index {color_index}"
        except Exception as e:
            logger.error(f"Error setting track color: {str(e)}")
            return f"Error setting track color: {str(e)}"

    @mcp.tool()
    def arm_track(ctx: Context, track_index: int) -> str:
        """Arm a track for recording. Parameters: track_index."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("arm_track", {"track_index": track_index})
            return f"Armed track {track_index} for recording"
        except Exception as e:
            logger.error(f"Error arming track: {str(e)}")
            return f"Error arming track: {str(e)}"

    @mcp.tool()
    def set_track_arm(ctx: Context, track_index: int, arm: bool) -> str:
        """Set the arm state of a track. Parameters: track_index, arm (True/False)."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_track_arm", {"track_index": track_index, "arm": arm})
            return f"Set track {track_index} arm to {arm}"
        except Exception as e:
            logger.error(f"Error setting track arm: {str(e)}")
            return f"Error setting track arm: {str(e)}"

    @mcp.tool()
    def get_all_tracks_info(ctx: Context) -> str:
        """Get summary info for all tracks at once."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_all_tracks_info")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting all tracks info: {str(e)}")
            return f"Error getting all tracks info: {str(e)}"

    @mcp.tool()
    def get_return_tracks_info(ctx: Context) -> str:
        """Get info for all return tracks."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_return_tracks_info")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting return tracks info: {str(e)}")
            return f"Error getting return tracks info: {str(e)}"
