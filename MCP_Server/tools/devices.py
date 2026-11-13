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
        """Call any Live Object Model method by dotted path, e.g. 'undo'. Pass an object as an argument with {"$path": "tracks.12.arrangement_clips.0"}.
        MIDI: 'tracks.17.create_midi_clip' [start_beats, length] makes an arrangement clip; '<clip>.get_notes_extended' [0, 128, 0, length] returns notes as dicts;
        '<clip>.add_new_notes' [{"$notes": [{"pitch": 36, "start_time": 0.5, "duration": 0.45, "velocity": 100, "probability": 1.0}]}] writes them;
        '<clip>.remove_notes_extended' [0, 128, 0, length] clears them. A new MIDI track auto-arms when selected: disarm it, or it monitors input instead of playing."""
        try:
            result = get_ableton_connection().send_command("lom_call", {"path": path, "args": args or []})
            return json.dumps(result, indent=2)
        except Exception as e:
            logger.error(f"Error in lom_call: {str(e)}")
            return f"Error in lom_call: {str(e)}"

    @mcp.tool()
    def lom_set_param(ctx: Context, path: str, value: Any, param: str = "") -> str:
        """Set a device parameter by the value Live shows, in one call: value "1.80 s", "830 Hz", "-18 dB", "40 %", "On" or "Ping Pong" (a number is taken as raw). path is the device ('return_tracks.0.devices.0') with param its name ('Decay Time'), or a parameter path ('tracks.3.mixer_device.volume')."""
        try:
            body = {"path": path, "value": value, **({"param": param} if param else {})}
            return json.dumps(get_ableton_connection().send_command("lom_set_param", body), indent=2)
        except Exception as e:
            logger.error(f"Error in lom_set_param: {str(e)}")
            return f"Error in lom_set_param: {str(e)}"

    @mcp.tool()
    def lom_batch(ctx: Context, ops: list[dict[str, Any]], continue_on_error: bool = False) -> str:
        """Run many operations in one round trip. Each op is {"op": "get"|"set"|"call"|"set_param"|"simpler_region", ...the same fields as that tool}. Stops at the first error unless continue_on_error."""
        try:
            body = {"ops": ops, "continue_on_error": continue_on_error}
            return json.dumps(get_ableton_connection().send_command("lom_batch", body), indent=2)
        except Exception as e:
            logger.error(f"Error in lom_batch: {str(e)}")
            return f"Error in lom_batch: {str(e)}"

    @mcp.tool()
    def browser_find(ctx: Context, name: str = "", contains: str = "", roots: list[str] | None = None, limit: int = 10) -> str:
        """Find Live browser items by exact name ("Serum 2") or substring, searched inside Live in one call. roots: plugins, audio_effects, instruments, midi_effects, user_folders, packs. Load a match with lom_call('app.browser.load_item', [{"$path": path}]) after selecting the track."""
        try:
            body = {"name": name, "contains": contains, "limit": limit, **({"roots": roots} if roots else {})}
            return json.dumps(get_ableton_connection().send_command("browser_find", body), indent=2)
        except Exception as e:
            logger.error(f"Error in browser_find: {str(e)}")
            return f"Error in browser_find: {str(e)}"

    @mcp.tool()
    def simpler_region(ctx: Context, path: str, start_ms: float | None = None, end_ms: float | None = None,
                       warp: bool | None = None, mode: str = "", fade_in: str = "", fade_out: str = "",
                       trigger: str = "") -> str:
        """Set what a Simpler shows, by path ('tracks.6.devices.0'): the visible start/end markers in ms (Fade Out acts at the end marker; S Start/S Length are reset so nothing is shortened twice), warp on/off, mode 'classic'|'one-shot'|'slicing', fade_in/fade_out like '80 ms', trigger 'Trigger'|'Gate'. Returns what it now shows."""
        try:
            body: dict[str, Any] = {"path": path}
            for k, v in (("start_ms", start_ms), ("end_ms", end_ms), ("warp", warp)):
                if v is not None:
                    body[k] = v
            for k, v in (("mode", mode), ("fade_in", fade_in), ("fade_out", fade_out), ("trigger", trigger)):
                if v:
                    body[k] = v
            return json.dumps(get_ableton_connection().send_command("simpler_region", body), indent=2)
        except Exception as e:
            logger.error(f"Error in simpler_region: {str(e)}")
            return f"Error in simpler_region: {str(e)}"
