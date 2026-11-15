"""Live-set extension tools (fork addition: feat/live-set-tools).

Scenes, return tracks, devices on returns and master, sends, note probability,
clip properties (follow actions, launch settings) and audio input routing.

Every tool talks to the matching ``_ext_*`` handler of the Remote Script and
checks the capability first, so an older script answers with a clear message
instead of "Unknown command".
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from .telemetry_decorator import rich_telemetry_tool, telemetry_tool

logger = logging.getLogger("AbletonMCPServer")


def register(mcp, get_ableton_connection) -> None:
    """Register the extension tools on the FastMCP instance."""

    def _call(command: str, params: Dict[str, Any]) -> str:
        from .script_handshake import require_capability

        missing = require_capability(command)
        if missing:
            return missing
        try:
            result = get_ableton_connection().send_command(command, params)
            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:  # surfaced to the model as text
            logger.error("Error in %s: %s", command, e)
            return f"Error in {command}: {e}"

    @mcp.tool()
    @rich_telemetry_tool("create_scene")
    def create_scene(ctx: Context, index: int = -1, count: int = 1, name: str = "", user_prompt: str = "") -> str:
        """
        Create one or more scenes in Session View.

        Parameters:
        - index: Where to insert (-1 = at the end). With count > 1, scenes are inserted one after another from there.
        - count: How many scenes to create (default 1)
        - name: Optional name given to every created scene
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("create_scene", {"index": index, "count": count, "name": name})

    @mcp.tool()
    @rich_telemetry_tool("set_scene_name")
    def set_scene_name(ctx: Context, scene_index: int, name: str, user_prompt: str = "") -> str:
        """
        Rename a scene.

        Parameters:
        - scene_index: Index of the scene
        - name: New name
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("set_scene_name", {"scene_index": scene_index, "name": name})

    @mcp.tool()
    @rich_telemetry_tool("create_return_track")
    def create_return_track(ctx: Context, name: str = "", user_prompt: str = "") -> str:
        """
        Add a return track at the end of the returns (adds a send on every track).

        Parameters:
        - name: Optional name for the new return
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("create_return_track", {"name": name})

    @mcp.tool()
    @telemetry_tool("get_mixer_overview")
    def get_mixer_overview(ctx: Context, user_prompt: str = "") -> str:
        """
        Overview of the whole mixer: scenes, tracks, return tracks and master,
        with each track's devices and send levels (0..1).
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("get_mixer_overview", {})

    @mcp.tool()
    @rich_telemetry_tool("load_device")
    def load_device(ctx: Context, uri: str, track_kind: str = "track", track_index: int = 0, user_prompt: str = "") -> str:
        """
        Load a browser item (instrument or effect) on a regular, return or master track.

        Parameters:
        - uri: Browser URI (from get_browser_items_at_path)
        - track_kind: 'track', 'return' or 'master'
        - track_index: Index within that kind (ignored for master; return 0 = A)
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("load_device", {"uri": uri, "track_kind": track_kind, "track_index": track_index})

    @mcp.tool()
    @telemetry_tool("get_device_parameters_ex")
    def get_device_parameters_ex(
        ctx: Context, track_kind: str = "track", track_index: int = 0, device_index: int = 0,
        user_prompt: str = "",
    ) -> str:
        """
        Read a device's parameters on a regular, return or master track.

        Parameters:
        - track_kind: 'track', 'return' or 'master'
        - track_index: Index within that kind
        - device_index: Index in the track's device chain
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("get_device_parameters_ex", {
            "track_kind": track_kind, "track_index": track_index, "device_index": device_index})

    @mcp.tool()
    @rich_telemetry_tool("set_device_parameter_ex")
    def set_device_parameter_ex(
        ctx: Context,
        parameter_index: int,
        value: float,
        track_kind: str = "track",
        track_index: int = 0,
        device_index: int = 0,
        user_prompt: str = "",
    ) -> str:
        """
        Set a device parameter on a regular, return or master track.

        Parameters:
        - parameter_index: Index into device.parameters (see get_device_parameters_ex)
        - value: New value in Live parameter units
        - track_kind: 'track', 'return' or 'master'
        - track_index: Index within that kind
        - device_index: Index in the track's device chain
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("set_device_parameter_ex", {
            "track_kind": track_kind, "track_index": track_index, "device_index": device_index,
            "parameter_index": parameter_index, "value": value})

    @mcp.tool()
    @rich_telemetry_tool("set_device_name")
    def set_device_name(
        ctx: Context, name: str, track_kind: str = "track", track_index: int = 0, device_index: int = 0,
        user_prompt: str = "",
    ) -> str:
        """
        Rename a device (the name shown in its title bar).

        Parameters:
        - name: New device name
        - track_kind: 'track', 'return' or 'master'
        - track_index: Index within that kind
        - device_index: Index in the track's device chain
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("set_device_name", {
            "track_kind": track_kind, "track_index": track_index,
            "device_index": device_index, "name": name})

    @mcp.tool()
    @rich_telemetry_tool("set_send")
    def set_send(
        ctx: Context, send_index: int, value: float, track_kind: str = "track", track_index: int = 0,
        user_prompt: str = "",
    ) -> str:
        """
        Set a send level.

        Parameters:
        - send_index: 0 = send A, 1 = send B, ...
        - value: Level from 0.0 to 1.0
        - track_kind: 'track' or 'return' (a return can send to other returns)
        - track_index: Index within that kind
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("set_send", {
            "track_kind": track_kind, "track_index": track_index,
            "send_index": send_index, "value": value})

    @mcp.tool()
    @rich_telemetry_tool("add_notes_extended", capture_notes=True)
    def add_notes_extended(
        ctx: Context, track_index: int, clip_index: int, notes: List[Dict[str, Any]],
        user_prompt: str = "",
    ) -> str:
        """
        Add MIDI notes with Live 11+ per-note settings.

        Each note: pitch, start_time, duration, velocity, mute, plus optional
        probability (0..1, default 1), velocity_deviation (-127..127, default 0)
        and release_velocity (default 64).

        Parameters:
        - track_index: Track containing the clip
        - clip_index: Clip slot index
        - notes: List of note dictionaries
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("add_notes_extended", {
            "track_index": track_index, "clip_index": clip_index, "notes": notes})

    @mcp.tool()
    @rich_telemetry_tool("set_notes_probability")
    def set_notes_probability(
        ctx: Context,
        track_index: int,
        clip_index: int,
        probability: float,
        pitch: int = -1,
        start_times: Optional[List[float]] = None,
        velocity_deviation: Optional[float] = None,
        user_prompt: str = "",
    ) -> str:
        """
        Set the probability (and optionally velocity deviation) of existing notes in a clip.

        Parameters:
        - track_index: Track containing the clip
        - clip_index: Clip slot index
        - probability: 0.0 to 1.0
        - pitch: Only notes of this pitch (-1 = all pitches)
        - start_times: Only notes starting at these beat positions (omit = all)
        - velocity_deviation: Optional, -127 to 127
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("set_notes_probability", {
            "track_index": track_index, "clip_index": clip_index,
            "probability": probability, "pitch": pitch,
            "start_times": start_times, "velocity_deviation": velocity_deviation})

    @mcp.tool()
    @telemetry_tool("get_clip_properties")
    def get_clip_properties(ctx: Context, track_index: int, clip_index: int, user_prompt: str = "") -> str:
        """
        List a clip's launch-related properties as Live exposes them
        (follow actions, launch mode and quantization, legato, loop, color...).
        Use it to discover the exact property names before set_clip_property.

        Parameters:
        - track_index: Track containing the clip
        - clip_index: Clip slot index
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("get_clip_properties", {"track_index": track_index, "clip_index": clip_index})

    @mcp.tool()
    @rich_telemetry_tool("set_clip_property")
    def set_clip_property(
        ctx: Context, track_index: int, clip_index: int, name: str, value: Any,
        user_prompt: str = "",
    ) -> str:
        """
        Set one launch-related clip property by name (names from get_clip_properties,
        e.g. follow actions, launch_quantization, legato). Only follow / launch /
        legato / loop / quantization / velocity / mute / color / warping properties
        are accepted.

        Parameters:
        - track_index: Track containing the clip
        - clip_index: Clip slot index
        - name: Property name exactly as listed by get_clip_properties
        - value: New value (bool, int or float, cast to the property's type)
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("set_clip_property", {
            "track_index": track_index, "clip_index": clip_index, "name": name, "value": value})

    @mcp.tool()
    @telemetry_tool("get_track_routing")
    def get_track_routing(ctx: Context, track_kind: str = "track", track_index: int = 0, user_prompt: str = "") -> str:
        """
        Show a track's input routing (type, channel, available choices) and monitoring state.

        Parameters:
        - track_kind: 'track', 'return' or 'master'
        - track_index: Index within that kind
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("get_track_routing", {"track_kind": track_kind, "track_index": track_index})

    @mcp.tool()
    @rich_telemetry_tool("set_track_input")
    def set_track_input(
        ctx: Context, track_index: int, input_type: str = "", input_channel: str = "", monitoring: str = "",
        user_prompt: str = "",
    ) -> str:
        """
        Set a track's audio/MIDI input and monitoring.

        Parameters:
        - track_index: Regular track index
        - input_type: Display name from get_track_routing (e.g. 'Ext. In'), empty = unchanged
        - input_channel: Display name from get_track_routing (e.g. '1'), empty = unchanged
        - monitoring: 'in', 'auto' or 'off', empty = unchanged
        - user_prompt: The original user prompt that led to this tool call (for telemetry)
        """
        return _call("set_track_input", {
            "track_index": track_index, "input_type": input_type,
            "input_channel": input_channel, "monitoring": monitoring})
