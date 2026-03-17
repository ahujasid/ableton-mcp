"""Browser navigation and instrument loading tools for AbletonMCP"""
import json
import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")


def _format_tree(node, indent=0) -> str:
    """Recursively format a browser tree node into a readable string."""
    lines = []
    prefix = "  " * indent + "\u2022 "
    name = node.get("name", "Unknown")
    path = node.get("path", "")
    children = node.get("children", [])
    is_folder = node.get("is_folder", bool(children))

    label = name
    if path:
        label += f" (path: {path})"

    if is_folder and children:
        lines.append(f"{prefix}{label}")
        for child in children:
            lines.append(_format_tree(child, indent + 1))
    elif is_folder:
        lines.append(f"{prefix}{label} [...]")
    else:
        lines.append(f"{prefix}{label}")

    return "\n".join(lines)


def _format_browser_tree(data, category_type) -> str:
    """Format the full browser tree response into a readable string."""
    if isinstance(data, dict) and "categories" in data:
        categories = data["categories"]
    elif isinstance(data, list):
        categories = data
    else:
        return json.dumps(data, indent=2)

    lines = [f"Browser tree for '{category_type}':"]
    for category in categories:
        lines.append(_format_tree(category, indent=1))
    return "\n".join(lines)


def register(mcp: FastMCP, get_connection, cache):
    """Register browser tools with the MCP server"""

    @mcp.tool()
    async def get_browser_tree(category_type: str = "all") -> str:
        """Get a hierarchical tree of Ableton's browser categories.

        Returns a readable tree of instruments, effects, drums, and sounds
        available in the browser. Use this to discover what's available
        before loading items onto tracks.

        Args:
            category_type: Filter by category - 'all', 'instruments', 'sounds',
                          'drums', 'audio_effects', or 'midi_effects'.
        """
        try:
            cache_key = f"browser_tree_{category_type}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_browser_tree", {"category_type": category_type})
            response = _format_browser_tree(result, category_type)
            cache.set(cache_key, response, ttl=60)
            return response
        except Exception as e:
            logger.error(f"Error getting browser tree: {e}")
            return f"Error getting browser tree: {e}"

    @mcp.tool()
    async def get_browser_items_at_path(path: str) -> str:
        """Get browser items at a specific path in Ableton's browser.

        Use this to drill into a specific folder after discovering paths
        via get_browser_tree. Returns the items (presets, devices, samples)
        available at the given path.

        Args:
            path: Browser path to explore (e.g., 'instruments/Synths/Bass').
        """
        try:
            cache_key = f"browser_items_{path}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("get_browser_items_at_path", {"path": path})
            response = json.dumps(result, indent=2)
            cache.set(cache_key, response, ttl=30)
            return response
        except Exception as e:
            logger.error(f"Error getting browser items at path '{path}': {e}")
            return f"Error getting browser items at path '{path}': {e}"

    @mcp.tool()
    async def search_browser(query: str, category_type: str = "all") -> str:
        """Search for items in Ableton's browser by name.

        More user-friendly than navigating the tree manually. Use this to
        quickly find instruments, effects, or presets by name.

        Args:
            query: Search query (e.g., 'bass', 'reverb', 'compressor').
            category_type: Limit search to a category - 'all', 'instruments',
                          'sounds', 'drums', 'audio_effects', or 'midi_effects'.
        """
        try:
            cache_key = f"browser_search_{query}_{category_type}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command("search_browser", {"query": query, "category_type": category_type})
            response = json.dumps(result, indent=2)
            cache.set(cache_key, response, ttl=30)
            return response
        except Exception as e:
            logger.error(f"Error searching browser for '{query}': {e}")
            return f"Error searching browser for '{query}': {e}"

    @mcp.tool()
    async def load_instrument_or_effect(track_index: int, uri: str) -> str:
        """Load an instrument or effect onto a track using its browser URI.

        Use get_browser_tree, get_browser_items_at_path, or search_browser
        first to find the URI of the item you want to load.

        Args:
            track_index: The zero-based index of the target track.
            uri: The browser URI of the instrument or effect to load.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command("load_browser_item", {"track_index": track_index, "item_uri": uri})
            cache.invalidate("browser")
            cache.invalidate("track")
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error loading item onto track {track_index}: {e}")
            return f"Error loading item onto track {track_index}: {e}"

    @mcp.tool()
    async def load_drum_kit(track_index: int, rack_uri: str, kit_path: str) -> str:
        """Load a drum rack and then a specific drum kit into it.

        This is a two-step process: first loads the drum rack onto the track,
        then finds and loads the specific kit. Use get_browser_tree or
        search_browser to find the rack_uri and kit_path.

        Args:
            track_index: The zero-based index of the target track.
            rack_uri: The browser URI of the drum rack to load.
            kit_path: The browser path to the specific drum kit to load into the rack.
        """
        try:
            conn = await get_connection()

            # Step 1: Load the drum rack onto the track
            rack_result = await conn.send_command(
                "load_browser_item", {"track_index": track_index, "item_uri": rack_uri}
            )

            # Step 2: Find the loadable kit at the given path
            kit_items = await conn.send_command("get_browser_items_at_path", {"path": kit_path})

            # Step 3: Find a loadable item in the results and load it
            loadable_uri = None
            items = kit_items if isinstance(kit_items, list) else kit_items.get("items", [])
            for item in items:
                if item.get("is_loadable") or item.get("uri"):
                    loadable_uri = item.get("uri")
                    break

            if loadable_uri is None:
                cache.invalidate("browser")
                cache.invalidate("track")
                return json.dumps({
                    "status": "partial",
                    "message": "Drum rack loaded but no loadable kit found at the given path.",
                    "rack_result": rack_result,
                    "kit_items": kit_items,
                }, indent=2)

            kit_result = await conn.send_command(
                "load_browser_item", {"track_index": track_index, "item_uri": loadable_uri}
            )

            cache.invalidate("browser")
            cache.invalidate("track")
            return json.dumps({
                "status": "success",
                "rack_result": rack_result,
                "kit_result": kit_result,
            }, indent=2)
        except Exception as e:
            logger.error(f"Error loading drum kit onto track {track_index}: {e}")
            return f"Error loading drum kit onto track {track_index}: {e}"
