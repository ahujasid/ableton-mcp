"""Audio tools: load sample."""

import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def load_audio_sample(
        ctx: Context,
        track_index: int,
        clip_index: int,
        file_path: str = "",
        browser_uri: str = "",
    ) -> str:
        """Load an audio sample into a clip slot. Use browser_uri (from browser) when possible; file_path loading may not be supported. Parameters: track_index, clip_index, file_path (optional), browser_uri (optional)."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("load_audio_sample", {
                "track_index": track_index,
                "clip_index": clip_index,
                "file_path": file_path,
                "browser_uri": browser_uri,
            })
            if result.get("loaded", False):
                return f"Loaded audio into track {track_index}, slot {clip_index}"
            return str(result.get("message", result))
        except Exception as e:
            logger.error(f"Error loading audio sample: {str(e)}")
            return f"Error loading audio sample: {str(e)}"
