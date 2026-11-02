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

from . import script_handshake
from .telemetry_decorator import telemetry_tool

logger = logging.getLogger("AbletonMCPServer")

# Extended commands that change the set; the connection gives them the longer
# modifying-command socket timeout.
MODIFYING_COMMANDS = frozenset({
    "undo", "redo", "delete_track",
    "set_track_routing", "set_track_monitoring", "set_track_mixer",
    "back_to_arrangement", "re_enable_automation",
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
