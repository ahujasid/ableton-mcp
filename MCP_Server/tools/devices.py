"""Device tools: get/set device parameters."""

import json
import logging
from typing import Any, Callable

from mcp.server.fastmcp import Context

logger = logging.getLogger("AbletonMCPServer")


def register(mcp: Any, get_ableton_connection: Callable[[], Any]) -> None:
    @mcp.tool()
    def get_device_parameters(
        ctx: Context,
        track_index: int,
        device_index: int,
        track_type: str = "track",
    ) -> str:
        """Get all parameters for a device. Parameters: track_index, device_index, track_type ('track'|'return'|'master')."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_device_parameters", {
                "track_index": track_index,
                "device_index": device_index,
                "track_type": track_type,
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting device parameters: {str(e)}")
            return f"Error getting device parameters: {str(e)}"

    @mcp.tool()
    def set_device_parameter(
        ctx: Context,
        track_index: int,
        device_index: int,
        parameter_index: int,
        value: float,
        track_type: str = "track",
    ) -> str:
        """Set a device parameter. Parameters: track_index, device_index, parameter_index, value (0.0-1.0), track_type."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "value": value,
                "track_type": track_type,
            })
            return f"Set device {device_index} parameter {parameter_index} to {value}"
        except Exception as e:
            logger.error(f"Error setting device parameter: {str(e)}")
            return f"Error setting device parameter: {str(e)}"

    @mcp.tool()
    def get_rack_device_info(
        ctx: Context,
        track_index: int,
        device_index: int,
        track_type: str = "track",
    ) -> str:
        """Get detailed information about a rack device's chains and nested devices.
        Recursively serializes all chains and devices. Parameters: track_index,
        device_index (the rack), track_type ('track'|'return'|'master')."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_rack_device_info", {
                "track_index": track_index,
                "device_index": device_index,
                "track_type": track_type,
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting rack device info: {str(e)}")
            return "Error getting rack device info"

    @mcp.tool()
    def get_chain_devices(
        ctx: Context,
        track_index: int,
        device_index: int,
        chain_index: int = 0,
        track_type: str = "track",
    ) -> str:
        """List all devices inside a rack's chain. Parameters: track_index, device_index (the rack), chain_index (default 0), track_type."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_chain_devices", {
                "track_index": track_index,
                "device_index": device_index,
                "chain_index": chain_index,
                "track_type": track_type,
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting chain devices: {str(e)}")
            return f"Error getting chain devices: {str(e)}"

    @mcp.tool()
    def get_chain_device_parameters(
        ctx: Context,
        track_index: int,
        device_index: int,
        chain_index: int,
        chain_device_index: int,
        track_type: str = "track",
    ) -> str:
        """Get all parameters for a device inside a rack's chain. Parameters: track_index, device_index (the rack), chain_index, chain_device_index, track_type."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("get_chain_device_parameters", {
                "track_index": track_index,
                "device_index": device_index,
                "chain_index": chain_index,
                "chain_device_index": chain_device_index,
                "track_type": track_type,
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error getting chain device parameters: {str(e)}")
            return f"Error getting chain device parameters: {str(e)}"

    @mcp.tool()
    def set_chain_device_parameter(
        ctx: Context,
        track_index: int,
        device_index: int,
        chain_index: int,
        chain_device_index: int,
        parameter_index: int,
        value: float,
        track_type: str = "track",
    ) -> str:
        """Set a parameter on a device inside a rack's chain. Parameters: track_index, device_index (the rack), chain_index, chain_device_index, parameter_index, value, track_type."""
        try:
            ableton = get_ableton_connection()
            ableton.send_command("set_chain_device_parameter", {
                "track_index": track_index,
                "device_index": device_index,
                "chain_index": chain_index,
                "chain_device_index": chain_device_index,
                "parameter_index": parameter_index,
                "value": value,
                "track_type": track_type,
            })
            return f"Set chain device {chain_device_index} parameter {parameter_index} to {value}"
        except Exception as e:
            logger.error(f"Error setting chain device parameter: {str(e)}")
            return f"Error setting chain device parameter: {str(e)}"

    @mcp.tool()
    def delete_device(
        ctx: Context,
        track_index: int,
        device_index: int,
        track_type: str = "track",
    ) -> str:
        """Delete a device from a track. Parameters: track_index, device_index, track_type."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("delete_device", {
                "track_index": track_index,
                "device_index": device_index,
                "track_type": track_type,
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error deleting device: {str(e)}")
            return f"Error deleting device: {str(e)}"

    @mcp.tool()
    def delete_chain_device(
        ctx: Context,
        track_index: int,
        device_index: int,
        chain_index: int,
        chain_device_index: int,
        track_type: str = "track",
    ) -> str:
        """Delete a device from inside a rack's chain. Parameters: track_index, device_index (the rack), chain_index, chain_device_index, track_type."""
        try:
            ableton = get_ableton_connection()
            result = ableton.send_command("delete_chain_device", {
                "track_index": track_index,
                "device_index": device_index,
                "chain_index": chain_index,
                "chain_device_index": chain_device_index,
                "track_type": track_type,
            })
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error deleting chain device: {str(e)}")
            return f"Error deleting chain device: {str(e)}"

    @mcp.tool()
    def lom_get(ctx: Context, path: str, list_attrs: bool = False) -> str:
        """Read anything in Live's Object Model by dotted path, e.g. 'tracks.12.fold_state' or 'tracks.14.devices.0.voices'. Starts at the Song ('app' starts at the Application). Use list_attrs=True to see what an object offers. Use this when no dedicated tool covers a setting."""
        try:
            result = get_ableton_connection().send_command("lom_get", {"path": path, "list_attrs": list_attrs})
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error in lom_get: {str(e)}")
            return f"Error in lom_get: {str(e)}"

    @mcp.tool()
    def lom_set(ctx: Context, path: str, value: Any = None, value_path: str = "") -> str:
        """Set any writable Live Object Model property by dotted path, e.g. 'tracks.12.fold_state' to 0 to open a group, or 'tracks.14.devices.0.voices' to 1 for a mono Simpler. To assign an object, give its path as value_path, e.g. 'view.selected_track' with value_path 'tracks.21'."""
        try:
            params = {"path": path, "value_path": value_path} if value_path else {"path": path, "value": value}
            result = get_ableton_connection().send_command("lom_set", params)
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error in lom_set: {str(e)}")
            return f"Error in lom_set: {str(e)}"

    @mcp.tool()
    def lom_call(ctx: Context, path: str, args: list[Any] | None = None) -> str:
        """Call any Live Object Model method by dotted path, e.g. 'undo'."""
        try:
            result = get_ableton_connection().send_command("lom_call", {"path": path, "args": args or []})
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error in lom_call: {str(e)}")
            return f"Error in lom_call: {str(e)}"
