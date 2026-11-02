"""Tools for the Remote Script's extended commands (undo, track deletion, and
later mixer, routing, monitoring and meters).

Kept out of server.py so the upstream file only gains one register() call.
Every tool returns the Remote Script's result as JSON on success and a string
starting with "Error" on failure, like the upstream tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP

from . import safety, script_handshake
from .telemetry_decorator import telemetry_tool

logger = logging.getLogger("AbletonMCPServer")

# Extended commands that change the set; the connection gives them the longer
# modifying-command socket timeout.
MODIFYING_COMMANDS = frozenset({
    "undo", "redo", "delete_track",
    "set_track_routing", "set_track_monitoring", "set_track_mixer",
    "back_to_arrangement", "re_enable_automation",
    "set_device_parameter_value", "set_device_active", "set_device_routing", "delete_device",
    "move_device", "set_clip_properties", "duplicate_track", "create_return_track", "create_scene",
    "duplicate_scene", "delete_scene", "set_scene", "fire_scene", "set_track_look",
    "set_song_settings", "jump_to_cue", "stop_all_clips", "capture_midi", "modify_notes", "remove_notes",
    "edit_clip",
})

def _call(get_connection: Callable[[], Any], command: str, params: dict | None, label: str) -> str:
    try:
        missing = script_handshake.require_capability(command)
        if missing:
            return missing
        result = get_connection().send_command(command, params or {})
        return json.dumps(result, indent=2)
    except Exception as e:  # noqa: BLE001 - reported to the agent as text
        logger.error("Error %s: %s", label, e)
        return f"Error {label}: {e}"


def register(mcp: FastMCP, get_connection: Callable[[], Any]) -> None:
    """Add the extended tools to the server."""

    @mcp.tool()
    @telemetry_tool("get_undo_state")
    def get_undo_state(ctx: Context, user_prompt: str = "") -> str:
        """Report whether Live's undo history has a step to undo or redo.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_undo_state", {}, "getting undo state")

    @mcp.tool()
    @telemetry_tool("undo")
    def undo(ctx: Context, user_prompt: str = "") -> str:
        """Undo the most recent step in Live's undo history (same as Ctrl+Z).

        Live keeps one history for everything, so this undoes the last change
        whoever made it - possibly the user's own edit, not this agent's. Call it
        right after the step you mean to revert, and say what you are undoing.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "undo", {}, "undoing")

    @mcp.tool()
    @telemetry_tool("redo")
    def redo(ctx: Context, user_prompt: str = "") -> str:
        """Redo the most recently undone step (same as Ctrl+Shift+Z).

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "redo", {}, "redoing")

    @mcp.tool()
    @telemetry_tool("delete_track")
    def delete_track(
        ctx: Context,
        track_index: int,
        expected_name: str,
        track_type: str = "track",
        user_prompt: str = "",
    ) -> str:
        """Delete a track or return track. Undo (Ctrl+Z or the undo tool) restores it.

        expected_name must equal the track's current name exactly. Read it with
        get_session_info or get_track_info first; if the indices have shifted the
        delete is refused instead of removing the wrong track. The master track
        and a set's last remaining track cannot be deleted.

        Parameters:
        - track_index: index of the track to delete (0-based)
        - expected_name: the track's current name, as a safety check
        - track_type: 'track' (default) or 'return'
        - user_prompt: leave empty
        """
        return _call(get_connection, "delete_track", {
            "track_index": track_index,
            "expected_name": expected_name,
            "track_type": track_type,
        }, "deleting track")

    # ------------------------------------------------------------------
    # Mixer, routing, monitoring, meters
    # ------------------------------------------------------------------

    @mcp.tool()
    @telemetry_tool("get_mixer_state")
    def get_mixer_state(ctx: Context, include_routing: bool = True, user_prompt: str = "") -> str:
        """Read the whole mixer in one call: every track, return track and the master.

        Per track: name, mute, solo, muted_via_solo (silenced because another
        track is soloed), arm and monitoring (In/Auto/Off), volume and pan
        (value plus Live's display text such as "-6.0 dB"), sends (with the
        return track's name), and Audio From / Audio To routing. Top level:
        soloed and silenced_by_solo name lists, back_to_arranger (Back to
        Arrangement is lit) and re_enable_automation_enabled (some automation
        is overridden). A null field means Live gave no value for that track
        type; its reason is under "unavailable". Null never means off or zero.

        Parameters:
        - include_routing: include Audio From/To for each track (default true)
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_mixer_state", {"include_routing": include_routing},
                     "getting mixer state")

    @mcp.tool()
    @telemetry_tool("get_track_routing")
    def get_track_routing(
        ctx: Context, track_index: int = 0, track_type: str = "track",
        include_available: bool = True, user_prompt: str = "",
    ) -> str:
        """Read a track's Audio/MIDI From and To (type and channel) and the choices Live offers.

        Example result: input_type "Ext. In", input_channel "3/4", output_type
        "Master", plus available_input_types etc. Use the exact choice names with
        set_track_routing.

        Parameters:
        - track_index: 0-based index within track_type
        - track_type: 'track' (default), 'return' or 'master'
        - include_available: also list the available choices (default true)
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_track_routing", {
            "track_index": track_index, "track_type": track_type,
            "include_available": include_available}, "getting track routing")

    @mcp.tool()
    @telemetry_tool("set_track_routing")
    def set_track_routing(
        ctx: Context, track_index: int = 0, track_type: str = "track",
        input_type: Optional[str] = None, input_channel: Optional[str] = None,
        output_type: Optional[str] = None, output_channel: Optional[str] = None,
        user_prompt: str = "",
    ) -> str:
        """Set a track's Audio From / Audio To by the names Live shows (e.g. input_type
        "Ext. In", input_channel "3/4", output_type "Ext. Out", output_channel "3").

        Give only the fields to change. Types are applied before channels. A name
        that is not on offer is refused with the list of valid choices; read them
        first with get_track_routing. Undo reverts it.

        Parameters:
        - track_index, track_type: which track ('track', 'return' or 'master')
        - input_type, input_channel, output_type, output_channel: choice names
        - user_prompt: leave empty
        """
        return _call(get_connection, "set_track_routing", {
            "track_index": track_index, "track_type": track_type,
            "input_type": input_type, "input_channel": input_channel,
            "output_type": output_type, "output_channel": output_channel}, "setting track routing")

    @mcp.tool()
    @telemetry_tool("set_track_monitoring")
    def set_track_monitoring(ctx: Context, track_index: int, state: str, user_prompt: str = "") -> str:
        """Set a track's Monitor switch: 'in', 'auto' or 'off'.

        Parameters:
        - track_index: 0-based regular track index
        - state: 'in', 'auto' or 'off'
        - user_prompt: leave empty
        """
        return _call(get_connection, "set_track_monitoring",
                     {"track_index": track_index, "state": state}, "setting monitoring")

    @mcp.tool()
    @telemetry_tool("set_track_mixer")
    def set_track_mixer(
        ctx: Context, track_index: int = 0, track_type: str = "track",
        volume: Optional[float] = None, volume_db: Optional[float] = None,
        panning: Optional[float] = None, sends: Optional[Dict[str, float]] = None,
        mute: Optional[bool] = None, solo: Optional[bool] = None, arm: Optional[bool] = None,
        exclusive_solo: bool = False, user_prompt: str = "",
    ) -> str:
        """Set a track's volume, pan, sends, mute, solo or arm. Give only what should change.

        - volume: raw fader value 0..1 (0.85 is 0 dB); or volume_db in dB, e.g. -6
          (found by asking Live which value displays as that many dB; max +6 dB)
        - panning: -1 (left) .. 1 (right)
        - sends: {"A": 0.5} or {"0": 0.5} or {"Reverb": 0.5}; values 0..1
        - solo: the API does not unsolo other tracks; pass exclusive_solo=true to
          unsolo every other track and return, like a normal click in Live
        Everything is validated before anything is written. The reply has before
        and after states. Undo reverts it.

        Parameters:
        - track_index, track_type: which track ('track', 'return' or 'master')
        - user_prompt: leave empty
        """
        return _call(get_connection, "set_track_mixer", {
            "track_index": track_index, "track_type": track_type, "volume": volume,
            "volume_db": volume_db, "panning": panning, "sends": sends or {},
            "mute": mute, "solo": solo, "arm": arm, "exclusive_solo": exclusive_solo,
        }, "setting track mixer")

    @mcp.tool()
    @telemetry_tool("get_track_meters")
    def get_track_meters(
        ctx: Context, tracks: Optional[List[Dict[str, Any]]] = None, duration_ms: int = 1000,
        interval_ms: int = 50, threshold: float = 0.001, user_prompt: str = "",
    ) -> str:
        """Watch input and output meters for a while and report each track's peaks.

        Answers "is signal leaving this track / arriving on that one". Playback
        or live input must be running for there to be anything to see.
        input_signal / output_signal are true when the peak passes threshold,
        false when it stays below, and null when Live has no meter of that kind
        for the track (unknown, not silent). Meter values are Live's 0..1 meter
        scale, not dB.

        Parameters:
        - tracks: e.g. [{"track_index": 2}, {"track_type": "return", "track_index": 0},
          {"track_type": "master"}]; omit for every track
        - duration_ms: how long to watch, up to 10000 (default 1000)
        - interval_ms: time between samples, at least 20 (default 50)
        - threshold: meter level counted as signal (default 0.001)
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_track_meters", {
            "tracks": tracks or [], "duration_ms": duration_ms,
            "interval_ms": interval_ms, "threshold": threshold}, "reading meters")

    @mcp.tool()
    @telemetry_tool("back_to_arrangement")
    def back_to_arrangement(ctx: Context, user_prompt: str = "") -> str:
        """Press Back to Arrangement: stop the Session clips that override the
        Arrangement so it plays again. Reports whether the button was lit.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "back_to_arrangement", {}, "going back to arrangement")

    @mcp.tool()
    @telemetry_tool("get_automation_overrides")
    def get_automation_overrides(ctx: Context, include_playing: bool = False, user_prompt: str = "") -> str:
        """List parameters whose automation you overrode by moving them by hand
        (the ones Re-Enable Automation would fix). Covers mixer volume, pan and
        sends and the top-level devices on every track, return and the master.

        Parameters:
        - include_playing: also list parameters whose automation is still playing
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_automation_overrides",
                     {"include_playing": include_playing}, "reading automation overrides")

    @mcp.tool()
    @telemetry_tool("re_enable_automation")
    def re_enable_automation(
        ctx: Context, track_index: Optional[int] = None, track_type: Optional[str] = None,
        user_prompt: str = "",
    ) -> str:
        """Re-enable overridden automation. With no track it presses Live's
        Re-Enable Automation button (whole set); with a track it re-enables
        only that track's mixer and device parameters.

        Parameters:
        - track_index, track_type: optional; limit to one track ('track', 'return', 'master')
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {}
        if track_index is not None or track_type is not None:
            params = {"track_index": track_index or 0, "track_type": track_type or "track"}
        return _call(get_connection, "re_enable_automation", params, "re-enabling automation")

    # ------------------------------------------------------------------
    # Safety switches (read-only view; only the user changes them)
    # ------------------------------------------------------------------

    @mcp.tool()
    @telemetry_tool("get_safety_config")
    def get_safety_config(ctx: Context, user_prompt: str = "") -> str:
        """Show which kinds of change the user currently allows: read_only, and
        the categories delete / playback / mixer / routing / structure / edit /
        undo, plus stricter rules for saved sets (real songs). A refused call
        names its category. There is no tool to change these switches: if one
        blocks what the user asked for, tell them; they change it with
        `ableton-mcp-safety <category> on|off` or by editing the file.

        Parameters:
        - user_prompt: leave empty
        """
        return json.dumps(safety.describe(), indent=2)

    # ------------------------------------------------------------------
    # Set, devices, signal path
    # ------------------------------------------------------------------

    @mcp.tool()
    @telemetry_tool("get_set_info")
    def get_set_info(ctx: Context, user_prompt: str = "") -> str:
        """Which Live set is open: its file path and name (empty for a new,
        unsaved set; is_saved tells them apart), track, return and scene counts,
        and tempo. Check it before changing anything.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_set_info", {}, "getting set info")

    @mcp.tool()
    @telemetry_tool("get_device_chain")
    def get_device_chain(
        ctx: Context, track_index: int = 0, track_type: str = "track", include_parameters: bool = True,
        max_parameters: int = 64, max_depth: int = 2, user_prompt: str = "",
    ) -> str:
        """Every device on a track in signal order: name, class, whether it is
        switched on, latency, sidechain routing, rack chains (down to max_depth),
        and each parameter with its raw value AND the text Live displays
        ("+15.0 dB", "50 %"), its range and automation state (none / active /
        overridden). Devices are addressed by path: "1" is the second device,
        "0/1/2" is device 2 in chain 1 of rack 0.

        Parameters:
        - track_index, track_type: 'track' (default), 'return' or 'master'
        - include_parameters: false for a quick list of devices only
        - max_parameters: per device (plugins can have hundreds)
        - max_depth: how many rack levels to open
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_device_chain",
                     {"track_index": track_index, "track_type": track_type,
                      "include_parameters": include_parameters, "max_parameters": max_parameters,
                      "max_depth": max_depth}, "reading device chain")

    @mcp.tool()
    @telemetry_tool("set_device_parameter_value")
    def set_device_parameter_value(
        ctx: Context, device: str, parameter: str, track_index: int = 0, track_type: str = "track",
        value: Optional[float] = None, display_value: Optional[str] = None,
        expected_device_name: Optional[str] = None, user_prompt: str = "",
    ) -> str:
        """Set one device parameter by name (or index) on any track, return or
        the master, either to a raw value or to what Live should display, e.g.
        display_value="+15 dB" on Utility's Gain or "On" for a switch. Returns
        before/after with display text. If the parameter is automated, the
        change overrides the automation and the result says so.

        Parameters:
        - device: device path, "0" or "0/1/2" for inside a rack (see get_device_chain)
        - parameter: name such as "Gain", or its index
        - value: raw value within min..max; or display_value: text such as "-6 dB"
        - expected_device_name: optional guard; refused if the device has another name
        - track_index, track_type: 'track', 'return' or 'master'
        - user_prompt: leave empty
        """
        return _call(get_connection, "set_device_parameter_value",
                     {"track_index": track_index, "track_type": track_type, "device": device,
                      "parameter": parameter, "value": value, "display_value": display_value,
                      "expected_device_name": expected_device_name}, "setting device parameter")

    @mcp.tool()
    @telemetry_tool("set_device_active")
    def set_device_active(
        ctx: Context, device: str, active: bool, track_index: int = 0, track_type: str = "track",
        user_prompt: str = "",
    ) -> str:
        """Switch a device on or off (its Device On button).

        Parameters:
        - device: device path, "0" or "0/1/2"
        - active: true = on, false = off (bypassed)
        - track_index, track_type: 'track', 'return' or 'master'
        - user_prompt: leave empty
        """
        return _call(get_connection, "set_device_active",
                     {"track_index": track_index, "track_type": track_type, "device": device,
                      "active": active}, "switching device")

    @mcp.tool()
    @telemetry_tool("get_device_routing")
    def get_device_routing(
        ctx: Context, device: str, track_index: int = 0, track_type: str = "track", user_prompt: str = "",
    ) -> str:
        """A device's sidechain input (Compressor, Gate, Auto Filter, ...): the
        current source type and channel and the choices. has_routing is false
        for devices without a sidechain.

        Parameters:
        - device: device path, "0" or "0/1/2"
        - track_index, track_type: 'track', 'return' or 'master'
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_device_routing",
                     {"track_index": track_index, "track_type": track_type, "device": device},
                     "reading device routing")

    @mcp.tool()
    @telemetry_tool("set_device_routing")
    def set_device_routing(
        ctx: Context, device: str, track_index: int = 0, track_type: str = "track",
        input_type: Optional[str] = None, input_channel: Optional[str] = None, user_prompt: str = "",
    ) -> str:
        """Set a device's sidechain source by the names Live shows (e.g.
        input_type="2-Kick", input_channel="Post FX"). A wrong name returns the
        valid choices. Turning the sidechain on is the device's own parameter
        (set_device_parameter_value, e.g. "S/C On").

        Parameters:
        - device: device path
        - input_type, input_channel: display names (see get_device_routing)
        - track_index, track_type: 'track', 'return' or 'master'
        - user_prompt: leave empty
        """
        return _call(get_connection, "set_device_routing",
                     {"track_index": track_index, "track_type": track_type, "device": device,
                      "input_type": input_type, "input_channel": input_channel}, "setting device routing")

    @mcp.tool()
    @telemetry_tool("delete_device")
    def delete_device(
        ctx: Context, device: str, expected_device_name: str, track_index: int = 0, track_type: str = "track",
        user_prompt: str = "",
    ) -> str:
        """Delete one device. expected_device_name must equal the device's
        current name (from get_device_chain), so a stale index can't delete the
        wrong one. Live's undo brings it back.

        Parameters:
        - device: device path, "0" or "0/1/2"
        - expected_device_name: the device's current name
        - track_index, track_type: 'track', 'return' or 'master'
        - user_prompt: leave empty
        """
        return _call(get_connection, "delete_device",
                     {"track_index": track_index, "track_type": track_type, "device": device,
                      "expected_device_name": expected_device_name}, "deleting device")

    @mcp.tool()
    @telemetry_tool("move_device")
    def move_device(
        ctx: Context, device: str, track_index: int = 0, track_type: str = "track",
        target_track_index: Optional[int] = None, target_track_type: Optional[str] = None,
        target_index: Optional[int] = None, expected_device_name: Optional[str] = None,
        user_prompt: str = "",
    ) -> str:
        """Move a device to another position in the chain, or onto another
        track. Without a target track it reorders within the same track; without
        target_index it goes to the end.

        Parameters:
        - device: device path of the device to move
        - target_track_index, target_track_type: where it goes (default: same track)
        - target_index: position in the target chain (0 = first)
        - expected_device_name: optional guard
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index, "track_type": track_type, "device": device,
                                  "expected_device_name": expected_device_name}
        if target_track_index is not None or target_track_type is not None:
            params["target_track_index"] = target_track_index or 0
            params["target_track_type"] = target_track_type or "track"
        if target_index is not None:
            params["target_index"] = target_index
        return _call(get_connection, "move_device", params, "moving device")

    @mcp.tool()
    @telemetry_tool("get_signal_path")
    def get_signal_path(
        ctx: Context, track_index: int = 0, track_type: str = "track", meter_ms: int = 0,
        user_prompt: str = "",
    ) -> str:
        """Trace one track's signal in a single call, for "why is this silent /
        too quiet / not reaching my hardware": input routing, monitoring, arm,
        mute/solo, fader, every device with on/off and its level-setting
        parameters (gain, output, drive, dry/wet) with display text and
        automation state, output routing, sends in use, and which tracks take
        this track as their input. "problems" lists plain-language reasons it
        could be silent. With meter_ms > 0 it also samples the meters of this
        track and the tracks it feeds (input and output: is signal leaving,
        is it arriving). "not_visible_to_the_api" lists what to check by hand.

        Parameters:
        - track_index, track_type: 'track', 'return' or 'master'
        - meter_ms: 0 = no metering; up to 10000 ms (play audio meanwhile)
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_signal_path",
                     {"track_index": track_index, "track_type": track_type, "meter_ms": meter_ms},
                     "tracing signal path")

    # ------------------------------------------------------------------
    # Clips
    # ------------------------------------------------------------------

    @mcp.tool()
    @telemetry_tool("get_clip_info")
    def get_clip_info(
        ctx: Context, track_index: int, clip_index: Optional[int] = None,
        arrangement_index: Optional[int] = None, user_prompt: str = "",
    ) -> str:
        """One clip's properties: name, length, loop on/start/end, start/end
        markers, muted, colour, launch mode; for audio clips also gain (raw and
        as Live shows it in dB), warping and warp mode, pitch, the sample file.
        Give clip_index for a Session slot or arrangement_index for the n-th
        Arrangement clip (order of get_arrangement_clips).

        Parameters:
        - track_index: the track
        - clip_index: Session clip slot (scene row), or
        - arrangement_index: index into the track's Arrangement clips
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index}
        if arrangement_index is not None:
            params["arrangement_index"] = arrangement_index
        else:
            params["clip_index"] = clip_index or 0
        return _call(get_connection, "get_clip_info", params, "reading clip")

    @mcp.tool()
    @telemetry_tool("set_clip_properties")
    def set_clip_properties(
        ctx: Context, track_index: int, clip_index: Optional[int] = None,
        arrangement_index: Optional[int] = None,
        looping: Optional[bool] = None, loop_start: Optional[float] = None, loop_end: Optional[float] = None,
        start_marker: Optional[float] = None, end_marker: Optional[float] = None,
        muted: Optional[bool] = None, gain: Optional[float] = None, gain_db: Optional[float] = None,
        pitch_coarse: Optional[int] = None, pitch_fine: Optional[float] = None,
        warping: Optional[bool] = None, color_index: Optional[int] = None,
        launch_mode: Optional[int] = None, user_prompt: str = "",
    ) -> str:
        """Change a clip: loop on/off and loop start/end, start/end markers (in
        beats), mute (the clip's own on/off), and for audio clips gain (raw
        0..1 or gain_db), pitch (semitones / cents) and warping. Only the fields
        given change; everything is checked before anything is written.

        Parameters:
        - track_index plus clip_index (Session) or arrangement_index
        - looping, loop_start, loop_end, start_marker, end_marker, muted
        - gain (0..1) or gain_db (e.g. 6.0), pitch_coarse (-48..48), pitch_fine (cents), warping
        - color_index, launch_mode (0 trigger, 1 gate, 2 toggle, 3 repeat)
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index}
        if arrangement_index is not None:
            params["arrangement_index"] = arrangement_index
        else:
            params["clip_index"] = clip_index or 0
        for k, v in (("looping", looping), ("loop_start", loop_start), ("loop_end", loop_end),
                     ("start_marker", start_marker), ("end_marker", end_marker), ("muted", muted),
                     ("gain", gain), ("gain_db", gain_db), ("pitch_coarse", pitch_coarse),
                     ("pitch_fine", pitch_fine), ("warping", warping), ("color_index", color_index),
                     ("launch_mode", launch_mode)):
            if v is not None:
                params[k] = v
        return _call(get_connection, "set_clip_properties", params, "setting clip properties")

    # ------------------------------------------------------------------
    # Structure: tracks, returns, scenes
    # ------------------------------------------------------------------

    @mcp.tool()
    @telemetry_tool("duplicate_track")
    def duplicate_track(ctx: Context, track_index: int, user_prompt: str = "") -> str:
        """Duplicate a track with its devices and clips; the copy lands right
        after it.

        Parameters:
        - track_index: the track to copy
        - user_prompt: leave empty
        """
        return _call(get_connection, "duplicate_track", {"track_index": track_index}, "duplicating track")

    @mcp.tool()
    @telemetry_tool("create_return_track")
    def create_return_track(ctx: Context, user_prompt: str = "") -> str:
        """Add a return track at the end of the returns.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "create_return_track", {}, "creating return track")

    @mcp.tool()
    @telemetry_tool("get_scenes")
    def get_scenes(ctx: Context, user_prompt: str = "") -> str:
        """List the Session scenes: name, empty or not, tempo and time signature
        (and whether they are enabled), colour.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_scenes", {}, "listing scenes")

    @mcp.tool()
    @telemetry_tool("create_scene")
    def create_scene(ctx: Context, index: int = -1, user_prompt: str = "") -> str:
        """Insert an empty scene at index (-1 = at the end).

        Parameters:
        - index: position, -1 for the end
        - user_prompt: leave empty
        """
        return _call(get_connection, "create_scene", {"index": index}, "creating scene")

    @mcp.tool()
    @telemetry_tool("duplicate_scene")
    def duplicate_scene(ctx: Context, scene_index: int, user_prompt: str = "") -> str:
        """Duplicate a scene with its clips; the copy goes right below it.

        Parameters:
        - scene_index: the scene to copy
        - user_prompt: leave empty
        """
        return _call(get_connection, "duplicate_scene", {"scene_index": scene_index}, "duplicating scene")

    @mcp.tool()
    @telemetry_tool("delete_scene")
    def delete_scene(
        ctx: Context, scene_index: int, expected_name: str, allow_clips: bool = False, user_prompt: str = "",
    ) -> str:
        """Delete a scene. expected_name must equal its current name ("" for an
        unnamed scene). A scene holding clips is refused unless allow_clips.

        Parameters:
        - scene_index: the scene
        - expected_name: its current name, from get_scenes
        - allow_clips: also delete the clips in it
        - user_prompt: leave empty
        """
        return _call(get_connection, "delete_scene",
                     {"scene_index": scene_index, "expected_name": expected_name, "allow_clips": allow_clips},
                     "deleting scene")

    @mcp.tool()
    @telemetry_tool("set_scene")
    def set_scene(
        ctx: Context, scene_index: int, name: Optional[str] = None, tempo: Optional[float] = None,
        tempo_enabled: Optional[bool] = None, time_signature_numerator: Optional[int] = None,
        time_signature_denominator: Optional[int] = None, color_index: Optional[int] = None,
        user_prompt: str = "",
    ) -> str:
        """Rename a scene or set its tempo / time signature / colour. Setting a
        tempo also enables it (pass tempo_enabled=false to keep it off).

        Parameters:
        - scene_index: the scene
        - name, tempo (BPM), tempo_enabled, time_signature_numerator/denominator, color_index
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"scene_index": scene_index}
        for k, v in (("name", name), ("tempo", tempo), ("tempo_enabled", tempo_enabled),
                     ("time_signature_numerator", time_signature_numerator),
                     ("time_signature_denominator", time_signature_denominator), ("color_index", color_index)):
            if v is not None:
                params[k] = v
        return _call(get_connection, "set_scene", params, "setting scene")

    @mcp.tool()
    @telemetry_tool("fire_scene")
    def fire_scene(ctx: Context, scene_index: int, user_prompt: str = "") -> str:
        """Launch a scene (all its clips), like clicking its launch button. This
        starts playback and makes sound.

        Parameters:
        - scene_index: the scene
        - user_prompt: leave empty
        """
        return _call(get_connection, "fire_scene", {"scene_index": scene_index}, "firing scene")

    @mcp.tool()
    @telemetry_tool("set_track_look")
    def set_track_look(
        ctx: Context, track_index: int, track_type: str = "track", color_index: Optional[int] = None,
        folded: Optional[bool] = None, user_prompt: str = "",
    ) -> str:
        """Set a track's colour (color_index 0..69, Live's palette) and fold or
        unfold a group track.

        Parameters:
        - track_index, track_type: 'track' or 'return'
        - color_index: 0..69
        - folded: true folds a group track, false unfolds it
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index, "track_type": track_type}
        if color_index is not None:
            params["color_index"] = color_index
        if folded is not None:
            params["folded"] = folded
        return _call(get_connection, "set_track_look", params, "setting track look")

    # ------------------------------------------------------------------
    # Transport and song settings
    # ------------------------------------------------------------------

    @mcp.tool()
    @telemetry_tool("get_transport")
    def get_transport(ctx: Context, user_prompt: str = "") -> str:
        """Transport and song settings in one call: playing, playhead, tempo,
        time signature, loop on/start/length, metronome, overdub, record and
        punch flags, count-in, launch quantization, MIDI record quantization,
        groove and swing, scale (root, name, on), locators (cue points) and
        Live's CPU load.

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "get_transport", {}, "reading transport")

    @mcp.tool()
    @telemetry_tool("set_song_settings")
    def set_song_settings(
        ctx: Context, loop: Optional[bool] = None, loop_start: Optional[float] = None,
        loop_length: Optional[float] = None, metronome: Optional[bool] = None, overdub: Optional[bool] = None,
        arrangement_overdub: Optional[bool] = None, punch_in: Optional[bool] = None,
        punch_out: Optional[bool] = None, clip_trigger_quantization: Optional[str] = None,
        midi_recording_quantization: Optional[str] = None, groove_amount: Optional[float] = None,
        swing_amount: Optional[float] = None, root_note: Optional[str] = None, scale_name: Optional[str] = None,
        scale_mode: Optional[bool] = None, signature_numerator: Optional[int] = None,
        signature_denominator: Optional[int] = None, user_prompt: str = "",
    ) -> str:
        """Change song-wide settings; only the fields given change. Starting a
        recording is deliberately not possible here.

        Parameters:
        - loop, loop_start, loop_length (beats): the Arrangement loop brace
        - metronome, overdub (session MIDI overdub), arrangement_overdub, punch_in, punch_out
        - clip_trigger_quantization: None, 8 Bars, 4 Bars, 2 Bars, 1 Bar, 1/2, 1/2T, 1/4, 1/4T, 1/8, 1/8T, 1/16, 1/16T, 1/32
        - midi_recording_quantization: None, 1/4, 1/8, 1/8T, 1/8+1/8T, 1/16, 1/16T, 1/16+1/16T, 1/32
        - groove_amount (0..1.31), swing_amount (0..1)
        - root_note (C, C#, ... B), scale_name (e.g. Major, Minor, Dorian), scale_mode
        - signature_numerator, signature_denominator
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {}
        for k, v in (("loop", loop), ("loop_start", loop_start), ("loop_length", loop_length),
                     ("metronome", metronome), ("overdub", overdub), ("arrangement_overdub", arrangement_overdub),
                     ("punch_in", punch_in), ("punch_out", punch_out),
                     ("clip_trigger_quantization", clip_trigger_quantization),
                     ("midi_recording_quantization", midi_recording_quantization),
                     ("groove_amount", groove_amount), ("swing_amount", swing_amount), ("root_note", root_note),
                     ("scale_name", scale_name), ("scale_mode", scale_mode),
                     ("signature_numerator", signature_numerator),
                     ("signature_denominator", signature_denominator)):
            if v is not None:
                params[k] = v
        return _call(get_connection, "set_song_settings", params, "changing song settings")

    @mcp.tool()
    @telemetry_tool("jump_to_cue")
    def jump_to_cue(ctx: Context, cue: str, user_prompt: str = "") -> str:
        """Move the playhead to a locator, by its index in time order ("0") or
        its name ("Chorus").

        Parameters:
        - cue: index or name
        - user_prompt: leave empty
        """
        return _call(get_connection, "jump_to_cue", {"cue": cue}, "jumping to locator")

    @mcp.tool()
    @telemetry_tool("stop_all_clips")
    def stop_all_clips(ctx: Context, user_prompt: str = "") -> str:
        """Stop every playing Session clip (Live's Stop All Clips button).

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "stop_all_clips", {}, "stopping clips")

    @mcp.tool()
    @telemetry_tool("capture_midi")
    def capture_midi(ctx: Context, user_prompt: str = "") -> str:
        """Capture MIDI: turn what was just played on an armed/monitored MIDI
        track into a clip (Live's Capture MIDI button).

        Parameters:
        - user_prompt: leave empty
        """
        return _call(get_connection, "capture_midi", {}, "capturing MIDI")

    # ------------------------------------------------------------------
    # Notes by id, clip edits
    # ------------------------------------------------------------------

    @mcp.tool()
    @telemetry_tool("get_notes")
    def get_notes(
        ctx: Context, track_index: int, clip_index: Optional[int] = None,
        arrangement_index: Optional[int] = None, user_prompt: str = "",
    ) -> str:
        """Every note in a MIDI clip with its note_id (for modify_notes and
        remove_notes), pitch, start_time, duration, velocity, mute,
        probability, velocity_deviation and release_velocity.

        Parameters:
        - track_index plus clip_index (Session) or arrangement_index
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index}
        if arrangement_index is not None:
            params["arrangement_index"] = arrangement_index
        else:
            params["clip_index"] = clip_index or 0
        return _call(get_connection, "get_notes", params, "reading notes")

    @mcp.tool()
    @telemetry_tool("modify_notes")
    def modify_notes(
        ctx: Context, track_index: int, notes: List[Dict[str, Any]], clip_index: Optional[int] = None,
        arrangement_index: Optional[int] = None, user_prompt: str = "",
    ) -> str:
        """Edit existing notes in place, by note_id from get_notes - no clearing
        and re-adding. Each entry is {note_id, and any of pitch, start_time,
        duration, velocity, mute, probability (0..1), velocity_deviation,
        release_velocity}. All entries are checked before anything changes.

        Parameters:
        - track_index plus clip_index (Session) or arrangement_index
        - notes: list of changes, e.g. [{"note_id": 12, "velocity": 90, "probability": 0.5}]
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index, "notes": notes}
        if arrangement_index is not None:
            params["arrangement_index"] = arrangement_index
        else:
            params["clip_index"] = clip_index or 0
        return _call(get_connection, "modify_notes", params, "modifying notes")

    @mcp.tool()
    @telemetry_tool("remove_notes")
    def remove_notes(
        ctx: Context, track_index: int, note_ids: List[int], clip_index: Optional[int] = None,
        arrangement_index: Optional[int] = None, user_prompt: str = "",
    ) -> str:
        """Delete specific notes by note_id (from get_notes). Refused if any id
        is not in the clip.

        Parameters:
        - track_index plus clip_index (Session) or arrangement_index
        - note_ids: ids to delete
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index, "note_ids": note_ids}
        if arrangement_index is not None:
            params["arrangement_index"] = arrangement_index
        else:
            params["clip_index"] = clip_index or 0
        return _call(get_connection, "remove_notes", params, "removing notes")

    @mcp.tool()
    @telemetry_tool("edit_clip")
    def edit_clip(
        ctx: Context, track_index: int, action: str, clip_index: Optional[int] = None,
        arrangement_index: Optional[int] = None, grid: str = "1/16", amount: float = 1.0,
        user_prompt: str = "",
    ) -> str:
        """Clip edits Live does in one step:
        - quantize: snap notes (MIDI) or warp markers to grid by amount (1.0 = fully)
        - duplicate_loop: double the loop, copying notes and envelopes (MIDI only)
        - crop: remove everything outside the loop (or outside the markers)

        Parameters:
        - track_index plus clip_index (Session) or arrangement_index
        - action: quantize, duplicate_loop or crop
        - grid: 1/4, 1/8, 1/8T, 1/8+1/8T, 1/16, 1/16T, 1/16+1/16T, 1/32 (quantize only)
        - amount: 0..1 (quantize only)
        - user_prompt: leave empty
        """
        params: Dict[str, Any] = {"track_index": track_index, "action": action, "grid": grid, "amount": amount}
        if arrangement_index is not None:
            params["arrangement_index"] = arrangement_index
        else:
            params["clip_index"] = clip_index or 0
        return _call(get_connection, "edit_clip", params, "editing clip")
