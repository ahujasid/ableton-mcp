"""Browser tools: tree, items at path, load instrument/effect."""

import json
import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def get_browser_tree(ctx: Context, category_type: str = "all") -> str:
        """Get a hierarchical tree of browser categories. Parameters: category_type ('all'|'instruments'|'sounds'|'drums'|'audio_effects'|'midi_effects')."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_browser_tree", {"category_type": category_type})
            if "available_categories" in result and len(result.get("categories", [])) == 0:
                return (
                    f"No categories found for '{category_type}'. "
                    f"Available: {', '.join(result.get('available_categories', []))}"
                )
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting browser tree: {str(e)}")
            return f"Error getting browser tree: {str(e)}"

    @mcp.tool()
    def get_browser_items_at_path(ctx: Context, path: str) -> str:
        """Get browser items at a path. Parameters: path (e.g. 'instruments/synths/bass')."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_browser_items_at_path", {"path": path})
            if "error" in result and "available_categories" in result:
                return f"Error: {result.get('error')}\nAvailable: {', '.join(result.get('available_categories', []))}"
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting browser items at path: {str(e)}")
            return f"Error getting browser items at path: {str(e)}"

    @mcp.tool()
    def load_instrument_or_effect(ctx: Context, track_index: int, uri: str, track_type: str = "track") -> str:
        """Load an instrument or effect onto a track by URI. Parameters: track_index, uri (e.g. from browser), track_type ('track'|'return'|'master'). For master, track_index is ignored."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("load_browser_item", {
                "track_index": track_index,
                "item_uri": uri,
                "track_type": track_type,
            })
            if result.get("loaded", False):
                target = result.get("track_name") or f"track {track_index}"
                return f"Loaded '{result.get('item_name', uri)}' on {target}"
            return f"Failed to load instrument with URI '{uri}'"
        except Exception as e:
            logger.error(f"Error loading instrument by URI: {str(e)}")
            return f"Error loading instrument by URI: {str(e)}"
