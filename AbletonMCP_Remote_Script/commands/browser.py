"""
Browser navigation and instrument loading commands.

These commands navigate Ableton's browser and load instruments/effects
onto tracks. Browser operations require access to the Application object.
"""

from typing import Any, Dict, Optional

from . import Command, CommandContext, CommandRegistry, ModifyingCommand


def _find_browser_item_by_uri(
    browser_or_item: Any,
    uri: str,
    cache: Dict[str, Any],
    max_depth: int = 10,
    current_depth: int = 0,
) -> Optional[Any]:
    """Find a browser item by its URI, using cache for O(1) lookup."""
    # Check cache first
    if uri in cache:
        return cache[uri]

    # Cache miss - populate cache if empty
    if not cache and hasattr(browser_or_item, "instruments"):
        _populate_browser_cache(browser_or_item, cache)

        # Try cache again
        if uri in cache:
            return cache[uri]

    # Fall back to original traversal for items not in cache
    if hasattr(browser_or_item, "uri") and browser_or_item.uri == uri:
        return browser_or_item

    if current_depth >= max_depth:
        return None

    if hasattr(browser_or_item, "instruments"):
        categories = [
            browser_or_item.instruments,
            browser_or_item.sounds,
            browser_or_item.drums,
            browser_or_item.audio_effects,
            browser_or_item.midi_effects,
        ]
        for category in categories:
            item = _find_browser_item_by_uri(category, uri, cache, max_depth, current_depth + 1)
            if item:
                cache[uri] = item  # Cache the find
                return item
        return None

    if hasattr(browser_or_item, "children") and browser_or_item.children:
        for child in browser_or_item.children:
            item = _find_browser_item_by_uri(child, uri, cache, max_depth, current_depth + 1)
            if item:
                cache[uri] = item  # Cache the find
                return item

    return None


def _populate_browser_cache(
    browser_or_item: Any,
    cache: Dict[str, Any],
    max_depth: int = 10,
    current_depth: int = 0,
) -> None:
    """Populate the URI cache from browser tree."""
    if current_depth >= max_depth:
        return

    # Add this item to cache if it has a URI
    if hasattr(browser_or_item, "uri") and browser_or_item.uri:
        cache[browser_or_item.uri] = browser_or_item

    # Check if this is a browser with root categories
    if hasattr(browser_or_item, "instruments"):
        categories = [
            browser_or_item.instruments,
            browser_or_item.sounds,
            browser_or_item.drums,
            browser_or_item.audio_effects,
            browser_or_item.midi_effects,
        ]
        for category in categories:
            _populate_browser_cache(category, cache, max_depth, current_depth + 1)
        return

    # Recurse into children
    if hasattr(browser_or_item, "children") and browser_or_item.children:
        for child in browser_or_item.children:
            _populate_browser_cache(child, cache, max_depth, current_depth + 1)


@CommandRegistry.register
class GetBrowserTreeCommand(Command):
    """Get a hierarchical tree of browser categories."""

    command_type = "get_browser_tree"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        category_type = params.get("category_type", "all")
        app = context.application

        if not app:
            raise RuntimeError("Could not access Live application")

        if not hasattr(app, "browser") or app.browser is None:
            raise RuntimeError("Browser is not available in the Live application")

        # Log available browser attributes to help diagnose issues
        browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith("_")]
        context.log(f"Available browser attributes: {browser_attrs}")

        result = {
            "type": category_type,
            "categories": [],
            "available_categories": browser_attrs,
            "failed_categories": [],
        }

        def process_item(item: Any) -> Optional[Dict[str, Any]]:
            if not item:
                return None

            return {
                "name": item.name if hasattr(item, "name") else "Unknown",
                "is_folder": hasattr(item, "children") and bool(item.children),
                "is_device": hasattr(item, "is_device") and item.is_device,
                "is_loadable": hasattr(item, "is_loadable") and item.is_loadable,
                "uri": item.uri if hasattr(item, "uri") else None,
                "children": [],
            }

        # Process based on category type
        category_map = {
            "instruments": ("Instruments", "instruments"),
            "sounds": ("Sounds", "sounds"),
            "drums": ("Drums", "drums"),
            "audio_effects": ("Audio Effects", "audio_effects"),
            "midi_effects": ("MIDI Effects", "midi_effects"),
        }

        categories_to_process = (
            category_map.items()
            if category_type == "all"
            else [(category_type, category_map.get(category_type, (category_type.capitalize(), category_type)))]
        )

        for _cat_key, (display_name, attr_name) in categories_to_process:
            if hasattr(app.browser, attr_name):
                try:
                    category_item = getattr(app.browser, attr_name)
                    category = process_item(category_item)
                    if category:
                        category["name"] = display_name
                        result["categories"].append(category)
                except Exception as e:
                    context.log(f"Error processing {attr_name}: {e}")
                    result["failed_categories"].append(attr_name)

        context.log(
            f"Browser tree generated for {category_type} with "
            f"{len(result['categories'])} root categories"
        )

        if result["failed_categories"]:
            result["warning"] = f"Some categories failed to load: {', '.join(result['failed_categories'])}"

        return result


@CommandRegistry.register
class GetBrowserItemsAtPathCommand(Command):
    """Get browser items at a specific path."""

    command_type = "get_browser_items_at_path"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        path = params.get("path", "")
        app = context.application

        if not app:
            raise RuntimeError("Could not access Live application")

        if not hasattr(app, "browser") or app.browser is None:
            raise RuntimeError("Browser is not available in the Live application")

        browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith("_")]

        # Parse the path
        path_parts = path.split("/")
        if not path_parts:
            raise ValueError("Invalid path")

        # Determine the root category
        root_category = path_parts[0].lower()
        current_item = None

        # Check standard categories
        category_attrs = {
            "instruments": "instruments",
            "sounds": "sounds",
            "drums": "drums",
            "audio_effects": "audio_effects",
            "midi_effects": "midi_effects",
        }

        if root_category in category_attrs:
            attr_name = category_attrs[root_category]
            if hasattr(app.browser, attr_name):
                current_item = getattr(app.browser, attr_name)
        else:
            # Try to find the category in other browser attributes
            for attr in browser_attrs:
                if attr.lower() == root_category:
                    try:
                        current_item = getattr(app.browser, attr)
                        break
                    except Exception as e:
                        context.log(f"Error accessing browser attribute {attr}: {e}")

        if current_item is None:
            return {
                "path": path,
                "error": f"Unknown or unavailable category: {root_category}",
                "available_categories": browser_attrs,
                "items": [],
            }

        # Navigate through the path
        for i in range(1, len(path_parts)):
            part = path_parts[i]
            if not part:  # Skip empty parts
                continue

            if not hasattr(current_item, "children"):
                return {
                    "path": path,
                    "error": f"Item at '{'/'.join(path_parts[:i])}' has no children",
                    "items": [],
                }

            found = False
            for child in current_item.children:
                if hasattr(child, "name") and child.name.lower() == part.lower():
                    current_item = child
                    found = True
                    break

            if not found:
                return {
                    "path": path,
                    "error": f"Path part '{part}' not found",
                    "items": [],
                }

        # Get items at the current path
        items = []
        if hasattr(current_item, "children"):
            for child in current_item.children:
                item_info = {
                    "name": child.name if hasattr(child, "name") else "Unknown",
                    "is_folder": hasattr(child, "children") and bool(child.children),
                    "is_device": hasattr(child, "is_device") and child.is_device,
                    "is_loadable": hasattr(child, "is_loadable") and child.is_loadable,
                    "uri": child.uri if hasattr(child, "uri") else None,
                }
                items.append(item_info)

        result = {
            "path": path,
            "name": current_item.name if hasattr(current_item, "name") else "Unknown",
            "uri": current_item.uri if hasattr(current_item, "uri") else None,
            "is_folder": hasattr(current_item, "children") and bool(current_item.children),
            "is_device": hasattr(current_item, "is_device") and current_item.is_device,
            "is_loadable": hasattr(current_item, "is_loadable") and current_item.is_loadable,
            "items": items,
        }

        context.log(f"Retrieved {len(items)} items at path: {path}")
        return result


@CommandRegistry.register
class GetBrowserItemCommand(Command):
    """Get a browser item by URI or path."""

    command_type = "get_browser_item"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        path = params.get("path")
        app = context.application

        if not app:
            raise RuntimeError("Could not access Live application")

        result = {
            "uri": uri,
            "path": path,
            "found": False,
        }

        # Try to find by URI first if provided
        if uri:
            item = _find_browser_item_by_uri(
                app.browser, uri, context.browser_uri_cache
            )
            if item:
                result["found"] = True
                result["item"] = {
                    "name": item.name,
                    "is_folder": item.is_folder,
                    "is_device": item.is_device,
                    "is_loadable": item.is_loadable,
                    "uri": item.uri,
                }
                return result

        # If URI not provided or not found, try by path
        if path:
            path_parts = path.split("/")

            # Determine the root based on the first part
            current_item = None
            first_part = path_parts[0].lower()

            if first_part == "instruments":
                current_item = app.browser.instruments
            elif first_part == "sounds":
                current_item = app.browser.sounds
            elif first_part == "drums":
                current_item = app.browser.drums
            elif first_part == "audio_effects":
                current_item = app.browser.audio_effects
            elif first_part == "midi_effects":
                current_item = app.browser.midi_effects
            else:
                # Default to instruments if not specified
                current_item = app.browser.instruments
                path_parts = ["instruments"] + path_parts

            # Navigate through the path
            for i in range(1, len(path_parts)):
                part = path_parts[i]
                if not part:
                    continue

                found = False
                for child in current_item.children:
                    if child.name.lower() == part.lower():
                        current_item = child
                        found = True
                        break

                if not found:
                    result["error"] = f"Path part '{part}' not found"
                    return result

            # Found the item
            result["found"] = True
            result["item"] = {
                "name": current_item.name,
                "is_folder": current_item.is_folder,
                "is_device": current_item.is_device,
                "is_loadable": current_item.is_loadable,
                "uri": current_item.uri,
            }

        return result


@CommandRegistry.register
class GetBrowserCategoriesCommand(Command):
    """Get available browser categories."""

    command_type = "get_browser_categories"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        category_type = params.get("category_type", "all")
        app = context.application

        if not app:
            raise RuntimeError("Could not access Live application")

        browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith("_")]

        return {
            "category_type": category_type,
            "available_categories": browser_attrs,
        }


@CommandRegistry.register
class GetBrowserItemsCommand(Command):
    """Get browser items at a path with optional filtering."""

    command_type = "get_browser_items"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        path = params.get("path", "")
        # Note: item_type filtering not yet implemented, delegates to path-based command

        # Delegate to GetBrowserItemsAtPathCommand
        items_cmd = GetBrowserItemsAtPathCommand()
        return items_cmd.execute(context, {"path": path})


@CommandRegistry.register
class LoadBrowserItemCommand(ModifyingCommand):
    """Load a browser item onto a track by its URI."""

    command_type = "load_browser_item"

    def execute(self, context: CommandContext, params: Dict[str, Any]) -> Dict[str, Any]:
        song = context.song
        app = context.application
        track_index = params.get("track_index", 0)
        item_uri = params.get("item_uri", "")

        if track_index < 0 or track_index >= len(song.tracks):
            raise IndexError("Track index out of range")

        track = song.tracks[track_index]

        # Find the browser item by URI
        item = _find_browser_item_by_uri(
            app.browser, item_uri, context.browser_uri_cache
        )

        if not item:
            raise ValueError(f"Browser item with URI '{item_uri}' not found")

        # Select the track
        song.view.selected_track = track

        # Load the item
        app.browser.load_item(item)

        return {
            "loaded": True,
            "item_name": item.name,
            "track_name": track.name,
            "uri": item_uri,
        }
