"""Device and parameter control tools for AbletonMCP"""
import json
import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: FastMCP, get_connection, cache):
    """Register device tools with the MCP server"""

    @mcp.tool()
    async def get_device_parameters(track_index: int, device_index: int) -> str:
        """Get all parameters of a device on a track.

        Returns a list of parameter dictionaries, each containing name, value,
        min, max, and is_quantized fields. Useful for discovering available
        parameters before setting them.

        Args:
            track_index: Zero-based index of the track containing the device.
            device_index: Zero-based index of the device on the track.
        """
        try:
            cache_key = f"device_params_{track_index}_{device_index}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command(
                "get_device_parameters",
                {"track_index": track_index, "device_index": device_index},
            )
            response = json.dumps(result, indent=2)
            cache.set(cache_key, response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting device parameters for track {track_index}, device {device_index}: {e}")
            return f"Error getting device parameters for track {track_index}, device {device_index}: {e}"

    @mcp.tool()
    async def set_device_parameter(track_index: int, device_index: int, parameter_index: int, value: float) -> str:
        """Set a specific device parameter by its index.

        Use get_device_parameters first to discover available parameters and
        their valid ranges (min/max).

        Args:
            track_index: Zero-based index of the track containing the device.
            device_index: Zero-based index of the device on the track.
            parameter_index: Zero-based index of the parameter to set.
            value: The new value for the parameter. Must be within the
                parameter's min/max range.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command(
                "set_device_parameter",
                {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_index": parameter_index,
                    "value": value,
                },
            )
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting device parameter for track {track_index}, device {device_index}, param {parameter_index}: {e}")
            return f"Error setting device parameter for track {track_index}, device {device_index}, param {parameter_index}: {e}"

    @mcp.tool()
    async def set_device_parameter_by_name(track_index: int, device_index: int, parameter_name: str, value: float) -> str:
        """Set a device parameter by its name instead of index.

        More user-friendly than set_device_parameter since you can reference
        parameters by name (e.g. "Filter Freq", "Resonance"). Use
        get_device_parameters to discover available parameter names.

        Args:
            track_index: Zero-based index of the track containing the device.
            device_index: Zero-based index of the device on the track.
            parameter_name: The exact name of the parameter to set.
            value: The new value for the parameter. Must be within the
                parameter's min/max range.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command(
                "set_device_parameter_by_name",
                {
                    "track_index": track_index,
                    "device_index": device_index,
                    "parameter_name": parameter_name,
                    "value": value,
                },
            )
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error setting parameter '{parameter_name}' for track {track_index}, device {device_index}: {e}")
            return f"Error setting parameter '{parameter_name}' for track {track_index}, device {device_index}: {e}"

    @mcp.tool()
    async def toggle_device(track_index: int, device_index: int) -> str:
        """Toggle a device on or off.

        Flips the enabled/disabled state of the device. If the device is
        currently active it will be bypassed, and vice versa.

        Args:
            track_index: Zero-based index of the track containing the device.
            device_index: Zero-based index of the device on the track.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command(
                "toggle_device",
                {"track_index": track_index, "device_index": device_index},
            )
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error toggling device for track {track_index}, device {device_index}: {e}")
            return f"Error toggling device for track {track_index}, device {device_index}: {e}"

    @mcp.tool()
    async def get_device_info(track_index: int, device_index: int) -> str:
        """Get detailed information about a specific device.

        Returns the device's name, class name, type, enabled state, and
        parameter count. Useful for identifying what a device is before
        querying or modifying its parameters.

        Args:
            track_index: Zero-based index of the track containing the device.
            device_index: Zero-based index of the device on the track.
        """
        try:
            cache_key = f"device_info_{track_index}_{device_index}"
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            conn = await get_connection()
            result = await conn.send_command(
                "get_device_info",
                {"track_index": track_index, "device_index": device_index},
            )
            response = json.dumps(result, indent=2)
            cache.set(cache_key, response, ttl=2)
            return response
        except Exception as e:
            logger.error(f"Error getting device info for track {track_index}, device {device_index}: {e}")
            return f"Error getting device info for track {track_index}, device {device_index}: {e}"

    @mcp.tool()
    async def delete_device(track_index: int, device_index: int) -> str:
        """Delete a device from a track.

        Permanently removes the device at the given index from the track's
        device chain. This action cannot be undone via MCP (use Ableton's
        undo if needed).

        Args:
            track_index: Zero-based index of the track containing the device.
            device_index: Zero-based index of the device to remove.
        """
        try:
            conn = await get_connection()
            result = await conn.send_command(
                "delete_device",
                {"track_index": track_index, "device_index": device_index},
            )
            cache.invalidate_all()
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error deleting device from track {track_index}, device {device_index}: {e}")
            return f"Error deleting device from track {track_index}, device {device_index}: {e}"
